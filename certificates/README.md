# Certificates

This directory contains **368 full-model optimality certificates** in three
families.  Certificate witnesses are released in sparse `csv.gz` form; all
indices are one-based and omitted entries are zero.

| Family | Certificates | Witnesses | Verification logs | Index |
|---|---:|---:|---:|---|
| SSCFLP | 150 | 150 | 149 | `results/certificates/sscflp_all_certificates.csv` |
| MS-CFLP | 209 | 209 | 209 | `results/certificates/mscflp_certificates.csv` |
| MS-CFLP-CI | 9 | 5 | 0 | `results/certificates/mscflp_ci_certificates.csv` |
| **Total** | **368** | **364** | **358** | |

## Layout

```text
certificates/
├── sscflp/records/<instance>/          # 150
│   ├── certificate.json
│   ├── optimal_solution.csv.gz
│   ├── verification.log.gz             # 149; p800-4400-88 has none
│   └── pricing_iterations.csv          # 131 phasewise
├── mscflp/records/<instance>/          # 209
│   ├── certificate.json
│   ├── optimal_solution.csv.gz
│   └── verification.log.gz
└── mscflp-ci/records/<instance>/       # 9
    ├── certificate.json
    └── optimal_solution.csv.gz         # 5; four have no witness
```

## SSCFLP — 150

The ledger is one campaign: 131 records retain LP-pricing and
verification-MIP telemetry (`trace_profile: lp_pricing_phasewise`) and 19
retain terminal safe-support telemetry (`terminal_safe_support`).  Relative to
the exact statuses reported in the PaKS benchmark table, 106 are first proofs
at a reported BKS, 28 are first proofs with an improved incumbent, and 16 are
re-certifications.

Common provenance for the phasewise records: reference values from Bakker et
al. (2025), arXiv:2512.08576v1; literature cutoff 2026-07-18; evidence from
PDF pp. 11 and 14 and the complete-results table.  Large temporary omitted-arc
dumps and simplex basis files are intentionally omitted.  The record
`p800-4400-88` closes directly after reduced-cost fixing
(`verification.status = not_needed`) and therefore has no verification log;
the other 130 phasewise records and all 19 terminal records do.

## MS-CFLP — 209

These are **full-model M1 optimality proofs** of the original MS-CFLP
formulation; PAR supplies the incumbent and M1 solves the complete model.  The
proof basis is `global_MIP_bound`, not a reduced-model optimum.

- 83 records agree with an individually identified published optimum
  (`Confirmed`), 117 are `Certified` without an individually identified prior
  proof, and 9 are `Certified dagger` with a literature discrepancy.
- 36 proofs confirm the PAR incumbent (`par_certified`); 173 improve it
  (`improved_certified`).
- Of 265 attempted instances, 56 remained uncertified and 180 were not
  attempted at the reporting cutoff.
- Mean total proof time is 601.4 s and median is 245.2 s.  Each record stores
  the proof time, objective, lower bound, proof tolerance, literature status,
  source-campaign hash, and released sparse witness.

`results/summaries/mscflp_proof_summary.json` records the aggregate counts and
times.  The supplement reports the full 445-instance view; the released index
contains the 209 certified rows.

## MS-CFLP-CI — 9

Nine historical full-model proofs.  Exact primal witnesses were preserved for
five; `wlp04`, `wlp05`, `wlp06`, and `wlp22` retain consistent proof metadata
but no exact primal vector.  Their records set
`optimal_solution_available = false`; no variables are inferred or fabricated.
The executable `src/certify_ci.py` generates new full-space certificates with
lazy conflict separation and a two-million-arc resource guard.

## Validation and integrity

- `results/summaries/certificate_validation.csv` has 155 rows: 131 phasewise
  SSCFLP, 19 terminal SSCFLP, and 5 CI witnesses.
- `results/summaries/certificate_integrity_audit.json` reports 364 verified
  witnesses with zero failures.
- Every `certificate.json` stores repository-relative paths and the SHA-256 of
  its released witness and proof logs.
- Logs are sanitized: only local filesystem paths and Gurobi license
  registration identifiers are redacted; numerical solver output is unchanged.
