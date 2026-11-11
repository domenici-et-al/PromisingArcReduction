"""Promising Arc Reduction (PAR): candidate facility lists for each customer."""

from __future__ import annotations

import hashlib
import json
import math


PROBLEMS = ("sscflp", "mscflp", "mscflp-ci")
# "par" is the method; the other variants are ablation controls from the paper.
VARIANTS = ("par", "no_congestion", "direct_adaptive", "unweighted_sqrt", "full")


def build_candidates(instance: dict, problem: str = "sscflp", variant: str = "par") -> dict:
    """Return the candidate lists P_i (cost order, 0-based facilities) and graph statistics."""
    n, m = instance["customers"], instance["facilities"]
    demands, capacities = instance["demands"], instance["capacities"]
    total_demand = sum(demands)
    mean_demand = total_demand / n
    rho = sum(capacities) / total_demand
    eta = math.sqrt(rho / max(rho - 1.0, 1e-12))

    # Eligible facilities J_i sorted by cost, ties broken by index.  Under
    # single sourcing a facility is eligible only if it can serve the whole demand.
    orders = []
    for i, row in enumerate(instance["assignment_costs"]):
        eligible = range(m) if problem != "sscflp" else (
            j for j in range(m) if capacities[j] + 1e-9 >= demands[i]
        )
        orders.append(sorted(eligible, key=lambda j: (row[j], j)))
    if variant == "full":
        return _summary(instance, problem, variant, orders, orders, rho, eta)

    # Preliminary neighborhoods Q_i and facility pressure p_j.
    horizon = max(1, min(m, math.ceil(eta * math.sqrt(m))))
    neighborhoods = [order[:horizon] for order in orders]
    if variant in ("direct_adaptive", "unweighted_sqrt"):
        pressures = [0.0] * m
    else:
        pressures = _pressure(demands, capacities, neighborhoods)
    availability = [1.0 / max(1.0, p) for p in pressures]

    # Customer target t_i and the shortest cost prefix that reaches it.
    widths = []
    for i, order in enumerate(orders):
        if variant == "unweighted_sqrt":
            target = math.sqrt(len(order))
        else:
            kappa = 1.0
            if variant == "par":
                kappa = _congestion(capacities, pressures, neighborhoods[i], eta)
            target = eta * math.sqrt(kappa) * math.sqrt(len(order) * demands[i] / mean_demand)
        widths.append(_prefix_width(order, availability, max(1.0, target)))

    # MS-CFLP-CI: shrink the width of customers with incompatibilities.
    if problem == "mscflp-ci":
        degrees = [0] * n
        for i, k in instance["incompatible_pairs"]:
            degrees[i] += 1
            degrees[k] += 1
        widths = [_contract_width(q, g, m) for q, g in zip(widths, degrees)]

    candidates = [order[:q] for order, q in zip(orders, widths)]
    return _summary(instance, problem, variant, candidates, orders, rho, eta)


def _pressure(demands, capacities, neighborhoods) -> list[float]:
    load = [0.0] * len(capacities)
    for demand, neighborhood in zip(demands, neighborhoods):
        share = demand / len(neighborhood)
        for j in neighborhood:
            load[j] += share
    return [load[j] / capacities[j] if capacities[j] > 0 else math.inf
            for j in range(len(capacities))]


def _congestion(capacities, pressures, neighborhood, eta) -> float:
    effective = sum(capacities[j] / max(1.0, pressures[j]) for j in neighborhood)
    if effective <= 1e-12:
        return 1.0
    weighted = sum(capacities[j] * pressures[j] / max(1.0, pressures[j]) for j in neighborhood)
    return max(1.0, math.sqrt(max(1.0, eta * (weighted / effective))))


def _prefix_width(order, availability, target) -> int:
    total = 0.0
    for rank, j in enumerate(order, 1):
        total += availability[j]
        if total >= target:
            return rank
    return len(order)


def _contract_width(width: int, degree: int, m: int) -> int:
    if degree <= 0:
        return width
    balance = 2.0 * m / degree
    root = 0.5 * balance * (math.sqrt(1.0 + 4.0 * width / balance) - 1.0)
    return max(1, min(width, math.ceil(root)))


def graph_sha256(candidates) -> str:
    payload = json.dumps([list(row) for row in candidates], separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _summary(instance, problem, variant, candidates, orders, rho, eta) -> dict:
    n, m = instance["customers"], instance["facilities"]
    arcs = sum(len(row) for row in candidates)
    sets = [set(row) for row in candidates]
    return {
        "candidates": [list(row) for row in candidates],
        "metadata": {
            "problem": problem,
            "variant": variant,
            "customers": n,
            "facilities": m,
            "rho": rho,
            "eta": eta,
            "candidate_arcs": arcs,
            "eligible_arcs": sum(len(row) for row in orders),
            "candidate_pct_full": 100.0 * arcs / (n * m),
            "conflict_rows": sum(len(sets[i] & sets[k]) for i, k in instance["incompatible_pairs"]),
            "graph_sha256": graph_sha256(candidates),
        },
    }
