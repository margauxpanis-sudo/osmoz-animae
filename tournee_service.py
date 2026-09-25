"""
Logique métier partagée entre les scripts en ligne de commande
(run_tournee.py, recalculer_nuitees.py) et l'API HTTP (app.py).

Pourquoi ce fichier existe : jusqu'ici cette logique était écrite une fois
dans chaque script CLI. Avec l'API qui doit faire exactement le même calcul
à la demande de l'interface (sans passer par un Terminal), dupliquer le code
une troisième fois aurait créé un risque concret de divergence silencieuse
entre "ce que Ludivine obtient via le bouton de l'interface" et "ce que
Margaux obtient en ligne de commande" -- exactement le genre de bug qui ne
se voit qu'après coup. Un seul jeu de fonctions, trois appelants.

TourneeError : toutes les erreurs "normales" (adresse introuvable, aucun
client planifiable, jour infaisable...) sont levées sous cette forme unique,
avec un message déjà rédigé pour être affiché tel quel à Ludivine -- l'API
le renvoie tel quel au navigateur, les scripts CLI l'impriment tel quel.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Callable

from form_import import import_responses
from ors_client import make_dist_fn as _default_dist_fn_factory
from ors_client import OrsError
from schema import DayConfig, DayPlan, DayResult
from solver import PREVIOUS_DAY_END, solve_multi_day
from weekly import DEPOT_ID, solve_week_balanced

# Comme dans form_import.py (map_days) : ne JAMAIS utiliser strftime("%A"),
# qui dépend de la locale système et renvoie le nom anglais dans certains
# environnements -- d'où ce mapping manuel, fiable partout.
_WEEKDAYS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]

DistFnFactory = Callable[[dict], Callable[[str, str], int]]


class TourneeError(Exception):
    """Échec métier normal (pas un bug) : message déjà prêt à afficher tel
    quel à Ludivine, que ce soit dans un Terminal ou dans l'interface."""


def build_days(start_date: date, n_days: int, max_span_h: int) -> list[DayConfig]:
    return [
        DayConfig(
            day_index=i,
            label=f"{_WEEKDAYS_FR[(start_date + timedelta(days=i)).weekday()].capitalize()} "
                  f"{(start_date + timedelta(days=i)).strftime('%d/%m')}",
            max_span_min=max_span_h * 60,
        )
        for i in range(n_days)
    ]


def export_for_interface(day_results: dict, clients_by_id: dict) -> dict:
    """Sérialise un dict {day_index: DayResult} (WeekResult.day_results, ou
    le résultat de solve_multi_day) au même format que sample_week_result.json,
    en réinjectant téléphone/notes/nom/lieu (absents de RouteStep, présents
    sur le Stop d'origine) pour que l'interface puisse générer les messages
    WhatsApp et afficher les coordonnées. Renvoie un dict prêt à sérialiser
    (json.dump côté CLI, réponse HTTP directe côté API) -- n'écrit plus de
    fichier lui-même, pour rester utilisable des deux côtés.

    Les points de passage (le dépôt, ou -- après une nuitée -- le client chez
    qui la journée précédente s'est terminée, ajouté par solve_multi_day
    comme départ de la journée suivante) sont exclus : un vrai arrêt client a
    toujours service_minutes > 0, un point de passage vaut toujours 0.
    Un simple test « stop_id connu » ne suffit pas ici -- l'arrêt du départ
    (nuitée de la veille) EST un client connu, juste pas un client DE CE
    JOUR-LÀ.

    IMPORTANT : client_name et lieu sont envoyés comme champs séparés,
    JAMAIS reconstruits en reparsant `label` côté interface -- label combine
    les deux dans un ordre qui a déjà changé une fois entre le prototype et
    form_import.py (bug trouvé le 24 sept. 2026 : message WhatsApp avec nom
    et lieu inversés)."""
    days_out = []
    for day_index in sorted(day_results.keys()):
        r: DayResult = day_results[day_index]
        steps_out = []
        for step in r.steps:
            client = clients_by_id.get(step.stop_id)
            if client is None or step.service_minutes <= 0:
                continue  # dépôt, ou point de départ hérité d'une nuitée -- pas un arrêt de CE jour
            steps_out.append({
                "stop_id": step.stop_id,
                "label": step.label,
                "client_name": client.client_name,
                "lieu": client.address,
                "arrival_min": step.arrival_min,
                "service_minutes": step.service_minutes,
                "phone": client.phone,
                "notes": client.notes,
                "abonnement_annuel": client.abonnement_annuel,
                "animals": client.animals,
            })
        days_out.append({
            "day_index": r.day_index,
            "label": r.label,
            "span_min": r.span_min,
            "finish_min": r.finish_min,
            "steps": steps_out,
        })
    return {"days": days_out}


def calculer_tournee(
    raw_responses: list[dict],
    start_date: date,
    n_days: int,
    depot: str,
    plafond: int = 12,
    dist_fn_factory: DistFnFactory = _default_dist_fn_factory,
) -> tuple[dict, list[str]]:
    """Premier calcul complet : export brut du formulaire -> tournée
    équilibrée sur n_days jours. dist_fn_factory est injectable (les tests
    passent une fabrique de test, sans appel réseau réel ; CLI et API
    utilisent ors_client.make_dist_fn par défaut).

    Renvoie (résultat exportable pour l'interface, avertissements à
    afficher). Lève TourneeError pour tout échec métier."""
    tournee_dates = [start_date + timedelta(days=i) for i in range(n_days)]
    stops, warnings = import_responses(raw_responses, tournee_dates)
    warnings = list(warnings)

    unschedulable = [s for s in stops if not s.allowed_days]
    if unschedulable:
        noms = ", ".join(s.label for s in unschedulable)
        warnings.append(f"Arrêt(s) sans aucun jour exploitable, retirés du calcul : {noms}")
        stops = [s for s in stops if s.allowed_days]

    if not stops:
        raise TourneeError("Aucun client planifiable dans cet export -- rien à calculer.")

    point_labels = {DEPOT_ID: depot, **{s.id: s.address for s in stops}}
    try:
        dist_fn = dist_fn_factory(point_labels)
    except OrsError as e:
        raise TourneeError(f"Erreur cartographie : {e}") from e

    days = build_days(start_date, n_days, plafond)
    result = solve_week_balanced(days, stops, dist_fn, depot_label=depot)

    clients_by_id = {s.id: s for s in stops}
    if not result.feasible:
        # Les clients "abonnement annuel" sont protégés en priorité par le
        # moteur (voir weekly.py, PRIORITY_PENALTY) -- s'ils apparaissent
        # quand même ici, c'est que même la priorité n'a pas suffi (tournée
        # bien trop chargée), donc à signaler très clairement à Ludivine.
        missing_stops = [clients_by_id[cid] for cid in result.missing_client_ids]
        noms = ", ".join(f"⭐{s.label}" if s.abonnement_annuel else s.label for s in missing_stops)
        msg = f"Clients NON casés par le moteur, à traiter à la main : {noms}"
        if any(s.abonnement_annuel for s in missing_stops):
            msg += " (⭐ = abonnement annuel, normalement protégé en priorité)"
        warnings.append(msg)

    exported = export_for_interface(result.day_results, clients_by_id)
    return exported, warnings


def recalculer_apres_nuitees(
    raw_responses: list[dict],
    decisions: dict,
    start_date: date,
    n_days: int,
    depot: str,
    dist_fn_factory: DistFnFactory = _default_dist_fn_factory,
) -> tuple[dict, list[str]]:
    """Recalcule uniquement l'ORDRE et LES HORAIRES après qu'une ou plusieurs
    nuitées manuelles ont été posées dans l'interface -- ne redécide JAMAIS
    quel client va quel jour (cette décision reste celle déjà validée).
    Réutilise solve_multi_day (solver.py) via PREVIOUS_DAY_END, comme les
    scripts CLI.

    `decisions` a la forme {"day_assignments": [{"day_index": int,
    "stops": [{"stop_id": str, "overnight": bool}, ...]}, ...]} -- c'est la
    structure déjà produite par revue_tournee.html.

    Lève TourneeError pour tout échec métier (nuitées multiples le même
    jour, arrêt inconnu, jour infaisable...)."""
    tournee_dates = [start_date + timedelta(days=i) for i in range(n_days)]
    stops, warnings = import_responses(raw_responses, tournee_dates)
    warnings = list(warnings)
    stops_by_id = {s.id: s for s in stops}

    overnight_stop_by_day: dict[int, str] = {}
    day_of_stop: dict[str, int] = {}
    unknown_ids: list[str] = []
    for day_entry in decisions.get("day_assignments", []):
        d = day_entry["day_index"]
        overnight_here = [s["stop_id"] for s in day_entry["stops"] if s.get("overnight")]
        if len(overnight_here) > 1:
            raise TourneeError(
                f"Jour {d} : plusieurs nuitées marquées le même jour ({overnight_here}) -- "
                "une seule nuitée possible par jour, corrige et relance."
            )
        if overnight_here:
            overnight_stop_by_day[d] = overnight_here[0]
        for s in day_entry["stops"]:
            sid = s["stop_id"]
            if sid not in stops_by_id:
                unknown_ids.append(sid)
                continue
            day_of_stop[sid] = d
            stops_by_id[sid].allowed_days = [d]

    if unknown_ids:
        raise TourneeError(
            f"Arrêt(s) introuvable(s) dans l'export du formulaire : {unknown_ids} -- "
            "l'export a dû changer depuis le premier calcul, relance un calcul complet d'abord."
        )

    active_stops = [s for s in stops if s.id in day_of_stop]
    if not active_stops:
        raise TourneeError("Aucun arrêt à recalculer (décisions vides).")

    point_labels = {DEPOT_ID: depot, **{s.id: s.address for s in active_stops}}
    try:
        dist_fn = dist_fn_factory(point_labels)
    except OrsError as e:
        raise TourneeError(f"Erreur cartographie : {e}") from e

    days_plan = []
    for i in range(n_days):
        overnight_id = overnight_stop_by_day.get(i)
        days_plan.append(DayPlan(
            day_index=i, label=f"Jour {i + 1}",
            start_id=DEPOT_ID if i == 0 else PREVIOUS_DAY_END,
            end_id=overnight_id if overnight_id else DEPOT_ID,
            open_route=False,
        ))

    day_results = solve_multi_day(days_plan, active_stops, point_labels, dist_fn)

    infeasible = {d: r.error for d, r in day_results.items() if not r.feasible}
    if infeasible:
        detail = "; ".join(f"jour {d} : {err}" for d, err in infeasible.items())
        raise TourneeError(
            f"Recalcul infaisable ({detail}) -- vérifie les fenêtres horaires des clients concernés "
            "et l'emplacement de la nuitée."
        )

    exported = export_for_interface(day_results, stops_by_id)
    return exported, warnings
