"""Full-model optimality certificate for MS-CFLP.

The PAR graph is used only to obtain an input incumbent.  Certification solves
the complete multi-source model over every customer-facility pair; a
certificate is issued only when Gurobi proves that model optimal and the
returned primal vector passes the independent validator.
"""

from __future__ import annotations

import argparse
import math
import platform
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

from instances import assignment_cost, read_instance
from results import read_solution, sha256, write_json, write_solution
from validate import validate


@dataclass(frozen=True)
class Config:
    threads: int = 1
    seed: int = 0
    time_limit: float = 0.0
    relative_proof_tolerance: float = 1e-9
    absolute_proof_tolerance: float = 1e-6
    max_full_arcs: int = 4_000_000


def certify(instance_path: str | Path, solution_path: str | Path,
            output: str | Path, config: Config = Config()) -> dict:
    gp, GRB = _gurobi()
    started = time.time()
    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    instance_path = Path(instance_path)
    solution_path = Path(solution_path)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)

    instance = read_instance(instance_path)
    incumbent = read_solution(
        solution_path, instance["customers"], instance["facilities"]
    )
    incumbent_check = validate(instance, incumbent, "mscflp")
    if not incumbent_check["valid"]:
        raise ValueError(
            f"The input incumbent is infeasible: {incumbent_check['errors']}"
        )

    n, m = instance["customers"], instance["facilities"]
    full_arcs = n * m
    if config.max_full_arcs and full_arcs > config.max_full_arcs:
        raise ValueError(
            f"The full model has {full_arcs:,} assignment arcs, above "
            f"--max-full-arcs {config.max_full_arcs:,}. Set the option to zero "
            "to disable this guard."
        )

    log_path = output / "gurobi.log"
    model_data = _build_full_model(instance, log_path, config, gp, GRB)
    model = model_data["model"]
    _apply_start(incumbent, model_data)

    error = None
    try:
        model.optimize()
    except gp.GurobiError as exc:
        error = {"code": getattr(exc, "errno", None), "message": str(exc)}

    status = _status(model.Status, GRB) if error is None else "solver_error"
    has_solution = model.SolCount > 0
    objective = _attr(model, "ObjVal") if has_solution else None
    bound = _attr(model, "ObjBound")
    proof_tolerance = _proof_tolerance(
        objective if objective is not None else incumbent_check["objective"], config
    )
    bound_matches = (
        objective is not None and bound is not None
        and abs(objective - bound) <= proof_tolerance
    )

    solution_files: dict = {}
    final_check = {"valid": False, "errors": ["No full-space incumbent was returned."]}
    if has_solution:
        final_solution = _extract_solution(instance, model_data)
        final_check = validate(instance, final_solution, "mscflp")
        solution_files = write_solution(
            output / "solution", instance["name"],
            final_solution["x"], final_solution["y"], dense=False,
        )

    primal_matches = (
        objective is not None and final_check.get("valid", False)
        and abs(final_check["objective"] - objective) <= proof_tolerance
    )
    certified = (
        error is None and model.Status == GRB.OPTIMAL
        and bound_matches and primal_matches and final_check["valid"]
    )
    improved = (
        certified and objective is not None
        and objective < incumbent_check["objective"] - proof_tolerance
    )
    runtime = _attr(model, "Runtime")
    nodes = _attr(model, "NodeCount")
    solver_gap = _attr(model, "MIPGap") if has_solution else None
    model.dispose()

    classification = (
        "improved_certified" if improved
        else "par_certified" if certified
        else "inconclusive"
    )
    certificate = {
        "schema_version": "1.0",
        "problem": "mscflp",
        "instance": instance["name"],
        "method": "M1",
        "status": "certified_global_optimum" if certified else "inconclusive",
        "solver_status": status,
        "classification": classification,
        "certified": certified,
        "proof_basis": "global_MIP_bound" if certified else None,
        "started_at": started_at,
        "finished_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "input_incumbent_objective": incumbent_check["objective"],
        "objective": objective,
        "best_bound": bound,
        "solver_gap": solver_gap,
        "proof_tolerance": proof_tolerance,
        "objective_bound_consistent": bound_matches,
        "recomputed_objective_consistent": primal_matches,
        "runtime_gurobi": runtime,
        "total_time": time.time() - started,
        "nodes": nodes,
        "threads": config.threads,
        "seed": config.seed,
        "time_limit": config.time_limit or None,
        "customers": n,
        "facilities": m,
        "full_assignment_arcs": full_arcs,
        "validation": final_check,
        "solver_error": error,
        "instance_file": instance_path.name,
        "instance_sha256": instance["sha256"],
        "input_solution_sha256": sha256(solution_path),
        "gurobi_version": ".".join(map(str, gp.gurobi.version())),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "source_sha256": _source_hashes(),
        "files": {
            "gurobi_log": _file_record(log_path, output),
            **_solution_records(solution_files, output),
        },
        "note": (
            "Complete MS-CFLP model. PAR supplies the incumbent; M1 proves "
            "the original-space optimum."
        ),
    }
    write_json(output / "certificate.json", certificate)
    return certificate


def _build_full_model(instance, log_path, config, gp, GRB):
    n, m = instance["customers"], instance["facilities"]
    arcs = gp.tuplelist((i, j) for i in range(n) for j in range(m))
    model = gp.Model(f"full_mscflp_{instance['name']}")
    model.Params.OutputFlag = 1
    model.Params.LogToConsole = 0
    model.Params.LogFile = str(log_path)
    model.Params.Threads = config.threads
    model.Params.Seed = config.seed
    model.Params.MIPGap = 0.0
    model.Params.MIPGapAbs = 0.0
    model.Params.FeasibilityTol = 1e-9
    model.Params.IntFeasTol = 1e-9
    model.Params.OptimalityTol = 1e-9
    model.Params.DualReductions = 0
    if config.time_limit:
        model.Params.TimeLimit = config.time_limit

    x = model.addVars(arcs, lb=0.0, vtype=GRB.CONTINUOUS, name="x")
    y = model.addVars(range(m), vtype=GRB.BINARY, name="y")
    model.setObjective(
        gp.quicksum(instance["fixed_costs"][j] * y[j] for j in range(m))
        + gp.quicksum(assignment_cost(instance, i, j) * x[i, j] for i, j in arcs),
        GRB.MINIMIZE,
    )
    for i in range(n):
        model.addConstr(
            gp.quicksum(x[i, j] for j in range(m)) == instance["demands"][i],
            name=f"demand[{i}]",
        )
    for j in range(m):
        model.addConstr(
            gp.quicksum(x[i, j] for i in range(n))
            <= instance["capacities"][j] * y[j],
            name=f"capacity[{j}]",
        )
    for i, j in arcs:
        upper = min(instance["demands"][i], instance["capacities"][j])
        model.addConstr(x[i, j] <= upper * y[j], name=f"link[{i},{j}]")
    model.update()
    return {"model": model, "x": x, "y": y, "arcs": arcs}


def _apply_start(solution, data):
    x_values = np.asarray(solution["x"], dtype=float)
    y_values = np.asarray(solution["y"], dtype=float)
    for (i, j), variable in data["x"].items():
        variable.Start = float(x_values[i, j])
    for j, variable in data["y"].items():
        variable.Start = 1.0 if y_values[j] > 0.5 else 0.0


def _extract_solution(instance, data):
    n, m = instance["customers"], instance["facilities"]
    x = np.zeros((n, m), dtype=float)
    for i, j in data["arcs"]:
        x[i, j] = data["x"][i, j].X
    y = np.array([data["y"][j].X for j in range(m)], dtype=float)
    return {"x": x, "y": y}


def _solution_records(files, root):
    records = {}
    path = files.get("sparse")
    if path:
        records["solution_sparse"] = _file_record(path, root)
    return records


def _source_hashes():
    source = Path(__file__).resolve().parent
    return {
        name: sha256(source / name)
        for name in ("certify_mscflp.py", "instances.py", "results.py", "validate.py")
    }


def _file_record(path, root):
    path = Path(path)
    if not path.exists():
        return None
    return {"path": path.relative_to(root).as_posix(), "sha256": sha256(path)}


def _proof_tolerance(objective, config):
    return max(config.absolute_proof_tolerance,
               config.relative_proof_tolerance * abs(objective))


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
    return {
        GRB.OPTIMAL: "optimal",
        GRB.TIME_LIMIT: "time_limit",
        GRB.INFEASIBLE: "infeasible",
        GRB.INTERRUPTED: "interrupted",
        GRB.MEM_LIMIT: "memory_limit",
        GRB.SOLUTION_LIMIT: "solution_limit",
    }.get(status, str(status))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("instance")
    parser.add_argument("solution")
    parser.add_argument("--output", required=True)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--time-limit", type=float, default=0)
    parser.add_argument("--max-full-arcs", type=int, default=4_000_000,
                        help="resource guard; zero disables it")
    args = parser.parse_args()
    config = Config(
        threads=args.threads,
        seed=args.seed,
        time_limit=args.time_limit,
        max_full_arcs=args.max_full_arcs,
    )
    result = certify(args.instance, args.solution, args.output, config)
    print(
        f"{result['instance']}: {result['status']} "
        f"objective={result.get('objective')} bound={result.get('best_bound')}"
    )


if __name__ == "__main__":
    main()
