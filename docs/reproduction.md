# Reproduction protocol

1. Install the dependencies from `requirements.txt` and activate a valid
   Gurobi license.  No license file belongs in this repository.
2. Obtain benchmark files from their original sources.  The instance names
   used in the paper are listed in the supplementary material.
3. Run `src/solve.py` with the corresponding problem name.  Defaults reproduce
   the frozen time, thread, seed, and initialization protocol.
4. Validate the dense or sparse timed solution with `src/validate.py`.
5. Compare the generated metadata and progress trace with the archived record.

The 600-second SSCFLP limit includes instance reading, graph construction,
constructive initialization, and optimization.  MS-CFLP also uses an
end-to-end 600-second limit but no initializer.  MS-CFLP-CI uses an end-to-end
limit of `10*sqrt(m)` seconds.  These timed runs produce and validate
incumbents; they are separate from full-model optimality proofs.

## SSCFLP certification

Every SSCFLP record follows the same validate--screen--solve--validate
interface: validate an incumbent, construct a globally safe support, solve its
exact verification MIP, and validate the returned assignment in the original
instance.  The frozen phasewise implementation may use 16 threads, accepts a
feasible incumbent from a reduced model solved to optimality, and records each
LP-pricing and MIP-verification stage.

The 150 released records are under `certificates/sscflp/records/<instance>/`:
131 retain LP-pricing phasewise telemetry and 19 retain terminal safe-support
telemetry.  `p800-4400-88` closes directly after reduced-cost fixing and has
no verification log.  The canonical index is
`results/certificates/sscflp_all_certificates.csv`.

Historical SSCFLP certificate records identify the exact certifier source by
SHA-256.  The released `src/certify.py` is the compact reference implementation
of the same proof procedure; it may produce different solver traces while
establishing the same full-space claim:

```powershell
python src/certify.py path\to\instance.plc path\to\solution.npz `
  --metadata path\to\metadata.json --output certificate --threads 16
```

## MS-CFLP full-model proof

The timed `src/solve.py mscflp` run is heuristic and does not prove
optimality.  The 209 released MS-CFLP certificates are full-model M1 proofs
produced by a separate, untimed certification solve.  `src/certify_mscflp.py`
builds the complete model with continuous flows and binary openings, starts
from the validated PAR incumbent, solves with `MIPGap = MIPGapAbs = 0` and
tolerances of `1e-9`, and certifies only when Gurobi returns an optimal status,
the objective and bound agree within the proof tolerance, and the returned
primal passes `src/validate.py`.

The 209 records are under `certificates/mscflp/records/<instance>/`, each with
a certificate, a sparse optimal witness, and a sanitized full-model solver
log.  The canonical index is
`results/certificates/mscflp_certificates.csv`; aggregate counts and times are
in `results/summaries/mscflp_proof_summary.json`.  The default resource guard
is four million assignment arcs; `--max-full-arcs 0` disables it when enough
memory is available.

```powershell
python src/certify_mscflp.py path\to\instance.plc path\to\par_solution.npz `
  --output mscflp-certificate --threads 16
```

## MS-CFLP-CI certification

The CI certifier accepts a validated incumbent, rebuilds the complete
assignment graph, and separates incompatibility rows exactly as lazy
constraints.  Its full-graph resource guard defaults to two million assignment
arcs and can be overridden with `--max-full-arcs 0`.

The nine historical CI records are under
`certificates/mscflp-ci/records/<instance>/`.  Five preserve exact primal
witnesses; `wlp04`, `wlp05`, `wlp06`, and `wlp22` retain proof metadata but no
exact primal vector, and their records state this explicitly.  The index is
`results/certificates/mscflp_ci_certificates.csv`.

```powershell
python src/certify_ci.py path\to\wlp01.dzn path\to\par_solution.npz `
  --output ci-certificate --threads 16
```

## Outputs and validation

New certificate runs write `certificate.json`, a sparse optimal witness, and
the solver log under the requested output directory.  Certificate witnesses use
the sparse one-based encoding; timed runs retain both dense and sparse
encodings.

`results/summaries/certificate_validation.csv` has 155 rows: 131 phasewise
SSCFLP, 19 terminal SSCFLP, and 5 CI witnesses.
`results/summaries/certificate_integrity_audit.json` reports 364 verified
witnesses.  The release-level provenance and redaction notes are in
`certificates/README.md`.

All commands are platform-independent; examples in the README use PowerShell.
