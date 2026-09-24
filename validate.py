"""
Garde-fous de bon sens sur un jeu de DayPlan/Stop avant de lancer le moteur.

Existe suite à un incident rencontré en généralisant le moteur (24 sept. 2026) :
un DayPlan sans start_window explicite a laissé le solveur choisir un départ
à 10h58 au lieu de tôt le matin, produisant un résultat plausible en apparence
mais 1h47 pire que la référence déjà validée (20h50 au lieu de 19h03) — sans
qu'aucune erreur ne soit levée. Le moteur ne proteste jamais tout seul contre
une contrainte manquante ; ces vérifications comblent ce point aveugle.
"""

from __future__ import annotations


from schema import DayPlan, Stop, WindowType


def validate_days(days: list[DayPlan], stops: list[Stop]) -> list[str]:
    """Renvoie une liste d'avertissements (liste vide = rien à signaler).
    N'empêche jamais de lancer le moteur — sert à attirer l'œil avant de
    faire confiance au résultat, dans le même esprit que la relecture
    humaine obligatoire avant tout envoi client."""
    warnings: list[str] = []
    stops_by_day: dict[int, list[Stop]] = {}
    for s in stops:
        if len(s.allowed_days) != 1:
            warnings.append(
                f"Arrêt '{s.label}' : {len(s.allowed_days)} jour(s) possible(s) "
                f"{s.allowed_days} passé(s) à validate_days/solve_multi_day, qui suppose un "
                "jour déjà fixé (1 seul). Pour un jour encore à décider par le moteur, "
                "utiliser solve_week / solve_week_balanced à la place."
            )
            continue
        stops_by_day.setdefault(s.allowed_days[0], []).append(s)

    for day in days:
        if day.start_window.type == WindowType.NONE:
            warnings.append(
                f"Jour {day.day_index} ({day.label}) : aucune fenêtre de départ définie — "
                "le moteur peut choisir un départ tardif contre-intuitif pour minimiser "
                "l'étalement de la journée. Vérifier si un start_window est attendu."
            )
        day_stops = stops_by_day.get(day.day_index, [])
        if not day_stops:
            warnings.append(f"Jour {day.day_index} ({day.label}) : aucun arrêt rattaché.")
        for s in day_stops:
            if s.window.type == WindowType.HARD and s.window.start_min is not None \
                    and s.window.end_min is not None and s.window.start_min >= s.window.end_min:
                warnings.append(
                    f"Arrêt '{s.label}' (jour {day.day_index}) : fenêtre horaire incohérente "
                    f"({s.window.start_min} >= {s.window.end_min})."
                )
            if s.service_minutes <= 0:
                warnings.append(f"Arrêt '{s.label}' (jour {day.day_index}) : durée de service nulle ou négative.")

    return warnings
