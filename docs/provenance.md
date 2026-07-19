# Provenance

This repository is a compact release assembled from the frozen final runs.
The public modules contain only the released PAR construction, three problem
formulations, validation, result I/O, and SSCFLP certification.  Development
drivers and discarded formulations are not part of the artifact.

The 970 timed solutions were converted without re-optimization.  SSCFLP
assignment files were expanded to complete binary `x` and `y` arrays.  The
archived MS-CFLP and MS-CFLP-CI full flow matrices were preserved exactly;
canonical `y` values indicate facilities carrying positive flow, and CI `a`
values indicate positive customer-facility use.  Each conversion preserves
the validated objective and is independently checked in both dense and sparse
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
Reference tables are copied without modification into `data/references/`, and
derived comparison tables are under `results/comparisons/`.

Raw benchmark files are third-party data and are not redistributed.  Their
names and SHA-256 digests are sufficient to detect version or formatting
differences before reproduction.

Gurobi logs retain solver parameters, model statistics, progress, bounds,
nodes, and timing.  Before publication, only local filesystem paths and Gurobi
license registration identifiers were redacted.  Each normalized metadata or
certificate record states this transformation and hashes the released log.
