"""
Test d'intégration de run_tournee.py, SANS appel réseau réel : vérifie que le
branchement complet (import du formulaire -> Stop avec adresse -> moteur ->
export JSON pour l'interface) fonctionne, en remplaçant uniquement
ors_client.make_dist_fn par la fonction de distances déjà vérifiées à la main
(même données que weekly_test.py). La fiabilité des distances ORS elles-mêmes
est déjà validée séparément (comparer_ors_vs_reference.py, exécuté par
Margaux le 24 sept. 2026 -- écart max 9 min, jugé normal).

Objectif ici : uniquement la plomberie (le formulaire brut arrive-t-il
correctement, avec la bonne adresse, jusqu'au JSON de sortie ?), pas l'API.
"""

from __future__ import annotations


import json
from datetime import date

from form_import import import_responses
from run_tournee import build_days, export_for_interface
from weekly import DEPOT_ID, solve_week_balanced

# Export brut simulé (même format que le vrai pont Apps Script), 5 clients
# réels déjà utilisés/vérifiés dans weekly_test.py.
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

tournee_dates = [date(2026, 11, 2), date(2026, 11, 3), date(2026, 11, 4)]  # lun-mar-mer

print("=== 1. Import du formulaire ===")
stops, warnings = import_responses(raw_responses, tournee_dates)
for s in stops:
    print(f"  {s.label:30s} address='{s.address}' jours={s.allowed_days} tel={s.phone}")
assert all(s.address for s in stops), "chaque Stop doit avoir une adresse géocodable"
# vérifie que l'adresse est bien celle du formulaire, pas le label affiché
assert stops[0].address == "Bodilis" and stops[0].label != stops[0].address
print("OK -- adresses correctement séparées des labels.\n")

print("=== 2. dist_fn de test (mêmes distances vérifiées que weekly_test.py) ===")
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

# Les id générés par import_responses incluent un suffixe d'index (ex.
# "bodilis_0") -- on construit donc un dist_fn qui retrouve la bonne entrée
# via l'adresse plutôt que l'id, pour coller à la vraie contrainte de
# make_dist_fn (indexé par id, mais on veut ici simuler la même chose sans
# réseau). On mappe chaque id de Stop vers sa clé "connue" via son adresse en
# minuscules/sans accents simplifié à la main pour ce test.
addr_to_key = {"bodilis": "bodilis", "saint-thegonnec": "saint_thegonnec", "landerneau": "landerneau",
               "lannion": "lannion", "plouaret": "plouaret"}
id_to_key = {}
for s in stops:
    key = s.address.lower().replace("é", "e")
    assert key in addr_to_key, f"adresse de test inattendue : {s.address}"
    id_to_key[s.id] = addr_to_key[key]


def dist_fn(a, b):
    ka = DEPOT_ID if a == DEPOT_ID else id_to_key[a]
    kb = DEPOT_ID if b == DEPOT_ID else id_to_key[b]
    if ka == kb:
        return 0
    return _dist[(ka, kb)]


print("OK\n")

print("=== 3. Résolution (solve_week_balanced) ===")
days = build_days(date(2026, 11, 2), 3, max_span_h=12)
result = solve_week_balanced(days, stops, dist_fn, depot_label="Camaret (dépôt)")
assert result.feasible, result.missing_client_ids
print("OK -- tous les clients casés.\n")

print("=== 4. Export JSON pour l'interface ===")
clients_by_id = {s.id: s for s in stops}
exported = export_for_interface(result.day_results, clients_by_id)

assert "days" in exported
total_steps = sum(len(d["steps"]) for d in exported["days"])
assert total_steps == 5, f"5 clients attendus dans l'export, trouvé {total_steps}"
for d in exported["days"]:
    for step in d["steps"]:
        assert set(step.keys()) == {
            "stop_id", "label", "client_name", "lieu", "arrival_min",
            "service_minutes", "phone", "notes", "abonnement_annuel", "animals",
        }
        assert step["phone"], f"téléphone manquant pour {step['label']} -- le rattachement Stop a dû échouer"
        assert step["client_name"], f"nom client manquant pour {step['label']}"
        assert step["lieu"], f"lieu manquant pour {step['label']}"

maïlys_step = next(s for d in exported["days"] for s in d["steps"] if "Maïlys" in s["label"])
assert "Chien parfois présent" in maïlys_step["notes"], "les remarques du formulaire doivent être rattachées"
assert maïlys_step["client_name"] == "Maïlys"
assert maïlys_step["lieu"] == "Plouaret"
# Non-régression du bug du 24 sept. 2026 (nom/lieu inversés) : client_name et lieu
# doivent être distincts et corrects indépendamment de l'ordre choisi dans label.
assert maïlys_step["client_name"] != maïlys_step["lieu"]

print("OK -- JSON exporté conforme au format attendu par l'interface, téléphone/notes bien rattachés.")
print(f"\nAperçu :\n{json.dumps(exported, ensure_ascii=False, indent=2)[:600]}...")
print("\n=== PIPELINE COMPLET VALIDÉ (hors appel réseau réel, déjà validé séparément) ===")
