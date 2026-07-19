"""Instance readers shared by the three PAR formulations.

The public artifact does not redistribute benchmark instances.  This module
reads the Guastaroba--Speranza PLC format, OR-Library cap instances, and the
MiniZinc DZN files used by the incompatibility extension.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Iterator

import numpy as np


NUMBER = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?")
P_NAME = re.compile(r"^p(?P<m>\d+)-(?P<n>\d+)-(?P<id>\d+)$")


def read_instance(path: str | Path) -> dict:
    path = Path(path)
    if path.suffix.lower() == ".plc":
        instance = _read_plc(path)
    elif path.suffix.lower() == ".dzn":
        instance = _read_dzn(path)
    else:
        instance = _read_orlib(path)
    validate_instance(instance)
    instance["sha256"] = file_sha256(path)
    return instance


def _read_plc(path: Path) -> dict:
    values = np.fromfile(path, sep=" ", dtype=np.float64)
    if len(values) < 2:
        raise ValueError(f"Missing PLC dimensions in {path}.")
    first, second = int(values[0]), int(values[1])
    parsed = P_NAME.match(path.stem)
    if parsed and first == int(parsed.group("n")) and second == int(parsed.group("m")):
        customers, facilities = first, second
        orientation = "customers_first"
    else:
        facilities, customers = first, second
        orientation = "facilities_first"

    expected = 2 + customers + 2 * facilities + customers * facilities
    if len(values) != expected:
        raise ValueError(f"{path} contains {len(values)} numeric values; expected {expected}.")
    offset = 2
    demands = values[offset:offset + customers]
    offset += customers
    capacities = values[offset:offset + facilities]
    offset += facilities
    fixed = values[offset:offset + facilities]
    offset += facilities
    costs = values[offset:].reshape(facilities, customers).T
    return _instance(path, customers, facilities, demands, capacities, fixed, costs,
                     [], "plc", "per_unit", orientation)


def _read_orlib(path: Path) -> dict:
    values = _numbers(path)
    facilities = int(_next(values, "facilities"))
    customers = int(_next(values, "customers"))
    capacities, fixed = [], []
    for _ in range(facilities):
        capacities.append(_next(values, "capacity"))
        fixed.append(_next(values, "fixed cost"))
    demands = [_next(values, "demand") for _ in range(customers)]
    costs = [[0.0] * facilities for _ in range(customers)]
    for j in range(facilities):
        for i in range(customers):
            costs[i][j] = _next(values, "assignment cost")
    return _instance(path, customers, facilities, demands, capacities, fixed, costs,
                     [], "orlib_cap", "total", "facilities_first")


def _read_dzn(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    facilities = _dzn_int(text, "Warehouses", "Facilities")
    customers = _dzn_int(text, "Stores", "Customers")
    capacities = _dzn_list(text, "Capacity")
    fixed = _dzn_list(text, "FixedCost")
    demands = _dzn_list(text, "Goods", "Demand")
    costs = _dzn_matrix(text, "SupplyCost", "ShippingCost")
    pairs = [(int(a) - 1, int(b) - 1) for a, b in _dzn_matrix(text, "IncompatiblePairs")]
    declared = _dzn_int(text, "Incompatibilities")
    if declared != len(pairs):
        raise ValueError("Declared incompatibility count does not match IncompatiblePairs.")
    return _instance(path, customers, facilities, demands, capacities, fixed, costs,
                     pairs, "dzn", "per_unit", "facilities_first")


def _instance(path, n, m, demands, capacities, fixed, costs, pairs, source, mode, orientation):
    vector = lambda values: values.astype(float, copy=False) if isinstance(values, np.ndarray) else [float(v) for v in values]
    matrix = costs.astype(float, copy=False) if isinstance(costs, np.ndarray) else [
        [float(v) for v in row] for row in costs
    ]
    return {
        "name": path.stem,
        "path": str(path),
        "source_format": source,
        "cost_mode": mode,
        "header_orientation": orientation,
        "customers": int(n),
        "facilities": int(m),
        "demands": vector(demands),
        "capacities": vector(capacities),
        "fixed_costs": vector(fixed),
        "assignment_costs": matrix,
        "incompatible_pairs": [(int(i), int(k)) for i, k in pairs],
    }


def validate_instance(instance: dict) -> None:
    n, m = instance["customers"], instance["facilities"]
    if len(instance["demands"]) != n or len(instance["assignment_costs"]) != n:
        raise ValueError("Customer dimensions are inconsistent.")
    if len(instance["capacities"]) != m or len(instance["fixed_costs"]) != m:
        raise ValueError("Facility dimensions are inconsistent.")
    if any(len(row) != m for row in instance["assignment_costs"]):
        raise ValueError("Assignment-cost matrix dimensions are inconsistent.")
    if sum(instance["capacities"]) + 1e-9 < sum(instance["demands"]):
        raise ValueError("Installed capacity is smaller than total demand.")
    if any(not (0 <= i < n and 0 <= k < n and i != k)
           for i, k in instance["incompatible_pairs"]):
        raise ValueError("An incompatible pair contains an invalid customer index.")


def assignment_cost(instance: dict, i: int, j: int) -> float:
    raw = instance["assignment_costs"][i][j]
    return raw if instance["cost_mode"] == "total" else instance["demands"][i] * raw


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _numbers(path: Path) -> Iterator[float]:
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            for token in NUMBER.findall(line):
                yield float(token)


def _next(values: Iterator[float], label: str) -> float:
    try:
        return next(values)
    except StopIteration as exc:
        raise ValueError(f"Unexpected end of file while reading {label}.") from exc


def _dzn_block(text: str, name: str) -> str:
    match = re.search(rf"\b{name}\s*=\s*", text)
    if not match:
        raise ValueError(f"DZN field {name} was not found.")
    end = text.find(";", match.end())
    if end < 0:
        raise ValueError(f"DZN field {name} has no closing semicolon.")
    return text[match.end():end]


def _dzn_int(text: str, *names: str) -> int:
    for name in names:
        match = re.search(rf"\b{name}\s*=\s*(\d+)\s*;", text)
        if match:
            return int(match.group(1))
    raise ValueError(f"None of the DZN fields {names} was found.")


def _dzn_list(text: str, *names: str) -> list[float]:
    for name in names:
        try:
            return [float(v) for v in NUMBER.findall(_dzn_block(text, name))]
        except ValueError:
            pass
    raise ValueError(f"None of the DZN fields {names} was found.")


def _dzn_matrix(text: str, *names: str) -> list[list[float]]:
    for name in names:
        try:
            block = _dzn_block(text, name)
            rows = [[float(v) for v in NUMBER.findall(row)] for row in re.findall(r"\|([^|]+)", block)]
            return [row for row in rows if row]
        except ValueError:
            pass
    raise ValueError(f"None of the DZN fields {names} was found.")
