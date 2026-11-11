"""Build the PAR graph and solve the reduced SSCFLP, MS-CFLP or MS-CFLP-CI model."""

from __future__ import annotations

import argparse
import math
import time
from pathlib import Path

import gurobipy as gp
import numpy as np
from gurobipy import GRB

from instances import assignment_cost, read_instance
from par import PROBLEMS, VARIANTS, build_candidates
from results import write_csv, write_json, write_solution
from validate import validate


STATUS = {GRB.OPTIMAL: "optimal", GRB.INFEASIBLE: "infeasible", GRB.TIME_LIMIT: "time_limit",
          GRB.SOLUTION_LIMIT: "solution_limit", GRB.INTERRUPTED: "interrupted",
          GRB.MEM_LIMIT: "memory_limit"}
# Seconds kept free at the end of the end-to-end limit to extract and save the solution.
RESERVE = 3.0


def solve(instance_path, output, problem, variant="par", time_limit=None, threads=1, seed=0,
          warm_start=None) -> dict:
    started = time.time()
    instance = read_instance(instance_path)
    if time_limit is None:
        time_limit = 10.0 * math.sqrt(instance["facilities"]) if problem == "mscflp-ci" else 600.0
    if warm_start is None:
        warm_start = problem == "sscflp"
    if warm_start and problem != "sscflp":
        raise ValueError("INIT is defined only for the SSCFLP")
    deadline = started + time_limit
    graph = build_candidates(instance, problem, variant)
    candidates = graph["candidates"]
    run = Path(output) / problem / instance["name"]
    run.mkdir(parents=True, exist_ok=True)

    start = None
    init = {"used": bool(warm_start)}
    if warm_start:
        start, init = _initial_assignment(instance, candidates, run, deadline, threads, seed)

    model, x, y, a = _build_model(instance, candidates, problem)
    _set_params(model, run / "gurobi.log", threads, seed)
    model.Params.MIPGap = 0.0
    model.Params.MIPGapAbs = 1e-6
    if problem == "sscflp":
        model.Params.MIPFocus = 1
        model.Params.Heuristics = 0.8
    if start is not None:
        opened = set(start)
        for (i, j), var in x.items():
            var.Start = 1.0 if start[i] == j else 0.0
        for j, var in y.items():
            var.Start = 1.0 if j in opened else 0.0
    model.Params.TimeLimit = max(0.01, deadline - time.time() - RESERVE)

    progress = []
    model.optimize(_progress_callback(started, deadline, time_limit, progress))
    found = model.SolCount > 0
    progress.append({"seconds": time.time() - started, "incumbent": model.ObjVal if found else "",
                     "bound": model.ObjBound if found else ""})
    write_csv(run / "progress.csv", progress)

    result = {
        "instance": instance["name"],
        "problem": problem,
        "variant": variant,
        "status": STATUS.get(model.Status, model.Status),
        "objective": model.ObjVal if found else None,
        "bound": model.ObjBound if found else None,
        "nodes": model.NodeCount,
        "gurobi_seconds": model.Runtime,
        "end_to_end_seconds": time.time() - started,
        "time_limit": time_limit,
        "threads": threads,
        "seed": seed,
        "initialization": init,
        "instance_sha256": instance["sha256"],
        "gurobi_version": ".".join(map(str, gp.gurobi.version())),
        "graph": graph["metadata"],
    }
    if found:
        solution = _dense(x, y, a, instance)
        write_solution(run / "solution.csv.gz", *solution)
        result["validation"] = validate(instance, dict(zip("xya", solution)), problem)
    write_json(run / "metadata.json", result)
    model.dispose()
    return result


def _build_model(instance, candidates, problem):
    n, m = instance["customers"], instance["facilities"]
    demands, capacities, fixed = instance["demands"], instance["capacities"], instance["fixed_costs"]
    arcs = [(i, j) for i, row in enumerate(candidates) for j in row]
    by_facility = [[] for _ in range(m)]
    for i, j in arcs:
        by_facility[j].append(i)
    model = gp.Model(f"par_{problem}_{instance['name']}")
    y = model.addVars(range(m), vtype=GRB.BINARY, name="y")
    a = None
    if problem == "sscflp":
        x = model.addVars(arcs, vtype=GRB.BINARY, name="x")
        model.setObjective(gp.quicksum(fixed[j] * y[j] for j in range(m))
                           + gp.quicksum(assignment_cost(instance, i, j) * x[i, j] for i, j in arcs),
                           GRB.MINIMIZE)
        for i in range(n):
            model.addConstr(gp.quicksum(x[i, j] for j in candidates[i]) == 1, name=f"assign[{i}]")
        for j in range(m):
            model.addConstr(gp.quicksum(demands[i] * x[i, j] for i in by_facility[j])
                            <= capacities[j] * y[j], name=f"capacity[{j}]")
        for i, j in arcs:
            model.addConstr(x[i, j] <= y[j], name=f"link[{i},{j}]")
    else:
        # Multi-source: x[i, j] is the quantity shipped; a[i, j] = 1 if customer i uses j (CI only).
        x = model.addVars(arcs, lb=0.0, vtype=GRB.CONTINUOUS, name="x")
        if problem == "mscflp-ci":
            a = model.addVars(arcs, vtype=GRB.BINARY, name="a")
        costs = instance["assignment_costs"]
        model.setObjective(gp.quicksum(fixed[j] * y[j] for j in range(m))
                           + gp.quicksum(costs[i, j] * x[i, j] for i, j in arcs), GRB.MINIMIZE)
        for i in range(n):
            model.addConstr(gp.quicksum(x[i, j] for j in candidates[i]) == demands[i],
                            name=f"demand[{i}]")
        for j in range(m):
            model.addConstr(gp.quicksum(x[i, j] for i in by_facility[j]) <= capacities[j] * y[j],
                            name=f"capacity[{j}]")
        for i, j in arcs:
            upper = min(demands[i], capacities[j])
            if a is None:
                model.addConstr(x[i, j] <= upper * y[j], name=f"link[{i},{j}]")
            else:
                model.addConstr(x[i, j] <= upper * a[i, j], name=f"flow_use[{i},{j}]")
                model.addConstr(a[i, j] <= y[j], name=f"use_open[{i},{j}]")
        if a is not None:
            # Conflict rows only where both customers keep the facility as a candidate.
            sets = [set(row) for row in candidates]
            for i, k in instance["incompatible_pairs"]:
                for j in sets[i] & sets[k]:
                    model.addConstr(a[i, j] + a[k, j] <= y[j], name=f"conflict[{i},{k},{j}]")
    model.update()
    return model, x, y, a


def _initial_assignment(instance, candidates, run, deadline, threads, seed):
    """INIT: first feasible single-source assignment on the PAR graph, ignoring fixed costs."""
    started = time.time()
    model = gp.Model(f"par_init_{instance['name']}")
    _set_params(model, run / "warm_start.log", threads, seed)
    model.Params.MIPFocus = 1
    model.Params.Heuristics = 1.0
    model.Params.SolutionLimit = 1
    model.Params.TimeLimit = max(0.01, deadline - time.time() - RESERVE)
    arcs = [(i, j) for i, row in enumerate(candidates) for j in row]
    by_facility = [[] for _ in range(instance["facilities"])]
    for i, j in arcs:
        by_facility[j].append(i)
    z = model.addVars(arcs, vtype=GRB.BINARY, name="x")
    model.setObjective(gp.quicksum(assignment_cost(instance, i, j) * z[i, j] for i, j in arcs))
    for i, row in enumerate(candidates):
        model.addConstr(gp.quicksum(z[i, j] for j in row) == 1)
    for j in range(instance["facilities"]):
        model.addConstr(gp.quicksum(instance["demands"][i] * z[i, j] for i in by_facility[j])
                        <= instance["capacities"][j])
    model.optimize()
    start = None
    if model.SolCount:
        start = [max(row, key=lambda j: z[i, j].X) for i, row in enumerate(candidates)]
    info = {"used": True, "status": STATUS.get(model.Status, model.Status),
            "seconds": time.time() - started}
    model.dispose()
    return start, info


def _set_params(model, log_path, threads, seed):
    model.Params.LogToConsole = 0
    model.Params.LogFile = str(log_path)
    model.Params.Threads = threads
    model.Params.Seed = seed


def _dense(x, y, a, instance):
    n, m = instance["customers"], instance["facilities"]
    xs = np.zeros((n, m))
    for (i, j), var in x.items():
        xs[i, j] = var.X
    ys = np.array([y[j].X for j in range(m)])
    if a is None:
        return xs, ys
    us = np.zeros((n, m))
    for (i, j), var in a.items():
        us[i, j] = var.X
    return xs, ys, us


def _progress_callback(started, deadline, time_limit, rows):
    """Stop at the end-to-end deadline and record the incumbent every minute (or every tenth of short limits)."""
    interval = 60.0 if time_limit >= 300 else max(1.0, time_limit / 10.0)
    next_record = [interval]

    def callback(model, where):
        if time.time() >= deadline:
            model.terminate()
        elapsed = time.time() - started
        if where == GRB.Callback.MIP and elapsed >= next_record[0]:
            rows.append({"seconds": elapsed, "incumbent": model.cbGet(GRB.Callback.MIP_OBJBST),
                         "bound": model.cbGet(GRB.Callback.MIP_OBJBND)})
            next_record[0] += interval
    return callback


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("problem", choices=PROBLEMS)
    parser.add_argument("instances", nargs="+")
    parser.add_argument("--output", default="output")
    parser.add_argument("--variant", choices=VARIANTS, default="par")
    parser.add_argument("--time-limit", type=float, help="end-to-end seconds (default 600, or 10*sqrt(m) for CI)")
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--warm-start", action=argparse.BooleanOptionalAction,
                        help="run INIT first (default: only for sscflp)")
    args = parser.parse_args()
    for path in args.instances:
        result = solve(path, args.output, args.problem, args.variant, args.time_limit,
                       args.threads, args.seed, args.warm_start)
        print(f"{result['instance']}: {result['status']} objective={result['objective']}", flush=True)


if __name__ == "__main__":
    main()
