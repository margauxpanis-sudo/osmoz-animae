"""
API HTTP du moteur de tournée -- ce qui manquait pour que Ludivine soit
vraiment autonome : jusqu'ici, calculer une tournée demandait un Terminal,
Python installé, et de taper des commandes (run_tournee.py, puis
recalculer_nuitees.py pour une nuitée). Cette API expose la même logique
(tournee_service.py, partagée avec les scripts CLI pour ne jamais diverger)
via deux routes que l'interface de relecture (revue_tournee.html) appelle
avec un simple bouton.

Hébergement : Render (voir README.md pour le déploiement pas à pas). Aucune
donnée n'est stockée ici -- chaque requête est calculée puis oubliée
(pas de base de données, pas de fichier écrit sur le serveur autre que le
cache de géocodage d'ors_client.py, propre à cette instance).

Protection : un jeton partagé simple (API_TOKEN, variable d'environnement
côté serveur, jamais commité dans le code) -- pas une authentification
forte, juste de quoi éviter qu'un inconnu qui tomberait sur l'URL ne
déclenche des calculs et ne consomme le quota gratuit OpenRouteService.
Proportionné à l'usage : un pilote à une seule utilisatrice, sur une page
d'interface privée, pas un service public.

Sert aussi l'interface elle-même (route "/", voir INTERFACE_PATH plus bas)
-- ajouté le 26 sept. 2026 après découverte qu'une page publiée via l'outil
Artefact de Claude a sa propre politique de sécurité (CSP) qui bloque tout
appel réseau sortant vers un serveur externe comme celui-ci, quels que
soient les réglages CORS de ce côté-ci : "Calculer la tournée" ne pouvait
donc jamais fonctionner depuis le lien claude.ai/artifact/... (le blocage
vient du navigateur/de la page Claude, pas de ce serveur). En servant
revue_tournee.html directement depuis ce même service, la page et l'API
sont sur la même origine -- plus aucune restriction cross-origin possible,
et le lien à utiliser devient l'adresse Render elle-même plutôt que le lien
d'artefact Claude (qui reste consultable mais n'est plus le lien à utiliser
pour un vrai calcul).

*Correctifs du même jour, dans l'ordre* :
1. Premier essai avec le fichier lu depuis ../interface/ (en dehors de
   engine/) -> Internal Server Error en production.
2. Deuxième essai : servi depuis engine/static/revue_tournee.html (dans
   engine/, pour ne dépendre d'aucune remontée de dossier) -> toujours
   Internal Server Error.
3. Cause réelle, trouvée en lisant les logs Render avec Margaux : le dépôt
   GitHub réel n'a JAMAIS eu de structure engine/ / interface/ / bridge/
   comme sur le Mac -- tous les fichiers (app.py, form_import.py,
   revue_tournee.html, les .gs...) sont à la RACINE du dépôt, à plat,
   malgré render.yaml qui déclare rootDir: engine (jamais vraiment
   appliqué -- Render tourne en fait à la racine, comme le confirment les
   chemins d'erreur observés : /opt/render/project/src/..., sans "engine"
   dedans). Corrigé une troisième fois : le fichier est maintenant attendu
   directement à côté de app.py, sans aucun sous-dossier -- ce qui
   correspond enfin à ce qui existe vraiment sur GitHub. À charge pour
   Margaux de remplacer le revue_tournee.html déjà présent à la racine du
   dépôt (fichier existant, à écraser par un nouvel upload du même nom) --
   plus besoin de créer le moindre dossier.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from tournee_service import TourneeError, calculer_tournee, recalculer_apres_nuitees

app = FastAPI(title="Osmoz Animae — moteur de tournée")

# Chemin vers l'interface -- à CÔTÉ de app.py, sans sous-dossier : voir la
# note "Correctifs du même jour" ci-dessus (le dépôt GitHub réel est plat,
# pas organisé en engine/ / interface/ / bridge/ comme sur le Mac).
INTERFACE_PATH = Path(__file__).resolve().parent / "revue_tournee.html"

# Ouvert à toute origine : pas de cookie/session côté serveur (le jeton
# passe par un en-tête Authorization explicite, jamais par un cookie), donc
# aucun risque à ce que n'importe quelle page puisse appeler l'API -- seul
# le jeton décide de l'accès.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _check_token(authorization: str | None) -> None:
    expected = os.environ.get("API_TOKEN")
    if not expected:
        # Pas de jeton configuré côté serveur -> on n'ouvre jamais l'accès
        # par erreur de configuration (on échoue fermé, jamais ouvert).
        raise HTTPException(status_code=500, detail="API_TOKEN non configuré côté serveur (voir Render > Environment).")
    if not authorization or authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="Jeton invalide ou manquant (en-tête Authorization).")


class CalculerRequest(BaseModel):
    export_json: list[dict]
    debut: str  # AAAA-MM-JJ
    jours: int = Field(gt=0, le=31)
    depot: str
    plafond: int = 12


class RecalculerRequest(BaseModel):
    export_json: list[dict]
    decisions: dict
    debut: str
    jours: int = Field(gt=0, le=31)
    depot: str


def _parse_debut(debut: str) -> date:
    try:
        return date.fromisoformat(debut)
    except ValueError:
        raise HTTPException(status_code=400, detail="Date de début invalide (attendu AAAA-MM-JJ).")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def interface():
    # Sert le fichier tel quel -- aucune donnée injectée côté serveur, c'est
    # toujours le navigateur qui charge l'export du formulaire et appelle
    # /calculer, exactement comme avant. Seule différence : la page est
    # maintenant sur la même origine que l'API (voir docstring en tête de
    # fichier), donc plus de blocage CSP/cross-origin possible.
    return FileResponse(INTERFACE_PATH, media_type="text/html")


@app.post("/calculer")
def calculer(body: CalculerRequest, authorization: str | None = Header(default=None)):
    _check_token(authorization)
    start_date = _parse_debut(body.debut)
    try:
        exported, warnings = calculer_tournee(body.export_json, start_date, body.jours, body.depot, body.plafond)
    except TourneeError as e:
        raise HTTPException(status_code=422, detail=str(e))
    exported["warnings"] = warnings
    return exported


@app.post("/recalculer-nuitees")
def recalculer(body: RecalculerRequest, authorization: str | None = Header(default=None)):
    _check_token(authorization)
    start_date = _parse_debut(body.debut)
    try:
        exported, warnings = recalculer_apres_nuitees(body.export_json, body.decisions, start_date, body.jours, body.depot)
    except TourneeError as e:
        raise HTTPException(status_code=422, detail=str(e))
    exported["warnings"] = warnings
    return exported
