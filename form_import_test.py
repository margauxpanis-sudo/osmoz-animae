"""
Test de form_import.py sur des formulations réellement rencontrées dans les
tournées Osmoz Animae (cf. tournee-19-oct-2026.md : "pas avant 16h30",
"impératif mardi après-midi", la tournée du 19 oct. qui contient DEUX
lundis dans la même période...).
"""

from __future__ import annotations


from datetime import date, timedelta

from form_import import import_responses, map_days, parse_animal_count, parse_window
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
    },
    {
        "_row": 3, "Nom et prénom": "Julien Le Goff",
        "Numéro de téléphone": "0611111111",
        "Lieu du rendez-vous": "Landerneau",
        "Nombre et type d'animaux à voir": "des chevaux",  # volontairement ambigu
        "Jours possibles sur la période": "Lundi, Mercredi",
        "Avez-vous une contrainte d'horaire ferme, ou juste une préférence ?": "aucune",
        "Remarques complémentaires": "",
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

print("\nOK — tous les cas testés se comportent comme attendu.")
