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
    build_days,
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

print("=== 5. calculer_tournee : jours_exclus retire un jour SANS casser l'équilibrage ===")
# Nov 2/3/4 2026 = lundi/mardi/mercredi (vérifié : date(2026,11,2).weekday() == 0).
# Exclure le mercredi ne doit RIEN casser : tout le monde a coché lundi ET
# mardi en plus du mercredi -> les 5 restent casables sur les 2 jours
# restants. Ce test couvre justement le piège découvert en implémentant la
# fonctionnalité (26 sept. 2026) : solve_week_balanced calcule un plafond
# UNIQUE par dichotomie sur le MINIMUM des plafonds des jours REÇUS -- si le
# mercredi exclu avait été modélisé en DayConfig à plafond 0 plutôt
# qu'absent de la liste, ce plafond 0 aurait fait chuter celui de TOUS les
# jours et rendu ce test infaisable à tort.
exported5, warnings5 = calculer_tournee(
    raw_responses, date(2026, 11, 2), 3, "Penfrat, Camaret-sur-Mer",
    plafond=12, jours_exclus=["Mercredi"], dist_fn_factory=_fake_dist_fn_factory,
)
assert not warnings5, f"aucun avertissement attendu (tout le monde a aussi lundi/mardi) : {warnings5}"
assert len(exported5["days"]) == 2, f"2 jours attendus (mercredi exclu), trouvé {len(exported5['days'])}"
assert {d["day_index"] for d in exported5["days"]} == {0, 1}, "le mercredi (day_index 2) ne doit apparaître nulle part"
total_steps5 = sum(len(d["steps"]) for d in exported5["days"])
assert total_steps5 == 5, f"5 clients toujours casables sur lundi/mardi, trouvé {total_steps5}"
print(f"OK -- mercredi exclu, {total_steps5} clients toujours casés sur {len(exported5['days'])} jours, aucun avertissement.\n")

print("=== 6. calculer_tournee : jours_exclus + client dont le SEUL jour coché est exclu ===")
raw_avec_mercredi_seul = raw_responses + [
    {"_row": 7, "Nom et prénom": "Solange", "Numéro de téléphone": "0606070809",
     "Lieu du rendez-vous": "Landerneau", "Nombre et type d'animaux à voir": "1 cheval",
     "Jours possibles sur la période": "Mercredi",
     "Avez-vous une contrainte d'horaire ferme, ou juste une préférence ?": "aucune",
     "Remarques complémentaires": ""},
]
exported6, warnings6 = calculer_tournee(
    raw_avec_mercredi_seul, date(2026, 11, 2), 3, "Penfrat, Camaret-sur-Mer",
    plafond=12, jours_exclus=["mercredi"], dist_fn_factory=_fake_dist_fn_factory,
)
# La cause doit être nommée explicitement (jour exclu), jamais fondue dans
# l'avertissement générique "sans aucun jour exploitable" -- principe du
# projet : ne jamais échouer silencieusement sur la vraie raison.
assert len(warnings6) == 1, f"un seul avertissement attendu (Solange écartée pour cause de jour exclu) : {warnings6}"
assert "Solange" in warnings6[0] and "exclu" in warnings6[0].lower(), f"avertissement pas assez explicite : {warnings6[0]}"
assert "sans aucun jour exploitable" not in warnings6[0], "ne doit pas se fondre dans le message générique"
total_steps6 = sum(len(d["steps"]) for d in exported6["days"])
assert total_steps6 == 5, f"les 5 autres clients (lundi/mardi dispo) restent casés, trouvé {total_steps6}"
print(f"OK -- Solange écartée avec la vraie cause nommée : {warnings6[0]}\n")

print("=== 7. build_days : horaires_jours applique des horaires propres à un jour de semaine ===")
days7 = build_days(date(2026, 11, 2), 3, 12, horaires_jours={"mardi": (9 * 60, 17 * 60)})
by_index = {d.day_index: d for d in days7}
assert by_index[0].day_start_min == 6 * 60 and by_index[0].day_end_min == 20 * 60 + 30, \
    "lundi doit garder les horaires par défaut"
assert by_index[1].day_start_min == 9 * 60 and by_index[1].day_end_min == 17 * 60, \
    "mardi doit avoir les horaires personnalisés"
assert by_index[2].day_start_min == 6 * 60 and by_index[2].day_end_min == 20 * 60 + 30, \
    "mercredi doit garder les horaires par défaut"
print("OK -- mardi a ses horaires propres (9h-17h), les autres jours gardent les horaires par défaut.\n")

print("=== 8. calculer_tournee : dates_fermees (fermeture ponctuelle par date, pas par motif hebdomadaire) ===")
exported8, warnings8 = calculer_tournee(
    raw_responses, date(2026, 11, 2), 3, "Penfrat, Camaret-sur-Mer",
    plafond=12, dates_fermees=["2026-11-04"], dist_fn_factory=_fake_dist_fn_factory,
)
assert not warnings8, f"aucun avertissement attendu (tout le monde a aussi lundi/mardi) : {warnings8}"
assert {d["day_index"] for d in exported8["days"]} == {0, 1}, "04/11 (mercredi, day_index 2) doit être absent"
total_steps8 = sum(len(d["steps"]) for d in exported8["days"])
assert total_steps8 == 5, f"5 clients toujours casables sur lundi/mardi, trouvé {total_steps8}"
print("OK -- 04/11 fermé par date précise, même effet qu'une exclusion par jour de semaine.\n")

print("=== 9. calculer_tournee : jours_exclus + dates_fermees se CUMULENT ===")
# plafond relevé à 14h (contre 12h ailleurs dans ce fichier) : caser les 5
# clients sur le SEUL jour restant (lundi) est plus serré qu'avec 2-3 jours
# disponibles -- vérifié à la main (13h : Laetitia ne rentre pas, 14h : si).
# Le point testé ici est la CUMULATION des deux exclusions, pas le réglage
# fin du plafond.
exported9, warnings9 = calculer_tournee(
    raw_responses, date(2026, 11, 2), 3, "Penfrat, Camaret-sur-Mer",
    plafond=14, jours_exclus=["mardi"], dates_fermees=["2026-11-04"],
    dist_fn_factory=_fake_dist_fn_factory,
)
assert {d["day_index"] for d in exported9["days"]} == {0}, \
    f"mardi (motif) ET le 04/11 (date, =mercredi) doivent être exclus, seul lundi doit rester : {exported9['days']}"
total_steps9 = sum(len(d["steps"]) for d in exported9["days"])
assert total_steps9 == 5, f"les 5 clients ont aussi coché lundi, doivent tous tenir sur ce seul jour : {total_steps9}"
print("OK -- jours_exclus (mardi) et dates_fermees (04/11=mercredi) se cumulent bien, seul lundi reste.\n")

print("=== 10. calculer_tournee : format_dispo='dates_precises' (mode consultations, quinzaine) ===")
# Quinzaine du 1er au 15 octobre 2026 -- volontairement plus longue qu'une
# semaine pour reproduire exactement le cas qui posait problème avec le
# format "jours de semaine" (deux mardis, deux mercredis, trois jeudis
# dans cette période -- voir map_days). Avec des dates précises, AUCUNE
# ambiguïté ne doit être soulevée, contrairement à ce que produirait le
# même texte interprété comme des noms de jour.
raw_responses_dates = [
    {"_row": 2, "Nom et prénom": "Nadège", "Numéro de téléphone": "0607080910",
     "Lieu du rendez-vous": "Landerneau", "Nombre et type d'animaux à voir": "1 cheval",
     "Dates possibles sur la période": "Mardi 06/10, Jeudi 08/10",
     "Avez-vous une contrainte d'horaire ferme, ou juste une préférence ?": "aucune",
     "Remarques complémentaires": ""},
    {"_row": 3, "Nom et prénom": "Elise", "Numéro de téléphone": "0608091011",
     "Lieu du rendez-vous": "Lannion", "Nombre et type d'animaux à voir": "1 cheval",
     "Dates possibles sur la période": "14/10",  # UN SEUL mercredi choisi, alors qu'il y en a deux dans la période
     "Avez-vous une contrainte d'horaire ferme, ou juste une préférence ?": "aucune",
     "Remarques complémentaires": ""},
    {"_row": 4, "Nom et prénom": "Fanny", "Numéro de téléphone": "0609101112",
     "Lieu du rendez-vous": "Plouaret", "Nombre et type d'animaux à voir": "1 cheval",
     "Dates possibles sur la période": "01/10, 15/10",
     "Avez-vous une contrainte d'horaire ferme, ou juste une préférence ?": "aucune",
     "Remarques complémentaires": ""},
]
exported10, warnings10 = calculer_tournee(
    raw_responses_dates, date(2026, 10, 1), 15, "Penfrat, Camaret-sur-Mer",
    plafond=12, format_dispo="dates_precises", dist_fn_factory=_fake_dist_fn_factory,
)
assert not any("apparaît" in w or "plusieurs" in w.lower() for w in warnings10), \
    f"aucune ambiguïté ne doit être soulevée avec des dates précises : {warnings10}"
total_steps10 = sum(len(d["steps"]) for d in exported10["days"])
assert total_steps10 == 3, f"3 clients attendus, trouvé {total_steps10}"
elise_days = [d["day_index"] for d in exported10["days"] if any(s["client_name"] == "Elise" for s in d["steps"])]
assert elise_days == [13], f"Elise n'a coché QUE le 14/10 (day_index 13), jamais le 07/10 (day_index 6) : {elise_days}"
print(f"OK -- {total_steps10} clients casés sur des dates précises, aucune ambiguïté, Elise casée uniquement le 14/10.\n")

print("=== 11. calculer_tournee : validations explicites (format_dispo, horaires, dates_fermees invalides) ===")
try:
    calculer_tournee(raw_responses, date(2026, 11, 2), 3, "Penfrat, Camaret-sur-Mer",
                      format_dispo="n_importe_quoi", dist_fn_factory=_fake_dist_fn_factory)
    raise AssertionError("TourneeError attendue, rien n'a été levé")
except TourneeError as e:
    assert "format_dispo" in str(e)
    print(f"OK -- format_dispo invalide rejeté proprement : {e}")

try:
    calculer_tournee(raw_responses, date(2026, 11, 2), 3, "Penfrat, Camaret-sur-Mer",
                      horaires_jours={"mardi": {"debut": "18:00", "fin": "09:00"}},
                      dist_fn_factory=_fake_dist_fn_factory)
    raise AssertionError("TourneeError attendue, rien n'a été levé")
except TourneeError as e:
    assert "avant l'heure de fin" in str(e)
    print(f"OK -- horaires incohérents (début après fin) rejetés proprement : {e}")

try:
    calculer_tournee(raw_responses, date(2026, 11, 2), 3, "Penfrat, Camaret-sur-Mer",
                      dates_fermees=["14 novembre"], dist_fn_factory=_fake_dist_fn_factory)
    raise AssertionError("TourneeError attendue, rien n'a été levé")
except TourneeError as e:
    assert "Date fermée invalide" in str(e)
    print(f"OK -- date fermée mal formée rejetée proprement : {e}\n")

print("=== 12. build_days : dates_dernier_recours marque le jour SANS l'exclure ===")
days12 = build_days(date(2026, 11, 2), 3, 12, dates_dernier_recours=["2026-11-04"])
assert len(days12) == 3, f"les 3 jours doivent tous être présents (contrairement à dates_fermees) : {len(days12)}"
by_index12 = {d.day_index: d for d in days12}
assert by_index12[0].dernier_recours is False and by_index12[1].dernier_recours is False
assert by_index12[2].dernier_recours is True, "04/11 (day_index 2) doit être marqué dernier_recours"
print("OK -- 04/11 marqué dernier_recours=True, toujours présent dans la liste (pas exclu).\n")

print("=== 13. build_days : une date ne peut pas être à la fois fermée ET dernier recours ===")
try:
    build_days(date(2026, 11, 2), 3, 12, dates_fermees=["2026-11-04"], dates_dernier_recours=["2026-11-04"])
    raise AssertionError("TourneeError attendue, rien n'a été levé")
except TourneeError as e:
    assert "fermé" in str(e).lower() and "dernier recours" in str(e).lower()
    print(f"OK -- contradiction rejetée proprement : {e}\n")

print("=== 14. calculer_tournee : un client sans autre option bascule sur le jour dernier recours ===")
raw_dernier_recours = [
    {**r, "Jours possibles sur la période": "Lundi, Mardi"} for r in raw_responses[:4]
] + [
    {"_row": 8, "Nom et prénom": "Solange", "Numéro de téléphone": "0607080910",
     "Lieu du rendez-vous": "Landerneau", "Nombre et type d'animaux à voir": "1 cheval",
     "Jours possibles sur la période": "Mercredi",
     "Avez-vous une contrainte d'horaire ferme, ou juste une préférence ?": "aucune",
     "Remarques complémentaires": ""},
]
exported14, warnings14 = calculer_tournee(
    raw_dernier_recours, date(2026, 11, 2), 3, "Penfrat, Camaret-sur-Mer",
    plafond=12, dates_dernier_recours=["2026-11-04"], dist_fn_factory=_fake_dist_fn_factory,
)
assert not any("non casé" in w.lower() for w in warnings14), f"personne ne doit être perdu : {warnings14}"
total_steps14 = sum(len(d["steps"]) for d in exported14["days"])
assert total_steps14 == 5, f"5 clients attendus, trouvé {total_steps14}"
solange_days = [d["day_index"] for d in exported14["days"] if any(s["client_name"] == "Solange" for s in d["steps"])]
assert solange_days == [2], f"Solange (seule option = mercredi) doit être sur le jour dernier recours (2) : {solange_days}"
autres_sur_mercredi = any(
    s["client_name"] != "Solange" for d in exported14["days"] if d["day_index"] == 2 for s in d["steps"]
)
assert not autres_sur_mercredi, "les 4 autres (flexibles lundi/mardi) ne doivent pas basculer sur le mercredi"
print("OK -- Solange (seule option) placée sur le jour dernier recours, les 4 autres restent sur lundi/mardi.\n")

print("=== 15. calculer_tournee : plafond_hebdo seul (sans l'appliquer) -> avertissement, rien de bloqué ===")
raw_plafond = [
    {"_row": 10 + i, "Nom et prénom": f"Cliente{i}", "Numéro de téléphone": f"060{i}000000",
     "Lieu du rendez-vous": addr, "Nombre et type d'animaux à voir": "1 cheval",
     "Dates possibles sur la période": "02/11",
     "Avez-vous une contrainte d'horaire ferme, ou juste une préférence ?": "aucune",
     "Remarques complémentaires": ""}
    for i, addr in enumerate(["Bodilis", "Saint-Thégonnec", "Landerneau", "Lannion"])
]
exported15, warnings15 = calculer_tournee(
    raw_plafond, date(2026, 11, 2), 7, "Penfrat, Camaret-sur-Mer",
    plafond=12, format_dispo="dates_precises", plafond_hebdo=3, dist_fn_factory=_fake_dist_fn_factory,
)
total_steps15 = sum(len(d["steps"]) for d in exported15["days"])
assert total_steps15 == 4, f"sans contrainte appliquée, les 4 doivent rester casées : {total_steps15}"
assert any("plafond hebdomadaire" in w.lower() and "4" in w for w in warnings15), \
    f"avertissement attendu mentionnant le dépassement (4 > 3) : {warnings15}"
print(f"OK -- {total_steps15} clientes casées (rien de bloqué), avertissement affiché : {warnings15[0]}\n")

print("=== 16. calculer_tournee : plafond_hebdo appliqué, sans flexibilité -> dégradation propre (pas de plantage) ===")
exported16, warnings16 = calculer_tournee(
    raw_plafond, date(2026, 11, 2), 7, "Penfrat, Camaret-sur-Mer",
    plafond=12, format_dispo="dates_precises", plafond_hebdo=3, appliquer_plafond_hebdo=True,
    dist_fn_factory=_fake_dist_fn_factory,
)
total_steps16 = sum(len(d["steps"]) for d in exported16["days"])
assert total_steps16 == 3, f"plafond appliqué, aucune flexibilité (une seule date par cliente) -> 3 casées, 1 sacrifiée : {total_steps16}"
assert any("non casé" in w.lower() for w in warnings16), f"la cliente sacrifiée doit être signalée : {warnings16}"
assert not any("anomalie" in w.lower() for w in warnings16), f"le plafond doit être respecté, pas d'anomalie attendue : {warnings16}"
print(f"OK -- {total_steps16}/4 casées, plafond respecté, cliente restante signalée plutôt que perdue silencieusement.\n")

print("=== 17. calculer_tournee : plafond_hebdo appliqué, AVEC flexibilité -> redistribution automatique vers l'autre semaine ===")
raw_plafond_flex = raw_plafond[:2] + [  # 2 clientes fixées sur le 02/11 (semaine 1), sous le plafond à elles seules
    {"_row": 20 + i, "Nom et prénom": f"Flex{i}", "Numéro de téléphone": f"061{i}000000",
     "Lieu du rendez-vous": addr, "Nombre et type d'animaux à voir": "1 cheval",
     "Dates possibles sur la période": "02/11, 09/11",  # les deux lundis -- un par semaine
     "Avez-vous une contrainte d'horaire ferme, ou juste une préférence ?": "aucune",
     "Remarques complémentaires": ""}
    for i, addr in enumerate(["Plouaret", "Bodilis", "Lannion"])
]
exported17, warnings17 = calculer_tournee(
    raw_plafond_flex, date(2026, 11, 2), 14, "Penfrat, Camaret-sur-Mer",
    plafond=12, format_dispo="dates_precises", plafond_hebdo=3, appliquer_plafond_hebdo=True,
    dist_fn_factory=_fake_dist_fn_factory,
)
total_steps17 = sum(len(d["steps"]) for d in exported17["days"])
assert total_steps17 == 5, f"toutes casables grâce à la flexibilité des Flex* -- aucune perte attendue : {total_steps17}"
assert not any("non casé" in w.lower() or "anomalie" in w.lower() for w in warnings17), \
    f"aucun avertissement attendu, la redistribution doit suffire : {warnings17}"
semaine1 = sum(len(d["steps"]) for d in exported17["days"] if d["day_index"] <= 6)
semaine2 = sum(len(d["steps"]) for d in exported17["days"] if d["day_index"] > 6)
assert semaine1 <= 3 and semaine2 <= 3, f"chaque semaine doit respecter le plafond de 3 : semaine1={semaine1}, semaine2={semaine2}"
print(f"OK -- {total_steps17}/5 casées, réparties {semaine1}/{semaine2} entre les deux semaines, plafond respecté partout.\n")

print("=== TOURNEE_SERVICE (chemin API) VALIDÉ DE BOUT EN BOUT (hors appel réseau réel) ===")
