"""Small end-to-end tests on synthetic instances.

    python -m unittest discover -s tests -v

The solver tests are skipped when gurobipy is not installed.
"""

from __future__ import annotations

import itertools
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from instances import read_instance  # noqa: E402
from par import VARIANTS, build_candidates  # noqa: E402
from results import read_solution, write_solution  # noqa: E402
from validate import validate  # noqa: E402

try:
    import gurobipy  # noqa: F401
except ImportError:
    gurobipy = None


def random_instance(seed, customers=8, facilities=4, rho=2.0):
    rng = np.random.default_rng(seed)
    demands = rng.integers(5, 20, customers).astype(float)
    capacities = rng.integers(20, 40, facilities).astype(float)
    capacities *= rho * demands.sum() / capacities.sum()
    capacities = np.ceil(capacities)
    fixed = rng.integers(50, 150, facilities).astype(float)
    points = rng.random((customers + facilities, 2))
    costs = np.round(10 * np.linalg.norm(points[:customers, None] - points[None, customers:], axis=2), 3)
    return demands, capacities, fixed, costs


def write_plc(path, demands, capacities, fixed, costs, customers_first=False):
    n, m = len(demands), len(capacities)
    header = f"{n} {m}" if customers_first else f"{m} {n}"
    body = [demands, capacities, fixed, costs.T.ravel()]
    path.write_text(header + "\n" + "\n".join(" ".join(map(str, v)) for v in body) + "\n")


def write_dzn(path, demands, capacities, fixed, costs, pairs):
    def vector(values):
        return "[" + ", ".join(str(int(v)) for v in values) + "]"

    def matrix(rows):
        return "[" + "".join("| " + ", ".join(str(v) for v in row) + " " for row in rows) + "|]"

    path.write_text(
        f"Warehouses = {len(capacities)};\nStores = {len(demands)};\n\n"
        f"Capacity = {vector(capacities)};\nFixedCost = {vector(fixed)};\nGoods = {vector(demands)};\n"
        f"SupplyCost = {matrix(costs)};\nIncompatibilities = {len(pairs)};\n"
        f"IncompatiblePairs = {matrix([(i + 1, k + 1) for i, k in pairs])};\n"
    )


def brute_force_sscflp(demands, capacities, fixed, costs):
    n, m = costs.shape
    best = np.inf
    for assignment in itertools.product(range(m), repeat=n):
        load = np.bincount(assignment, weights=demands, minlength=m)
        if (load > capacities + 1e-9).any():
            continue
        opened = load > 0
        cost = fixed[opened].sum() + (demands * costs[np.arange(n), assignment]).sum()
        best = min(best, cost)
    return best


class ReaderTests(unittest.TestCase):
    def test_plc_header_order(self):
        data = random_instance(0, customers=5, facilities=3)
        with tempfile.TemporaryDirectory() as tmp:
            plain = Path(tmp) / "tiny.plc"
            named = Path(tmp) / "p3-5-1.plc"
            write_plc(plain, *data)
            write_plc(named, *data, customers_first=True)
            for path in (plain, named):
                instance = read_instance(path)
                self.assertEqual((instance["customers"], instance["facilities"]), (5, 3))
                np.testing.assert_allclose(instance["demands"], data[0])
                np.testing.assert_allclose(instance["capacities"], data[1])
                np.testing.assert_allclose(instance["assignment_costs"], data[3])

    def test_dzn(self):
        data = random_instance(1, customers=5, facilities=3)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tiny.dzn"
            write_dzn(path, *data, pairs=[(0, 1), (2, 4)])
            instance = read_instance(path)
        self.assertEqual(instance["incompatible_pairs"], [(0, 1), (2, 4)])
        np.testing.assert_allclose(instance["assignment_costs"], data[3])
        np.testing.assert_allclose(instance["fixed_costs"], data[2])


class GraphTests(unittest.TestCase):
    def setUp(self):
        demands, capacities, fixed, costs = random_instance(2, customers=40, facilities=30)
        capacities[0] = 1.0  # too small for any customer under single sourcing
        self.instance = {"name": "tiny", "customers": 40, "facilities": 30, "demands": demands,
                         "capacities": capacities, "fixed_costs": fixed, "assignment_costs": costs,
                         "incompatible_pairs": [(0, 1), (0, 2), (3, 4)]}

    def test_candidates_are_cost_prefixes(self):
        for problem in ("sscflp", "mscflp", "mscflp-ci"):
            full = build_candidates(self.instance, problem, "full")["candidates"]
            for variant in VARIANTS:
                graph = build_candidates(self.instance, problem, variant)
                for row, order in zip(graph["candidates"], full):
                    self.assertGreaterEqual(len(row), 1)
                    self.assertEqual(row, order[:len(row)])
                self.assertEqual(graph["metadata"]["candidate_arcs"], sum(map(len, graph["candidates"])))
        sscflp = build_candidates(self.instance, "sscflp", "full")["candidates"]
        self.assertTrue(all(0 not in row and len(row) == 29 for row in sscflp))

    def test_par_is_sparser_than_full(self):
        par = build_candidates(self.instance, "sscflp")["metadata"]
        self.assertLess(par["candidate_arcs"], par["eligible_arcs"])

    def test_incompatibilities_shrink_lists(self):
        plain = build_candidates(self.instance, "mscflp")["candidates"]
        ci = build_candidates(self.instance, "mscflp-ci")["candidates"]
        self.assertLessEqual(len(ci[0]), len(plain[0]))
        self.assertEqual(ci[10], plain[10])


class ValidationTests(unittest.TestCase):
    def test_capacity_and_cost(self):
        instance = {"customers": 2, "facilities": 2, "demands": np.array([3.0, 4.0]),
                    "capacities": np.array([5.0, 10.0]), "fixed_costs": np.array([10.0, 20.0]),
                    "assignment_costs": np.array([[1.0, 2.0], [3.0, 4.0]]), "incompatible_pairs": []}
        y = np.array([1.0, 0.0])
        result = validate(instance, {"x": np.array([[1.0, 0.0], [1.0, 0.0]]), "y": y}, "sscflp")
        self.assertFalse(result["valid"])
        self.assertIn("capacity exceeded", result["errors"])
        result = validate(instance, {"x": np.array([[1.0, 0.0], [0.0, 1.0]]), "y": np.ones(2)}, "sscflp")
        self.assertTrue(result["valid"])
        self.assertAlmostEqual(result["objective"], 10 + 20 + 3 * 1 + 4 * 4)

    def test_solution_roundtrip(self):
        x = np.array([[0.0, 2.5], [1.0, 0.0]])
        y = np.array([1.0, 1.0])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "solution.csv.gz"
            write_solution(path, x, y)
            solution = read_solution(path, 2, 2)
        np.testing.assert_array_equal(solution["x"], x)
        np.testing.assert_array_equal(solution["y"], y)


@unittest.skipIf(gurobipy is None, "gurobipy is not installed")
class SolverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_sscflp_solve_and_certify(self):
        import certify
        from solve import solve

        data = random_instance(3)
        path = self.dir / "tiny.plc"
        write_plc(path, *data)
        result = solve(path, self.dir / "runs", "sscflp", time_limit=60)
        self.assertTrue(result["validation"]["valid"])
        proof = certify.certify(path, self.dir / "runs/sscflp/tiny/solution.csv.gz", self.dir / "proof")
        self.assertIn(proof["status"], ("certified", "certified_improved"))
        self.assertAlmostEqual(proof["objective"], brute_force_sscflp(*data), places=6)
        self.assertLessEqual(proof["objective"], result["objective"] + 1e-6)

    def test_mscflp_solve_and_certify(self):
        import certify_mscflp
        from solve import solve

        path = self.dir / "tiny.plc"
        write_plc(path, *random_instance(4, customers=12, facilities=6, rho=1.5))
        result = solve(path, self.dir / "runs", "mscflp", time_limit=60)
        self.assertTrue(result["validation"]["valid"])
        proof = certify_mscflp.certify(path, self.dir / "runs/mscflp/tiny/solution.csv.gz",
                                       self.dir / "proof")
        self.assertIn(proof["status"], ("certified", "certified_improved"))
        self.assertLessEqual(proof["objective"], result["objective"] + 1e-6)
        optimum = read_solution(self.dir / "proof/optimal_solution.csv.gz", 12, 6)
        self.assertTrue(validate(read_instance(path), optimum, "mscflp")["valid"])

    def test_mscflp_ci_solve_and_certify(self):
        import certify_ci
        from solve import solve

        path = self.dir / "tiny.dzn"
        pairs = [(0, 1), (0, 2), (1, 3), (4, 5), (6, 7), (2, 9)]
        write_dzn(path, *random_instance(5, customers=12, facilities=6, rho=1.5), pairs=pairs)
        result = solve(path, self.dir / "runs", "mscflp-ci", time_limit=60)
        self.assertTrue(result["validation"]["valid"])
        proof = certify_ci.certify(path, self.dir / "runs/mscflp-ci/tiny/solution.csv.gz",
                                   self.dir / "proof", threads=1)
        self.assertIn(proof["status"], ("certified", "certified_improved"))
        self.assertLessEqual(proof["objective"], result["objective"] + 1e-6)
        optimum = read_solution(self.dir / "proof/optimal_solution.csv.gz", 12, 6)
        self.assertTrue(validate(read_instance(path), optimum, "mscflp-ci")["valid"])


if __name__ == "__main__":
    unittest.main()
