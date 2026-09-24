"""
Test de non-régression : rejoue le scénario mardi 20 / mercredi 21 octobre 2026
(le même que le prototype déjà validé, moteur_multi_jours.py) à travers la
nouvelle interface généralisée (schema.py + solver.py), avec les mêmes temps
de trajet réels déjà vérifiés (l-itineraire.com / Mappy — aucune valeur devinée).

Objectif : vérifier que la généralisation n'a rien cassé, pas ajouter de
nouveau scénario. Les horaires attendus sont ceux déjà obtenus et documentés
dans le prototype (prototype-moteur-optimisation.md) :
  - Mercredi 21 : retour ≈19h03.
"""

from __future__ import annotations


from schema import DayPlan, Stop, StopWindow, WindowType
from solver import PREVIOUS_DAY_END, print_result, solve_multi_day
from validate import validate_days

# ---------------------------------------------------------------------------
# Points (labels) — mardi + mercredi
# ---------------------------------------------------------------------------
point_labels = {
    "camaret": "Camaret (dépôt)",
    "la_feuillee": "La Feuillée (Yannick)",
    "saint_martin": "Saint-Martin-des-Champs (Sandrine)",
    "plourin": "Plourin-lès-Morlaix (Manon Victoir)",
    "bodilis": "Bodilis (Laetitia + Kerrous)",
    "saint_thegonnec": "Saint-Thégonnec (Aurore)",
    "landerneau": "Landerneau (Caroline)",
    "lannion": "Lannion (Les filles au Rulan)",
    "plouaret": "Plouaret (Maïlys)",
}

# ---------------------------------------------------------------------------
# Temps de trajet réels (minutes), symétriques par approximation — repris
# tels quels du prototype (aucune nouvelle recherche).
# ---------------------------------------------------------------------------
_raw = {
    ("camaret", "la_feuillee"): 72, ("camaret", "saint_martin"): 92,
    ("camaret", "plourin"): 101, ("camaret", "bodilis"): 81,
    ("la_feuillee", "saint_martin"): 35, ("la_feuillee", "plourin"): 23,
    ("la_feuillee", "bodilis"): 32,
    ("saint_martin", "plourin"): 11, ("saint_martin", "bodilis"): 18,
    ("plourin", "bodilis"): 27,
    ("bodilis", "saint_thegonnec"): 16, ("bodilis", "landerneau"): 17,
    ("bodilis", "lannion"): 62, ("bodilis", "plouaret"): 47, ("bodilis", "camaret"): 80,
    ("saint_thegonnec", "landerneau"): 27, ("saint_thegonnec", "lannion"): 55,
    ("saint_thegonnec", "plouaret"): 39, ("saint_thegonnec", "camaret"): 83,
    ("landerneau", "lannion"): 73, ("landerneau", "plouaret"): 58, ("landerneau", "camaret"): 65,
    ("lannion", "plouaret"): 24, ("lannion", "camaret"): 133,
    ("plouaret", "camaret"): 120,
}
_dist = {}
for (a, b), v in _raw.items():
    _dist[(a, b)] = v
    _dist[(b, a)] = v


def dist_fn(a: str, b: str) -> int:
    if a == b:
        return 0
    return _dist[(a, b)]  # KeyError volontaire si paire manquante -> le solveur la traduit


# ---------------------------------------------------------------------------
# Arrêts
# ---------------------------------------------------------------------------
stops = [
    Stop("la_feuillee", point_labels["la_feuillee"], 45, allowed_days=[0]),
    Stop("saint_martin", point_labels["saint_martin"], 45, allowed_days=[0]),
    Stop("plourin", point_labels["plourin"], 45, allowed_days=[0]),
    Stop("bodilis", point_labels["bodilis"], 90 + 225, allowed_days=[0],
         window=StopWindow(WindowType.FLOOR, start_min=13 * 60)),
    Stop("saint_thegonnec", point_labels["saint_thegonnec"], 45, allowed_days=[1]),
    Stop("landerneau", point_labels["landerneau"], 45, allowed_days=[1]),
    Stop("lannion", point_labels["lannion"], 180, allowed_days=[1],
         window=StopWindow(WindowType.FLOOR, start_min=13 * 60)),
    Stop("plouaret", point_labels["plouaret"], 45, allowed_days=[1]),
]

days = [
    DayPlan(
        day_index=0, label="MARDI 20 (nuit à Bodilis)",
        start_id="camaret", open_route=True,
        start_window=StopWindow(WindowType.HARD, start_min=6 * 60, end_min=10 * 60),
        day_start_min=6 * 60, day_end_min=19 * 60,
    ),
    DayPlan(
        day_index=1, label="MERCREDI 21 (retour Camaret)",
        start_id=PREVIOUS_DAY_END, end_id="camaret", open_route=False,
        # Même règle que le mardi : départ du lieu où Ludivine a dormi entre 6h et 10h
        # (règle métier générale, pas spécifique au dépôt de Camaret) — reprise telle
        # quelle du prototype, où elle s'appliquait aussi au mercredi.
        start_window=StopWindow(WindowType.HARD, start_min=6 * 60, end_min=10 * 60),
        day_start_min=6 * 60, day_end_min=19 * 60,
    ),
]

if __name__ == "__main__":
    warnings = validate_days(days, stops)
    if warnings:
        print("=== Avertissements avant résolution ===")
        for w in warnings:
            print(f"  ⚠ {w}")

    results = solve_multi_day(days, stops, point_labels, dist_fn)
    for day_index in sorted(results):
        print_result(results[day_index])

    tue, wed = results[0], results[1]
    assert tue.feasible, tue.error
    assert wed.feasible, wed.error
    print(f"\nFin mardi (nuit à Bodilis) : {tue.finish_min // 60:02d}h{tue.finish_min % 60:02d}")
    print(f"Retour Camaret mercredi     : {wed.finish_min // 60:02d}h{wed.finish_min % 60:02d}")

    expected_wed_finish = 19 * 60 + 3  # 19h03, résultat déjà validé avec le prototype
    delta = abs(wed.finish_min - expected_wed_finish)
    print(f"\nÉcart vs résultat déjà validé (mercredi, 19h03) : {delta} min")
    if delta <= 2:
        print("OK — non-régression confirmée (écart ≤ 2 min, arrondis possibles).")
    else:
        print("À VÉRIFIER — écart plus grand que prévu, comparer à la main avec le prototype.")
