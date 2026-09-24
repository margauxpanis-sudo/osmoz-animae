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

    # -------------------------------------------------------------------
    # Priorité "abonnement annuel" (25 sept. 2026) : sur une tournée
    # volontairement TROP chargée pour caser tout le monde (un seul jour,
    # plafond serré, deux gros clients qui ne rentrent pas ensemble), le
    # client abonné doit être celui qu'on garde -- et le moteur doit
    # renvoyer un résultat exploitable (feasible=False, missing_client_ids
    # renseigné) plutôt que de planter, même au plafond le plus large fourni.
    # -------------------------------------------------------------------
    print("\n\n########## Priorité abonnement annuel (tournée volontairement surchargée) ##########")
    # Plafond et durées choisis pour que CHAQUE client tienne seul dans le
    # plafond (aller-retour dépôt inclus) mais que les DEUX ensemble ne
    # tiennent plus (depot<->landerneau=65 et depot<->bodilis=80, distance
    # landerneau<->bodilis=17 -- valeurs réelles déjà vérifiées ci-dessus) :
    # seul : 65*2+180=310 ou 80*2+180=340, tous les deux <= 360 (plafond) ;
    # ensemble : 65+17+80+180*2=522, très au-delà du plafond.
    one_day = [DayConfig(0, "Jour unique", max_span_min=6 * 60)]
    overloaded_clients = [
        Stop("landerneau", "Landerneau (Caroline, abonnée)", 180, allowed_days=[0], abonnement_annuel=True),
        Stop("bodilis", "Bodilis (Laetitia, non abonnée)", 180, allowed_days=[0], abonnement_annuel=False),
    ]
    r3 = solve_week(one_day, overloaded_clients, dist_fn, time_limit_s=5)
    assert not r3.feasible, "ce cas doit être volontairement infaisable pour tout le monde à la fois"
    assert r3.missing_client_ids == ["bodilis"], (
        "le client SANS abonnement annuel doit être celui sacrifié, pas l'abonnée "
        f"-- obtenu : {r3.missing_client_ids}"
    )
    print(f"OK — client(s) non casé(s) : {r3.missing_client_ids} (l'abonnée annuelle est bien conservée)")

    print("\n########## Même cas, via solve_week_balanced (ne doit plus planter) ##########")
    r4 = solve_week_balanced(one_day, overloaded_clients, dist_fn, search_time_limit_s=3, final_time_limit_s=5)
    assert not r4.feasible
    assert r4.missing_client_ids == ["bodilis"], r4.missing_client_ids
    print("OK — solve_week_balanced renvoie un résultat partiel exploitable au lieu de planter.")
