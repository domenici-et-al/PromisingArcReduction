# Provenance

This repository is a compact release assembled from the frozen final runs.
The public modules contain only the released PAR construction, three problem
formulations, validation, result I/O, and separate SSCFLP, MS-CFLP, and
MS-CFLP-CI certification.  Development drivers and discarded formulations are
not part of the artifact.

The 970 timed solutions were converted without re-optimization.  SSCFLP
assignment files were expanded to complete binary `x` and `y` arrays.  The
archived MS-CFLP and MS-CFLP-CI full flow matrices were preserved exactly;
canonical `y` values indicate facilities carrying positive flow, and CI `a`
values indicate positive customer-facility use.  Each conversion preserves the
validated objective and is independently checked in both dense and sparse
encodings.

For 13 archived runs, the scalar objective written in the historical solver
record was outside the stated numerical tolerance of the cost independently
recomputed from that record's saved primal vector.  The original validation
breakdown agrees with the recomputed primal cost.  The public comparison tables
therefore use the released primal cost, preserve the historical scalar in
metadata, and enumerate every difference in
`results/summaries/historical_objective_reconciliation.csv`.  No variable was
changed to perform this reconciliation.

The released CI graph matches the archived final experiment, including exact
candidate-arc and materialized-conflict-row counts for all 80 instances.
Derived comparison tables are under `results/comparisons/`; the MS-CFLP table
records its `reference_source` per row, and the SSCFLP and CI tables retain the
reference values used in the paper.

Raw benchmark files and third-party reference tables are not redistributed.

## SSCFLP

The outcome ledger contains one campaign with 150 exact records: 131 retain
LP-pricing and verification-MIP telemetry, and 19 retain terminal safe-support
telemetry.  The two amounts refer to the same original-space proof scope, not
to separate campaigns.  Relative to the exact statuses reported in the PaKS
benchmark table, the ledger has 106 first proofs at a reported BKS, 28 first
proofs with an improved incumbent, and 16 re-certifications.  The 19 terminal
records add 14 proofs at a reported BKS and 5 improved proofs to the 131
phasewise records.

All 150 records now use one directory layout under
`certificates/sscflp/records/<instance>/`; `trace_profile` preserves the
noncomparable telemetry distinction.  One phasewise record,
`p800-4400-88`, closes directly after reduced-cost fixing and has no
verification log.  The common reference provenance (Bakker et al. 2025,
arXiv:2512.08576v1, cutoff 2026-07-18, source evidence, omitted intermediate
dumps) is recorded in `certificates/README.md`.

## MS-CFLP

The 209 MS-CFLP certificates are full-model M1 proofs of the original
multi-source formulation.  PAR supplies the incumbent; M1 solves the complete
model and reports `proof_basis = global_MIP_bound`.  The split is 83
`Confirmed`, 117 `Certified` without an individually identified prior proof,
and 9 `Certified dagger` with a literature discrepancy.  Thirty-six proofs
confirm the PAR incumbent and 173 improve it.  Of 265 attempted instances, 56
remained uncertified and 180 were not attempted at the reporting cutoff.  Mean
total proof time is 601.4 s and median is 245.2 s.

The released records are under `certificates/mscflp/records/<instance>/`, with
one certificate, one sparse optimal witness, and one sanitized full-model
solver log per record.  The canonical index is
`results/certificates/mscflp_certificates.csv`; aggregate counts and times are
in `results/summaries/mscflp_proof_summary.json`.  The supplement reports the
full 445-instance view, including the 56 attempted-but-uncertified and 180
not-attempted instances.

## MS-CFLP-CI

The nine released CI records precede the current executable certifier and have
historical full-model solver provenance.  Five preserve exact primal
witnesses; `wlp04`, `wlp05`, `wlp06`, and `wlp22` retain consistent proof
metadata but no exact primal vector.  The release sets
`optimal_solution_available = false` for those four and does not reconstruct
missing variables.

## Logs and common provenance

Gurobi logs retain solver parameters, model statistics, progress, bounds,
nodes, and timing.  Before publication, only local filesystem paths and Gurobi
license registration identifiers were redacted.  Each certificate record
hashes its released witness and logs; the release-level redaction and source
notes are in `certificates/README.md`.

The three certificate indices and the 155-row validation table are listed in
[`artifact-format.md`](artifact-format.md).  The release has 368 certificate
records and 364 verified witnesses.
