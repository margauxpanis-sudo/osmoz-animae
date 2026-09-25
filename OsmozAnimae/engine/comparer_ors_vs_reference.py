"""
Compare les temps de trajet calcules par OpenRouteService (via ors_client.py)
aux distances deja verifiees a la main (Mappy / l-itineraire.com), reprises
de weekly_test.py. Sert a valider que l'integration ORS est correcte avant de
lui faire confiance pour de vrai sur une tournee.

Usage :
  cd ~/Documents/OsmozAnimae/engine
  python3 comparer_ors_vs_reference.py
"""
import ors_client as ors

# Adresses (niveau commune -- suffisant pour ce controle de coherence)
points = {
    "depot": "Penfrat, Camaret-sur-Mer, France",
    "bodilis": "Bodilis, France",
    "saint_thegonnec": "Saint-Thegonnec, France",
    "landerneau": "Landerneau, France",
    "lannion": "Lannion, France",
    "plouaret": "Plouaret, France",
}

# Reference verifiee a la main (minutes), depuis weekly_test.py
reference = {
    ("depot", "bodilis"): 80,
    ("depot", "saint_thegonnec"): 83,
    ("depot", "landerneau"): 65,
    ("depot", "lannion"): 133,
    ("depot", "plouaret"): 120,
    ("bodilis", "saint_thegonnec"): 16,
    ("bodilis", "landerneau"): 17,
    ("bodilis", "lannion"): 62,
    ("bodilis", "plouaret"): 47,
    ("saint_thegonnec", "landerneau"): 27,
    ("saint_thegonnec", "lannion"): 55,
    ("saint_thegonnec", "plouaret"): 39,
    ("landerneau", "lannion"): 73,
    ("landerneau", "plouaret"): 58,
    ("lannion", "plouaret"): 24,
}

print("Appel a l'API OpenRouteService (geocodage + matrice)...")
dist_fn = ors.make_dist_fn(points)
print("OK, reponse recue.\n")

print(f"{'Trajet':45s} {'Reference':>10s} {'ORS':>8s} {'Ecart':>8s}")
print("-" * 75)
max_ecart = 0
for (a, b), ref_min in reference.items():
    ors_min = dist_fn(a, b)
    ecart = ors_min - ref_min
    max_ecart = max(max_ecart, abs(ecart))
    label = f"{a} <-> {b}"
    print(f"{label:45s} {ref_min:>8d}min {ors_min:>6d}min {ecart:>+7d}min")

print("-" * 75)
print(f"\nEcart maximum observe : {max_ecart} min")
if max_ecart <= 10:
    print("OK -- coherent avec les distances verifiees a la main (ecart normal : itineraires/trafic).")
else:
    print("ATTENTION -- ecart important sur au moins un trajet, a verifier avant utilisation reelle.")
