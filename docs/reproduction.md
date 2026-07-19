# Reproduction protocol

1. Install the dependencies from `requirements.txt` and activate a valid
   Gurobi license.  No license file belongs in this repository.
2. Obtain benchmark files from their original sources.
3. Verify each file against `data/instance_manifest.csv`.
4. Run `src/solve.py` with the corresponding problem name.  Defaults reproduce
   the frozen time, thread, seed, and initialization protocol.
5. Validate the dense or sparse solution with `src/validate.py`.
6. Compare the generated metadata and progress trace with the archived record.

The 600-second SSCFLP limit includes instance reading, graph construction,
constructive initialization, and optimization.  MS-CFLP also uses an
end-to-end 600-second limit but no initializer.  MS-CFLP-CI uses an end-to-end
limit of `10*sqrt(m)` seconds.

Full-space certification is a separate, untimed experiment.  It may use 16
threads and is never included in the 600-second heuristic comparison.  The
certifier accepts only a feasible incumbent from a reduced model solved to
optimality and records each LP-pricing and MIP-verification stage.

Historical SSCFLP certificate records identify the exact certifier source by
SHA-256.  The released `src/certify.py` is the compact reference implementation
of the same proof procedure; it may produce different solver traces while
establishing the same full-space claim.

Run `python src/results.py checksums .` after producing or changing artifacts.
All commands are platform-independent; examples in the README use PowerShell.
