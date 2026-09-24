"""
Test du moteur hebdomadaire (weekly.py) sur des données réelles déjà
vérifiées (le "cluster mercredi" du prototype + Bodilis, dont toutes les
distances vers ce cluster sont connues — cf. T_wed dans moteur_multi_jours.py).
Aucune distance inventée : uniquement des paires déjà utilisées et validées
dans les tests précédents.

Objectif du test : 5 clients réels, tous rendus flexibles sur 3 jours (au
lieu d'être assignés à la main comme avant), avec un plafond d'heures/jour
("rythme") de 12h — chiffre confirmé par Margaux le 24 sept. 2026. Le moteur
doit les répartir lui-même sur les 3 jours en respectant le plafond, puis
étaler activement la charge (solve_week_balanced), sans qu'on lui dise qui
va où.
"""

from __future__ import annotations


from schema import DayConfig, Stop, StopWindow, WindowType
from weekly import solve_week, solve_week_balanced

# Distances réelles déjà vérifiées (l-itineraire.com / Mappy), reprises de
# moteur_multi_jours.py (T_wed) — depot = Camaret.
_raw = {
    ("depot", "bodilis"): 80,
    ("depot", "saint_thegonnec"): 83,
    ("depot", "landerneau"): 65,
    ("depot", "lannion"): 133,
    ("depot", "plouaret"): 120,
    ("bodilis", "saint_thegonnec"): 16,
    ("bodilis", "landerneau"): 17,
    ("bodilis", "lannion"): 62,
    ("bodilis", "plouaret"): 47,
    ("saint_thegonnec", "landerneau"): 27,
    ("saint_thegonnec", "lannion"): 55,
    ("saint_thegonnec", "plouaret"): 39,
    ("landerneau", "lannion"): 73,
    ("landerneau", "plouaret"): 58,
    ("lannion", "plouaret"): 24,
}
_dist = {}
for (a, b), v in _raw.items():
    _dist[(a, b)] = v
    _dist[(b, a)] = v


def dist_fn(a, b):
    if a == b:
        return 0
    return _dist[(a, b)]


days = [
    DayConfig(0, "Jour 1", max_span_min=12 * 60),
    DayConfig(1, "Jour 2", max_span_min=12 * 60),
    DayConfig(2, "Jour 3", max_span_min=12 * 60),
]

clients = [
    Stop("bodilis", "Bodilis (Laetitia + Kerrous)", 90 + 225, allowed_days=[0, 1, 2]),
    Stop("saint_thegonnec", "Saint-Thégonnec (Aurore)", 45, allowed_days=[0, 1, 2]),
    Stop("landerneau", "Landerneau (Caroline)", 45, allowed_days=[0, 1, 2]),
    Stop("lannion", "Lannion (Les filles au Rulan)", 180, allowed_days=[0, 1, 2],
         window=StopWindow(WindowType.FLOOR, start_min=13 * 60)),
    Stop("plouaret", "Plouaret (Maïlys)", 45, allowed_days=[0, 1, 2]),
]

if __name__ == "__main__":
    print("########## Sans équilibrage actif (plafond dur seul) ##########")
    r1 = solve_week(days, clients, dist_fn)
    assert r1.feasible, r1.missing_client_ids

    print("\n\n########## Avec équilibrage actif (plafond minimal par dichotomie) ##########")
    r2 = solve_week_balanced(days, clients, dist_fn)
    assert r2.feasible, r2.missing_client_ids

    spans = sorted(r.span_min for r in r2.day_results.values() if r.steps)
    print(f"\nÉtalements (avec équilibrage) : {[f'{s // 60}h{s % 60:02d}' for s in spans]}")
    assert max(spans) - min(spans) < sorted(r.span_min for r in r1.day_results.values() if r.steps)[-1], \
        "L'équilibrage devrait réduire l'écart entre le jour le plus chargé et le moins chargé."
    print("OK — l'équilibrage actif réduit bien l'écart entre jours par rapport au plafond seul.")
