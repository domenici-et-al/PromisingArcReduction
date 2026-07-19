"""Independent primal validation for SSCFLP, MS-CFLP, and MS-CFLP-CI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from instances import assignment_cost, read_instance
from results import read_solution


def validate(instance: dict, solution: dict, problem: str, tolerance: float = 1e-6) -> dict:
    n, m = instance["customers"], instance["facilities"]
    x = np.asarray(solution["x"], dtype=float)
    y = np.asarray(solution["y"], dtype=float)
    a = np.asarray(solution.get("a", x > tolerance), dtype=float)
    errors = []
    if x.shape != (n, m):
        return {"valid": False, "errors": [f"x shape {x.shape}, expected {(n, m)}"]}
    if y.shape != (m,):
        return {"valid": False, "errors": [f"y shape {y.shape}, expected {(m,)}"]}
    if np.min(x) < -tolerance:
        errors.append("negative flow or assignment value")
    if np.min(y) < -tolerance or np.max(y) > 1 + tolerance:
        errors.append("facility variable outside [0,1]")

    demands = np.asarray(instance["demands"])
    capacities = np.asarray(instance["capacities"])
    if problem == "sscflp":
        if np.max(np.abs(x.sum(axis=1) - 1.0)) > tolerance:
            errors.append("single-source assignment equations violated")
        if np.max(np.abs(x - np.rint(x))) > tolerance:
            errors.append("single-source assignment is not binary")
        flow = demands[:, None] * x
    else:
        if np.max(np.abs(x.sum(axis=1) - demands)) > tolerance:
            errors.append("demand equations violated")
        flow = x
    if np.max(flow.sum(axis=0) - capacities * y) > tolerance:
        errors.append("facility capacity violated")
    if np.max((x > tolerance).astype(float) - y[None, :]) > tolerance:
        errors.append("assignment-to-opening link violated")

    if problem == "sscflp":
        for i in range(n):
            for j in np.flatnonzero(x[i] > tolerance):
                if capacities[j] + tolerance < demands[i]:
                    errors.append(f"ineligible assignment x[{i + 1},{j + 1}]")
                    break
    if problem == "mscflp-ci":
        if a.shape != (n, m):
            errors.append(f"a shape {a.shape}, expected {(n, m)}")
        else:
            if np.max((x > tolerance).astype(float) - a) > tolerance:
                errors.append("flow-to-use link violated")
            if np.max(a - y[None, :]) > tolerance:
                errors.append("use-to-opening link violated")
            used = a > 0.5
            for i, k in instance["incompatible_pairs"]:
                common = np.flatnonzero(used[i] & used[k])
                if len(common):
                    errors.append(f"incompatible customers {i + 1},{k + 1} share facility {common[0] + 1}")
                    if len(errors) >= 20:
                        break

    fixed = sum(instance["fixed_costs"][j] * y[j] for j in range(m))
    if problem == "sscflp":
        transport = sum(assignment_cost(instance, i, j) * x[i, j] for i in range(n) for j in range(m))
    else:
        transport = sum(instance["assignment_costs"][i][j] * x[i, j] for i in range(n) for j in range(m))
    return {
        "valid": not errors,
        "problem": problem,
        "instance": instance["name"],
        "objective": float(fixed + transport),
        "fixed_cost": float(fixed),
        "assignment_cost": float(transport),
        "open_facilities": int(np.count_nonzero(y > tolerance)),
        "positive_assignments": int(np.count_nonzero(x > tolerance)),
        "max_capacity_violation": float(max(0.0, np.max(flow.sum(axis=0) - capacities * y))),
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("problem", choices=("sscflp", "mscflp", "mscflp-ci"))
    parser.add_argument("instance")
    parser.add_argument("solution")
    parser.add_argument("--tolerance", type=float, default=1e-6)
    args = parser.parse_args()
    instance = read_instance(args.instance)
    solution = read_solution(args.solution, instance["customers"], instance["facilities"])
    result = validate(instance, solution, args.problem, args.tolerance)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["valid"] else 1)


if __name__ == "__main__":
    main()
