# Promising Arc Reduction

Computational artifact for **Promising arc reduction and full-space
certification for large-scale SSCFLP**.

PAR deterministically constructs a small customer-facility assignment graph
before optimization.  This repository contains the frozen implementation,
complete primal solutions in two encodings, solver logs, progress traces,
comparison tables, and full-space optimality certificates.

The release contains **970 complete validated primal solutions**: 445 for
SSCFLP, 445 for MS-CFLP, and 80 for MS-CFLP-CI.  It also contains 131 audited
SSCFLP full-space certificates (115 first optimality proofs and 16
re-certifications), each with a complete optimal primal witness.

## Scope

| Problem | Instances | Time limit | Threads | Initialization |
|---|---:|---:|---:|---|
| SSCFLP | 445 | 600 s end-to-end | 1 | first feasible assignment |
| MS-CFLP | 445 | 600 s end-to-end | 1 | none |
| MS-CFLP-CI | 80 | `10*sqrt(m)` s end-to-end | 1 | none |

Benchmark instances are **not redistributed**.  Their expected filenames and
SHA-256 hashes are listed in [`data/instance_manifest.csv`](data/instance_manifest.csv).

## Install

Python 3.11 or newer and a working Gurobi license are required.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run

```powershell
# Frozen SSCFLP protocol (600 s, one thread, constructive initialization)
python src/solve.py sscflp path/to/p800-4400-1.plc --output reproduced

# Direct transfer to splittable demand
python src/solve.py mscflp path/to/p800-4400-1.plc --output reproduced

# Customer-incompatibility extension; the default limit is 10*sqrt(m)
python src/solve.py mscflp-ci path/to/wlp01.dzn --output reproduced

# Independently validate either published solution encoding
python src/validate.py sscflp path/to/p800-4400-1.plc \
  artifacts/solutions/sscflp/dense/p800-4400-1.npz
```

For an optimal reduced SSCFLP run:

```powershell
python src/certify.py path/to/instance.plc path/to/solution.npz \
  --metadata path/to/metadata.json --output certificate --threads 16
```

## Artifact map

- `src/`: six self-contained Python modules implementing the released method.
- `configs/`: frozen protocols and the stratified ablation subset.
- `data/`: instance manifest and unmodified reference tables.
- `artifacts/metadata/`: one normalized JSON record per run.
- `artifacts/solutions/`: dense NPZ and sparse `csv.gz` primal solutions.
- `artifacts/logs/`: compressed Gurobi logs, separate from solutions.
- `artifacts/progress/`: compressed end-to-end progress traces.
- `results/`: comparison, ablation, and diagnostic tables used by the paper.
- `certificates/`: proof indices, proof records, logs, and optimal witnesses.
- `docs/`: method, format, provenance, and reproduction details.
- `SHA256SUMS`: integrity manifest for all tracked artifact files.

All indices in human-readable solution files are one-based.  Omitted entries
in sparse files have value zero; dense NPZ files explicitly store every
variable.  See [`docs/artifact-format.md`](docs/artifact-format.md).

The CI archive records nine historical full-model optimality proofs.  Exact
primal witnesses were preserved for five of them; the four unavailable
witnesses are explicitly identified in the certificate index and are not
represented by reconstructed data.  See
[`docs/certification.md`](docs/certification.md).

## Reproducibility

- [`configs/protocols.json`](configs/protocols.json) freezes time, thread,
  seed, initialization, and proof tolerances.
- [`data/instance_manifest.csv`](data/instance_manifest.csv) identifies every
  external instance by SHA-256.
- [`results/summaries/artifact_validation.csv`](results/summaries/artifact_validation.csv)
  reports the independent solution audit.
- [`results/summaries/historical_objective_reconciliation.csv`](results/summaries/historical_objective_reconciliation.csv)
  preserves the 13 cases in which an archived solver objective differed from
  the objective recomputed from its saved primal vector.
- `SHA256SUMS` authenticates every released file.

The release environment was Python 3.13.12, NumPy 2.4.3, Gurobi 13.0.1,
Windows 11 Pro, and an AMD Ryzen 9 9950X with 64 GB RAM.  The timed experiments
used one solver thread.

## Licensing

Source code is released under the MIT License.  Result tables, logs, metadata,
and generated solution artifacts are released under CC BY 4.0; see
[`LICENSE-DATA`](LICENSE-DATA).  Original benchmark data remain under their
respective authors' terms.
