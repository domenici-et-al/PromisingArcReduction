"""Reading and writing solutions and result files."""

from __future__ import annotations

import csv
import gzip
import json
from pathlib import Path

import numpy as np


def write_solution(path: str | Path, x, y, a=None, tolerance: float = 1e-9) -> None:
    """Write the nonzero entries of x, y (and a) as variable,index_1,index_2,value.

    Indices are one-based; omitted entries are zero.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["variable", "index_1", "index_2", "value"])
        for i, j in np.argwhere(np.abs(x) > tolerance):
            writer.writerow(["x", i + 1, j + 1, _number(x[i, j])])
        for j in np.flatnonzero(np.abs(y) > tolerance):
            writer.writerow(["y", j + 1, "", _number(y[j])])
        if a is not None:
            for i, j in np.argwhere(np.abs(a) > tolerance):
                writer.writerow(["a", i + 1, j + 1, _number(a[i, j])])


def read_solution(path: str | Path, customers: int, facilities: int) -> dict:
    """Read a sparse .csv/.csv.gz solution or a dense .npz solution into dense arrays."""
    path = Path(path)
    if path.suffix == ".npz":
        with np.load(path) as data:
            return {name: data[name].copy() for name in data.files}
    values = {"x": np.zeros((customers, facilities)), "y": np.zeros(facilities)}
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            name, first, value = row["variable"], int(row["index_1"]) - 1, float(row["value"])
            if name == "y":
                values["y"][first] = value
            else:
                if name not in values:
                    values[name] = np.zeros((customers, facilities))
                values[name][first, int(row["index_2"]) - 1] = value
    return values


def write_json(path: str | Path, value: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def write_csv(path: str | Path, rows: list[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _number(value) -> str:
    value = float(value)
    integer = round(value)
    return str(integer) if abs(value - integer) <= 1e-9 else f"{value:.17g}"
