"""Full-space optimality certification for an optimal reduced SSCFLP solution.

The procedure solves the LP relaxation while pricing omitted eligible arcs,
uses the resulting full-LP lower bound for reduced-cost fixing, and solves a
verification MIP over every arc that has not been fixed.  A certificate is
reported only if every stage terminates with an optimal status.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from instances import assignment_cost, read_instance
from par import build_candidates
from results import read_solution, sha256, write_csv, write_json, write_solution
from validate import validate


@dataclass(frozen=True)
class Config:
    threads: int = 1
    seed: int = 0
    pricing_time_limit: float = 0.0
    verification_time_limit: float = 0.0
    max_pricing_iterations: int = 100
    reduced_cost_tolerance: float = 1e-7
    relative_proof_tolerance: float = 1e-9
    absolute_proof_tolerance: float = 1e-6


def certify(instance_path: str | Path, solution_path: str | Path, output: str | Path,
            config: Config = Config(), metadata_path: str | Path | None = None) -> dict:
    gp, GRB = _gurobi()
    started = time.time()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    instance = read_instance(instance_path)
    graph = build_candidates(instance, "sscflp", "par")
    solution = read_solution(solution_path, instance["customers"], instance["facilities"])
    check = validate(instance, solution, "sscflp")
    if not check["valid"]:
        raise ValueError(f"The incumbent is infeasible: {check['errors']}")
    if metadata_path:
        metadata = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
        reduced_status = metadata.get("status", metadata.get("solver", {}).get("status"))
        if reduced_status != "optimal":
            raise ValueError("Certification requires an optimally solved reduced model.")
        recorded_hash = metadata.get("graph", {}).get("graph_sha256")
        if recorded_hash and recorded_hash != graph["metadata"]["graph_sha256"]:
            raise ValueError("The rebuilt PAR graph differs from the run metadata.")

    incumbent = float(check["objective"])
    assignments = np.argmax(solution["x"], axis=1).astype(int).tolist()
    pricing = _pricing(instance, graph["candidates"], output, config, gp, GRB)
    proof_tolerance = _proof_tolerance(incumbent, config)
    proof = {
        "instance": instance["name"],
        "status": "inconclusive",
        "certified": False,
        "reduced_objective": incumbent,
        "par_arcs": graph["metadata"]["candidate_arcs"],
        "graph_sha256": graph["metadata"]["graph_sha256"],
        "instance_sha256": instance["sha256"],
        "incumbent_solution_sha256": sha256(solution_path),
        "gurobi_version": ".".join(map(str, gp.gurobi.version())),
        "pricing_status": pricing["status"],
        "pricing_lower_bound": pricing["lower_bound"],
        "pricing_iterations": pricing["iterations"],
        "pricing_added_arcs": len(pricing["added_final_state"]),
        "pricing_time": pricing["runtime"],
        "reduced_cost_tolerance": config.reduced_cost_tolerance,
        "proof_tolerance": proof_tolerance,
    }
    if pricing["status"] != "optimal":
        proof["total_time"] = time.time() - started
        write_json(output / "proof.json", proof)
        return proof

    lower_bound = float(pricing["lower_bound"])
    if lower_bound > incumbent + proof_tolerance:
        raise ValueError("The priced LP lower bound exceeds the validated incumbent.")
    budget = max(0.0, incumbent - lower_bound)
    fixed_facilities = {
        j for j, (value, rc) in enumerate(zip(pricing["facility_values"], pricing["facility_rc"]))
        if value <= 1e-8 and rc > budget + config.reduced_cost_tolerance
    }
    external = set()
    fixed_omitted = 0
    for i, j, rc in pricing["omitted_rc"]:
        if j in fixed_facilities or rc > budget + config.reduced_cost_tolerance:
            fixed_omitted += 1
        else:
            external.add((i, j))
    par_sets = [set(row) for row in graph["candidates"]]
    for i, j, value, rc in pricing["added_final_state"]:
        if j in par_sets[i]:
            continue
        if j in fixed_facilities or (value <= 1e-8 and rc > budget + config.reduced_cost_tolerance):
            fixed_omitted += 1
        else:
            external.add((i, j))
    write_csv(output / "unfixed_omitted_arcs.csv.gz", (
        {"customer": i + 1, "facility": j + 1} for i, j in sorted(external)
    ), ["customer", "facility"])

    verification = _verification(instance, graph["candidates"], external, assignments,
                                 incumbent, output, config, gp, GRB)
    proof.update({
        "pricing_gap": budget,
        "fixed_zero_facilities": len(fixed_facilities),
        "fixed_omitted_arcs": fixed_omitted,
        "unfixed_omitted_arcs": len(external),
        "verification_status": verification["status"],
        "verification_arcs": verification["arcs"],
        "verification_objective": verification.get("objective"),
        "verification_bound": verification.get("bound"),
        "verification_nodes": verification.get("nodes"),
        "verification_time": verification["runtime"],
        "certified": verification["certified"],
        "status": "certified_improved" if verification["certified"] and verification["objective"] < incumbent - proof_tolerance
                  else "certified" if verification["certified"] else "inconclusive",
        "certified_objective": verification["objective"] if verification["certified"] else None,
        "total_time": time.time() - started,
    })
    if verification.get("solution") is not None:
        x, y = verification["solution"]
        write_solution(output / "solution", instance["name"], x, y, dense=False)
    write_json(output / "proof.json", proof)
    return proof


def _pricing(instance, candidates, output, config, gp, GRB):
    started = time.time()
    n, m = instance["customers"], instance["facilities"]
    active = [set(row) for row in candidates]
    model = gp.Model(f"par_pricing_{instance['name']}")
    model.Params.OutputFlag = 1
    model.Params.LogToConsole = 0
    model.Params.LogFile = str(output / "pricing.log")
    model.Params.Threads = config.threads
    model.Params.Method = 1
    model.Params.Presolve = 1
    y = model.addVars(range(m), lb=0, ub=1, obj=instance["fixed_costs"], name="y")
    assign_rows = {i: model.addConstr(gp.LinExpr() == 1, name=f"assign[{i}]") for i in range(n)}
    capacity_rows = {j: model.addConstr(-instance["capacities"][j] * y[j] <= 0,
                                        name=f"capacity[{j}]") for j in range(m)}
    x = {}
    for i in range(n):
        for j in sorted(active[i]):
            _add_lp_arc(model, x, y, assign_rows, capacity_rows, instance, i, j, gp)
    model.ModelSense = GRB.MINIMIZE
    model.update()
    iterations, added = [], []
    final_omitted, lower_bound, status = [], math.nan, "iteration_limit"
    for iteration in range(1, config.max_pricing_iterations + 1):
        if config.pricing_time_limit:
            remaining = config.pricing_time_limit - (time.time() - started)
            if remaining <= 0:
                status = "time_limit"
                break
            model.Params.TimeLimit = remaining
        model.optimize()
        if model.Status != GRB.OPTIMAL:
            status = _status(model.Status, GRB)
            break
        lower_bound = float(model.ObjVal)
        assign_pi = [assign_rows[i].Pi for i in range(n)]
        capacity_pi = [capacity_rows[j].Pi for j in range(m)]
        omitted, negative = [], []
        for i in range(n):
            for j in range(m):
                if j in active[i] or instance["capacities"][j] + 1e-9 < instance["demands"][i]:
                    continue
                rc = assignment_cost(instance, i, j) - assign_pi[i] - instance["demands"][i] * capacity_pi[j]
                omitted.append((i, j, rc))
                if rc < -config.reduced_cost_tolerance:
                    negative.append((i, j, rc))
        iterations.append({"iteration": iteration, "lower_bound": lower_bound,
                           "active_arcs": sum(map(len, active)), "omitted_arcs": len(omitted),
                           "negative_arcs": len(negative), "elapsed_seconds": time.time() - started})
        write_csv(output / "pricing_iterations.csv", iterations)
        if not negative:
            status, final_omitted = "optimal", omitted
            break
        for i, j, _ in negative:
            active[i].add(j)
            added.append((i, j))
            _add_lp_arc(model, x, y, assign_rows, capacity_rows, instance, i, j, gp)
        model.update()
    result = {
        "status": status,
        "lower_bound": lower_bound,
        "iterations": len(iterations),
        "omitted_rc": final_omitted,
        "facility_values": [float(y[j].X) for j in range(m)] if status == "optimal" else [],
        "facility_rc": [float(y[j].RC) for j in range(m)] if status == "optimal" else [],
        "added_final_state": [(i, j, float(x[i, j].X), float(x[i, j].RC)) for i, j in added]
                             if status == "optimal" else [],
        "runtime": time.time() - started,
    }
    model.dispose()
    return result


def _add_lp_arc(model, x, y, assign_rows, capacity_rows, instance, i, j, gp):
    column = gp.Column([1.0, instance["demands"][i]], [assign_rows[i], capacity_rows[j]])
    variable = model.addVar(lb=0, ub=1, obj=assignment_cost(instance, i, j),
                            column=column, name=f"x[{i},{j}]")
    model.addConstr(variable <= y[j], name=f"link[{i},{j}]")
    x[i, j] = variable


def _verification(instance, par_candidates, external, incumbent_assignment, incumbent,
                  output, config, gp, GRB):
    started = time.time()
    n, m = instance["customers"], instance["facilities"]
    sets = [set(row) for row in par_candidates]
    for i, j in external:
        sets[i].add(j)
    arcs = [(i, j) for i in range(n) for j in sorted(sets[i])]
    model = gp.Model(f"par_verification_{instance['name']}")
    model.Params.OutputFlag = 1
    model.Params.LogToConsole = 0
    model.Params.LogFile = str(output / "verification.log")
    model.Params.Threads = config.threads
    model.Params.Seed = config.seed
    model.Params.MIPGap = 0
    model.Params.MIPGapAbs = max(1e-9, _proof_tolerance(incumbent, config) * 0.01)
    model.Params.FeasibilityTol = 1e-9
    model.Params.IntFeasTol = 1e-9
    model.Params.OptimalityTol = 1e-9
    model.Params.DualReductions = 0
    if config.verification_time_limit:
        model.Params.TimeLimit = config.verification_time_limit
    x = model.addVars(arcs, vtype=GRB.BINARY, name="x")
    y = model.addVars(range(m), vtype=GRB.BINARY, name="y")
    model.setObjective(gp.quicksum(instance["fixed_costs"][j] * y[j] for j in range(m))
                       + gp.quicksum(assignment_cost(instance, i, j) * x[i, j] for i, j in arcs))
    for i in range(n):
        model.addConstr(gp.quicksum(x[i, j] for j in sets[i]) == 1)
    by_facility = [[] for _ in range(m)]
    for i, j in arcs:
        model.addConstr(x[i, j] <= y[j])
        by_facility[j].append(i)
    for j in range(m):
        model.addConstr(gp.quicksum(instance["demands"][i] * x[i, j] for i in by_facility[j])
                        <= instance["capacities"][j] * y[j])
    opened = set(incumbent_assignment)
    for i, j in enumerate(incumbent_assignment):
        x[i, j].Start = 1
    for j in range(m):
        y[j].Start = int(j in opened)
    model.optimize()
    certified = model.Status == GRB.OPTIMAL
    objective = float(model.ObjVal) if model.SolCount else math.inf
    solution = None
    if certified:
        dense_x = np.zeros((n, m))
        for (i, j), variable in x.items():
            dense_x[i, j] = variable.X
        dense_y = np.array([y[j].X for j in range(m)])
        solution = dense_x, dense_y
    result = {"status": _status(model.Status, GRB), "certified": certified,
              "objective": objective, "bound": _attr(model, "ObjBound"),
              "nodes": _attr(model, "NodeCount"), "arcs": len(arcs),
              "runtime": time.time() - started, "solution": solution}
    model.dispose()
    return result


def _proof_tolerance(objective, config):
    return max(config.absolute_proof_tolerance, config.relative_proof_tolerance * abs(objective))


def _gurobi():
    try:
        import gurobipy as gp
        from gurobipy import GRB
    except ImportError as exc:
        raise RuntimeError("gurobipy is required for certification.") from exc
    return gp, GRB


def _attr(model, name):
    try:
        value = getattr(model, name)
        return value if not isinstance(value, float) or math.isfinite(value) else None
    except Exception:
        return None


def _status(status, GRB):
    return {GRB.OPTIMAL: "optimal", GRB.TIME_LIMIT: "time_limit", GRB.INFEASIBLE: "infeasible",
            GRB.INTERRUPTED: "interrupted", GRB.MEM_LIMIT: "memory_limit"}.get(status, str(status))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("instance")
    parser.add_argument("solution")
    parser.add_argument("--metadata")
    parser.add_argument("--output", required=True)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--pricing-time-limit", type=float, default=0)
    parser.add_argument("--verification-time-limit", type=float, default=0)
    args = parser.parse_args()
    config = Config(threads=args.threads, seed=args.seed,
                    pricing_time_limit=args.pricing_time_limit,
                    verification_time_limit=args.verification_time_limit)
    proof = certify(args.instance, args.solution, args.output, config, args.metadata)
    print(f"{proof['instance']}: {proof['status']} objective={proof.get('certified_objective')}")


if __name__ == "__main__":
    main()
