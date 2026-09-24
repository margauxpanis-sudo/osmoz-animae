"""
Moteur d'optimisation de tournée — Osmoz Animae.

Généralisation du prototype validé (moteur_multi_jours.py) : plus de
matrices ni d'arrêts codés en dur, tout vient des structures définies
dans schema.py. Le moteur lui-même (OR-Tools, TSP à fenêtres horaires,
un jour = un problème résolu, jours enchaînés via le point de départ)
n'a pas changé de logique par rapport au prototype déjà testé sur des
données réelles.
"""

from __future__ import annotations


from typing import Callable, Optional

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from schema import DayPlan, DayResult, RouteStep, Stop, WindowType

# Sentinel utilisé comme start_id d'un DayPlan pour dire "reprendre là où
# la journée précédente s'est terminée" (cas d'une nuitée sur place).
PREVIOUS_DAY_END = "__previous_day_end__"

DistanceFn = Callable[[str, str], int]  # (id_a, id_b) -> minutes ; lève KeyError si inconnu


class MissingDistanceError(Exception):
    def __init__(self, a: str, b: str):
        self.a, self.b = a, b
        super().__init__(
            f"Temps de trajet manquant entre '{a}' et '{b}'. "
            "Le moteur ne devine jamais une distance : il faut la fournir "
            "(recherche manuelle ou API cartographie) avant de relancer."
        )


def fmt(minutes: int) -> str:
    return f"{int(minutes // 60):02d}h{int(minutes % 60):02d}"


def solve_day(
    day: DayPlan,
    day_stops: list[Stop],
    point_labels: dict[str, str],
    dist_fn: DistanceFn,
    time_limit_s: int = 5,
) -> DayResult:
    """Résout une seule journée (TSP à fenêtres horaires).

    day.open_route=True  -> pas de retour, la tournée se termine au dernier
                             arrêt résolu (nuit sur place).
    day.open_route=False -> retour obligatoire à day.end_id.
    """
    if day.start_id == PREVIOUS_DAY_END:
        raise ValueError(
            f"Jour {day.day_index} ({day.label}) : start_id non résolu "
            "(PREVIOUS_DAY_END) — utiliser solve_multi_day pour les tournées "
            "enchaînées sur plusieurs jours."
        )

    real_ids = [day.start_id] + [s.id for s in day_stops]
    if not day.open_route:
        if day.end_id is None:
            raise ValueError(f"Jour {day.day_index} : route fermée mais end_id manquant.")
        if day.end_id not in real_ids:
            real_ids.append(day.end_id)

    n_real = len(real_ids)
    id_by_index = list(real_ids)
    if day.open_route:
        id_by_index = id_by_index + ["__sentinel__"]
    num_nodes = len(id_by_index)

    # matrice de coûts (minutes), construite via dist_fn -> lève une erreur
    # explicite et actionnable si une paire manque (jamais de valeur devinée)
    cost = {}
    try:
        for i in range(n_real):
            for j in range(n_real):
                if i == j:
                    cost[(i, j)] = 0
                else:
                    a, b = id_by_index[i], id_by_index[j]
                    try:
                        cost[(i, j)] = dist_fn(a, b)
                    except KeyError:
                        raise MissingDistanceError(a, b)
        if day.open_route:
            sentinel = n_real
            for i in range(num_nodes):
                cost[(i, sentinel)] = 0
                cost[(sentinel, i)] = 0
    except MissingDistanceError as e:
        return DayResult(day.day_index, day.label, [], 0, feasible=False, error=str(e))

    start_index = 0
    end_index = (n_real if day.open_route else real_ids.index(day.end_id))

    manager = pywrapcp.RoutingIndexManager(num_nodes, 1, [start_index], [end_index])
    routing = pywrapcp.RoutingModel(manager)

    stop_by_id = {s.id: s for s in day_stops}
    service_by_index = {}
    for idx, node_id in enumerate(id_by_index):
        if day.open_route and idx == n_real:
            service_by_index[idx] = 0
        else:
            service_by_index[idx] = stop_by_id[node_id].service_minutes if node_id in stop_by_id else 0

    def time_callback(from_index, to_index):
        f = manager.IndexToNode(from_index)
        t = manager.IndexToNode(to_index)
        return cost[(f, t)] + service_by_index.get(f, 0)

    cb = routing.RegisterTransitCallback(time_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(cb)
    routing.AddDimension(cb, 600, 24 * 60, False, "Time")
    time_dim = routing.GetDimensionOrDie("Time")
    # Pénaliser l'étalement total de la journée, pas seulement le kilométrage —
    # sans ça le solveur peut choisir un ordre qui minimise la distance mais
    # laisse une attente énorme avant un plancher horaire (bug rencontré et
    # corrigé pendant le prototypage, cf. prototype-moteur-optimisation.md).
    time_dim.SetSpanCostCoefficientForVehicle(100, 0)

    for idx, node_id in enumerate(id_by_index):
        if day.open_route and idx == n_real:
            continue  # nœud fictif de fin, pas de fenêtre
        cumul_var = time_dim.CumulVar(manager.NodeToIndex(idx))
        if node_id == day.start_id:
            if day.start_window.type != WindowType.NONE:
                lo, hi = day.start_window.resolve(day.day_start_min, day.day_end_min)
            else:
                lo, hi = day.day_start_min, day.day_end_min
        elif not day.open_route and node_id == day.end_id:
            if day.end_id != day.start_id:
                # Bug OR-Tools (9.15.6755) trouvé le 24 sept. 2026, en ajoutant
                # la possibilité de terminer une journée chez un client précis
                # (nuitée manuelle) plutôt qu'au dépôt : quand le véhicule a un
                # départ et une arrivée différents, l'index renvoyé par
                # manager.NodeToIndex() pour le nœud de fin N'EST PAS le même
                # que celui de routing.End() -- poser une contrainte de fenêtre
                # via NodeToIndex() sur ce nœud fait planter le solveur
                # (segfault natif, aucune exception Python, aucun message)
                # plutôt que de lever une erreur propre. Isolé avec un repro
                # minimal hors de ce fichier avant correction. routing.End()
                # est le seul index correct pour ce rôle dans ce cas ; le cas
                # symétrique (retour au dépôt, start_id == end_id) n'est PAS
                # concerné et continue d'utiliser NodeToIndex comme avant
                # (déjà validé par tous les tests existants).
                cumul_var = time_dim.CumulVar(routing.End(0))
            if node_id in stop_by_id:
                lo, hi = stop_by_id[node_id].window.resolve(day.day_start_min, day.day_end_min)
            elif day.end_window.type != WindowType.NONE:
                lo, hi = day.end_window.resolve(day.day_start_min, day.day_end_min)
            else:
                continue  # pas de contrainte ajoutée sur le retour : géré via routing.End()
        elif node_id in stop_by_id:
            lo, hi = stop_by_id[node_id].window.resolve(day.day_start_min, day.day_end_min)
        else:
            lo, hi = day.day_start_min, day.day_end_min
        cumul_var.SetRange(lo, hi)

    for v in range(routing.vehicles()):
        routing.AddVariableMinimizedByFinalizer(time_dim.CumulVar(routing.End(v)))

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    params.time_limit.FromSeconds(time_limit_s)

    solution = routing.SolveWithParameters(params)
    if not solution:
        return DayResult(
            day.day_index, day.label, [], 0, feasible=False,
            error="Aucune solution trouvée (contraintes horaires probablement incompatibles).",
        )

    steps: list[RouteStep] = []
    index = routing.Start(0)
    while not routing.IsEnd(index):
        node = manager.IndexToNode(index)
        arrival = solution.Value(time_dim.CumulVar(index))
        node_id = id_by_index[node]
        steps.append(RouteStep(
            stop_id=node_id,
            label=point_labels.get(node_id, node_id),
            arrival_min=arrival,
            service_minutes=service_by_index.get(node, 0),
        ))
        index = solution.Value(routing.NextVar(index))
    node = manager.IndexToNode(index)
    if node < n_real:  # nœud réel (pas le sentinel fictif de fin de route ouverte)
        arrival = solution.Value(time_dim.CumulVar(index))
        node_id = id_by_index[node]
        steps.append(RouteStep(
            stop_id=node_id,
            label=point_labels.get(node_id, node_id),
            arrival_min=arrival,
            service_minutes=service_by_index.get(node, 0),
        ))

    finish = steps[-1].departure_min if steps else day.day_start_min
    span = (finish - steps[0].arrival_min) if steps else 0
    return DayResult(day.day_index, day.label, steps, finish, feasible=True, span_min=span)


def solve_multi_day(
    days: list[DayPlan],
    stops: list[Stop],
    point_labels: dict[str, str],
    dist_fn: DistanceFn,
    time_limit_s: int = 5,
) -> dict[int, DayResult]:
    """Résout une séquence de jours enchaînés. Un DayPlan dont start_id vaut
    PREVIOUS_DAY_END reprend automatiquement au dernier arrêt résolu du jour
    précédent (cas d'une nuitée sur place, comme mardi -> mercredi dans le
    prototype)."""
    results: dict[int, DayResult] = {}
    prev_end_id: Optional[str] = None

    for day in sorted(days, key=lambda d: d.day_index):
        resolved_day = day
        if day.start_id == PREVIOUS_DAY_END:
            if prev_end_id is None:
                results[day.day_index] = DayResult(
                    day.day_index, day.label, [], 0, feasible=False,
                    error="start_id = PREVIOUS_DAY_END mais aucun jour précédent résolu.",
                )
                continue
            resolved_day = DayPlan(**{**day.__dict__, "start_id": prev_end_id})

        day_stops = [s for s in stops if day.day_index in s.allowed_days]
        result = solve_day(resolved_day, day_stops, point_labels, dist_fn, time_limit_s)
        results[day.day_index] = result
        if result.feasible and result.steps:
            prev_end_id = result.steps[-1].stop_id

    return results


def print_result(result: DayResult) -> None:
    print(f"\n=== {result.label} ===")
    if not result.feasible:
        print(f"  INFAISABLE : {result.error}")
        return
    for step in result.steps:
        tag = f"(durée {step.service_minutes} min)" if step.service_minutes else "(dépôt / point de passage)"
        print(f"  {step.label:42s} arrivée {fmt(step.arrival_min)} -> {fmt(step.departure_min)}  {tag}")
    print(f"  -> fin de journée : {fmt(result.finish_min)}")
