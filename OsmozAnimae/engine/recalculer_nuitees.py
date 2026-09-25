"""
Recalcule les horaires d'une tournée après une nuitée manuelle -- outil de
secours / débogage en ligne de commande.

Depuis que l'API (app.py) existe, ce n'est plus le chemin normal : dans
l'interface, le bouton "Recalculer après nuitée" appelle directement l'API
(même logique, tournee_service.py) sans télécharger/relancer quoi que ce
soit à la main. Ce script reste utile en filet de secours si l'hébergement
est indisponible.

Différence essentielle avec un premier calcul : ce script NE REDÉCIDE JAMAIS
quel client va quel jour -- cette décision reste celle déjà validée par
Ludivine lors du premier calcul. Il recalcule uniquement L'ORDRE et LES
HORAIRES à l'intérieur de chaque jour, en tenant compte du nouveau point de
départ (la nuitée) pour les jours suivants.

Usage :
  cd ~/Documents/OsmozAnimae/engine
  python3 recalculer_nuitees.py export_tournee.json decisions.json \
      --debut 2026-11-02 --jours 3 --depot "Penfrat, Camaret-sur-Mer" \
      --sortie tournee_recalculee.json

"export_tournee.json" est le MÊME fichier d'export brut du formulaire que
celui déjà utilisé pour le premier calcul (nécessaire pour retrouver
adresse, fenêtre horaire, durée de service de chaque client -- ces
informations ne sont pas dans le JSON affiché par l'interface).
"decisions.json" est le fichier produit par le bouton "Télécharger les
décisions" de l'interface (options avancées).

Contrainte : au plus une nuitée par jour (poser une nuitée revient à choisir
où la journée s'arrête -- deux nuitées le même jour n'a pas de sens).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from tournee_service import TourneeError, recalculer_apres_nuitees


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("export_json", help="Export brut du formulaire (le même que pour run_tournee.py)")
    p.add_argument("decisions_json", help="Fichier téléchargé depuis l'interface (\"Télécharger les décisions\")")
    p.add_argument("--debut", required=True, help="Date du premier jour de la tournée, AAAA-MM-JJ")
    p.add_argument("--jours", type=int, required=True, help="Nombre de jours de la tournée")
    p.add_argument("--depot", required=True, help="Adresse précise du point de départ/retour")
    p.add_argument("--sortie", default="tournee_recalculee.json", help="Fichier JSON de sortie pour l'interface")
    args = p.parse_args()

    start_date = date.fromisoformat(args.debut)

    with open(args.export_json, encoding="utf-8") as f:
        raw_responses = json.load(f)
    with open(args.decisions_json, encoding="utf-8") as f:
        decisions = json.load(f)

    print("=== Recalcul de l'ordre et des horaires (jours déjà décidés) ===\n")
    try:
        exported, warnings = recalculer_apres_nuitees(raw_responses, decisions, start_date, args.jours, args.depot)
    except TourneeError as e:
        print(f"❌ {e}")
        sys.exit(1)

    if warnings:
        print(f"⚠ {len(warnings)} point(s) déjà signalé(s) lors du premier calcul (pour mémoire) :")
        for w in warnings:
            print(f"  - {w}")
        print()

    with open(args.sortie, "w", encoding="utf-8") as f:
        json.dump(exported, f, ensure_ascii=False, indent=2)

    print(f"✅ Recalcul terminé, écrit dans {args.sortie} -- à recharger dans l'interface de relecture.\n")
    for d in exported["days"]:
        print(f"  {d['label']} : {len(d['steps'])} client(s), fin {d['finish_min'] // 60:02d}h{d['finish_min'] % 60:02d}")


if __name__ == "__main__":
    main()
