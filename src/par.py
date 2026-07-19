"""Deterministic Promising Arc Reduction (PAR) graph construction."""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from typing import Sequence


GRAPH_VARIANTS = ("par", "without_congestion", "pressure_free", "unweighted_root", "full")
PROBLEMS = ("sscflp", "mscflp", "mscflp-ci")


def build_candidates(instance: dict, problem: str = "sscflp", variant: str = "par") -> dict:
    if problem not in PROBLEMS:
        raise ValueError(f"Unknown problem: {problem}")
    if variant not in GRAPH_VARIANTS:
        raise ValueError(f"Unknown graph variant: {variant}")

    n, m = instance["customers"], instance["facilities"]
    demands = instance["demands"]
    capacities = instance["capacities"]
    total_demand = sum(demands)
    mean_demand = total_demand / n
    rho = sum(capacities) / total_demand
    eta = math.sqrt(rho / max(rho - 1.0, 1e-12))

    orders = []
    for i, row in enumerate(instance["assignment_costs"]):
        eligible = range(m) if problem != "sscflp" else (
            j for j in range(m) if capacities[j] + 1e-9 >= demands[i]
        )
        order = sorted(eligible, key=lambda j: (row[j], j))
        if not order:
            raise ValueError(f"Customer {i + 1} has no eligible facility.")
        orders.append(order)

    eligible_widths = [len(order) for order in orders]
    if variant == "full":
        return _package(instance, problem, variant, orders, orders, [0.0] * m,
                        [1.0] * m, [1.0] * n, [float(v) for v in eligible_widths],
                        eligible_widths, eligible_widths, rho, eta, 0, [0] * n)

    horizon = max(1, min(m, math.ceil(eta * math.sqrt(m))))
    neighborhoods = [order[:min(horizon, len(order))] for order in orders]
    pressures = [0.0] * m if variant in {"pressure_free", "unweighted_root"} else _pressure(
        demands, capacities, neighborhoods
    )
    availability = [1.0 / max(1.0, p) for p in pressures]

    congestion, targets, inherited_widths = [], [], []
    for i, order in enumerate(orders):
        kappa = 1.0
        if variant in {"par", "without_congestion"}:
            kappa = _congestion(capacities, pressures, neighborhoods[i], eta)
        theta = 1.0 if variant == "without_congestion" else math.sqrt(max(1.0, kappa))
        target = math.sqrt(len(order)) if variant == "unweighted_root" else (
            eta * theta * math.sqrt(len(order) * demands[i] / mean_demand)
        )
        target = max(1.0, target)
        width = _weighted_prefix(order, availability, target)
        congestion.append(kappa)
        targets.append(target)
        inherited_widths.append(width)

    final_widths = list(inherited_widths)
    degrees = [0] * n
    if problem == "mscflp-ci":
        for i, k in instance["incompatible_pairs"]:
            degrees[i] += 1
            degrees[k] += 1
        final_widths = [_contract_width(q, degree, m) for q, degree in zip(inherited_widths, degrees)]

    candidates = [order[:q] for order, q in zip(orders, final_widths)]
    return _package(instance, problem, variant, candidates, orders, pressures, availability,
                    congestion, targets, inherited_widths, final_widths, rho, eta, horizon, degrees)


def _pressure(demands, capacities, neighborhoods) -> list[float]:
    load = [0.0] * len(capacities)
    for demand, neighborhood in zip(demands, neighborhoods):
        share = demand / len(neighborhood)
        for j in neighborhood:
            load[j] += share
    return [load[j] / capacities[j] if capacities[j] > 0 else math.inf for j in range(len(capacities))]


def _congestion(capacities, pressures, neighborhood, eta) -> float:
    effective = sum(capacities[j] / max(1.0, pressures[j]) for j in neighborhood)
    if effective <= 1e-12:
        return 1.0
    weighted = sum(capacities[j] * pressures[j] / max(1.0, pressures[j]) for j in neighborhood)
    local_pressure = weighted / effective
    return max(1.0, math.sqrt(max(1.0, eta * local_pressure)))


def _weighted_prefix(order: Sequence[int], availability: Sequence[float], target: float) -> int:
    total = 0.0
    for rank, j in enumerate(order, 1):
        total += availability[j]
        if total >= target:
            return rank
    return len(order)


def _contract_width(base_width: int, degree: int, facilities: int) -> int:
    if degree <= 0:
        return base_width
    balance = 2.0 * facilities / degree
    root = 0.5 * balance * (math.sqrt(1.0 + 4.0 * base_width / balance) - 1.0)
    return max(1, min(base_width, math.ceil(root)))


def graph_sha256(candidates: Sequence[Sequence[int]]) -> str:
    payload = json.dumps([list(row) for row in candidates], separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _percentile(values, q):
    values = sorted(float(v) for v in values)
    if not values:
        return 0.0
    position = q * (len(values) - 1)
    lo, hi = math.floor(position), math.ceil(position)
    return values[lo] if lo == hi else values[lo] + (values[hi] - values[lo]) * (position - lo)


def _package(instance, problem, variant, candidates, orders, pressures, availability,
             congestion, targets, inherited, widths, rho, eta, horizon, degrees):
    n, m = instance["customers"], instance["facilities"]
    arcs = sum(len(row) for row in candidates)
    eligible = sum(len(row) for row in orders)
    conflicts = instance["incompatible_pairs"]
    sets = [set(row) for row in candidates]
    conflict_rows = sum(len(sets[i] & sets[k]) for i, k in conflicts)
    expected_rows = sum(widths[i] * widths[k] for i, k in conflicts) / m if m else 0.0
    metadata = {
        "problem": problem,
        "variant": variant,
        "customers": n,
        "facilities": m,
        "total_demand": sum(instance["demands"]),
        "mean_demand": sum(instance["demands"]) / n,
        "total_capacity": sum(instance["capacities"]),
        "rho": rho,
        "eta": eta,
        "preliminary_horizon": horizon,
        "candidate_arcs": arcs,
        "eligible_arcs": eligible,
        "full_arcs": n * m,
        "candidate_pct_full": 100.0 * arcs / (n * m),
        "candidate_pct_eligible": 100.0 * arcs / eligible,
        "mean_width": statistics.fmean(widths),
        "median_width": statistics.median(widths),
        "p90_width": _percentile(widths, 0.90),
        "max_width": max(widths),
        "pressure_p95": _percentile(pressures, 0.95),
        "pressure_max": max(pressures, default=0.0),
        "conflict_pairs": len(conflicts),
        "expected_conflict_rows": expected_rows,
        "materialized_conflict_rows": conflict_rows,
        "graph_sha256": graph_sha256(candidates),
    }
    return {
        "candidates": [list(row) for row in candidates],
        "orders": [list(row) for row in orders],
        "pressures": list(pressures),
        "availability": list(availability),
        "congestion": list(congestion),
        "targets": list(targets),
        "inherited_widths": list(inherited),
        "widths": list(widths),
        "conflict_degrees": list(degrees),
        "metadata": metadata,
    }
