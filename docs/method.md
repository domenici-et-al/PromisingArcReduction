# Released method

Let `n` and `m` be the numbers of customers and facilities, `d_i` customer
demand, `s_j` facility capacity, and `c_ij` assignment cost.  For SSCFLP,
facility `j` is eligible for customer `i` only if `s_j >= d_i`; all facilities
are eligible when demand is splittable.  Each customer's eligible facilities
are ordered by `(c_ij, j)`.

PAR computes the total-demand ratio `rho = sum(s_j)/sum(d_i)` and the aggregate
tightness scale `eta = sqrt(rho/(rho-1))`.  Its preliminary horizon is
`q = ceil(eta*sqrt(m))`.  If `Q_i` is the first `min(q,m_i)` facilities in
customer `i`'s ordering, pressure and availability are

```text
p_j = (1/s_j) * sum_{i: j in Q_i} d_i/|Q_i|,
w_j = 1/max(1,p_j).
```

Thus an uncongested facility contributes one effective option, while a shared
facility contributes less than one.

For each customer, local pressure, its damped congestion factor, and the final
effective-option target are

```text
pbar_i = sum_{j in Q_i} p_j*s_j*w_j / sum_{j in Q_i} s_j*w_j,
kappa_i = sqrt(max(1, eta*pbar_i)),
t_i = max(1, eta*sqrt(kappa_i*m_i*d_i/dbar)),
```

where `dbar` is mean demand.  PAR retains the shortest cost-ordered prefix
`P_i` satisfying `sum_{j in P_i} w_j >= t_i`; if no shorter prefix reaches the
target, it retains the complete eligible list.  The square roots encode
sublinear candidate growth and damp both global tightness and local pressure.
No trained coefficient, user-selected parameter, or instance-class branch is
used.

For MS-CFLP, demand is splittable and every facility is eligible; the same
pressure, congestion, target, and weighted stopping rule is retained.  For
MS-CFLP-CI, the inherited MS-CFLP width is contracted according to each
customer's conflict degree.  If the inherited width is `r0`, degree is `g`,
and there are `m` facilities, the retained width is the ceiling of the positive
solution of

```text
r + g*r^2/(2m) = r0,
```

bounded between one and `r0`.  This balances assignment arcs and the expected
number of conflict rows induced by candidate-set overlap.  After candidate
sets are built, their intersections are computed exactly; only those conflict
constraints are materialized.

The complete implementation is in [`src/par.py`](../src/par.py).  Tie breaking,
rounding, and all ablation variants are explicit there.

## Interpretation and scope

When assignment costs reflect distance or another local metric, increasing a
cost radius linearly can reveal a superlinear number of nearby facilities.  A
square-root rank scale is the planar version of this geometric effect and is
used here as a deliberately damped baseline; pressure and capacity tightness
then correct it for competition.  This argument motivates the scale but is not
an assumption that every benchmark matrix is exactly Euclidean or
two-dimensional.

PAR is a deterministic heuristic graph restriction, not a theorem that every
global optimum lies in the retained graph.  Every reduced-model incumbent is
feasible for the original formulation after omitted variables are set to zero.
Global-optimality claims require the separate full-space procedure described
in [`certification.md`](certification.md).
