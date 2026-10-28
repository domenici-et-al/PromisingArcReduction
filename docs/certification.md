# Full-space certification

The release contains **368 full-model optimality certificates** in three
families.  A reduced-graph optimum is never reported as a full-space
certificate: every record requires an optimal full-model solver status, an
objective that agrees with the certified bound within the declared tolerance,
and a primal vector accepted by the independent validator.

| Family | Certificates | Witnesses | Method |
|---|---:|---:|---|
| SSCFLP | 150 | 150 | LP pricing, reduced-cost fixing, verification MIP |
| MS-CFLP | 209 | 209 | complete-model M1 solve |
| MS-CFLP-CI | 9 | 5 | complete model with lazy conflict separation |

## SSCFLP — 150

All 150 records belong to one full-space certification campaign and one
outcome ledger.  The common interface validates an incumbent, constructs a
support guaranteed to contain every original-space solution no worse than
that incumbent, solves the exact verification MIP on that support, and
independently validates the returned assignment.

### LP-pricing phasewise profile (131)

1. It solves the active LP and prices every omitted eligible assignment arc.
   Arcs with negative reduced cost beyond the stated tolerance are inserted,
   and LP pricing repeats until none remain.
2. Reduced-cost fixing discards only omitted arcs and inactive facilities that
   cannot participate in an integer solution at or below the incumbent within
   the proof tolerance.
3. If no omitted variable survives fixing, the incumbent is certified
   directly.  Otherwise, a verification MIP containing every remaining
   variable is solved to optimality.  The incumbent is certified only when its
   objective matches the full-space verification optimum within tolerance.

The released tolerances are in `configs/protocols.json`.  Every phasewise
record stores the pricing lower bound, numbers of priced and unfixed arcs,
verification size, objective, times, source hashes, available stage logs, and
complete optimal primal vector.  `p800-4400-88` closes directly after fixing
(`verification.status = not_needed`) and has no verification log; the other
130 phasewise records include one.  Relative to the exact statuses reported in
the PaKS benchmark table, 92 are first proofs at a reported BKS, 23 are first
proofs with an improved incumbent, and 16 are re-certifications.

### Terminal safe-support profile (19)

Nineteen records retain terminal safe-support telemetry rather than the
pricing-iteration fields.  Every record contains an optimal solver status, a
matching objective and bound, a feasible complete customer assignment, a
redacted solver log, and source hashes.  No interrupted or positive-gap run is
included.  The 19 records add 14 first proofs at a reported BKS and 5 first
proofs with an improved incumbent.

The unified ledger has 150 records: 106 first proofs at a reported BKS, 28
first proofs with an improved incumbent, and 16 re-certifications.  The
canonical index is `results/certificates/sscflp_all_certificates.csv`; its
`trace_profile` field distinguishes the two telemetry layouts.  All records
are under `certificates/sscflp/records/<instance>/`; the earlier
`optimal-solutions/` and `followup-records/` layouts are not used.

The executable `src/certify.py` is the compact reference implementation of the
SSCFLP proof procedure.  It writes a sparse optimal witness and its proof logs
under the requested output directory.

## MS-CFLP — 209

The 209 MS-CFLP certificates are **full-model M1 optimality proofs** of the
original multi-source formulation.  PAR supplies the incumbent; M1 solves the
complete model over every customer-facility pair.  The record's
`proof_basis` is `global_MIP_bound`, never a reduced-model status.

`src/certify_mscflp.py` builds the complete model with continuous flows
`x[n,m]` and binary openings `y[m]`, demand and capacity rows, and the linking
inequality `x_ij <= min(d_i, s_j) y_j`.  It starts from the validated
incumbent, sets `MIPGap = MIPGapAbs = 0` and primal/dual/integrality
tolerances of `1e-9`, and certifies only when Gurobi returns `OPTIMAL`, the
objective and bound agree within the proof tolerance, and the returned primal
passes `src/validate.py`.  The default resource guard is four million
assignment arcs; `--max-full-arcs 0` disables it when enough memory is
available.

The released records split as follows:

- 83 `Confirmed` (agreement with an individually identified published
  optimum), 117 `Certified` without an individually identified prior proof,
  and 9 `Certified dagger` with a literature discrepancy;
- 36 `par_certified` and 173 `improved_certified`;
- 265 attempted instances, of which 56 remained uncertified and 180 were not
  attempted at the reporting cutoff;
- mean total proof time 601.4 s, median 245.2 s.

The index is `results/certificates/mscflp_certificates.csv`; aggregate counts
and times are in `results/summaries/mscflp_proof_summary.json`.  Records live
under `certificates/mscflp/records/<instance>/` with `certificate.json`, a
sparse optimal witness, and the sanitized full-model solver log.

## MS-CFLP-CI — 9

MS-CFLP-CI uses a separate full-space certifier because an omitted flow arc
also introduces a binary customer-facility use variable and conflict rows; the
SSCFLP reduced-cost argument therefore does not transfer unchanged.
`src/certify_ci.py` rebuilds every flow and use variable in the original
assignment graph and uses the validated PAR solution only as a MIP start.
Incompatibility rows are separated exactly at integer incumbents through
Gurobi lazy constraints.  A record is certified only if Gurobi terminates with
an optimal status, the objective and bound agree within the declared proof
tolerance, and the complete returned primal vector passes `src/validate.py`.
Time- or memory-limited runs remain explicitly inconclusive.

Correctness follows directly from exact separation.  The base MIP contains all
original flow, use, and opening variables and all constraints except customer
incompatibilities.  At every integer incumbent, the callback examines every
facility used by every incompatible customer pair.  Each detected violation is
excluded by its original inequality.  Consequently, every integer incumbent
accepted by the callback satisfies every omitted conflict row.  If Gurobi
returns an optimal status, its incumbent is therefore globally optimal for the
complete MS-CFLP-CI formulation.  The certificate additionally requires the
saved primal objective to equal the solver objective and bound within the
declared tolerance.

The full-space construction has `2nm+m` variables and may be too large for the
largest CI instances.  Lazy separation avoids materializing all `m|E|`
potential conflict rows, but it does not reduce the number of flow and use
variables.  This limitation is explicit and no reduced-graph CI optimum is
reported as a full-space certificate.  The executable defaults to a two-million
assignment-arc resource guard; `--max-full-arcs 0` disables it when sufficient
memory is available.

The nine released CI records predate this executable certifier and have
historical full-model solver provenance.  Five have preserved exact primal
witnesses.  Four (`wlp04`, `wlp05`, `wlp06`, and `wlp22`) retain consistent
proof metadata but no exact primal vector in the available archive.  Their
records set `optimal_solution_available` to false; the release does not infer
or fabricate missing variables.  The index is
`results/certificates/mscflp_ci_certificates.csv`.

## Output and examples

Every certificate record uses repository-relative paths and stores the
SHA-256 of its released witness and proof logs.  Certificate witnesses use the
sparse one-based encoding; timed runs retain both dense and sparse encodings.
The certificate `README.md` records the common provenance and redaction notes.

```powershell
# SSCFLP: reduced model built with src/solve.py, then full-space certification
python src/certify.py path\to\instance.plc path\to\solution.npz `
  --metadata path\to\metadata.json --output certificate --threads 16

# MS-CFLP: full-model M1 certificate from a validated PAR incumbent
python src/certify_mscflp.py path\to\instance.plc path\to\par_solution.npz `
  --output mscflp-certificate --threads 16

# MS-CFLP-CI: complete model with lazy conflict separation
python src/certify_ci.py path\to\wlp01.dzn path\to\par_solution.npz `
  --output ci-certificate --threads 16
```
