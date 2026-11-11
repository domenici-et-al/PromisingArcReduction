"""Prove MS-CFLP or MS-CFLP-CI optimality by solving the complete model from a feasible PAR solution.

MS-CFLP: the transportation is first reoptimized with the PAR opening decisions fixed;
the result is the MIP start for the complete model over every customer-facility pair.
MS-CFLP-CI: the PAR solution is the start, and incompatibility rows
a[i, j] + a[k, j] <= 1 are added lazily, only when an integer solution violates them.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import gurobipy as gp
import numpy as np
from gurobipy import GRB

from instances import read_instance
from results import read_solution, write_json, write_solution
from solve import STATUS
from validate import validate


REL_PROOF_TOL = 1e-9
ABS_PROOF_TOL = 1e-6


def certify(problem, instance_path, solution_path, output, threads=1, seed=0, time_limit=0.0) -> dict:
    started = time.time()
    ci = problem == "mscflp-ci"
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    instance = read_instance(instance_path)
    n, m = instance["customers"], instance["facilities"]
    solution = read_solution(solution_path, n, m)
    check = validate(instance, solution, problem)
    if not check["valid"]:
        raise ValueError(f"infeasible incumbent: {check['errors']}")

    demands, capacities = instance["demands"], instance["capacities"]
    model = gp.Model(f"{problem}_{instance['name']}")
    model.Params.LogToConsole = 0
    model.Params.LogFile = str(output / "verification.log")
    model.Params.Threads = threads
    model.Params.Seed = seed
    model.Params.MIPGap = 0
    model.Params.MIPGapAbs = 0 if ci else 1e-7
    model.Params.FeasibilityTol = model.Params.IntFeasTol = model.Params.OptimalityTol = 1e-9 if ci else 1e-8
    model.Params.DualReductions = 0
    if ci:
        model.Params.LazyConstraints = 1
    x = model.addVars(n, m, lb=0.0, name="x")
    a = model.addVars(n, m, vtype=GRB.BINARY, name="a") if ci else None
    y = model.addVars(m, vtype=GRB.BINARY, name="y")
    model.setObjective(gp.quicksum(instance["fixed_costs"][j] * y[j] for j in range(m))
                       + gp.quicksum(instance["assignment_costs"][i, j] * x[i, j]
                                     for i in range(n) for j in range(m)), GRB.MINIMIZE)
    for i in range(n):
        model.addConstr(x.sum(i, "*") == demands[i])
    for j in range(m):
        model.addConstr(x.sum("*", j) <= capacities[j] * y[j])
    for i in range(n):
        for j in range(m):
            upper = min(demands[i], capacities[j])
            if ci:
                model.addConstr(x[i, j] <= upper * a[i, j])
                model.addConstr(a[i, j] <= y[j])
            else:
                model.addConstr(x[i, j] <= upper * y[j])

    opened = solution["y"] > 0.5
    start_objective = None
    if ci:
        use = solution.get("a", solution["x"] > 1e-9)
        for (i, j), var in x.items():
            var.Start = solution["x"][i, j]
            a[i, j].Start = float(use[i, j] > 0.5)
    else:
        # Transportation with the incumbent's open facilities, then the complete model.
        for j in range(m):
            y[j].LB = y[j].UB = float(opened[j])
        model.optimize()
        start_objective = model.ObjVal
        values = model.getAttr("X", x)
        for j in range(m):
            y[j].LB, y[j].UB = 0.0, 1.0
        for key, var in x.items():
            var.Start = values[key]
    for j in range(m):
        y[j].Start = float(opened[j])
    if time_limit:
        model.Params.TimeLimit = time_limit

    neighbors = [set() for _ in range(n)]
    for i, k in instance["incompatible_pairs"]:
        neighbors[i].add(k)
        neighbors[k].add(i)
    added = set()

    def separate(model, where):
        if where != GRB.Callback.MIPSOL:
            return
        values = model.cbGetSolution(a)
        users = [[] for _ in range(m)]
        for (i, j), value in values.items():
            if value > 0.5:
                users[j].append(i)
        for j, customers in enumerate(users):
            for i in customers:
                for k in neighbors[i].intersection(customers):
                    if i < k and (i, k, j) not in added:
                        model.cbLazy(a[i, j] + a[k, j] <= 1)
                        added.add((i, k, j))

    model.optimize(separate if ci else None)

    found = model.SolCount > 0
    objective = model.ObjVal if found else None
    bound = model.ObjBound if found else None
    result = {
        "instance": instance["name"],
        "status": "inconclusive",
        "solver_status": STATUS.get(model.Status, model.Status),
        "incumbent": check["objective"],
        "objective": objective,
        "bound": bound,
        "nodes": model.NodeCount,
        "total_seconds": time.time() - started,
    }
    if ci:
        result["lazy_rows"] = len(added)
    else:
        result["start_objective"] = start_objective
    if model.Status == GRB.OPTIMAL:
        xs = np.array([[x[i, j].X for j in range(m)] for i in range(n)])
        ys = np.array([y[j].X for j in range(m)])
        us = np.array([[a[i, j].X for j in range(m)] for i in range(n)]) if ci else None
        final = validate(instance, {"x": xs, "y": ys, "a": us} if ci else {"x": xs, "y": ys}, problem)
        tolerance = max(ABS_PROOF_TOL, REL_PROOF_TOL * abs(objective))
        if final["valid"] and abs(final["objective"] - bound) <= tolerance:
            result["status"] = "certified_improved" if objective < check["objective"] - tolerance else "certified"
            write_solution(output / "optimal_solution.csv.gz", xs, ys, us)
    write_json(output / "proof.json", result)
    model.dispose()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("problem", choices=("mscflp", "mscflp-ci"))
    parser.add_argument("instance")
    parser.add_argument("solution", help="feasible solution (.csv.gz)")
    parser.add_argument("--output", required=True)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--time-limit", type=float, default=0, help="seconds; 0 = none")
    args = parser.parse_args()
    result = certify(args.problem, args.instance, args.solution, args.output, args.threads, args.seed,
                     args.time_limit)
    print(f"{result['instance']}: {result['status']} objective={result['objective']} bound={result['bound']}")


if __name__ == "__main__":
    main()
