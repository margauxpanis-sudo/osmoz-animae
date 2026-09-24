"""
Point d'entrée en ligne de commande (outil de secours / débogage) : export
brut du formulaire (JSON du pont Apps Script) -> tournée complète calculée ->
JSON exploitable par l'interface de relecture (revue_tournee.html).

Depuis que l'API (app.py, hébergée sur Render) existe, ce script n'est plus
le chemin normal d'usage pour Ludivine -- elle passe par le bouton
"Calculer" de l'interface, qui appelle la même logique (tournee_service.py)
sans Terminal ni installation Python. Ce script reste utile comme filet de
secours (si l'hébergement est indisponible) et pour du débogage en local.

Usage :
  cd ~/Documents/OsmozAnimae/engine
  python3 run_tournee.py export_tournee_2026-10-19.json \
      --debut 2026-10-19 --jours 8 \
      --depot "Penfrat, Camaret-sur-Mer" \
      --plafond 12 \
      --sortie tournee_calculee.json

Le fichier d'entrée est celui produit par le menu "Osmoz Animae > Exporter en
JSON" du Google Form (voir bridge/Code.gs).

IMPORTANT : les avertissements de form_import (adresse ambiguë, jour non
reconnu, nombre d'animaux incertain...) sont affichés en premier et bien en
évidence -- à lire et vérifier à la main AVANT de faire confiance au résultat
calculé. Ce script ne devine jamais silencieusement ; il signale.
"""

from __future__ import annotations


import argparse
import json
import sys
from datetime import date

# Ré-exportés pour compatibilité : d'anciens tests et recalculer_nuitees.py
# importent encore build_days/export_for_interface depuis ce module. La
# logique elle-même vit maintenant dans tournee_service.py (voir sa
# docstring : partagée avec l'API pour ne jamais diverger).
from tournee_service import (  # noqa: F401
    TourneeError,
    build_days,
    calculer_tournee,
    export_for_interface,
)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("export_json", help="Export brut du formulaire (menu Apps Script > Exporter en JSON)")
    p.add_argument("--debut", required=True, help="Date du premier jour de la tournée, AAAA-MM-JJ")
    p.add_argument("--jours", type=int, required=True, help="Nombre de jours de la tournée")
    p.add_argument("--depot", required=True, help="Adresse précise du point de départ/retour (modifiable à chaque tournée)")
    p.add_argument("--plafond", type=int, default=12, help="Plafond d'heures/jour (le \"rythme\"), défaut 12")
    p.add_argument("--sortie", default="tournee_calculee.json", help="Fichier JSON de sortie pour l'interface")
    args = p.parse_args()

    start_date = date.fromisoformat(args.debut)

    with open(args.export_json, encoding="utf-8") as f:
        raw_responses = json.load(f)

    print(f"=== Import de {len(raw_responses)} réponse(s) du formulaire ===\n")
    print("=== Calcul des temps de trajet réels (OpenRouteService) et de l'organisation optimale ===\n")
    try:
        exported, warnings = calculer_tournee(raw_responses, start_date, args.jours, args.depot, args.plafond)
    except TourneeError as e:
        print(f"❌ {e}")
        sys.exit(1)

    if warnings:
        print(f"⚠ {len(warnings)} point(s) à vérifier À LA MAIN avant de faire confiance au calcul :\n")
        for w in warnings:
            print(f"  - {w}")
        print()
    else:
        print("Aucune ambiguïté détectée sur l'import.\n")

    with open(args.sortie, "w", encoding="utf-8") as f:
        json.dump(exported, f, ensure_ascii=False, indent=2)
    print(f"✅ Résultat écrit dans {args.sortie} -- à charger dans l'interface de relecture.")


if __name__ == "__main__":
    main()
