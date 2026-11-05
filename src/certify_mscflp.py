"""Prove MS-CFLP optimality by solving the complete model from a feasible PAR solution.

The transportation is first reoptimized with the PAR opening decisions fixed; the
result is the MIP start for the complete model over every customer-facility pair.
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


def certify(instance_path, solution_path, output, threads=1, seed=0, time_limit=0.0) -> dict:
    started = time.time()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    instance = read_instance(instance_path)
    n, m = instance["customers"], instance["facilities"]
    solution = read_solution(solution_path, n, m)
    check = validate(instance, solution, "mscflp")
    if not check["valid"]:
        raise ValueError(f"infeasible incumbent: {check['errors']}")

    demands, capacities = instance["demands"], instance["capacities"]
    model = gp.Model(f"mscflp_{instance['name']}")
    model.Params.LogToConsole = 0
    model.Params.LogFile = str(output / "verification.log")
    model.Params.Threads = threads
    model.Params.Seed = seed
    model.Params.MIPGap = 0
    model.Params.MIPGapAbs = 1e-7
    model.Params.FeasibilityTol = 1e-8
    model.Params.IntFeasTol = 1e-8
    model.Params.OptimalityTol = 1e-8
    model.Params.DualReductions = 0
    x = model.addVars(n, m, lb=0.0, name="x")
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
            model.addConstr(x[i, j] <= min(demands[i], capacities[j]) * y[j])

    # Transportation with the incumbent's open facilities, then the complete model.
    opened = solution["y"] > 0.5
    for j in range(m):
        y[j].LB = y[j].UB = float(opened[j])
    model.optimize()
    start_objective = model.ObjVal
    values = model.getAttr("X", x)
    for j in range(m):
        y[j].LB, y[j].UB, y[j].Start = 0.0, 1.0, float(opened[j])
    for key, var in x.items():
        var.Start = values[key]
    if time_limit:
        model.Params.TimeLimit = time_limit
    model.optimize()

    found = model.SolCount > 0
    objective = model.ObjVal if found else None
    bound = model.ObjBound if found else None
    result = {
        "instance": instance["name"],
        "status": "inconclusive",
        "solver_status": STATUS.get(model.Status, model.Status),
        "incumbent": check["objective"],
        "start_objective": start_objective,
        "objective": objective,
        "bound": bound,
        "nodes": model.NodeCount,
        "total_seconds": time.time() - started,
    }
    if model.Status == GRB.OPTIMAL:
        xs = np.array([[x[i, j].X for j in range(m)] for i in range(n)])
        ys = np.array([y[j].X for j in range(m)])
        final = validate(instance, {"x": xs, "y": ys}, "mscflp")
        tolerance = max(ABS_PROOF_TOL, REL_PROOF_TOL * abs(objective))
        if final["valid"] and abs(final["objective"] - bound) <= tolerance:
            result["status"] = "certified_improved" if objective < check["objective"] - tolerance else "certified"
            write_solution(output / "optimal_solution.csv.gz", xs, ys)
    write_json(output / "proof.json", result)
    model.dispose()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("instance")
    parser.add_argument("solution", help="feasible MS-CFLP solution (.csv.gz or .npz)")
    parser.add_argument("--output", required=True)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--time-limit", type=float, default=0, help="seconds; 0 = none")
    args = parser.parse_args()
    result = certify(args.instance, args.solution, args.output, args.threads, args.seed, args.time_limit)
    print(f"{result['instance']}: {result['status']} objective={result['objective']} bound={result['bound']}")


if __name__ == "__main__":
    main()
