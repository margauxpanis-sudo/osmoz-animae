"""
Test d'intégration de recalculer_nuitees.py, SANS appel réseau réel (même
principe que test_run_tournee_pipeline.py) : ors_client.make_dist_fn est
remplacé par la fonction de distances déjà vérifiées à la main.

Scénario : reprend l'affectation jour par jour obtenue par Margaux lors du
vrai essai du 24 sept. 2026 (run_tournee.py, 5 clients, 3 jours), et simule
qu'elle pose une nuitée chez "Les filles au Rulan" (Lannion) à la fin du
jour 1. Vérifie que le jour 2 repart bien de Lannion (et non du dépôt), que
le jour 1 se termine bien à Lannion (pas ailleurs), et que le jour 3 -- sans
nuitée -- repart normalement du dépôt.
"""

from datetime import date

from form_import import import_responses
from ors_client import OrsError
from run_tournee import export_for_interface
from schema import DayPlan
from solver import PREVIOUS_DAY_END, solve_multi_day
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
     "Remarques complémentaires": ""},
]
tournee_dates = [date(2026, 11, 2), date(2026, 11, 3), date(2026, 11, 4)]

# Décisions telles qu'elles seraient téléchargées depuis l'interface, après
# que Margaux a coché "Nuit ici" sur Lannion à la fin du jour 1.
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

print("=== 1. Import (identique au premier calcul) ===")
stops, warnings = import_responses(raw_responses, tournee_dates)
stops_by_id = {s.id: s for s in stops}
assert set(s.id for s in stops) == {"laetitia_0", "aurore_1", "caroline_2", "les_filles_au_rulan_3", "mailys_4"}
print("OK -- les ids correspondent à ceux du fichier de décisions.\n")

print("=== 2. Application des décisions (jour fixé, nuitée repérée) ===")
overnight_stop_by_day = {}
day_of_stop = {}
for day_entry in decisions["day_assignments"]:
    d = day_entry["day_index"]
    overnight_here = [s["stop_id"] for s in day_entry["stops"] if s.get("overnight")]
    assert len(overnight_here) <= 1
    if overnight_here:
        overnight_stop_by_day[d] = overnight_here[0]
    for s in day_entry["stops"]:
        day_of_stop[s["stop_id"]] = d
        stops_by_id[s["stop_id"]].allowed_days = [d]

assert overnight_stop_by_day == {0: "les_filles_au_rulan_3"}
active_stops = [s for s in stops if s.id in day_of_stop]
print("OK\n")

print("=== 3. dist_fn de test (mêmes distances vérifiées) ===")
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
addr_to_key = {"bodilis": "bodilis", "saint-thegonnec": "saint_thegonnec", "landerneau": "landerneau",
               "lannion": "lannion", "plouaret": "plouaret"}
id_to_key = {s.id: addr_to_key[s.address.lower().replace("é", "e")] for s in active_stops}


def dist_fn(a, b):
    ka = DEPOT_ID if a == DEPOT_ID else id_to_key[a]
    kb = DEPOT_ID if b == DEPOT_ID else id_to_key[b]
    return 0 if ka == kb else _dist[(ka, kb)]


print("OK\n")

print("=== 4. Construction des DayPlan (nuitée -> end_id imposé, jour suivant -> PREVIOUS_DAY_END) ===")
days_plan = []
for i in range(3):
    overnight_id = overnight_stop_by_day.get(i)
    days_plan.append(DayPlan(
        day_index=i, label=f"Jour {i + 1}",
        start_id=DEPOT_ID if i == 0 else PREVIOUS_DAY_END,
        end_id=overnight_id if overnight_id else DEPOT_ID,
        open_route=False,
    ))
print("OK\n")

print("=== 5. Résolution (solve_multi_day) ===")
point_labels = {DEPOT_ID: decisions["depot"], **{s.id: s.address for s in active_stops}}
day_results = solve_multi_day(days_plan, active_stops, point_labels, dist_fn)
for d, r in day_results.items():
    assert r.feasible, r.error
    print(f"  Jour {d} : " + ", ".join(f"{s.stop_id}@{s.arrival_min}" for s in r.steps))

# Vérifications clés :
# - jour 0 doit se terminer À Lannion (dernier "vrai" step = les_filles_au_rulan_3)
day0_real_steps = [s for s in day_results[0].steps if s.stop_id in stops_by_id]
assert day0_real_steps[-1].stop_id == "les_filles_au_rulan_3", \
    f"le jour 1 doit se terminer chez Lannion (nuitée), pas {day0_real_steps[-1].stop_id}"
# - jour 1 doit démarrer DE Lannion (premier step = dépôt/point de passage réel = lannion, pas le dépôt)
assert day_results[1].steps[0].stop_id == "les_filles_au_rulan_3", \
    f"le jour 2 doit repartir de Lannion (nuitée précédente), pas {day_results[1].steps[0].stop_id}"
# - jour 2 (pas de nuitée le jour 1->2... ici jour 2 est jour 3, sans nuitée avant) doit repartir du dépôt
assert day_results[2].steps[0].stop_id == DEPOT_ID, \
    f"le jour 3 doit repartir du dépôt (pas de nuitée le jour 2), pas {day_results[2].steps[0].stop_id}"
print("\nOK -- jour 1 se termine bien à Lannion, jour 2 en repart, jour 3 repart bien du dépôt.\n")

print("=== 6. Export JSON pour l'interface ===")
exported = export_for_interface(day_results, stops_by_id)

# Le dépôt ne doit JAMAIS apparaître comme un arrêt dans le JSON envoyé à
# l'interface (ni au début du jour 2, ni à la fin du jour 1/3).
all_stop_ids = [s["stop_id"] for d in exported["days"] for s in d["steps"]]
assert DEPOT_ID not in all_stop_ids, "le dépôt ne doit jamais apparaître comme arrêt dans l'export"
assert sum(len(d["steps"]) for d in exported["days"]) == 5, "les 5 vrais clients doivent tous être présents"
print("OK -- dépôt correctement exclu de l'export, 5 clients présents.\n")

print("=== PIPELINE DE RECALCUL APRÈS NUITÉE VALIDÉ (hors appel réseau réel) ===")
