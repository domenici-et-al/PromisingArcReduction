"""Artifact I/O and result-table helpers for PAR experiments."""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
from pathlib import Path
from typing import Iterable

import numpy as np


SCHEMA_VERSION = "1.0"


def write_solution(directory: str | Path, name: str, x: np.ndarray, y: np.ndarray,
                   a: np.ndarray | None = None, tolerance: float = 1e-9,
                   dense: bool = True) -> dict:
    """Write the complete primal vector, optionally in both representations.

    Dense NPZ arrays contain every variable value.  Sparse CSV files use
    one-based indices and omit values whose absolute value is at most the
    stated tolerance; every omitted value is exactly zero by convention.
    """
    directory = Path(directory)
    sparse = directory / "sparse" / f"{name}.csv.gz"
    sparse.parent.mkdir(parents=True, exist_ok=True)

    with gzip.open(sparse, "wt", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["variable", "index_1", "index_2", "value"])
        for i, j in np.argwhere(np.abs(x) > tolerance):
            writer.writerow(["x", int(i) + 1, int(j) + 1, _number(x[i, j])])
        for j in np.flatnonzero(np.abs(y) > tolerance):
            writer.writerow(["y", int(j) + 1, "", _number(y[j])])
        if a is not None:
            for i, j in np.argwhere(np.abs(a) > tolerance):
                writer.writerow(["a", int(i) + 1, int(j) + 1, _number(a[i, j])])

    result = {
        "sparse": sparse,
        "sparse_sha256": sha256(sparse),
        "zero_default_tolerance": tolerance,
    }
    if dense:
        dense_path = directory / "dense" / f"{name}.npz"
        dense_path.parent.mkdir(parents=True, exist_ok=True)
        arrays = {"x": np.asarray(x), "y": np.asarray(y)}
        if a is not None:
            arrays["a"] = np.asarray(a)
        np.savez_compressed(dense_path, **arrays)
        result.update({"dense": dense_path, "dense_sha256": sha256(dense_path)})
    return result


def read_solution(path: str | Path, customers: int, facilities: int) -> dict:
    path = Path(path)
    if path.suffix == ".npz":
        with np.load(path) as data:
            return {name: data[name].copy() for name in data.files}
    x = np.zeros((customers, facilities), dtype=float)
    y = np.zeros(facilities, dtype=float)
    a = None
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            variable = row["variable"]
            first = int(row["index_1"]) - 1
            value = float(row["value"])
            if variable == "y":
                y[first] = value
            else:
                second = int(row["index_2"]) - 1
                if variable == "x":
                    x[first, second] = value
                elif variable == "a":
                    if a is None:
                        a = np.zeros((customers, facilities), dtype=float)
                    a[first, second] = value
                else:
                    raise ValueError(f"Unknown variable in {path}: {variable}")
    result = {"x": x, "y": y}
    if a is not None:
        result["a"] = a
    return result


def write_json(path: str | Path, value: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: str | Path, rows: Iterable[dict], fields: list[str] | None = None) -> None:
    path = Path(path)
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = []
        for row in rows:
            fields.extend(key for key in row if key not in fields)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "wt" if path.suffix == ".gz" else "w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: str | Path) -> list[dict[str, str]]:
    path = Path(path)
    with path.open(encoding="utf-8-sig", newline="") as stream:
        sample = stream.readline()
        stream.seek(0)
        return list(csv.DictReader(stream, delimiter=";" if sample.count(";") > sample.count(",") else ","))


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _number(value) -> str:
    value = float(value)
    integer = round(value)
    return str(integer) if abs(value - integer) <= 1e-9 else f"{value:.17g}"



