"""
Interprétation des réponses du formulaire (export brut du pont Apps Script,
voir bridge/Code.gs) -> objets Stop utilisables par le moteur.

Principe directeur (le même que validate.py) : ne JAMAIS deviner
silencieusement une information ambiguë. Quand le texte libre d'une réponse
ne peut pas être interprété avec confiance, l'arrêt est quand même produit
(avec une valeur par défaut prudente) mais signalé dans la liste des
avertissements — à vérifier à la main avant de lancer le moteur pour de
vrai. Testé ci-dessous sur des formulations réellement vues dans les
tournées Osmoz Animae (voir tournee-19-oct-2026.md).
"""

from __future__ import annotations


import re
import unicodedata
from dataclasses import dataclass
from datetime import date

from schema import Stop, StopWindow, WindowType

SERVICE_MINUTES_PER_ANIMAL = 45  # règle actée : "Séances : 45 min par animal" (tournee-19-oct-2026.md)

_FRENCH_NUMBERS = {
    "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5,
    "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10,
}

_WEEKDAYS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _norm(s: str) -> str:
    return _strip_accents(str(s or "")).lower().strip()


@dataclass
class ParsedAnimals:
    count: int
    confident: bool


def parse_animal_count(text: str) -> ParsedAnimals:
    """Compte le nombre total d'animaux dans un texte libre du type
    "2 chevaux, 1 chien". Ne comprend PAS les quantités implicites (ex.
    "des chevaux" sans nombre) -> renvoie confident=False plutôt que de
    deviner un chiffre."""
    t = _norm(text)
    if not t:
        return ParsedAnimals(0, confident=False)

    total = 0
    found_any = False
    for m in re.finditer(r"\d+", t):
        total += int(m.group())
        found_any = True

    # remplace aussi les nombres écrits en toutes lettres, un par un, pour ne
    # pas les compter deux fois si un chiffre était déjà présent juste à côté
    words_used = 0
    for word, val in _FRENCH_NUMBERS.items():
        count_word = len(re.findall(rf"\b{word}\b", t))
        if count_word:
            total += val * count_word
            words_used += count_word
            found_any = True

    if not found_any:
        return ParsedAnimals(0, confident=False)
    return ParsedAnimals(total, confident=True)


def parse_window(text: str) -> tuple[StopWindow, bool]:
    """Interprète la réponse à "contrainte ferme ou préférence ?" en
    StopWindow. Renvoie (window, confident). confident=False -> le texte
    ne correspond à aucun des motifs connus, à relire à la main (la
    fenêtre renvoyée est alors NONE par prudence, jamais une supposition)."""
    t = _norm(text)
    if not t or t in ("aucune", "aucune contrainte", "pas de contrainte", "non", "rien"):
        return StopWindow(WindowType.NONE), True

    m = re.search(r"pas avant (\d{1,2})\s*h\s*(\d{2})?", t)
    if m:
        h = int(m.group(1))
        mn = int(m.group(2)) if m.group(2) else 0
        return StopWindow(WindowType.FLOOR, start_min=h * 60 + mn), True

    m = re.search(r"apres (\d{1,2})\s*h\s*(\d{2})?", t)
    if m:
        h = int(m.group(1))
        mn = int(m.group(2)) if m.group(2) else 0
        return StopWindow(WindowType.FLOOR, start_min=h * 60 + mn), True

    if "apres-midi" in t or "après-midi" in text.lower() or "l'apres midi" in t:
        # convention déjà utilisée dans le prototype : après-midi -> plancher 13h
        return StopWindow(WindowType.FLOOR, start_min=13 * 60), True

    if "matin" in t and "apres" not in t:
        # "seulement le matin" -> fenêtre dure qui se termine à midi
        return StopWindow(WindowType.HARD, start_min=None, end_min=12 * 60), True

    m = re.search(r"entre (\d{1,2})\s*h\s*(\d{2})?\s*et\s*(\d{1,2})\s*h\s*(\d{2})?", t)
    if m:
        h1, mn1 = int(m.group(1)), int(m.group(2) or 0)
        h2, mn2 = int(m.group(3)), int(m.group(4) or 0)
        return StopWindow(WindowType.HARD, start_min=h1 * 60 + mn1, end_min=h2 * 60 + mn2), True

    # motif non reconnu -> ne pas deviner
    return StopWindow(WindowType.NONE), False


def parse_abonnement(text: str) -> tuple[bool, bool]:
    """Interprète la réponse à la question "Abonnement annuel ?" (case à
    cocher, ou oui/non selon le formulaire) en booléen. Renvoie
    (abonnement, confident). Par prudence (même principe que les autres
    parseurs de ce fichier) : un texte non reconnu est traité comme "non
    abonné" plutôt que d'accorder à tort la protection anti-suppression de
    Stop.abonnement_annuel (voir schema.py) -- mieux vaut relire un vrai
    abonné à la main qu'accorder la priorité à qui ne l'a pas. Une réponse
    absente (question pas encore posée sur ce formulaire, ou champ laissé
    vide) est traitée comme "non abonné" sans avertissement -- c'est déjà
    le comportement par défaut avant l'ajout de cette question."""
    t = _norm(text)
    if not t or t in ("non", "no", "false", "0", "aucun", "aucune"):
        return False, True
    if t in ("oui", "yes", "true", "1", "x", "coche", "abonnement annuel"):
        return True, True
    return False, False


def map_days(text: str, tournee_dates: list[date]) -> tuple[list[int], list[str]]:
    """Convertit les jours cochés (ex. "Lundi, Mercredi") en indices de jour
    (position dans tournee_dates). ATTENTION : une tournée de plus de 7 jours
    peut contenir deux fois le même jour de semaine (ex. lundi 19 ET lundi 26,
    cas réel déjà rencontré le 19 oct. 2026) — dans ce cas les DEUX indices
    sont retenus et un avertissement est renvoyé, plutôt que de choisir au
    hasard lequel des deux le client voulait dire."""
    t = _norm(text)
    warnings: list[str] = []
    if not t:
        return [], ["Aucun jour possible renseigné."]

    weekday_by_index = [d.strftime("%A") for d in tournee_dates]
    # strftime renvoie le nom anglais selon la locale du système -> on
    # calcule plutôt nous-mêmes via .weekday() (0=lundi) pour rester fiable
    # indépendamment de la locale de l'environnement d'exécution.
    weekday_by_index = [_WEEKDAYS_FR[d.weekday()] for d in tournee_dates]

    matched_indices = []
    for name in _WEEKDAYS_FR:
        if re.search(rf"\b{name}\b", t):
            indices = [i for i, wd in enumerate(weekday_by_index) if wd == name]
            if not indices:
                warnings.append(f"Jour '{name}' coché mais absent de la période de la tournée fournie.")
                continue
            if len(indices) > 1:
                dates_str = ", ".join(tournee_dates[i].strftime("%d/%m") for i in indices)
                warnings.append(
                    f"'{name.capitalize()}' apparaît {len(indices)} fois dans cette tournée "
                    f"({dates_str}) — les deux jours sont retenus, à confirmer avec le client "
                    "lequel il voulait dire (ou si les deux conviennent)."
                )
            matched_indices.extend(indices)

    if not matched_indices:
        warnings.append(f"Aucun jour reconnu dans le texte : '{text}'.")
    return sorted(set(matched_indices)), warnings


def _slug(text: str) -> str:
    t = _strip_accents(str(text)).lower()
    t = re.sub(r"[^a-z0-9]+", "_", t).strip("_")
    return t or "sans_nom"


def import_responses(
    raw_responses: list[dict],
    tournee_dates: list[date],
    field_map: dict[str, str] | None = None,
) -> tuple[list[Stop], list[str]]:
    """Transforme l'export brut du pont Apps Script (une liste de dicts,
    une entrée par réponse, clés = intitulés exacts des questions) en liste
    de Stop, plus la liste consolidée des points à vérifier à la main avant
    de lancer le moteur.

    field_map permet de faire correspondre les intitulés exacts du
    formulaire (qui peuvent varier légèrement d'une tournée à l'autre) aux
    noms de champs attendus ici : nom, telephone, lieu, animaux, jours,
    contrainte, remarques. Par défaut, suppose les intitulés du template
    (pre-tournee-templates.md)."""
    default_map = {
        "nom": "Nom et prénom",
        "telephone": "Numéro de téléphone",
        "lieu": "Lieu du rendez-vous",
        "animaux": "Nombre et type d'animaux à voir",
        "jours": "Jours possibles sur la période",
        "contrainte": "Avez-vous une contrainte d'horaire ferme, ou juste une préférence ?",
        "remarques": "Remarques complémentaires",
        "abonnement": "Abonnement annuel ?",
    }
    fmap = {**default_map, **(field_map or {})}

    stops: list[Stop] = []
    all_warnings: list[str] = []

    for i, resp in enumerate(raw_responses):
        row_ref = resp.get("_row", i + 2)
        nom = str(resp.get(fmap["nom"], "")).strip() or f"(sans nom, ligne {row_ref})"
        lieu = str(resp.get(fmap["lieu"], "")).strip()
        animaux_text = resp.get(fmap["animaux"], "")
        jours_text = resp.get(fmap["jours"], "")
        contrainte_text = resp.get(fmap["contrainte"], "")
        abonnement_text = resp.get(fmap["abonnement"], "")

        prefix = f"Ligne {row_ref} ({nom})"

        animals = parse_animal_count(animaux_text)
        if not animals.confident:
            all_warnings.append(
                f"{prefix} : nombre d'animaux non reconnu dans '{animaux_text}' — "
                "durée de service à vérifier à la main."
            )
        service_minutes = max(animals.count, 1) * SERVICE_MINUTES_PER_ANIMAL

        window, window_confident = parse_window(contrainte_text)
        if not window_confident:
            all_warnings.append(
                f"{prefix} : contrainte horaire non reconnue dans '{contrainte_text}' — "
                "traitée comme 'aucune contrainte' par défaut, à vérifier à la main."
            )

        abonnement, abonnement_confident = parse_abonnement(abonnement_text)
        if not abonnement_confident:
            all_warnings.append(
                f"{prefix} : réponse 'Abonnement annuel ?' non reconnue dans '{abonnement_text}' — "
                "traitée comme 'non abonné' par défaut, à vérifier à la main."
            )

        allowed_days, day_warnings = map_days(jours_text, tournee_dates)
        for w in day_warnings:
            all_warnings.append(f"{prefix} : {w}")
        if not allowed_days:
            # Pas de jour exploitable -> l'arrêt ne peut pas être planifié.
            # On le crée quand même (allowed_days vide lèvera une erreur
            # explicite côté moteur plutôt que de disparaître silencieusement),
            # et on le signale ici en tête de liste.
            all_warnings.append(f"{prefix} : AUCUN JOUR EXPLOITABLE — cet arrêt ne pourra pas être planifié tel quel.")

        stop_id = f"{_slug(nom)}_{i}"
        label = f"{nom} ({lieu})" if lieu else nom

        stops.append(Stop(
            id=stop_id,
            label=label,
            service_minutes=service_minutes,
            allowed_days=allowed_days,
            window=window,
            animals=str(animaux_text),
            phone=str(resp.get(fmap["telephone"], "")),
            notes=str(resp.get(fmap["remarques"], "")),
            address=lieu,
            client_name=nom,
            abonnement_annuel=abonnement,
        ))

    return stops, all_warnings
