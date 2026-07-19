# Benchmark instances

The benchmark files are not redistributed.  Place locally obtained files in
any directory and pass their paths to `src/solve.py`.

The large `p` instances originate from the Guastaroba--Speranza capacitated
facility-location collection and are used in both SSCFLP and MS-CFLP form.  The
SSCFLP comparison values are those reported by Bakker et al.; the MS-CFLP table
records its comparator source per row.  The WLP and CFLP-CI DZN instances are
from the customer-incompatibility benchmark used by the cited LNS work.

[`data/instance_manifest.csv`](../data/instance_manifest.csv) identifies every
expected file by name and SHA-256.  A run should be compared with the published
artifact only when its hash matches.  The `distributed` column is false for
every benchmark.

Primary references:

- Guastaroba and Speranza (2012), *Kernel search for the capacitated facility
  location problem*.
- Bakker et al. (2025), arXiv:2512.08576.
- Gjergji et al. (2026), arXiv:2605.28337.
