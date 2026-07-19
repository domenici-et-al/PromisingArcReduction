# Full-space certification

The reduced graph is a heuristic restriction.  Optimality of its MIP alone is
not a proof for the original SSCFLP.  The separate certifier starts from an
optimal reduced-model incumbent and performs three auditable stages.

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

The released tolerances are in `configs/protocols.json`.  Every SSCFLP record
stores the pricing lower bound, numbers of priced and unfixed arcs, verification
size, objective, times, source hashes, available stage logs, and complete
optimal primal vector.  One historical record closes directly after fixing;
the other 130 include a verification-MIP log.
The certificate index reports 131 audited global optima: 92 first proofs at a
reported BKS, 23 first proofs with an improved incumbent, and 16
re-certifications.

The nine MS-CFLP-CI records have a different provenance: they are historical
full-model solver proofs, not outputs of the SSCFLP pricing certifier.  Five
have preserved exact primal witnesses.  Four (`wlp04`, `wlp05`, `wlp06`, and
`wlp22`) retain consistent proof metadata but no exact primal vector in the
available archive.  Their records set `optimal_solution_available` to false;
the release does not infer or fabricate missing variables.
