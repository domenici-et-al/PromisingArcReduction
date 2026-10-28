# Promising Arc Reduction

Computational artifact for **Full-space certification at scale for
single-source capacitated facility location with deterministic promising-arc
reduction**.

PAR deterministically constructs a small customer-facility assignment graph
before optimization.  This repository contains the frozen implementation,
complete primal solutions in two encodings, solver logs, progress traces,
comparison tables, and full-space optimality certificates.

The release contains **970 complete validated primal solutions**: 445 for
SSCFLP, 445 for MS-CFLP, and 80 for MS-CFLP-CI. It also contains **368
full-model optimality certificates**: 150 SSCFLP full-space certificates,
209 MS-CFLP full-model M1 certificates, and 9 MS-CFLP-CI historical proofs.

The 150 SSCFLP records comprise 134 first optimality proofs relative to the
exact statuses reported in the PaKS benchmark table and 16 re-certifications.
Within the 134 first proofs, 28 improve a reported BKS and 106 prove the
reported BKS; 131 records retain frozen LP-pricing and verification-MIP
telemetry and 19 retain terminal safe-support telemetry.

The 209 MS-CFLP certificates are full-model M1 proofs: 83 agree with an
individually identified published optimum, 117 are certified without an
individually identified prior proof, and 9 carry a literature discrepancy.
Of 265 attempted instances, 56 remained uncertified and 180 were not attempted
at the reporting cutoff. The 9 MS-CFLP-CI records are historical full-model
proofs; five retain exact primal witnesses and four are explicitly identified
as unavailable.

## Scope

| Problem | Instances | Time limit | Threads | Initialization |
|---|---:|---:|---:|---|
| SSCFLP | 445 | 600 s end-to-end | 1 | first feasible assignment |
| MS-CFLP | 445 | 600 s end-to-end | 1 | none |
| MS-CFLP-CI | 80 | `10*sqrt(m)` s end-to-end | 1 | none |

Benchmark instances are **not redistributed**.  Obtain them from their original
sources; the instance names used in the paper are listed in the supplementary
material.

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

For full-space MS-CFLP-CI certification from a validated PAR incumbent:

```powershell
python src/certify_ci.py path/to/wlp01.dzn path/to/par_solution.npz \
  --output ci-certificate --threads 16
```

For full-model MS-CFLP certification from a validated PAR incumbent:

```powershell
python src/certify_mscflp.py path/to/instance.plc path/to/par_solution.npz \
  --output mscflp-certificate --threads 16
```

## Artifact map

- `src/`: compact Python implementation of PAR, validation, and certification.
- `configs/`: frozen protocols and the stratified 45- and 90-instance ablation
  panels.
- `artifacts/metadata/`: one normalized JSON record per run.
- `artifacts/solutions/`: dense NPZ and sparse `csv.gz` primal solutions.
- `artifacts/logs/`: compressed Gurobi logs, separate from solutions.
- `artifacts/progress/`: compressed end-to-end progress traces.
- `results/`: comparison, ablation, and diagnostic tables used by the paper.
- `certificates/`: proof indices, proof records, logs, and sparse optimal
  witnesses for SSCFLP, MS-CFLP, and MS-CFLP-CI.
- `docs/`: method, format, provenance, and reproduction details.

All indices in human-readable solution files are one-based.  Omitted entries
in sparse files have value zero; dense NPZ files explicitly store every
variable.  See [`docs/artifact-format.md`](docs/artifact-format.md).

The three certificate families are indexed under `results/certificates/`:
`sscflp_all_certificates.csv` (150), `mscflp_certificates.csv` (209), and
`mscflp_ci_certificates.csv` (9). The SSCFLP ledger combines 131 LP-pricing
phasewise records and 19 terminal safe-support records; the MS-CFLP index
records the full-model M1 classification, literature status, and proof times;
the CI index records the five preserved witnesses and the four explicitly
unavailable ones. Certificate witnesses are released in sparse form. See
[`docs/certification.md`](docs/certification.md).

New MS-CFLP proofs can be generated with `src/certify_mscflp.py`; it solves the
complete multi-source model, and a certificate is issued only when the
full-model MIP is optimal and the primal validator accepts the returned vector.
The CI archive records nine historical full-model proofs; five witnesses are
preserved and four are explicitly identified as unavailable.

## Reproducibility

- [`configs/protocols.json`](configs/protocols.json) freezes time, thread,
  seed, initialization, and proof tolerances.
- [`results/summaries/artifact_validation.csv`](results/summaries/artifact_validation.csv)
  reports the independent solution audit.
- [`results/summaries/certificate_validation.csv`](results/summaries/certificate_validation.csv)
  reports the independent validation of the 155 certificate witnesses:
  131 phasewise SSCFLP, 19 terminal SSCFLP, and 5 CI.
- [`results/certificates/mscflp_certificates.csv`](results/certificates/mscflp_certificates.csv)
  lists the 209 full-model MS-CFLP certificates with their literature status
  and proof times.
- [`results/summaries/historical_objective_reconciliation.csv`](results/summaries/historical_objective_reconciliation.csv)
  preserves the 13 cases in which an archived solver objective differed from
  the objective recomputed from its saved primal vector.
- Each run's metadata stores the SHA-256 of its released solution, logs, and
  progress trace; each certificate record stores the hashes of its proof files.

The release environment was Python 3.13.12, NumPy 2.4.3, Gurobi 13.0.1,
Windows 11 Pro, and an AMD Ryzen 9 9950X with 64 GB RAM.  The timed experiments
used one solver thread.

## Licensing

Source code is released under the MIT License.  Result tables, logs, metadata,
and generated solution artifacts are released under CC BY 4.0; see
[`LICENSE-DATA`](LICENSE-DATA).  Original benchmark data remain under their
respective authors' terms.
