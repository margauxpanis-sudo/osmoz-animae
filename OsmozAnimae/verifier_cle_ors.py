"""
Verification rapide de la cle OpenRouteService.
A lancer depuis un Terminal normal (Applications > Utilitaires > Terminal),
PAS depuis une session Claude -- c'est important : les sessions Claude (cloud
et sur cette machine) passent par une politique reseau qui bloque les appels
vers des API externes comme celle-ci. Un Terminal classique n'est pas
concerne par cette politique.

Usage :
  cd ~/Documents/OsmozAnimae
  python3 verifier_cle_ors.py
"""
import json
import urllib.request
import urllib.parse

API_KEY = "eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6ImFiMjc0Y2JhMDViNjQzY2U5NzJmZjM2MTAzYmE1YmEyIiwiaCI6Im11cm11cjY0In0="

params = urllib.parse.urlencode({
    "api_key": API_KEY,
    "text": "Camaret-sur-Mer, France",
    "boundary.country": "FR",
    "size": 1,
})
url = f"https://api.openrouteservice.org/geocode/search?{params}"

try:
    with urllib.request.urlopen(url, timeout=15) as resp:
        data = json.loads(resp.read())
        features = data.get("features", [])
        if features:
            lon, lat = features[0]["geometry"]["coordinates"]
            print(f"OK -- la cle fonctionne. Camaret-sur-Mer localise a lon={lon}, lat={lat}")
        else:
            print("Reponse recue mais aucun resultat de geocodage (la cle est probablement valide quand meme).")
            print(json.dumps(data, indent=2))
except Exception as e:
    print(f"ECHEC : {type(e).__name__}: {e}")
