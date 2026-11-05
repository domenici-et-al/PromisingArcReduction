"""Prove full-model SSCFLP optimality from a feasible PAR solution (Algorithm 2 of the paper).

1. Solve the LP relaxation on the PAR graph and price every omitted eligible arc,
   adding arcs with negative reduced cost until none is left; this gives the
   full-LP lower bound L.
2. Reduced-cost fixing with the incumbent value z: drop every omitted arc and
   every closed facility whose reduced cost exceeds z - L.
3. Solve the SSCFLP on the remaining arcs to optimality.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import gurobipy as gp
import numpy as np
from gurobipy import GRB

from instances import read_instance
from par import build_candidates
from results import read_solution, write_csv, write_json, write_solution
from solve import STATUS
from validate import validate


MAX_PRICING_ITERATIONS = 100
RC_TOL = 1e-7
REL_PROOF_TOL = 1e-9
ABS_PROOF_TOL = 1e-6


def certify(instance_path, solution_path, output, threads=1, seed=0,
            pricing_time_limit=0.0, verification_time_limit=0.0) -> dict:
    started = time.time()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    instance = read_instance(instance_path)
    candidates = build_candidates(instance, "sscflp")["candidates"]
    solution = read_solution(solution_path, instance["customers"], instance["facilities"])
    check = validate(instance, solution, "sscflp")
    if not check["valid"]:
        raise ValueError(f"infeasible incumbent: {check['errors']}")
    incumbent = check["objective"]
    tolerance = max(ABS_PROOF_TOL, REL_PROOF_TOL * abs(incumbent))

    pricing = _price(instance, candidates, output, threads, pricing_time_limit)
    proof = {
        "instance": instance["name"],
        "status": "inconclusive",
        "incumbent": incumbent,
        "pricing_status": pricing["status"],
        "lp_bound": pricing["bound"],
        "pricing_iterations": pricing["iterations"],
        "pricing_added_arcs": len(pricing["added"]),
        "pricing_seconds": pricing["seconds"],
    }
    if pricing["status"] != "optimal":
        write_json(output / "proof.json", proof)
        return proof
    if pricing["bound"] > incumbent + tolerance:
        raise ValueError("the LP bound exceeds the incumbent value")

    # Reduced-cost fixing.  An arc or facility whose reduced cost exceeds z - L
    # cannot be used by any solution of value at most z.
    budget = max(0.0, incumbent - pricing["bound"]) + RC_TOL
    closed = (pricing["y"] <= 1e-8) & (pricing["y_rc"] > budget)
    keep = pricing["omitted"] & ~closed[None, :] & (pricing["rc"] <= budget)
    for i, j, value, rc in pricing["added"]:
        keep[i, j] = not (closed[j] or (value <= 1e-8 and rc > budget))

    assigned = solution["x"].argmax(axis=1).tolist()
    verification = _verify(instance, candidates, keep, assigned, incumbent, tolerance,
                           output, threads, seed, verification_time_limit)
    certified = verification["status"] == "optimal"
    proof.update({
        "closed_facilities": int(closed.sum()),
        "unfixed_omitted_arcs": int(keep.sum()),
        "verification_arcs": verification["arcs"],
        "verification_status": verification["status"],
        "objective": verification["objective"],
        "bound": verification["bound"],
        "nodes": verification["nodes"],
        "verification_seconds": verification["seconds"],
        "total_seconds": time.time() - started,
    })
    if certified:
        improved = verification["objective"] < incumbent - tolerance
        proof["status"] = "certified_improved" if improved else "certified"
        write_solution(output / "optimal_solution.csv.gz", *verification["solution"])
    write_json(output / "proof.json", proof)
    return proof


def _price(instance, candidates, output, threads, time_limit):
    started = time.time()
    n, m = instance["customers"], instance["facilities"]
    demands, capacities = instance["demands"], instance["capacities"]
    cost = demands[:, None] * instance["assignment_costs"]
    eligible = capacities[None, :] + 1e-9 >= demands[:, None]
    active = np.zeros((n, m), dtype=bool)
    for i, row in enumerate(candidates):
        active[i, row] = True

    model = gp.Model(f"pricing_{instance['name']}")
    model.Params.LogToConsole = 0
    model.Params.LogFile = str(output / "pricing.log")
    model.Params.Threads = threads
    model.Params.Method = 1
    model.Params.Presolve = 1
    y = model.addVars(range(m), lb=0, ub=1, obj=instance["fixed_costs"], name="y")
    assign = [model.addConstr(gp.LinExpr() == 1, name=f"assign[{i}]") for i in range(n)]
    capacity = [model.addConstr(-capacities[j] * y[j] <= 0, name=f"capacity[{j}]") for j in range(m)]
    x = {}

    def add_arc(i, j):
        column = gp.Column([1.0, demands[i]], [assign[i], capacity[j]])
        x[i, j] = model.addVar(lb=0, ub=1, obj=cost[i, j], column=column, name=f"x[{i},{j}]")
        model.addConstr(x[i, j] <= y[j], name=f"link[{i},{j}]")

    for i, j in np.argwhere(active):
        add_arc(i, j)
    model.update()

    status, bound, rows, added = "iteration_limit", None, [], []
    for iteration in range(1, MAX_PRICING_ITERATIONS + 1):
        if time_limit:
            if time.time() - started >= time_limit:
                status = "time_limit"
                break
            model.Params.TimeLimit = time_limit - (time.time() - started)
        model.optimize()
        if model.Status != GRB.OPTIMAL:
            status = STATUS.get(model.Status, model.Status)
            break
        bound = model.ObjVal
        pi = np.array(model.getAttr("Pi", assign))
        beta = np.array(model.getAttr("Pi", capacity))
        # Reduced cost of an omitted arc: its link row is absent, so gamma_ij = 0.
        rc = cost - pi[:, None] - demands[:, None] * beta[None, :]
        omitted = eligible & ~active
        negative = np.argwhere(omitted & (rc < -RC_TOL))
        rows.append({"iteration": iteration, "lower_bound": bound, "active_arcs": int(active.sum()),
                     "omitted_arcs": int(omitted.sum()), "negative_arcs": len(negative),
                     "elapsed_seconds": time.time() - started})
        if not len(negative):
            status = "optimal"
            break
        for i, j in negative:
            active[i, j] = True
            added.append((i, j))
            add_arc(i, j)
        model.update()
    if rows:
        write_csv(output / "pricing_iterations.csv", rows)

    result = {"status": status, "bound": bound, "iterations": len(rows), "added": [],
              "seconds": time.time() - started}
    if status == "optimal":
        result.update({
            "rc": rc,
            "omitted": omitted,
            "y": np.array(model.getAttr("X", y.values())),
            "y_rc": np.array(model.getAttr("RC", y.values())),
            "added": [(i, j, x[i, j].X, x[i, j].RC) for i, j in added],
        })
    model.dispose()
    return result


def _verify(instance, candidates, extra, assigned, incumbent, tolerance, output, threads, seed,
            time_limit):
    started = time.time()
    n, m = instance["customers"], instance["facilities"]
    demands, capacities, costs = instance["demands"], instance["capacities"], instance["assignment_costs"]
    # PAR arcs, arcs that survived fixing, and the incumbent's own arcs.
    sets = [set(row) | set(np.flatnonzero(extra[i]).tolist()) | {assigned[i]}
            for i, row in enumerate(candidates)]
    arcs = [(i, j) for i in range(n) for j in sorted(sets[i])]

    model = gp.Model(f"verification_{instance['name']}")
    model.Params.LogToConsole = 0
    model.Params.LogFile = str(output / "verification.log")
    model.Params.Threads = threads
    model.Params.Seed = seed
    model.Params.MIPGap = 0
    model.Params.MIPGapAbs = max(1e-9, 0.01 * tolerance)
    model.Params.FeasibilityTol = 1e-9
    model.Params.IntFeasTol = 1e-9
    model.Params.OptimalityTol = 1e-9
    model.Params.DualReductions = 0
    if time_limit:
        model.Params.TimeLimit = time_limit
    x = model.addVars(arcs, vtype=GRB.BINARY, name="x")
    y = model.addVars(range(m), vtype=GRB.BINARY, name="y")
    model.setObjective(gp.quicksum(instance["fixed_costs"][j] * y[j] for j in range(m))
                       + gp.quicksum(demands[i] * costs[i, j] * x[i, j] for i, j in arcs))
    for i in range(n):
        model.addConstr(gp.quicksum(x[i, j] for j in sets[i]) == 1)
    by_facility = [[] for _ in range(m)]
    for i, j in arcs:
        model.addConstr(x[i, j] <= y[j])
        by_facility[j].append(i)
    for j in range(m):
        model.addConstr(gp.quicksum(demands[i] * x[i, j] for i in by_facility[j]) <= capacities[j] * y[j])
    opened = set(assigned)
    for i, j in enumerate(assigned):
        x[i, j].Start = 1
    for j in range(m):
        y[j].Start = int(j in opened)
    model.optimize()

    found = model.SolCount > 0
    result = {"status": STATUS.get(model.Status, model.Status), "arcs": len(arcs),
              "objective": model.ObjVal if found else None, "bound": model.ObjBound if found else None,
              "nodes": model.NodeCount, "seconds": time.time() - started}
    if model.Status == GRB.OPTIMAL:
        xs = np.zeros((n, m))
        for (i, j), var in x.items():
            xs[i, j] = var.X
        result["solution"] = (xs, np.array([y[j].X for j in range(m)]))
    model.dispose()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("instance")
    parser.add_argument("solution", help="feasible SSCFLP solution (.csv.gz or .npz)")
    parser.add_argument("--output", required=True)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--pricing-time-limit", type=float, default=0, help="seconds; 0 = none")
    parser.add_argument("--verification-time-limit", type=float, default=0, help="seconds; 0 = none")
    args = parser.parse_args()
    proof = certify(args.instance, args.solution, args.output, args.threads, args.seed,
                    args.pricing_time_limit, args.verification_time_limit)
    print(f"{proof['instance']}: {proof['status']} objective={proof.get('objective')}")


if __name__ == "__main__":
    main()
