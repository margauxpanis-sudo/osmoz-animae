"""
Test de form_import.py sur des formulations réellement rencontrées dans les
tournées Osmoz Animae (cf. tournee-19-oct-2026.md : "pas avant 16h30",
"impératif mardi après-midi", la tournée du 19 oct. qui contient DEUX
lundis dans la même période...).
"""

from __future__ import annotations


from datetime import date, timedelta

from form_import import _parse_horodateur, import_responses, map_dates, map_days, parse_abonnement, parse_animal_count, parse_window
from schema import WindowType

# ---------------------------------------------------------------------------
# 1. Cas simples et fiables -> doivent être reconnus avec confidence=True
# ---------------------------------------------------------------------------
cases_animaux = [
    ("2 chevaux, 1 chien", 3, True),
    ("4 chevaux", 4, True),
    ("un cheval", 1, True),
    ("un cheval et un chien", 2, True),
    ("des chevaux", 0, False),   # pas de quantité -> ne doit PAS deviner
    ("", 0, False),
]
print("=== parse_animal_count ===")
for text, expected_count, expected_confident in cases_animaux:
    r = parse_animal_count(text)
    status = "OK" if (r.count, r.confident) == (expected_count, expected_confident) else "FAIL"
    print(f"  [{status}] '{text}' -> count={r.count}, confident={r.confident} (attendu {expected_count}/{expected_confident})")
    assert (r.count, r.confident) == (expected_count, expected_confident), text

cases_fenetre = [
    ("aucune contrainte", WindowType.NONE, True),
    ("pas avant 16h", WindowType.FLOOR, True),
    ("pas avant 16h30", WindowType.FLOOR, True),
    ("seulement l'après-midi", WindowType.FLOOR, True),
    ("seulement le matin", WindowType.HARD, True),
    ("entre 14h et 17h30", WindowType.HARD, True),
    ("flexible mais pas trop tôt idéalement", WindowType.NONE, False),  # motif inconnu -> ne doit pas deviner
]
print("\n=== parse_window ===")
for text, expected_type, expected_confident in cases_fenetre:
    w, confident = parse_window(text)
    status = "OK" if (w.type, confident) == (expected_type, expected_confident) else "FAIL"
    print(f"  [{status}] '{text}' -> {w.type.value}, confident={confident} (attendu {expected_type.value}/{expected_confident})")
    assert (w.type, confident) == (expected_type, expected_confident), text

cases_abonnement = [
    ("Oui", True, True),
    ("oui", True, True),
    ("Non", False, True),
    ("", False, True),           # question pas posée / laissée vide -> non abonné, sans ambiguïté
    ("peut-être", False, False),  # motif inconnu -> ne doit PAS accorder la priorité par erreur
]
print("\n=== parse_abonnement ===")
for text, expected_bool, expected_confident in cases_abonnement:
    b, confident = parse_abonnement(text)
    status = "OK" if (b, confident) == (expected_bool, expected_confident) else "FAIL"
    print(f"  [{status}] '{text}' -> {b}, confident={confident} (attendu {expected_bool}/{expected_confident})")
    assert (b, confident) == (expected_bool, expected_confident), text

# ---------------------------------------------------------------------------
# 2. Cas réel du 19 oct. 2026 : tournée de 8 jours, DEUX lundis (19 et 26)
# ---------------------------------------------------------------------------
tournee_dates = [date(2026, 10, 19) + timedelta(days=i) for i in range(8)]  # lundi 19 -> lundi 26
print("\n=== map_days (tournée à 2 lundis, cas réel) ===")
indices, warnings = map_days("Lundi", tournee_dates)
print(f"  'Lundi' -> indices {indices}")
for w in warnings:
    print(f"    ⚠ {w}")
assert indices == [0, 7], indices  # les deux lundis (19 et 26) doivent être retenus, pas un choisi au hasard
assert warnings, "doit signaler l'ambiguïté"

indices2, warnings2 = map_days("Mercredi, Jeudi", tournee_dates)
print(f"  'Mercredi, Jeudi' -> indices {indices2}")
assert indices2 == [2, 3] and not warnings2

# ---------------------------------------------------------------------------
# 2bis. map_dates (mode consultations, 26 sept. 2026) : même période à 2
# lundis, mais AUCUNE ambiguïté attendue puisque les cases cochées sont des
# dates précises, pas des noms de jour -- exactement le cas que map_days ne
# peut pas gérer proprement à l'échelle d'un mois.
# ---------------------------------------------------------------------------
print("\n=== map_dates (même période à 2 lundis, mais dates précises -- aucune ambiguïté) ===")
indices3, warnings3 = map_dates("Lundi 19/10", tournee_dates)
print(f"  'Lundi 19/10' -> indices {indices3}")
assert indices3 == [0] and not warnings3, "doit retenir SEULEMENT le 19/10, jamais le 26/10"

indices4, warnings4 = map_dates("19/10, 26/10", tournee_dates)
print(f"  '19/10, 26/10' -> indices {indices4}")
assert indices4 == [0, 7] and not warnings4, "les deux dates explicitement cochées doivent être retenues, sans avertissement"

indices5, warnings5 = map_dates("01/01", tournee_dates)
print(f"  '01/01' (hors période) -> indices {indices5}")
for w in warnings5:
    print(f"    ⚠ {w}")
assert indices5 == [] and warnings5, "une date hors période doit être signalée, pas ignorée silencieusement"

indices6, warnings6 = map_dates("", tournee_dates)
assert indices6 == [] and warnings6, "un champ vide doit être signalé"
print("  OK -- dates précises, hors période et champ vide correctement gérés.")

# ---------------------------------------------------------------------------
# 3. Import complet d'un export brut simulé (format du pont Apps Script)
# ---------------------------------------------------------------------------
raw = [
    {
        "_row": 2, "Nom et prénom": "Camille Herry",
        "Numéro de téléphone": "0600000000",
        "Lieu du rendez-vous": "Saint-Thégonnec",
        "Nombre et type d'animaux à voir": "2 chiens",
        "Jours possibles sur la période": "Mercredi",
        "Avez-vous une contrainte d'horaire ferme, ou juste une préférence ?": "pas avant 15h",
        "Remarques complémentaires": "",
        "Abonnement annuel ?": "Oui",
    },
    {
        "_row": 3, "Nom et prénom": "Julien Le Goff",
        "Numéro de téléphone": "0611111111",
        "Lieu du rendez-vous": "Landerneau",
        "Nombre et type d'animaux à voir": "des chevaux",  # volontairement ambigu
        "Jours possibles sur la période": "Lundi, Mercredi",
        "Avez-vous une contrainte d'horaire ferme, ou juste une préférence ?": "aucune",
        "Remarques complémentaires": "",
        # pas de clé "Abonnement annuel ?" du tout ici -> simule un ancien
        # export de formulaire (question ajoutée après coup) : ne doit pas
        # planter, ni produire un avertissement -- juste "non abonné".
    },
]
five_day_tournee = [date(2026, 11, 2) + timedelta(days=i) for i in range(5)]  # lundi -> vendredi, pas de doublon
print("\n=== import_responses (export simulé) ===")
stops, warns = import_responses(raw, five_day_tournee)
for s in stops:
    print(f"  {s.label:25s} service={s.service_minutes:3d}min  jours={s.allowed_days}  fenêtre={s.window.type.value}")
for w in warns:
    print(f"  ⚠ {w}")

assert stops[0].service_minutes == 90  # 2 chiens x 45
assert stops[0].window.type == WindowType.FLOOR and stops[0].window.start_min == 15 * 60
assert any("animaux non reconnu" in w for w in warns), "doit signaler l'ambiguïté sur 'des chevaux'"
assert stops[1].service_minutes == 45  # valeur prudente (1 animal minimum) faute de mieux, mais SIGNALÉE ci-dessus

# address doit porter l'adresse brute du formulaire (séparée du label affiché),
# c'est ce champ qui sera géocodé par ors_client.py -- jamais le label.
assert stops[0].address == "Saint-Thégonnec", stops[0].address
assert stops[1].address == "Landerneau", stops[1].address

# abonnement_annuel doit être répercuté sur le Stop -- avec valeur par défaut
# (non abonné) et sans avertissement quand la question n'a pas été posée.
assert stops[0].abonnement_annuel is True, stops[0].abonnement_annuel
assert stops[1].abonnement_annuel is False, stops[1].abonnement_annuel
assert not any("Abonnement annuel" in w for w in warns), \
    "l'absence de la question ne doit pas déclencher un avertissement"

# ---------------------------------------------------------------------------
# 4. _parse_horodateur (28 sept. 2026, demande de Margaux : réutiliser le
#    même formulaire d'une tournée à l'autre sans recréer un formulaire
#    identique -> filtrage par colonne "Horodateur")
# ---------------------------------------------------------------------------
cases_horodateur = [
    ("2026-11-05T14:32:10.000Z", date(2026, 11, 5)),  # JSON.stringify d'un objet Date JS (cas normal)
    ("2026-11-05T14:32:10", date(2026, 11, 5)),
    ("05/11/2026 14:32:10", date(2026, 11, 5)),  # filet de sécurité, colonne convertie en texte français
    ("", None),
    ("texte quelconque", None),
]
print("\n=== _parse_horodateur ===")
for raw_val, expected in cases_horodateur:
    got = _parse_horodateur(raw_val)
    status = "OK" if got == expected else "FAIL"
    print(f"  [{status}] '{raw_val}' -> {got} (attendu {expected})")
    assert got == expected, raw_val

# ---------------------------------------------------------------------------
# 4bis. import_responses avec depuis : une réponse antérieure est ignorée,
# une réponse sans Horodateur reconnaissable est gardée par précaution.
# ---------------------------------------------------------------------------
raw_depuis = [
    {
        "_row": 2, "Nom et prénom": "Ancienne Réponse",
        "Horodateur": "2026-10-01T09:00:00.000Z",  # avant le "depuis" -> doit être ignorée
        "Numéro de téléphone": "0600000001", "Lieu du rendez-vous": "Brest",
        "Nombre et type d'animaux à voir": "1 chien",
        "Jours possibles sur la période": "Lundi",
        "Avez-vous une contrainte d'horaire ferme, ou juste une préférence ?": "aucune",
        "Remarques complémentaires": "", "Abonnement annuel ?": "",
    },
    {
        "_row": 3, "Nom et prénom": "Nouvelle Réponse",
        "Horodateur": "2026-11-05T09:00:00.000Z",  # après le "depuis" -> doit être gardée
        "Numéro de téléphone": "0600000002", "Lieu du rendez-vous": "Brest",
        "Nombre et type d'animaux à voir": "1 chien",
        "Jours possibles sur la période": "Mardi",
        "Avez-vous une contrainte d'horaire ferme, ou juste une préférence ?": "aucune",
        "Remarques complémentaires": "", "Abonnement annuel ?": "",
    },
    {
        "_row": 4, "Nom et prénom": "Réponse Sans Horodateur",
        # pas de clé "Horodateur" du tout -> illisible, gardée par précaution
        "Numéro de téléphone": "0600000003", "Lieu du rendez-vous": "Brest",
        "Nombre et type d'animaux à voir": "1 chien",
        "Jours possibles sur la période": "Jeudi",
        "Avez-vous une contrainte d'horaire ferme, ou juste une préférence ?": "aucune",
        "Remarques complémentaires": "", "Abonnement annuel ?": "",
    },
]
print("\n=== import_responses avec depuis ===")
stops_depuis, warns_depuis = import_responses(raw_depuis, five_day_tournee, depuis=date(2026, 11, 1))
noms = sorted(s.client_name for s in stops_depuis)
print(f"  clients retenus : {noms}")
for w in warns_depuis:
    print(f"  ⚠ {w}")
assert noms == ["Nouvelle Réponse", "Réponse Sans Horodateur"], noms
assert any("1 réponse(s) antérieure(s)" in w for w in warns_depuis), "doit signaler le nombre de réponses ignorées"
assert any("Horodateur' illisible" in w for w in warns_depuis), "doit signaler la réponse sans Horodateur reconnaissable"

# Sans depuis (défaut) : comportement historique inchangé, tout le monde est gardé.
stops_sans_depuis, warns_sans_depuis = import_responses(raw_depuis, five_day_tournee)
assert len(stops_sans_depuis) == 3, len(stops_sans_depuis)
assert not any("antérieure" in w or "illisible" in w for w in warns_sans_depuis)
print("  OK -- sans 'depuis', comportement historique inchangé (aucun filtre, aucun avertissement lié).")

print("\nOK — tous les cas testés se comportent comme attendu.")
