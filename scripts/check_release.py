"""Check the released runs and certificates against the benchmark instances.

For every released run, rebuild the PAR graph and compare it with the recorded
hash, then validate the released solution and, when there is one, the optimal
solution of its certificate, and compare the recomputed costs with the recorded ones.

    python scripts/check_release.py DIR [--workers 8]

DIR is searched recursively for the .plc and .dzn instance files.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from instances import read_instance  # noqa: E402
from par import PROBLEMS, build_candidates  # noqa: E402
from results import read_solution  # noqa: E402
from validate import validate  # noqa: E402


def check(problem: str, name: str, path: Path) -> list[str]:
    instance = read_instance(path)
    metadata = json.loads((ROOT / "artifacts/metadata" / problem / f"{name}.json").read_text())
    errors = []
    # MS-CFLP records keep only the arc count, the others also the graph hash.
    graph = build_candidates(instance, problem)["metadata"]
    for key in ("candidate_arcs", "graph_sha256"):
        if key in metadata["graph"] and graph[key] != metadata["graph"][key]:
            errors.append(f"PAR graph differs from the released one ({key})")

    files = [(ROOT / "artifacts/solutions" / problem / "sparse" / f"{name}.csv.gz",
              metadata["released_solution"]["objective"])]
    certificate = ROOT / "certificates" / problem / "records" / name
    if (certificate / "certificate.json").exists():
        recorded = json.loads((certificate / "certificate.json").read_text())["objective"]
        files.append((certificate / "optimal_solution.csv.gz", recorded))
    for file, recorded in files:
        solution = read_solution(file, instance["customers"], instance["facilities"])
        result = validate(instance, solution, problem)
        if not result["valid"]:
            errors.append(f"{file.relative_to(ROOT)}: {result['errors']}")
        elif abs(result["objective"] - recorded) > max(1e-6, 1e-9 * abs(recorded)):
            errors.append(f"{file.relative_to(ROOT)}: cost {result['objective']} != recorded {recorded}")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("instances", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--problems", nargs="+", choices=PROBLEMS, default=PROBLEMS)
    args = parser.parse_args()

    files = {p.stem: p for p in args.instances.rglob("*") if p.suffix in (".plc", ".dzn")}
    tasks = []
    for problem in args.problems:
        for record in sorted((ROOT / "artifacts/metadata" / problem).glob("*.json")):
            tasks.append((problem, record.stem, files.get(record.stem)))
    missing = [name for _, name, path in tasks if path is None]
    if missing:
        raise SystemExit(f"instance files not found: {', '.join(missing[:10])}")

    failures = 0
    with ProcessPoolExecutor(args.workers) as pool:
        for (problem, name, _), errors in zip(tasks, pool.map(check, *zip(*tasks))):
            for error in errors:
                print(f"{problem} {name}: {error}", flush=True)
            failures += bool(errors)
    print(f"{len(tasks)} runs checked, {failures} with problems")
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
