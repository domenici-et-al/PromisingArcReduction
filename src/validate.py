"""Check a solution against the original instance and recompute its cost."""

from __future__ import annotations

import argparse
import json

import numpy as np

from instances import read_instance
from par import PROBLEMS
from results import read_solution


def validate(instance: dict, solution: dict, problem: str, tolerance: float = 1e-6) -> dict:
    n, m = instance["customers"], instance["facilities"]
    x = np.asarray(solution["x"], dtype=float)
    y = np.asarray(solution["y"], dtype=float)
    if x.shape != (n, m) or y.shape != (m,):
        return {"valid": False, "errors": [f"shapes x{x.shape} y{y.shape}, expected ({n}, {m})"]}
    demands = instance["demands"]
    capacities = instance["capacities"]
    costs = instance["assignment_costs"]
    used = x > tolerance
    errors = []

    def check(ok, message):
        if not ok:
            errors.append(message)

    check(x.min() >= -tolerance, "negative x")
    check(np.abs(y - np.rint(y)).max() <= tolerance and y.min() >= -tolerance
          and y.max() <= 1 + tolerance, "y is not binary")
    if problem == "sscflp":
        check(np.abs(x - np.rint(x)).max() <= tolerance, "x is not binary")
        check(np.abs(x.sum(axis=1) - 1.0).max() <= tolerance, "a customer is not assigned exactly once")
        check(not (used & (capacities[None, :] + tolerance < demands[:, None])).any(),
              "a customer is assigned to a facility smaller than its demand")
        flow = demands[:, None] * x
    else:
        check(np.abs(x.sum(axis=1) - demands).max() <= tolerance, "demand not met")
        flow = x
    check((flow.sum(axis=0) - capacities * y).max() <= tolerance, "capacity exceeded")
    check(not (used & (y[None, :] < 0.5)).any(), "flow to a closed facility")

    if problem == "mscflp-ci":
        a = np.asarray(solution.get("a", used), dtype=float)
        check(np.abs(a - np.rint(a)).max() <= tolerance, "a is not binary")
        check(not (used & (a < 0.5)).any(), "flow without a use variable")
        check(not ((a > 0.5) & (y[None, :] < 0.5)).any(), "use of a closed facility")
        for i, k in instance["incompatible_pairs"]:
            shared = np.flatnonzero((a[i] > 0.5) & (a[k] > 0.5))
            if len(shared):
                errors.append(f"incompatible customers {i + 1} and {k + 1} share facility {shared[0] + 1}")
                break

    fixed_cost = float(instance["fixed_costs"] @ y)
    assignment_cost = float((costs * flow).sum())
    return {
        "valid": not errors,
        "objective": fixed_cost + assignment_cost,
        "fixed_cost": fixed_cost,
        "assignment_cost": assignment_cost,
        "open_facilities": int((y > 0.5).sum()),
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("problem", choices=PROBLEMS)
    parser.add_argument("instance")
    parser.add_argument("solution", help="solution file (.csv.gz)")
    args = parser.parse_args()
    instance = read_instance(args.instance)
    solution = read_solution(args.solution, instance["customers"], instance["facilities"])
    result = validate(instance, solution, args.problem)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["valid"] else 1)


if __name__ == "__main__":
    main()
