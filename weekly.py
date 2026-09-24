"""
Moteur "semaine" — affectation automatique du jour + optimisation du rythme.

Complète solver.py (qui optimise l'ordre à l'intérieur d'un jour déjà fixé)
avec la capacité de décider LUI-MÊME sur quel jour caser chaque client,
parmi ses jours possibles (Stop.allowed_days, plusieurs éléments).

Technique OR-Tools : un "véhicule" par jour ; chaque client avec plusieurs
jours possibles est représenté par une copie de nœud par jour possible
(même lieu, même service), et une contrainte de disjonction force à en
visiter exactement une (les autres copies restent fictives).

NUITÉES : décision de Margaux (24 sept. 2026) — le moteur ne les décide pas
lui-même. Chaque jour repart du dépôt et y retourne par défaut ; une nuitée
sur place devient une option manuelle posée par Ludivine dans l'interface
de relecture (à ce moment-là, relancer solve_multi_day avec PREVIOUS_DAY_END
pour les jours suivants — solver.py gère déjà ce cas, rien à ajouter ici).

ÉQUILIBRAGE : solve_week() seul respecte un plafond dur d'heures/jour mais
ne cherche pas à étaler activement la charge. solve_week_balanced() ajoute
ça — voir sa docstring pour la méthode retenue (et celle essayée puis
abandonnée après vérification empirique qu'elle ne fonctionnait pas : ni le
coefficient de coût linéaire renforcé, ni le coût quadratique au-delà d'un
seuil, n'ont eu le moindre effet mesuré sur cette version d'OR-Tools).
"""

from __future__ import annotations


from typing import Optional

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from schema import DayConfig, DayResult, RouteStep, Stop, StopWindow, WeekResult

DEPOT_ID = "depot"


def fmt(m: int) -> str:
    return f"{int(m // 60):02d}h{int(m % 60):02d}"


def solve_week(
    days: list[DayConfig],
    clients: list[Stop],
    dist_fn,
    depot_label: str = "Camaret (dépôt)",
    time_limit_s: int = 15,
    span_cost_coef: int = 100,
    verbose: bool = True,
) -> WeekResult:
    """Affecte chaque client à l'un de ses jours possibles, calcule l'ordre
    et les horaires — plafond dur par jour, mais sans étalement actif (voir
    solve_week_balanced pour ça). dist_fn(a_id, b_id) reçoit DEPOT_ID pour
    le dépôt et les Stop.id pour les clients."""
    n_days = len(days)
    day_by_index = {d.day_index: d for d in days}

    for c in clients:
        if not c.allowed_days:
            raise ValueError(f"Client '{c.label}' : allowed_days vide, aucun jour possible.")

    # Construction des nœuds : 0 = dépôt (partagé par tous les véhicules/jours) ;
    # puis une copie par (client, jour possible).
    node_labels: list[str] = [depot_label]
    node_service: list[int] = [0]
    node_window: list[Optional[StopWindow]] = [None]
    node_client: list[Optional[str]] = [None]
    node_day: list[Optional[int]] = [None]
    copies_by_client: dict[str, list[int]] = {}

    for c in clients:
        copies_by_client[c.id] = []
        for d in c.allowed_days:
            idx = len(node_labels)
            node_labels.append(c.label)
            node_service.append(c.service_minutes)
            node_window.append(c.window)
            node_client.append(c.id)
            node_day.append(d)
            copies_by_client[c.id].append(idx)

    num_nodes = len(node_labels)
    manager = pywrapcp.RoutingIndexManager(num_nodes, n_days, 0)  # dépôt = nœud 0, partagé par tous les jours
    routing = pywrapcp.RoutingModel(manager)

    def time_callback(from_index, to_index):
        f = manager.IndexToNode(from_index)
        t = manager.IndexToNode(to_index)
        a = DEPOT_ID if f == 0 else node_client[f]
        b = DEPOT_ID if t == 0 else node_client[t]
        travel = 0 if a == b else dist_fn(a, b)
        return travel + node_service[f]

    cb = routing.RegisterTransitCallback(time_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(cb)

    routing.AddDimension(cb, 600, 24 * 60, False, "Time")
    time_dim = routing.GetDimensionOrDie("Time")
    for v in range(n_days):
        time_dim.SetSpanCostCoefficientForVehicle(span_cost_coef, v)

    # Chaque véhicule = un jour -> ses propres horaires de dépôt, et un plafond
    # dur d'heures cumulées si défini (le "rythme").
    for v, day in enumerate(days):
        start_idx = routing.Start(v)
        end_idx = routing.End(v)
        time_dim.CumulVar(start_idx).SetRange(day.day_start_min, day.day_end_min)
        if day.max_span_min is not None:
            routing.solver().Add(
                time_dim.CumulVar(end_idx) - time_dim.CumulVar(start_idx) <= day.max_span_min
            )

    # Chaque copie de nœud n'est autorisée que sur le véhicule (jour) qu'elle représente.
    # (SetAllowedVehiclesForIndex plante avec cette version d'OR-Tools (9.15) —
    # binding cassé côté absl::Span. Contournement fiable : contraindre
    # directement la variable "véhicule" du nœud via VehicleVar(...).SetValues().)
    for idx in range(1, num_nodes):
        solver_index = manager.NodeToIndex(idx)
        # -1 = "non visité" (convention OR-Tools pour un nœud optionnel non
        # retenu par la disjonction) : il faut l'autoriser en plus du jour
        # réel, sinon les copies non choisies n'ont aucune valeur possible
        # et le problème entier devient infaisable.
        routing.VehicleVar(solver_index).SetValues([node_day[idx], -1])
        day = day_by_index[node_day[idx]]
        w = node_window[idx]
        lo, hi = w.resolve(day.day_start_min, day.day_end_min) if w else (day.day_start_min, day.day_end_min)
        time_dim.CumulVar(solver_index).SetRange(lo, hi)

    # Une seule copie visitée par client (disjonction, pénalité très forte pour
    # ne jamais laisser un client sans jour assigné en pratique).
    BIG_PENALTY = 10_000_000
    for client_id, node_indices in copies_by_client.items():
        solver_indices = [manager.NodeToIndex(i) for i in node_indices]
        # max_cardinality=1 : au plus une des copies (jours possibles) est visitée.
        routing.AddDisjunction(solver_indices, BIG_PENALTY, 1)

    for v in range(n_days):
        routing.AddVariableMinimizedByFinalizer(time_dim.CumulVar(routing.End(v)))

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    params.time_limit.FromSeconds(time_limit_s)

    solution = routing.SolveWithParameters(params)
    if not solution:
        if verbose:
            print("Aucune solution trouvée.")
        return WeekResult(day_results={}, missing_client_ids=[c.id for c in clients])

    day_results: dict[int, DayResult] = {}
    for v, day in enumerate(days):
        index = routing.Start(v)
        start_cumul = solution.Value(time_dim.CumulVar(index))
        steps: list[RouteStep] = []
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            arrival = solution.Value(time_dim.CumulVar(index))
            if node != 0:
                steps.append(RouteStep(node_client[node], node_labels[node], arrival, node_service[node]))
            index = solution.Value(routing.NextVar(index))
        end_cumul = solution.Value(time_dim.CumulVar(index))
        if steps:
            finish = steps[-1].departure_min + dist_fn(steps[-1].stop_id, DEPOT_ID)
        else:
            finish = end_cumul
        day_results[day.day_index] = DayResult(
            day_index=day.day_index, label=day.label, steps=steps,
            finish_min=finish, feasible=True, span_min=end_cumul - start_cumul,
        )

    visited_clients = {step.stop_id for r in day_results.values() for step in r.steps}
    missing_ids = [c.id for c in clients if c.id not in visited_clients]

    if verbose:
        print("\n=== Affectation trouvée (jour choisi par le moteur) ===")
        for day in days:
            r = day_results[day.day_index]
            print(f"\n--- {r.label} (plafond {fmt(day.max_span_min) if day.max_span_min else 'aucun'}, "
                  f"étalement réel {fmt(r.span_min)}) ---")
            if not r.steps:
                print("  (rien ce jour-là)")
                continue
            for step in r.steps:
                print(f"  {step.label:30s} arrivée {fmt(step.arrival_min)} -> {fmt(step.departure_min)}  "
                      f"(durée {step.service_minutes} min)")
            print(f"  -> retour dépôt estimé : {fmt(r.finish_min)}")

        missing_labels = [c.label for c in clients if c.id in missing_ids]
        if missing_labels:
            print(f"\n⚠ Clients NON casés par le moteur (à vérifier à la main) : {missing_labels}")
        else:
            print("\nTous les clients ont été casés sur un de leurs jours possibles.")

    return WeekResult(day_results=day_results, missing_client_ids=missing_ids)


def solve_week_balanced(
    days: list[DayConfig],
    clients: list[Stop],
    dist_fn,
    depot_label: str = "Camaret (dépôt)",
    search_time_limit_s: int = 5,
    final_time_limit_s: int = 20,
    resolution_min: int = 15,
    span_cost_coef: int = 100,
) -> WeekResult:
    """Étalement actif de la charge (décision Margaux, 24 sept. 2026) : plutôt
    que de faire confiance à un coût "mou" dont OR-Tools s'est révélé ne PAS
    tenir compte en pratique dans cette version — coefficient linéaire
    renforcé et coût quadratique au-delà d'un seuil essayés, AUCUN effet
    mesuré même à des valeurs extrêmes, vérifié sur un cas isolé avant
    d'abandonner la piste — on réutilise le seul mécanisme dont on a vérifié
    qu'il fonctionne vraiment : le plafond dur par jour. On cherche par
    dichotomie le plafond le plus bas qui reste faisable pour tous les
    clients : par définition, c'est répartir le plus possible sans dépasser
    ce qui est nécessaire."""
    hard_caps = [d.max_span_min for d in days if d.max_span_min is not None]
    if not hard_caps:
        raise ValueError("Au moins un jour doit avoir un max_span_min défini pour chercher un plafond équilibré.")
    ceiling = min(hard_caps)

    def try_cap(cap: int) -> WeekResult:
        trial_days = [DayConfig(d.day_index, d.label, d.day_start_min, d.day_end_min, max_span_min=cap) for d in days]
        return solve_week(trial_days, clients, dist_fn, depot_label, search_time_limit_s, span_cost_coef, verbose=False)

    # Le plafond ne peut de toute façon jamais descendre sous le service+trajet
    # du client le plus lourd tout seul : borne basse raisonnable pour ne pas
    # perdre de temps de recherche sous ce seuil.
    lo = max(c.service_minutes for c in clients)
    hi = ceiling
    if not try_cap(hi).feasible:
        raise RuntimeError(
            f"Même le plafond le plus large fourni ({fmt(hi)}) ne suffit pas à caser tous les clients — "
            "vérifier les jours possibles ou le nombre de jours disponibles."
        )

    best_cap = hi
    while hi - lo > resolution_min:
        mid = (lo + hi) // 2
        if try_cap(mid).feasible:
            best_cap = mid
            hi = mid
        else:
            lo = mid + 1

    print(f"Plafond minimal trouvé pour tout caser : {fmt(best_cap)} (au lieu du plafond fourni {fmt(ceiling)})")
    final_days = [DayConfig(d.day_index, d.label, d.day_start_min, d.day_end_min, max_span_min=best_cap) for d in days]
    return solve_week(final_days, clients, dist_fn, depot_label, final_time_limit_s, span_cost_coef, verbose=True)
