"""
Test d'intégration de tournee_service.py -- le chemin exact emprunté par
app.py (l'API) et par les scripts CLI, injecté avec une fabrique de
distances de test (dist_fn_factory) pour rester SANS appel réseau réel,
même principe que test_run_tournee_pipeline.py et
test_recalculer_nuitees_pipeline.py, qui testent le même scénario mais en
passant par les fonctions internes (solve_week_balanced / solve_multi_day)
plutôt que par calculer_tournee/recalculer_apres_nuitees eux-mêmes.

Important : c'est ce fichier-ci qui garantit que l'API produit exactement
le même résultat que les scripts CLI, puisqu'ils appellent maintenant tous
les trois les mêmes fonctions de tournee_service.py.
"""

from __future__ import annotations

from datetime import date

from tournee_service import (
    TourneeError,
    calculer_tournee,
    recalculer_apres_nuitees,
)
from weekly import DEPOT_ID

raw_responses = [
    {"_row": 2, "Nom et prénom": "Laetitia", "Numéro de téléphone": "0601020304",
     "Lieu du rendez-vous": "Bodilis", "Nombre et type d'animaux à voir": "5 chevaux",
     "Jours possibles sur la période": "Lundi, Mardi, Mercredi",
     "Avez-vous une contrainte d'horaire ferme, ou juste une préférence ?": "aucune",
     "Remarques complémentaires": ""},
    {"_row": 3, "Nom et prénom": "Aurore", "Numéro de téléphone": "0602030405",
     "Lieu du rendez-vous": "Saint-Thégonnec", "Nombre et type d'animaux à voir": "1 cheval",
     "Jours possibles sur la période": "Lundi, Mardi, Mercredi",
     "Avez-vous une contrainte d'horaire ferme, ou juste une préférence ?": "aucune",
     "Remarques complémentaires": ""},
    {"_row": 4, "Nom et prénom": "Caroline", "Numéro de téléphone": "0603040506",
     "Lieu du rendez-vous": "Landerneau", "Nombre et type d'animaux à voir": "1 cheval",
     "Jours possibles sur la période": "Lundi, Mardi, Mercredi",
     "Avez-vous une contrainte d'horaire ferme, ou juste une préférence ?": "aucune",
     "Remarques complémentaires": ""},
    {"_row": 5, "Nom et prénom": "Les filles au Rulan", "Numéro de téléphone": "0604050607",
     "Lieu du rendez-vous": "Lannion", "Nombre et type d'animaux à voir": "4 chevaux",
     "Jours possibles sur la période": "Lundi, Mardi, Mercredi",
     "Avez-vous une contrainte d'horaire ferme, ou juste une préférence ?": "pas avant 13h",
     "Remarques complémentaires": ""},
    {"_row": 6, "Nom et prénom": "Maïlys", "Numéro de téléphone": "0605060708",
     "Lieu du rendez-vous": "Plouaret", "Nombre et type d'animaux à voir": "1 cheval",
     "Jours possibles sur la période": "Lundi, Mardi, Mercredi",
     "Avez-vous une contrainte d'horaire ferme, ou juste une préférence ?": "aucune",
     "Remarques complémentaires": "Chien parfois présent, non concerné par la séance"},
]

_raw = {
    ("depot", "bodilis"): 80, ("depot", "saint_thegonnec"): 83, ("depot", "landerneau"): 65,
    ("depot", "lannion"): 133, ("depot", "plouaret"): 120,
    ("bodilis", "saint_thegonnec"): 16, ("bodilis", "landerneau"): 17, ("bodilis", "lannion"): 62,
    ("bodilis", "plouaret"): 47, ("saint_thegonnec", "landerneau"): 27, ("saint_thegonnec", "lannion"): 55,
    ("saint_thegonnec", "plouaret"): 39, ("landerneau", "lannion"): 73, ("landerneau", "plouaret"): 58,
    ("lannion", "plouaret"): 24,
}
_dist = {}
for (a, b), v in _raw.items():
    _dist[(a, b)] = v
    _dist[(b, a)] = v
_addr_to_key = {"bodilis": "bodilis", "saint-thegonnec": "saint_thegonnec", "landerneau": "landerneau",
                "lannion": "lannion", "plouaret": "plouaret"}


def _fake_dist_fn_factory(point_labels):
    """Remplace ors_client.make_dist_fn : mêmes distances vérifiées à la
    main que les autres tests, indexées par adresse plutôt que par id (les
    id générés par import_responses incluent un suffixe d'index)."""
    id_to_key = {}
    for pid, label in point_labels.items():
        if pid == DEPOT_ID:
            continue
        id_to_key[pid] = _addr_to_key[label.lower().replace("é", "e")]

    def dist_fn(a, b):
        ka = DEPOT_ID if a == DEPOT_ID else id_to_key[a]
        kb = DEPOT_ID if b == DEPOT_ID else id_to_key[b]
        return 0 if ka == kb else _dist[(ka, kb)]

    return dist_fn


print("=== 1. calculer_tournee (chemin exact utilisé par l'API /calculer) ===")
exported, warnings = calculer_tournee(
    raw_responses, date(2026, 11, 2), 3, "Penfrat, Camaret-sur-Mer",
    plafond=12, dist_fn_factory=_fake_dist_fn_factory,
)
assert not warnings, f"aucun avertissement attendu sur ce jeu de données propre : {warnings}"
total_steps = sum(len(d["steps"]) for d in exported["days"])
assert total_steps == 5, f"5 clients attendus, trouvé {total_steps}"
for d in exported["days"]:
    for step in d["steps"]:
        assert step["phone"], f"téléphone manquant pour {step['label']}"
        assert step["client_name"] != step["lieu"]
print(f"OK -- {total_steps} clients casés sur {len(exported['days'])} jours, aucun avertissement.\n")

print("=== 2. calculer_tournee : erreur métier propre si aucun client planifiable ===")
raw_sans_jour = [{**raw_responses[0], "Jours possibles sur la période": "Jeudi"}]  # jeudi hors période testée
try:
    calculer_tournee(raw_sans_jour, date(2026, 11, 2), 3, "Penfrat, Camaret-sur-Mer",
                      dist_fn_factory=_fake_dist_fn_factory)
    raise AssertionError("TourneeError attendue, rien n'a été levé")
except TourneeError as e:
    assert "planifiable" in str(e)
    print(f"OK -- TourneeError propre : {e}\n")

print("=== 3. recalculer_apres_nuitees (chemin exact utilisé par l'API /recalculer-nuitees) ===")
decisions = {
    "depot": "Penfrat, Camaret-sur-Mer",
    "day_assignments": [
        {"day_index": 0, "stops": [{"stop_id": "les_filles_au_rulan_3", "overnight": True}]},
        {"day_index": 1, "stops": [{"stop_id": "mailys_4", "overnight": False},
                                    {"stop_id": "aurore_1", "overnight": False}]},
        {"day_index": 2, "stops": [{"stop_id": "caroline_2", "overnight": False},
                                    {"stop_id": "laetitia_0", "overnight": False}]},
    ],
}
exported2, warnings2 = recalculer_apres_nuitees(
    raw_responses, decisions, date(2026, 11, 2), 3, "Penfrat, Camaret-sur-Mer",
    dist_fn_factory=_fake_dist_fn_factory,
)
day0_ids = [s["stop_id"] for s in exported2["days"][0]["steps"]]
assert day0_ids[-1] == "les_filles_au_rulan_3", "jour 1 doit se terminer à Lannion (nuitée)"
day1_ids = [s["stop_id"] for s in exported2["days"][1]["steps"]]
assert "les_filles_au_rulan_3" not in day1_ids, "Lannion (point de passage hérité) ne doit pas réapparaître comme arrêt du jour 2"
assert DEPOT_ID not in [s["stop_id"] for d in exported2["days"] for s in d["steps"]]
print("OK -- jour 1 se termine à Lannion, jour 2 n'y compte pas de doublon, dépôt jamais exporté.\n")

print("=== 4. recalculer_apres_nuitees : erreur métier propre si deux nuitées le même jour ===")
decisions_invalides = {
    "day_assignments": [
        {"day_index": 0, "stops": [
            {"stop_id": "les_filles_au_rulan_3", "overnight": True},
            {"stop_id": "mailys_4", "overnight": True},
        ]},
        {"day_index": 1, "stops": [{"stop_id": "aurore_1", "overnight": False}]},
        {"day_index": 2, "stops": [{"stop_id": "caroline_2", "overnight": False},
                                    {"stop_id": "laetitia_0", "overnight": False}]},
    ],
}
try:
    recalculer_apres_nuitees(raw_responses, decisions_invalides, date(2026, 11, 2), 3,
                              "Penfrat, Camaret-sur-Mer", dist_fn_factory=_fake_dist_fn_factory)
    raise AssertionError("TourneeError attendue, rien n'a été levé")
except TourneeError as e:
    assert "plusieurs nuitées" in str(e)
    print(f"OK -- TourneeError propre : {e}\n")

print("=== TOURNEE_SERVICE (chemin API) VALIDÉ DE BOUT EN BOUT (hors appel réseau réel) ===")
