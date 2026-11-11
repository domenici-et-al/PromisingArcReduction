"""Readers for the PLC (SSCFLP and MS-CFLP) and DZN (MS-CFLP-CI) instance files."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import numpy as np


NUMBER = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?")
P_NAME = re.compile(r"^p(?P<m>\d+)-(?P<n>\d+)-\d+$")


def read_instance(path: str | Path) -> dict:
    path = Path(path)
    instance = _read_dzn(path) if path.suffix.lower() == ".dzn" else _read_plc(path)
    instance["sha256"] = file_sha256(path)
    return instance


def _read_plc(path: Path) -> dict:
    values = np.fromfile(path, sep=" ", dtype=np.float64)
    first, second = int(values[0]), int(values[1])
    # The header order varies across files; the name p<m>-<n>-<id> resolves it.
    parsed = P_NAME.match(path.stem)
    if parsed and (first, second) == (int(parsed["n"]), int(parsed["m"])):
        n, m = first, second
    else:
        m, n = first, second
    if len(values) != 2 + n + 2 * m + n * m:
        raise ValueError(f"{path}: unexpected number of values")
    demands = values[2:2 + n]
    capacities = values[2 + n:2 + n + m]
    fixed = values[2 + n + m:2 + n + 2 * m]
    costs = values[2 + n + 2 * m:].reshape(m, n).T
    return _instance(path, demands, capacities, fixed, costs)


def _read_dzn(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    capacities = _numbers(_field(text, "Capacity"))
    fixed = _numbers(_field(text, "FixedCost"))
    demands = _numbers(_field(text, "Goods", "Demand"))
    costs = _rows(_field(text, "SupplyCost", "ShippingCost"))
    pairs = [(int(i) - 1, int(k) - 1) for i, k in _rows(_field(text, "IncompatiblePairs"))]
    return _instance(path, demands, capacities, fixed, costs, pairs)


def _instance(path, demands, capacities, fixed, costs, pairs=()):
    return {
        "name": path.stem,
        "customers": len(demands),
        "facilities": len(capacities),
        "demands": np.asarray(demands, dtype=float),
        "capacities": np.asarray(capacities, dtype=float),
        "fixed_costs": np.asarray(fixed, dtype=float),
        "assignment_costs": np.asarray(costs, dtype=float),
        "incompatible_pairs": list(pairs),
    }


def assignment_cost(instance: dict, i: int, j: int) -> float:
    """SSCFLP cost of assigning customer i to facility j (costs are per unit)."""
    return instance["demands"][i] * instance["assignment_costs"][i, j]


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _field(text: str, *names: str) -> str:
    for name in names:
        match = re.search(rf"\b{name}\s*=\s*([^;]*);", text)
        if match:
            return match.group(1)
    raise ValueError(f"DZN field {names[0]} not found")


def _numbers(block: str) -> list[float]:
    return [float(v) for v in NUMBER.findall(block)]


def _rows(block: str) -> list[list[float]]:
    rows = (_numbers(row) for row in re.findall(r"\|([^|]+)", block))
    return [row for row in rows if row]
