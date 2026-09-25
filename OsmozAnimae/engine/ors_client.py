"""
Client OpenRouteService — géocodage + matrice de distances/temps de trajet.

Remplace les dictionnaires de distances vérifiées à la main (voir
weekly_test.py, test_engine.py) par des appels réels à l'API OpenRouteService
(https://openrouteservice.org).

Deux fonctions bas niveau :
  - geocode(address)  -> (lon, lat)
  - matrix(coords)    -> {'durations': [[s...]], 'distances': [[m...]]}

Et une fonction haut niveau, directement compatible avec solver.py/weekly.py :
  - make_dist_fn(point_labels) -> dist_fn(a_id, b_id) -> minutes

Un cache disque (.ors_cache.json, à côté de ce fichier) évite de re-
questionner l'API pour des points déjà résolus : le quota gratuit
OpenRouteService est de 2000 requêtes/jour et 40/minute — chaque géocodage
et chaque appel matrix comptent comme une requête. Une tournée déjà
géocodée une fois ne re-consomme plus de quota au relancement du moteur.
"""

from __future__ import annotations


import json
import os
from pathlib import Path

import requests

_ENV_PATH = Path(__file__).parent / ".env"
_CACHE_PATH = Path(__file__).parent / ".ors_cache.json"

GEOCODE_URL = "https://api.openrouteservice.org/geocode/search"
MATRIX_URL = "https://api.openrouteservice.org/v2/matrix/driving-car"


class OrsError(Exception):
    pass


def _load_api_key() -> str:
    if "ORS_API_KEY" in os.environ:
        return os.environ["ORS_API_KEY"]
    if _ENV_PATH.exists():
        for line in _ENV_PATH.read_text().splitlines():
            if line.startswith("ORS_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError(
        "Clé ORS introuvable. Définis la variable d'environnement ORS_API_KEY "
        f"ou crée un fichier {_ENV_PATH} contenant ORS_API_KEY=<ta clé>."
    )


def _load_cache() -> dict:
    if _CACHE_PATH.exists():
        try:
            return json.loads(_CACHE_PATH.read_text())
        except json.JSONDecodeError:
            pass
    return {"geocode": {}, "matrix": {}}


def _save_cache(cache: dict) -> None:
    _CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2))


def geocode(address: str, country_bias: str = "FR") -> tuple[float, float]:
    """Renvoie (lon, lat) pour une adresse texte. Lève OrsError si rien
    trouvé. Résultat mis en cache disque (une adresse ne bouge pas)."""
    cache = _load_cache()
    key = address.strip().lower()
    if key in cache["geocode"]:
        return tuple(cache["geocode"][key])

    try:
        resp = requests.get(
            GEOCODE_URL,
            params={
                "api_key": _load_api_key(),
                "text": address,
                "boundary.country": country_bias,
                "size": 1,
            },
            timeout=10,
        )
    except requests.exceptions.RequestException as e:
        # Panne réseau (timeout, DNS, proxy, ORS injoignable...) -- pas
        # seulement un mauvais code HTTP. Sans ce filet, une coupure réseau
        # remontait en erreur Python brute jusqu'à l'API (page 500 illisible
        # pour Ludivine) au lieu d'un message clair. Trouvé en testant
        # l'API en local (25 sept. 2026).
        raise OrsError(f"Impossible de joindre OpenRouteService pour géocoder '{address}' : {e}") from e
    if resp.status_code != 200:
        raise OrsError(f"Géocodage échoué pour '{address}' : HTTP {resp.status_code} — {resp.text[:200]}")
    data = resp.json()
    features = data.get("features", [])
    if not features:
        raise OrsError(f"Aucun résultat de géocodage pour '{address}'.")
    lon, lat = features[0]["geometry"]["coordinates"]
    cache["geocode"][key] = [lon, lat]
    _save_cache(cache)
    return (lon, lat)


def matrix(coords: list[tuple[float, float]]) -> dict:
    """coords : liste de (lon, lat). Renvoie {'durations': [[s...]], 'distances': [[m...]]}."""
    try:
        resp = requests.post(
            MATRIX_URL,
            json={"locations": [[lon, lat] for lon, lat in coords], "metrics": ["duration", "distance"]},
            headers={"Authorization": _load_api_key(), "Content-Type": "application/json"},
            timeout=20,
        )
    except requests.exceptions.RequestException as e:
        raise OrsError(f"Impossible de joindre OpenRouteService pour calculer les trajets : {e}") from e
    if resp.status_code != 200:
        raise OrsError(f"Appel matrix échoué : HTTP {resp.status_code} — {resp.text[:300]}")
    return resp.json()


def make_dist_fn(point_labels: dict[str, str], country_bias: str = "FR"):
    """Construit une fonction dist_fn(a_id, b_id) -> minutes, compatible avec
    solver.py / weekly.py, à partir d'un dict {id: adresse texte}. Géocode
    chaque adresse et calcule la matrice une fois, met le résultat en cache
    disque pour ne pas re-consommer de quota au prochain lancement sur la
    même tournée."""
    cache = _load_cache()
    ids = list(point_labels.keys())
    cache_key = "|".join(sorted(ids)) + "::" + "|".join(point_labels[i] for i in ids)

    if cache_key in cache["matrix"]:
        durations = cache["matrix"][cache_key]
    else:
        coords = [geocode(point_labels[i], country_bias=country_bias) for i in ids]
        result = matrix(coords)
        durations = result["durations"]  # secondes
        cache["matrix"][cache_key] = durations
        _save_cache(cache)

    id_index = {i: idx for idx, i in enumerate(ids)}

    def dist_fn(a_id: str, b_id: str) -> int:
        if a_id not in id_index or b_id not in id_index:
            raise KeyError(f"Point inconnu pour dist_fn : {a_id} ou {b_id}")
        seconds = durations[id_index[a_id]][id_index[b_id]]
        if seconds is None:
            raise OrsError(f"Pas de trajet routier trouvé entre {a_id} et {b_id}.")
        return round(seconds / 60)

    return dist_fn
