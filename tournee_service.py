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

# Le champ "jours" du formulaire n'a pas le même intitulé ni le même sens
# selon format_dispo (voir calculer_tournee) : "Jours possibles sur la
# période" pour une tournée classique (cases à cocher lundi-dimanche,
# interprétées par map_days), "Dates possibles sur la période" pour le mode
# consultations (cases à cocher des dates précises du mois, interprétées
# par map_dates) -- deux formulaires différents, jamais le même champ lu
# avec le mauvais parseur.
_JOURS_FIELD_BY_FORMAT = {
    "jours_semaine": "Jours possibles sur la période",
    "dates_precises": "Dates possibles sur la période",
}

DistFnFactory = Callable[[dict], Callable[[str, str], int]]


class TourneeError(Exception):
    """Échec métier normal (pas un bug) : message déjà prêt à afficher tel
    quel à Ludivine, que ce soit dans un Terminal ou dans l'interface."""


def _parse_hhmm(s: str) -> int:
    """"HH:MM" -> minutes depuis minuit, avec une erreur métier claire (pas
    un plantage brut) sur tout format inattendu -- même principe que le
    reste du fichier : jamais deviner un horaire mal saisi."""
    try:
        hh, mm = str(s).strip().split(":")
        h, m = int(hh), int(mm)
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError
        return h * 60 + m
    except (ValueError, AttributeError):
        raise TourneeError(f"Horaire invalide : '{s}' (attendu HH:MM, ex. '09:00').")


def _parse_dates_fermees(dates_fermees: list[str] | None) -> set[date]:
    """Chaînes ISO ("AAAA-MM-JJ") -> objets date, avec erreur métier claire
    sur tout format invalide plutôt qu'un plantage brut."""
    parsed: set[date] = set()
    for s in dates_fermees or []:
        s = s.strip()
        if not s:
            continue
        try:
            parsed.add(date.fromisoformat(s))
        except ValueError:
            raise TourneeError(f"Date fermée invalide : '{s}' (attendu AAAA-MM-JJ).")
    return parsed


def _excluded_day_indices(
    start_date: date,
    n_days: int,
    jours_exclus: list[str] | None,
    dates_fermees: list[str] | None = None,
) -> set[int]:
    """Traduit deux réglages -- jours_exclus (motif récurrent par jour de
    semaine, ex. ["dimanche"]) et dates_fermees (fermetures ponctuelles,
    ex. ["2026-10-14"]) -- en day_index (décalage calendaire depuis
    start_date) pour CETTE tournée précise. Les deux sont des réglages par
    tournée, jamais mémorisés d'un calcul à l'autre, et se CUMULENT : un
    jour exclu par l'un OU l'autre motif est exclu (demande de Margaux,
    26 sept. 2026 -- le mode "consultations" en Alsace a besoin des deux à
    la fois : un rythme hebdomadaire de base, plus des absences ponctuelles
    qui ne suivent aucun motif régulier)."""
    excluded: set[int] = set()

    exclus_norm = {j.strip().lower() for j in (jours_exclus or []) if j.strip()}
    if exclus_norm:
        excluded |= {
            i for i in range(n_days)
            if _WEEKDAYS_FR[(start_date + timedelta(days=i)).weekday()] in exclus_norm
        }

    fermees = _parse_dates_fermees(dates_fermees)
    if fermees:
        excluded |= {
            i for i in range(n_days)
            if (start_date + timedelta(days=i)) in fermees
        }

    return excluded


def _format_excluded_days(start_date: date, excluded: set[int]) -> str:
    """Liste lisible des jours exclus (jour de semaine + date), pour les
    messages d'avertissement/erreur -- peu importe que l'exclusion vienne
    d'un motif hebdomadaire ou d'une date ponctuelle, ce qui compte pour
    Ludivine c'est QUELS jours sont concernés."""
    return ", ".join(
        f"{_WEEKDAYS_FR[(start_date + timedelta(days=i)).weekday()].capitalize()} "
        f"{(start_date + timedelta(days=i)).strftime('%d/%m')}"
        for i in sorted(excluded)
    )


def build_days(
    start_date: date,
    n_days: int,
    max_span_h: int,
    jours_exclus: list[str] | None = None,
    dates_fermees: list[str] | None = None,
    horaires_jours: dict[str, tuple[int, int]] | None = None,
) -> list[DayConfig]:
    """Un DayConfig par jour calendaire de la période, SAUF les jours
    exclus par jours_exclus ou dates_fermees (voir _excluded_day_indices) :
    ceux-là sont absents de la liste renvoyée, day_index restant aligné sur
    le décalage calendaire (donc pas forcément contigu --
    solve_week/solve_week_balanced n'en ont pas besoin, voir weekly.py).

    Pourquoi absent et pas "DayConfig à plafond 0" (première idée envisagée) :
    solve_week_balanced calcule un plafond UNIQUE par dichotomie, appliqué à
    TOUS les jours de la liste reçue (`ceiling = min(hard_caps)`, voir sa
    docstring dans weekly.py) -- un jour à plafond 0 dans le lot ferait
    chuter le plafond de TOUS les jours à 0 et rendrait la tournée entière
    infaisable, pas seulement ce jour-là. L'omission pure évite ce piège.
    Contrepartie : calculer_tournee doit aussi retirer ces day_index des
    allowed_days de chaque client AVANT d'appeler le solveur (sinon un
    client dont le seul jour coché tombe sur un jour exclu ferait planter
    solve_week avec un day_by_index[d] introuvable).

    horaires_jours (ex. {"mardi": (9*60, 17*60)}, déjà converti en minutes
    par calculer_tournee) : horaires de journée PROPRES à un jour de
    semaine donné, pour un rythme irrégulier (mode consultations, demande
    de Margaux 26 sept. 2026 -- pas les mêmes horaires que les tournées
    bretonnes classiques). Un jour de semaine absent de horaires_jours
    garde les horaires par défaut de DayConfig (6h-20h30). Vérifié que ça
    survit à l'équilibrage de solve_week_balanced : sa dichotomie ne
    touche QUE max_span_min, elle reconstruit chaque DayConfig d'essai en
    reprenant explicitement day_start_min/day_end_min du jour d'origine
    (voir weekly.py, try_cap)."""
    excluded = _excluded_day_indices(start_date, n_days, jours_exclus, dates_fermees)
    horaires = horaires_jours or {}
    days = []
    for i in range(n_days):
        if i in excluded:
            continue
        d = start_date + timedelta(days=i)
        weekday_name = _WEEKDAYS_FR[d.weekday()]
        kwargs = {}
        if weekday_name in horaires:
            kwargs["day_start_min"], kwargs["day_end_min"] = horaires[weekday_name]
        days.append(DayConfig(
            day_index=i,
            label=f"{weekday_name.capitalize()} {d.strftime('%d/%m')}",
            max_span_min=max_span_h * 60,
            **kwargs,
        ))
    return days


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
    jours_exclus: list[str] | None = None,
    dates_fermees: list[str] | None = None,
    horaires_jours: dict[str, dict[str, str]] | None = None,
    format_dispo: str = "jours_semaine",
    dist_fn_factory: DistFnFactory = _default_dist_fn_factory,
) -> tuple[dict, list[str]]:
    """Premier calcul complet : export brut du formulaire -> tournée
    équilibrée sur n_days jours. dist_fn_factory est injectable (les tests
    passent une fabrique de test, sans appel réseau réel ; CLI et API
    utilisent ors_client.make_dist_fn par défaut).

    format_dispo : "jours_semaine" (défaut, tournées classiques -- la
    question du formulaire coche des jours de semaine, interprétée par
    map_days) ou "dates_precises" (mode consultations -- Ludivine en
    Alsace, formulaire partagé sur un mois entier, demande de Margaux
    26 sept. 2026 -- la question coche des dates précises du mois,
    interprétée par map_dates ; voir _JOURS_FIELD_BY_FORMAT pour le champ
    de formulaire lu dans chaque cas). Jamais mélangé : une tournée
    classique ne doit jamais être interprétée avec le parseur de dates, et
    inversement -- l'un suppose une ambiguïté possible à lever (plusieurs
    lundis dans la période), l'autre suppose l'inverse (chaque date est
    unique par construction).

    jours_exclus (ex. ["dimanche"]) et dates_fermees (ex. ["2026-10-14"]) :
    jours à ne jamais proposer sur CETTE tournée précise -- réglages
    optionnels, propres à ce calcul, qui se cumulent (voir
    _excluded_day_indices). Un client dont le SEUL jour coché tombe sur un
    jour exclu ne doit pas se fondre dans l'avertissement générique "sans
    aucun jour exploitable" plus bas -- ce serait échouer silencieusement
    sur la vraie cause -- d'où le traitement séparé ici, avant ce test
    générique.

    horaires_jours (ex. {"mardi": {"debut": "09:00", "fin": "17:00"}}) :
    horaires de journée propres à un jour de semaine, pour un rythme
    irrégulier (mode consultations) -- voir build_days. Un jour de semaine
    absent garde les horaires par défaut (6h-20h30).

    Renvoie (résultat exportable pour l'interface, avertissements à
    afficher). Lève TourneeError pour tout échec métier."""
    if format_dispo not in _JOURS_FIELD_BY_FORMAT:
        raise TourneeError(
            f"format_dispo invalide : '{format_dispo}' (attendu 'jours_semaine' ou 'dates_precises')."
        )

    horaires_min: dict[str, tuple[int, int]] = {}
    for jour, hv in (horaires_jours or {}).items():
        jour_norm = jour.strip().lower()
        debut_min = _parse_hhmm(hv.get("debut", ""))
        fin_min = _parse_hhmm(hv.get("fin", ""))
        if debut_min >= fin_min:
            raise TourneeError(
                f"Horaires invalides pour {jour} : l'heure de début ({hv.get('debut')}) doit être "
                f"avant l'heure de fin ({hv.get('fin')})."
            )
        horaires_min[jour_norm] = (debut_min, fin_min)

    tournee_dates = [start_date + timedelta(days=i) for i in range(n_days)]
    stops, warnings = import_responses(
        raw_responses, tournee_dates,
        field_map={"jours": _JOURS_FIELD_BY_FORMAT[format_dispo]},
        jours_format="dates" if format_dispo == "dates_precises" else "semaine",
    )
    warnings = list(warnings)

    excluded = _excluded_day_indices(start_date, n_days, jours_exclus, dates_fermees)
    if excluded:
        jours_exclus_lisible = _format_excluded_days(start_date, excluded)
        vides_par_exclusion: set[str] = set()
        for s in stops:
            avait_des_jours = bool(s.allowed_days)
            s.allowed_days = [d for d in s.allowed_days if d not in excluded]
            if avait_des_jours and not s.allowed_days:
                vides_par_exclusion.add(s.id)
        if vides_par_exclusion:
            noms = ", ".join(s.label for s in stops if s.id in vides_par_exclusion)
            warnings.append(
                f"Arrêt(s) écarté(s) du calcul : leur(s) seul(s) jour(s) coché(s) tombe(nt) "
                f"uniquement sur (un) jour(s) exclu(s) de cette tournée ({jours_exclus_lisible}) : {noms}"
            )
            stops = [s for s in stops if s.id not in vides_par_exclusion]

    unschedulable = [s for s in stops if not s.allowed_days]
    if unschedulable:
        noms = ", ".join(s.label for s in unschedulable)
        warnings.append(f"Arrêt(s) sans aucun jour exploitable, retirés du calcul : {noms}")
        stops = [s for s in stops if s.allowed_days]

    if not stops:
        raise TourneeError("Aucun client planifiable dans cet export -- rien à calculer.")

    days = build_days(start_date, n_days, plafond, jours_exclus, dates_fermees, horaires_min)
    if not days:
        raise TourneeError(
            f"Tous les jours de cette tournée ({n_days} jour(s) à partir du "
            f"{start_date.strftime('%d/%m/%Y')}) tombent sur un jour exclu "
            f"({_format_excluded_days(start_date, excluded)}) -- rien à calculer, vérifie la période "
            "ou les jours exclus/fermés choisis."
        )

    point_labels = {DEPOT_ID: depot, **{s.id: s.address for s in stops}}
    try:
        dist_fn = dist_fn_factory(point_labels)
    except OrsError as e:
        raise TourneeError(f"Erreur cartographie : {e}") from e

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
