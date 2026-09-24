# Moteur d'optimisation de tournée — Osmoz Animae

Version généralisée du prototype validé sur la tournée réelle du 19 octobre 2026
(gain mesuré : ~20 à 37 min par jour testé, à distances vérifiées), étendue le
24 sept. 2026 avec l'affectation automatique du jour et l'équilibrage actif de
la charge (demande de Margaux).

Contrairement aux scripts de prototypage (`moteur_tournee.py`, `moteur_multi_jours.py`,
dans les tests précédents), ce module ne code plus les arrêts et les matrices de
distance en dur : il prend une liste de jours et d'arrêts en entrée (structure de
données définie dans `schema.py`) et fonctionne pour n'importe quel nombre de
jours/arrêts, sans modification du code à chaque nouvelle tournée.

## Deux moteurs, un seul jeu de structures de données (schema.py)

- **`solver.py`** — le jour est déjà décidé (Stop.allowed_days à un seul élément) :
  calcule l'ordre optimal et les horaires. Gère aussi l'enchaînement de plusieurs
  jours quand une nuitée est posée manuellement (PREVIOUS_DAY_END).
- **`weekly.py`** — le jour n'est pas encore décidé (Stop.allowed_days à plusieurs
  éléments, ex. les jours cochés au formulaire) : le moteur choisit lui-même quel
  client va quel jour, avec un plafond d'heures/jour et, avec `solve_week_balanced`,
  un étalement actif de la charge. Retour au dépôt chaque soir par défaut — les
  nuitées restent une décision manuelle de Ludivine (voir la docstring du fichier).

## Fichiers

- `schema.py` — toutes les structures de données, partagées par les deux moteurs
  (Stop, StopWindow, DayPlan, DayConfig, DayResult, RouteStep, WeekResult).
- `solver.py` + `test_engine.py` (test de non-régression : rejoue mardi 20 / mercredi 21,
  identique au prototype déjà validé — retour 19h03, écart 0 min).
- `weekly.py` + `weekly_test.py` (test sur 5 clients réels, distances déjà vérifiées,
  aucune inventée : compare plafond fixe seul vs étalement actif).
- `validate.py` — garde-fous de bon sens avant de lancer un calcul (cf. incidents
  documentés dedans — pourquoi ce fichier existe).

## Ce qui n'est volontairement PAS géré ici (limite connue, actée dès le prototype)

Le moteur ne connaît que ce qu'on lui donne explicitement en contrainte. Il ne
"sait" pas qu'un placement précis dans la semaine peut avoir une raison
relationnelle (ex. Caroline Picard placée tôt pour une raison humaine, pas
géométrique). Ce genre d'arbitrage reste à la charge de qui relit la
proposition avant validation — d'où la brique "interface de relecture"
prévue dans la feuille de route, jamais un envoi automatique sans passage
humain.
