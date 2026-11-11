# Promising Arc Reduction

Code and results for the paper *Promising Arc Reduction for Capacitated Facility
Location: Heuristic Search and Optimality Proofs* (Domenici, Leão and Castellucci).

PAR keeps, for each customer, a short prefix of its cheapest facilities and
solves the reduced model with Gurobi. The prefix length depends only on the
instance data: the capacity ratio, the customer's demand and how contested the
nearby facilities are. The method is in [`src/par.py`](src/par.py).

| Problem | Instances | Optimality proofs |
|---|---:|---:|
| SSCFLP | 445 | 150 |
| MS-CFLP | 445 | 209 |
| MS-CFLP-CI | 80 | 9 |

The benchmark instances are not included; they are available from their
original sources. Names follow the original files (`p800-4400-1.plc`,
`wlp01.dzn`, `cflp-ci_00.dzn`, ...).

## Install

Python 3.11+ and a Gurobi license.

```
pip install -r requirements.txt
```

## Usage

Run from the repository root. Outputs go to `output/` by default.

```
# PAR run (600 s, 1 thread; the CI default is 10*sqrt(m) s)
python src/solve.py sscflp path/to/p800-4400-1.plc
python src/solve.py mscflp path/to/p800-4400-1.plc
python src/solve.py mscflp-ci path/to/wlp01.dzn

# check a solution and recompute its cost
python src/validate.py sscflp path/to/p800-4400-1.plc runs/sscflp/p800-4400-1/solution.csv.gz

# optimality proofs from a feasible solution
python src/certify.py path/to/p800-4400-1.plc runs/sscflp/p800-4400-1/solution.csv.gz --output output/proof
python src/certify_full.py mscflp path/to/p800-4400-1.plc runs/mscflp/p800-4400-1/solution.csv.gz --output output/proof
python src/certify_full.py mscflp-ci path/to/wlp01.dzn runs/mscflp-ci/wlp01/solution.csv.gz --output output/proof
```

`solve.py` writes `solution.csv.gz`, `gurobi.log`, `progress.csv` and
`metadata.json` to `output/<problem>/<instance>/`. Use `--help` for the
available variants, initialization options and solver limits.

## Contents

```
src/
  par.py            PAR candidate lists
  solve.py          PAR run: the reduced model with Gurobi
  certify.py        SSCFLP optimality proof (Algorithm 2 of the paper)
  certify_full.py   MS-CFLP and MS-CFLP-CI proofs on the complete model
  validate.py       feasibility check and cost of a solution
  instances.py      instance readers (.plc, .dzn)
  results.py        solution and result files
runs/<problem>/<instance>/     solution.csv.gz, gurobi.log.gz, progress.csv.gz
                               (and warm_start.log.gz for the SSCFLP)
proofs/<problem>/<instance>/   optimal_solution.csv.gz, verification.log.gz (where available)
results/
  sscflp.csv        445 SSCFLP results
  mscflp.csv        445 MS-CFLP results
  mscflp_ci.csv      80 MS-CFLP-CI results
  ablations.csv      9 control summaries
```

## Results

The three problem tables have one row per instance and follow the final
manuscript. Their columns are:

| Column | Meaning |
|---|---|
| `instance` | Original instance name, without the file extension. |
| `group` / `dataset` | Cost regime (TB-A, TB-B, TB-C) or CI benchmark set (WLP, CFLP-CI). |
| `rho` | Total capacity divided by total demand; included for SSCFLP. |
| `par_objective` | Objective of the PAR heuristic solution, recomputed from the solution. |
| `reference_objective` | Literature reference used in the paper. |
| `advantage_pct` | `100 * (reference_objective - par_objective) / reference_objective`; positive favors PAR. |
| `retained_arcs_pct` | Candidate arcs as a percentage of all customer-facility pairs. |
| `retained_conflict_rows_pct` | Retained conflict rows as a percentage of all potential conflict rows; CI only. |
| `time_s` | Reported PAR elapsed time in seconds, excluding the subsequent proof phase. |
| `proven_optimum` | Full-model optimum established in the separate proof phase, when available. |

Empty cells mean that no reference or optimality proof is reported. The PAR
objective and the proven optimum refer to separate stages and may differ.
References follow the paper: Bakker et al. for SSCFLP; Guastaroba and Speranza,
Caserta and Voß, and Avella et al. for MS-CFLP; the enhanced LNS best-of-ten
results for MS-CFLP-CI.

`ablations.csv` summarizes six formula controls on 90 instances and three
solver controls on 45 instances. It reports the control name, number of
instances, mean, median and maximum objective difference, and arc difference.
Objective differences are `100 * (control - PAR) / PAR`, so positive values
favor PAR. `arc_difference_pp` is the control's retained arc percentage minus
PAR's, in percentage points. These summaries use the matched panels only.

## Solutions and logs

Solution files have one row per nonzero variable: `variable,index_1,index_2,value`
with `variable` in `x`, `y`, `a` and one-based indices. `x` is the assignment
(SSCFLP) or the shipped quantity (MS-CFLP), `y` opens a facility and `a` marks
customer-facility use in MS-CFLP-CI. Omitted entries are zero. The validator
checks feasibility and recomputes the objective against the original instance.

The original Gurobi logs, initialization logs and progress traces are retained
alongside the solutions. Progress columns differ between problems. A solver
log records the runtime of that optimization; this is not the overall PAR
elapsed time in `time_s`. Solver-reported objectives can differ from the
recomputed solution costs used in the result tables. Local paths and license
identifiers were removed from the logs.

## Environment

The reported runs used Python 3.13.12, NumPy 2.4.3 and Gurobi 13.0.1 on
Windows 11 with an AMD Ryzen 9 9950X (64 GB RAM).

## License

Code: MIT ([`LICENSE`](LICENSE)). Results, logs and solutions: CC BY 4.0
([`LICENSE-DATA`](LICENSE-DATA)). The benchmark instances keep their original
terms.
