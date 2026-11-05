# Promising Arc Reduction

Code and results for the paper *Promising Arc Reduction for Capacitated Facility
Location: Heuristic Search and Optimality Proofs* (Domenici, Leão and Castellucci).

PAR keeps, for each customer, a short prefix of its cheapest facilities and
solves the reduced model with Gurobi. The prefix length depends only on the
instance data: the capacity ratio, the customer's demand and how contested the
nearby facilities are. The method is in [`src/par.py`](src/par.py).

| Problem | Instances | Runs | Optimality proofs |
|---|---:|---:|---:|
| SSCFLP | 445 | 445 | 150 |
| MS-CFLP | 445 | 445 | 209 |
| MS-CFLP-CI | 80 | 80 | 9 |

The benchmark instances are not included; they are available from their
original sources. Names follow the original files (`p800-4400-1.plc`,
`wlp01.dzn`, `cflp-ci_00.dzn`, ...).

## Install

Python 3.11+ and a Gurobi license.

```
pip install -r requirements.txt
```

## Usage

The scripts are in `src/` and are run from the repository root.

```
# PAR run (600 s, 1 thread; the CI default is 10*sqrt(m) s)
python src/solve.py sscflp path/to/p800-4400-1.plc --output runs
python src/solve.py mscflp path/to/p800-4400-1.plc --output runs
python src/solve.py mscflp-ci path/to/wlp01.dzn --output runs

# check a solution and recompute its cost
python src/validate.py sscflp path/to/p800-4400-1.plc artifacts/solutions/sscflp/sparse/p800-4400-1.csv.gz

# optimality proofs from a feasible solution
python src/certify.py path/to/p800-4400-1.plc runs/sscflp/p800-4400-1/solution.csv.gz --output proof --threads 8
python src/certify_mscflp.py path/to/p800-4400-1.plc runs/mscflp/p800-4400-1/solution.csv.gz --output proof
python src/certify_ci.py path/to/wlp01.dzn runs/mscflp-ci/wlp01/solution.csv.gz --output proof
```

`solve.py` writes `metadata.json`, `solution.csv.gz`, `gurobi.log` and
`progress.csv` to `runs/<problem>/<instance>/`. The ablation controls are
selected with `--variant` (`no_congestion`, `direct_adaptive`,
`unweighted_sqrt`, `full`) and `--no-warm-start`.

To check the whole release against the instance files (rebuilds every PAR
graph and validates every released solution, without Gurobi):

```
python scripts/check_release.py path/to/instances --workers 8
```

Tests on small synthetic instances (the solver tests need Gurobi):

```
python -m unittest discover -s tests -v
```

## Contents

```
src/                 PAR, the three models, validation and the certifiers
scripts/             check_release.py
tests/               synthetic tests
configs/             run protocols and the two ablation panels
artifacts/
  metadata/<problem>/<instance>.json         PAR graph, status, objective, bound, times
  solutions/<problem>/sparse/<instance>.csv.gz
  solutions/<problem>/dense/<instance>.npz   the same solutions as full arrays
  logs/<problem>/<instance>/                 Gurobi logs (and the SSCFLP warm start)
  progress/<problem>/<instance>.csv.gz       incumbent and bound over time
certificates/<problem>/records/<instance>/   certificate.json, optimal_solution.csv.gz,
                                             verification.log.gz (+ pricing_iterations.csv)
results/
  comparisons/       PAR against the best known results
  ablations/         ablation results (both panels and a few stress cases)
  certificates/      one row per optimality proof
  diagnostics/       hard SSCFLP cases
  summaries/         totals and release audits
```

Solution files have one row per nonzero variable: `variable,index_1,index_2,value`
with `variable` in `x`, `y`, `a` and one-based indices. `x` is the assignment
(SSCFLP) or the shipped quantity (MS-CFLP), `y` opens a facility and `a` marks
customer-facility use in MS-CFLP-CI. In the metadata, `released_solution.objective`
is the cost recomputed from the released solution; for 13 runs it differs from
the objective printed by the solver, and these cases are listed in
`results/summaries/historical_objective_reconciliation.csv`. Local paths and
license identifiers were removed from the logs.

## Notes on the proofs

**SSCFLP (150).** Reference values are from Bakker et al. (2025),
arXiv:2512.08576v1, with literature cutoff 2026-07-18: 134 proofs are the first
for their instance (28 of them improve the best known solution) and 16 confirm
known optima. 131 proofs follow Algorithm 2 of the paper and `certify.py`
(LP pricing, reduced-cost fixing, verification MIP); `p800-4400-88` closes at
the fixing step and has no verification log. The other 19 (`trace_profile =
terminal_safe_support` in `certificate.json`) removed omitted arcs with
Lagrangian bounds instead of LP reduced costs (a regret bound plus residual
knapsack tests, with the LP duals and the best subgradient multipliers) and then
solved the remaining model to optimality. That test is not part of `certify.py`;
for these 19 instances the repository has the certificate, the optimal
solution and the verification log. Proofs used 8 threads, except
`p800-4400-51`, `p1200-3000-60` and `p2000-2000-67`, which used 16.

**MS-CFLP (209).** `certify_mscflp.py` solves the complete model starting from
the PAR solution (1 thread). 83 proofs agree with a published optimum, 117 have
no published proof and 9 disagree with a published value. 56 more instances
were attempted without a proof and 180 were not attempted.

**MS-CFLP-CI (9).** These proofs were obtained with the complete model before
`certify_ci.py` was written. All nine optimal solutions are included. Solver
logs with the final bound were recovered for `wlp01`-`wlp04`, `wlp21` and
`wlp22` (`certificates/mscflp-ci/evidence/`); for `wlp05`, `wlp06` and `wlp23`
only the recorded objective and bound remain.

**Ablations.** The 90-instance panel compares PAR with six changes to the
formula and the 45-instance panel with three solver settings (no warm start,
full graph, full graph with warm start). Of the six formula controls, three are
available as `--variant` (`no_congestion`, `direct_adaptive`,
`unweighted_sqrt`); the other three (no capacity scaling, no demand scaling,
unit prefix weights) are not.

## Environment

The reported runs used Python 3.13.12, NumPy 2.4.3 and Gurobi 13.0.1 on
Windows 11 with an AMD Ryzen 9 9950X (64 GB RAM).

## License

Code: MIT ([`LICENSE`](LICENSE)). Results, logs and solutions: CC BY 4.0
([`LICENSE-DATA`](LICENSE-DATA)). The benchmark instances keep their original
terms.
