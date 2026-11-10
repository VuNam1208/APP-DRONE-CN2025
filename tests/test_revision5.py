import unittest

from evaluate_revision5 import conflict_pairs_3d, profile, spatial_retention
from replan_coordinator import ReplanConfig, ReplanCoordinator, assign_contiguous_residual_segments


class RevisionFiveTests(unittest.TestCase):
    def test_retraced_original_path_counts_geometric_overlap_once(self):
        original = {1: [(0, 0), (10, 0), (0, 0)]}
        flown = {2: [(0, 0), (10, 0)]}
        self.assertAlmostEqual(spatial_retention(original, flown, 0.25), 50)

    def test_collinear_subdivision_is_not_a_spatial_loss(self):
        original = {1: [(0, 0), (5, 0), (10, 0)]}
        self.assertAlmostEqual(spatial_retention(original, {2: [(0, 0), (10, 0)]}, 0.25), 100)

    def test_parallel_path_outside_tolerance_is_not_retained(self):
        original = {1: [(0, 0), (10, 0)]}
        self.assertAlmostEqual(spatial_retention(original, {2: [(0, 2), (10, 2)]}, 1), 0)

    def test_partial_overlap_has_length_weighted_retention(self):
        original = {1: [(0, 0), (10, 0)]}
        self.assertAlmostEqual(spatial_retention(original, {2: [(0, 0), (5, 0)]}, 1), 60)

    def test_empty_edge_set_is_undefined(self):
        self.assertIsNone(spatial_retention({1: [(0, 0)]}, {2: [(0, 0), (1, 0)]}, 1))

    def test_altitude_crossing_is_detected_between_endpoints(self):
        paths = {1: [(0, (0, 0, 0)), (10, (0, 0, 10))],
                 2: [(0, (0, 0, 10)), (10, (0, 0, 0))]}
        self.assertEqual(conflict_pairs_3d(paths, 1, 1), 1)

    def test_threshold_equality_is_not_a_conflict(self):
        paths = {1: [(0, (0, 0, 0)), (10, (0, 0, 0))],
                 2: [(0, (0, 0, 4)), (10, (0, 0, 4))]}
        self.assertEqual(conflict_pairs_3d(paths, 1, 4), 0)

    def test_horizontal_and_vertical_violations_must_coincide(self):
        paths = {1: [(0, (0, 0, 0)), (10, (0, 0, 0))],
                 2: [(0, (0, 0, 10)), (10, (10, 0, 0))]}
        self.assertEqual(conflict_pairs_3d(paths, 1, 1), 0)

    def test_final_hold_is_checked(self):
        paths = {1: [(0, (0, 0, 0)), (1, (1, 0, 0))],
                 2: [(0, (10, 0, 0)), (10, (0, 0, 0))]}
        self.assertEqual(conflict_pairs_3d(paths, 0.5, 1), 1)

    def test_initially_separated_ascent_can_cross_a_held_vehicle(self):
        routes = {1: [(0, 0), (5, 0)], 2: [(10, 0), (15, 0)]}
        nominal = {1: profile(routes[1], 22, 22, 0), 2: profile(routes[2], 27, 27, 2)}
        transition = {1: profile(routes[1], 22, 22, 0), 2: profile(routes[2], 12, 27, 2)}
        self.assertEqual(conflict_pairs_3d(nominal, 15, 4), 0)
        self.assertEqual(conflict_pairs_3d(transition, 15, 4), 1)

    def test_budget_constraint_selects_an_alternative_helper(self):
        a, b = (21.0, 105.8), (21.0, 105.801)
        own, positions = {2: [], 3: []}, {2: a, 3: b}
        baseline = assign_contiguous_residual_segments([a, b], [2, 3], own, positions)
        self.assertTrue(baseline[2])
        constrained = assign_contiguous_residual_segments(
            [a, b], [2, 3], own, positions,
            range_budgets_m={2: 10, 3: 1000}, return_homes=positions)
        self.assertFalse(constrained[2])
        self.assertTrue(constrained[3])

    def test_no_feasible_assignment_returns_none(self):
        a, b = (21.0, 105.8), (21.0, 105.801)
        shares = assign_contiguous_residual_segments(
            [a, b], [2, 3], {2: [], 3: []}, {2: a, 3: b},
            range_budgets_m={2: 10, 3: 10}, return_homes={2: a, 3: b})
        self.assertIsNone(shares)

    def test_incomplete_budget_inputs_are_rejected(self):
        a, b = (21.0, 105.8), (21.0, 105.801)
        with self.assertRaises(ValueError):
            assign_contiguous_residual_segments(
                [a, b], [2], {2: []}, {2: a}, range_budgets_m={2: 100})

    def test_coordinator_does_not_finalize_infeasible_routes(self):
        a, b = (21.0, 105.8), (21.0, 105.801)
        coord = ReplanCoordinator("", ReplanConfig(
            monitor_indices=(1, 2), remap_mode="waypoints", local_only=True,
            contiguous_failed_handoff=True, write_plans=False,
            range_budgets_m={2: 10}, return_homes={2: a}), log_fn=lambda message: None)
        for drone, route in {1: [a, b], 2: [a]}.items():
            coord.update_position(drone, *route[0], 12)
            coord.mark_connected(drone, True)
            coord.set_remaining_waypoints(drone, route)
        coord.states[1].failed = True
        coord._finalize_replan = lambda **kwargs: self.fail("Infeasible routes must not be finalized")
        self.assertIsNone(coord.build_replan(1))


if __name__ == "__main__":
    unittest.main()
