"""Run the frozen PAR protocols for SSCFLP, MS-CFLP, and MS-CFLP-CI."""

from __future__ import annotations

import argparse
import csv
import math
import platform
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from instances import assignment_cost, read_instance
from par import GRAPH_VARIANTS, PROBLEMS, build_candidates
from results import SCHEMA_VERSION, sha256, write_json, write_solution
from validate import validate


POSTPROCESS_RESERVE = 3.0


def solve(instance_path: str | Path, output: str | Path, problem: str,
          variant: str = "par", time_limit: float | None = None, threads: int = 1,
          seed: int = 0, warm_start: bool | None = None) -> dict:
    gp, GRB = _gurobi()
    started = time.time()
    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    instance_path, output = Path(instance_path), Path(output)
    instance = read_instance(instance_path)
    if time_limit is None:
        time_limit = 10.0 * math.sqrt(instance["facilities"]) if problem == "mscflp-ci" else 600.0
    if warm_start is None:
        warm_start = problem == "sscflp"
    if warm_start and problem != "sscflp":
        raise ValueError("The published constructive initialization is used only for SSCFLP.")
    deadline = started + time_limit
    graph = build_candidates(instance, problem, variant)
    run = output / problem / instance["name"]
    run.mkdir(parents=True, exist_ok=True)

    warm = _construct_sscflp_start(instance, graph["candidates"], run, deadline,
                                   threads, seed, gp, GRB) if warm_start else {
        "status": "disabled", "time": 0.0, "assignment": None, "log": None
    }
    model_data = _build_model(instance, graph["candidates"], problem, gp, GRB)
    model = model_data["model"]
    log_path = run / "gurobi.log"
    model.Params.OutputFlag = 1
    model.Params.LogToConsole = 0
    model.Params.LogFile = str(log_path)
    model.Params.Threads = threads
    model.Params.Seed = seed
    model.Params.MIPGap = 0.0
    model.Params.MIPGapAbs = 1e-6
    if problem == "sscflp":
        model.Params.MIPFocus = 1
        model.Params.Heuristics = 0.8
    if warm["assignment"] is not None:
        _apply_sscflp_start(warm["assignment"], model_data)

    model.Params.TimeLimit = max(0.01, deadline - time.time() - POSTPROCESS_RESERVE)
    progress_path = run / "progress.csv"
    callback = _progress_callback(started, deadline, time_limit, progress_path, gp, GRB)
    error = None
    try:
        model.optimize(callback)
    except gp.GurobiError as exc:
        error = {"code": getattr(exc, "errno", None), "message": str(exc)}
    _append_progress(progress_path, time.time() - started, "final", model, GRB)

    has_solution = model.SolCount > 0
    solution_files, validation = {}, {}
    if has_solution:
        x, y, a = _extract_solution(instance, problem, model_data)
        solution_files = write_solution(run / "solutions", instance["name"], x, y, a)
        validation = validate(instance, {"x": x, "y": y, **({"a": a} if a is not None else {})}, problem)

    status = "solver_error_with_incumbent" if error and has_solution else (
        "solver_error" if error else _status(model.Status, GRB)
    )
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "instance": instance["name"],
        "problem": problem,
        "method": "PAR",
        "graph_variant": variant,
        "started_at": started_at,
        "finished_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "status": status,
        "has_solution": has_solution,
        "objective": _attr(model, "ObjVal") if has_solution else None,
        "best_bound": _attr(model, "ObjBound"),
        "mip_gap": _attr(model, "MIPGap") if has_solution else None,
        "nodes": _attr(model, "NodeCount"),
        "solutions_found": _attr(model, "SolCount"),
        "gurobi_time": _attr(model, "Runtime"),
        "end_to_end_time": time.time() - started,
        "time_limit": time_limit,
        "threads": threads,
        "seed": seed,
        "constructive_initialization": bool(warm_start),
        "warm_start": {
            **{key: value for key, value in warm.items() if key not in {"assignment", "log"}},
            "log": str(Path(warm["log"]).relative_to(output)).replace("\\", "/") if warm.get("log") else None,
        },
        "solver_error": error,
        "instance_file": instance_path.name,
        "instance_sha256": instance["sha256"],
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "gurobi_version": ".".join(map(str, gp.gurobi.version())),
        "graph": graph["metadata"],
        "parameters": {
            "facility_pressure": graph["pressures"],
            "facility_availability": graph["availability"],
            "customer_congestion": graph["congestion"],
            "customer_target": graph["targets"],
            "inherited_width": graph["inherited_widths"],
            "retained_width": graph["widths"],
            "conflict_degree": graph["conflict_degrees"],
        },
        "files": {
            "logs": [
                {"path": str(log_path.relative_to(output)).replace("\\", "/"), "sha256": sha256(log_path)},
                *([{"path": str(Path(warm["log"]).relative_to(output)).replace("\\", "/"),
                    "sha256": sha256(warm["log"])}] if warm.get("log") else []),
            ],
            "progress": {"path": str(progress_path.relative_to(output)).replace("\\", "/"),
                         "sha256": sha256(progress_path)},
            **{key: str(path.relative_to(output)) if isinstance(path, Path) else path
               for key, path in solution_files.items()},
        },
        "validation": validation,
    }
    metadata_path = run / "metadata.json"
    write_json(metadata_path, metadata)
    model.dispose()
    return metadata


def _build_model(instance, candidates, problem, gp, GRB):
    n, m = instance["customers"], instance["facilities"]
    arcs = [(i, j) for i, row in enumerate(candidates) for j in row]
    by_facility = [[] for _ in range(m)]
    for i, j in arcs:
        by_facility[j].append(i)
    model = gp.Model(f"par_{problem}_{instance['name']}")
    y = model.addVars(range(m), vtype=GRB.BINARY, name="y")
    if problem == "sscflp":
        x = model.addVars(arcs, vtype=GRB.BINARY, name="x")
        a = None
        model.setObjective(
            gp.quicksum(instance["fixed_costs"][j] * y[j] for j in range(m))
            + gp.quicksum(assignment_cost(instance, i, j) * x[i, j] for i, j in arcs),
            GRB.MINIMIZE,
        )
        for i in range(n):
            model.addConstr(gp.quicksum(x[i, j] for j in candidates[i]) == 1, name=f"assign[{i}]")
        for j in range(m):
            model.addConstr(gp.quicksum(instance["demands"][i] * x[i, j] for i in by_facility[j])
                            <= instance["capacities"][j] * y[j], name=f"capacity[{j}]")
        for i, j in arcs:
            model.addConstr(x[i, j] <= y[j], name=f"link[{i},{j}]")
    else:
        x = model.addVars(arcs, lb=0.0, vtype=GRB.CONTINUOUS, name="x")
        a = model.addVars(arcs, vtype=GRB.BINARY, name="a") if problem == "mscflp-ci" else None
        model.setObjective(
            gp.quicksum(instance["fixed_costs"][j] * y[j] for j in range(m))
            + gp.quicksum(instance["assignment_costs"][i][j] * x[i, j] for i, j in arcs),
            GRB.MINIMIZE,
        )
        for i in range(n):
            model.addConstr(gp.quicksum(x[i, j] for j in candidates[i]) == instance["demands"][i],
                            name=f"demand[{i}]")
        for j in range(m):
            model.addConstr(gp.quicksum(x[i, j] for i in by_facility[j])
                            <= instance["capacities"][j] * y[j], name=f"capacity[{j}]")
        for i, j in arcs:
            if a is None:
                model.addConstr(x[i, j] <= min(instance["demands"][i], instance["capacities"][j]) * y[j],
                                name=f"link[{i},{j}]")
            else:
                model.addConstr(x[i, j] <= min(instance["demands"][i], instance["capacities"][j]) * a[i, j],
                                name=f"flow_use[{i},{j}]")
                model.addConstr(a[i, j] <= y[j], name=f"use_open[{i},{j}]")
        if a is not None:
            sets = [set(row) for row in candidates]
            for i, k in instance["incompatible_pairs"]:
                for j in sets[i] & sets[k]:
                    model.addConstr(a[i, j] + a[k, j] <= y[j], name=f"conflict[{i},{k},{j}]")
    model.update()
    return {"model": model, "x": x, "y": y, "a": a, "arcs": arcs}


def _construct_sscflp_start(instance, candidates, run, deadline, threads, seed, gp, GRB):
    started = time.time()
    model = gp.Model(f"par_initializer_{instance['name']}")
    log = run / "warm_start.log"
    model.Params.OutputFlag = 1
    model.Params.LogToConsole = 0
    model.Params.LogFile = str(log)
    model.Params.Threads = threads
    model.Params.Seed = seed
    model.Params.MIPFocus = 1
    model.Params.Heuristics = 1.0
    model.Params.SolutionLimit = 1
    model.Params.TimeLimit = max(0.01, deadline - time.time() - POSTPROCESS_RESERVE)
    arcs = [(i, j) for i, row in enumerate(candidates) for j in row]
    by_facility = [[] for _ in range(instance["facilities"])]
    for i, j in arcs:
        by_facility[j].append(i)
    x = model.addVars(arcs, vtype=GRB.BINARY, name="x")
    model.setObjective(gp.quicksum(assignment_cost(instance, i, j) * x[i, j] for i, j in arcs))
    for i, row in enumerate(candidates):
        model.addConstr(gp.quicksum(x[i, j] for j in row) == 1)
    for j in range(instance["facilities"]):
        model.addConstr(gp.quicksum(instance["demands"][i] * x[i, j]
                                    for i in by_facility[j])
                        <= instance["capacities"][j])
    model.optimize()
    assignment = None
    if model.SolCount:
        assignment = [max(candidates[i], key=lambda j: x[i, j].X) for i in range(instance["customers"])]
    result = {
        "status": _status(model.Status, GRB),
        "time": time.time() - started,
        "objective": _attr(model, "ObjVal") if model.SolCount else None,
        "log": str(log),
        "assignment": assignment,
    }
    model.dispose()
    return result


def _apply_sscflp_start(assignment, data):
    opened = set(assignment)
    for (i, j), variable in data["x"].items():
        variable.Start = 1.0 if assignment[i] == j else 0.0
    for j, variable in data["y"].items():
        variable.Start = 1.0 if j in opened else 0.0


def _extract_solution(instance, problem, data):
    n, m = instance["customers"], instance["facilities"]
    x = np.zeros((n, m), dtype=float)
    for (i, j), variable in data["x"].items():
        x[i, j] = variable.X
    y = np.array([data["y"][j].X for j in range(m)], dtype=float)
    a = None
    if data["a"] is not None:
        a = np.zeros((n, m), dtype=float)
        for (i, j), variable in data["a"].items():
            a[i, j] = variable.X
    return x, y, a


def _progress_callback(started, deadline, budget, path, gp, GRB):
    interval = 60.0 if budget >= 300 else max(1.0, budget / 10.0)
    state = {"next": interval}
    def callback(model, where):
        elapsed = time.time() - started
        if elapsed >= deadline - started:
            model.terminate()
        if where not in (GRB.Callback.MIP, GRB.Callback.MIPSOL) or elapsed < state["next"]:
            return
        if where == GRB.Callback.MIPSOL:
            objective = model.cbGet(GRB.Callback.MIPSOL_OBJ)
            bound = model.cbGet(GRB.Callback.MIPSOL_OBJBND)
            nodes = model.cbGet(GRB.Callback.MIPSOL_NODCNT)
            solutions = ""
        else:
            objective = model.cbGet(GRB.Callback.MIP_OBJBST)
            bound = model.cbGet(GRB.Callback.MIP_OBJBND)
            nodes = model.cbGet(GRB.Callback.MIP_NODCNT)
            solutions = int(model.cbGet(GRB.Callback.MIP_SOLCNT))
        _append_progress_values(path, elapsed, "checkpoint", objective, bound, nodes, solutions)
        state["next"] += interval
    return callback


def _append_progress(path, elapsed, event, model, GRB):
    objective = _attr(model, "ObjVal") if model.SolCount else math.inf
    _append_progress_values(path, elapsed, event, objective, _attr(model, "ObjBound"),
                            _attr(model, "NodeCount"), _attr(model, "SolCount"))


def _append_progress_values(path, elapsed, event, objective, bound, nodes, solutions):
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    finite_obj = objective if math.isfinite(float(objective)) else ""
    gap = "" if finite_obj == "" or not math.isfinite(float(bound)) else abs(float(objective) - float(bound)) / max(1e-12, abs(float(objective)))
    with path.open("a", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        if not exists:
            writer.writerow(["elapsed_seconds", "event", "incumbent", "best_bound", "gap", "nodes", "solutions"])
        writer.writerow([elapsed, event, finite_obj, bound, gap, nodes, solutions])


def _gurobi():
    try:
        import gurobipy as gp
        from gurobipy import GRB
    except ImportError as exc:
        raise RuntimeError("gurobipy is required to solve PAR models.") from exc
    return gp, GRB


def _attr(model, name):
    try:
        value = getattr(model, name)
        return value if not isinstance(value, float) or math.isfinite(value) else None
    except Exception:
        return None


def _status(status, GRB):
    return {GRB.OPTIMAL: "optimal", GRB.TIME_LIMIT: "time_limit", GRB.INFEASIBLE: "infeasible",
            GRB.INTERRUPTED: "interrupted", GRB.SOLUTION_LIMIT: "solution_limit",
            GRB.MEM_LIMIT: "memory_limit"}.get(status, str(status))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("problem", choices=PROBLEMS)
    parser.add_argument("instances", nargs="+")
    parser.add_argument("--output", default="runs")
    parser.add_argument("--variant", choices=GRAPH_VARIANTS, default="par")
    parser.add_argument("--time-limit", type=float)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--warm-start", action=argparse.BooleanOptionalAction, default=None)
    args = parser.parse_args()
    for path in args.instances:
        result = solve(path, args.output, args.problem, args.variant, args.time_limit,
                       args.threads, args.seed, args.warm_start)
        print(f"{result['instance']}: {result['status']} objective={result['objective']}", flush=True)


if __name__ == "__main__":
    main()
