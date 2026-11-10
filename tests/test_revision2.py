import unittest

from evaluate_revision2 import fidelity_metrics, generate_mission, plan_routes
from replan_coordinator import assign_contiguous_residual_segments


class RevisionTwoTests(unittest.TestCase):
    def test_repeated_original_edge_uses_presence_not_multiplicity(self):
        a, b = (21.0, 105.8), (21.0, 105.801)
        metrics = fidelity_metrics({1: [a, b, a]}, {2: [a, b]})
        self.assertEqual(metrics["edge_retention_pct"], 100)
        self.assertEqual(metrics["nonoriginal_pct"], 0)

    def test_point_retention_does_not_imply_edge_retention(self):
        a, b, c = (21.0, 105.8), (21.0, 105.801), (21.001, 105.801)
        metrics = fidelity_metrics({1: [a, b, c]}, {2: [a, c, b]})
        self.assertEqual(metrics["eta_pct"], 100)
        self.assertGreater(metrics["edge_retention_pct"], 0)
        self.assertLess(metrics["edge_retention_pct"], 100)
        self.assertGreater(metrics["nonoriginal_pct"], 0)

    def test_reversal_and_shared_boundary_keep_edges(self):
        a, b, c = (21.0, 105.8), (21.0, 105.801), (21.001, 105.801)
        metrics = fidelity_metrics({1: [a, b, c]}, {2: [b, a], 3: [b, c]})
        self.assertEqual(metrics["edge_retention_pct"], 100)
        self.assertEqual(metrics["nonoriginal_pct"], 0)

    def test_generated_missions_are_reproducible_and_distinct(self):
        self.assertEqual(generate_mission(1), generate_mission(1))
        self.assertNotEqual(generate_mission(1), generate_mission(2))

    def test_application_planner_preserves_synthetic_edges(self):
        plans, _ = generate_mission(7)
        flown, _ = plan_routes(plans, 1, "B1")
        metrics = fidelity_metrics(plans, flown)
        self.assertEqual(metrics["eta_pct"], 100)
        self.assertAlmostEqual(metrics["edge_retention_pct"], 100)

    def test_submeter_vertices_are_preserved_in_own_and_failed_routes(self):
        plans = {
            drone: [(21.0 + drone * 0.001, 105.8 + offset)
                    for offset in (0, 0.000005, 0.00002)]
            for drone in (1, 2, 3)
        }
        flown, _ = plan_routes(plans, 1, "B1")
        metrics = fidelity_metrics(plans, flown)
        self.assertEqual(metrics["eta_pct"], 100)
        self.assertAlmostEqual(metrics["edge_retention_pct"], 100)

    def test_single_waypoint_is_assigned_to_exactly_one_helper(self):
        target = (21.0, 105.8)
        own = {2: [(21.001, 105.8)], 3: [(21.002, 105.8)]}
        shares = assign_contiguous_residual_segments(
            [target], list(own), own, {drone: route[0] for drone, route in own.items()}
        )
        self.assertEqual(sum(len(route) for route in shares.values()), 1)
        self.assertIn([target], shares.values())
        flown, _ = plan_routes({1: [target], **own}, 1, "B1")
        self.assertEqual(fidelity_metrics({1: [target], **own}, flown)["eta_pct"], 100)

    def test_empty_failed_route_creates_no_shares(self):
        own = {2: [(21.001, 105.8)], 3: [(21.002, 105.8)]}
        shares = assign_contiguous_residual_segments(
            [], list(own), own, {drone: route[0] for drone, route in own.items()}
        )
        self.assertEqual(shares, {2: [], 3: []})


if __name__ == "__main__":
    unittest.main()
