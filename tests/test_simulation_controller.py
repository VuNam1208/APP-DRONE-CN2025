import os
import tempfile
import unittest

from replan_coordinator import (
    build_qgc_plan,
    build_serpentine_remap_routes,
    count_conflicts,
    count_conflicts_continuous,
    haversine_m,
    prepend_route_starts,
    serpentine_in_bbox,
)
from simulation_controller import (
    DroneStatus,
    SimulationController,
    SimulationStatus,
)
from simulate_replan_experiments import ScenarioSetup, load_plans, run_strategy


class SimulationControllerTests(unittest.TestCase):
    def test_continuous_checker_detects_between_sample_conflict(self):
        # The crossing occurs between coarse one-second samples.
        routes = {
            1: [(21.0, 105.0), (21.0, 105.00002)],
            2: [(20.99999, 105.00001), (21.00001, 105.00001)],
        }
        altitudes = {1: 12.0, 2: 12.0}
        speeds = {1: 4.2, 2: 4.4}
        delays = {1: 0.0, 2: 0.0}
        sampled = count_conflicts(
            routes, altitudes, speeds, delays, 0.25, sample_dt=1.0
        )
        continuous = count_conflicts_continuous(
            routes, altitudes, speeds, delays, 0.25
        )
        self.assertEqual(sampled, 0)
        self.assertEqual(continuous, 1)

    def test_conflict_prediction_includes_transit_to_replanned_route(self):
        starts = {
            1: (21.0, 105.0),
            2: (21.0, 105.001),
        }
        routes = {
            1: [(21.001, 105.001), (21.002, 105.001)],
            2: [(21.001, 105.0), (21.002, 105.0)],
        }
        coverage_only = count_conflicts(
            routes, {1: 12.0, 2: 12.0}, {1: 10.0, 2: 10.0},
            {1: 0.0, 2: 0.0}, 15.0,
        )
        with_transit = count_conflicts(
            prepend_route_starts(routes, starts),
            {1: 12.0, 2: 12.0},
            {1: 10.0, 2: 10.0},
            {1: 0.0, 2: 0.0},
            15.0,
        )
        self.assertEqual(coverage_only, 0)
        self.assertEqual(with_transit, 1)

    def test_serpentine_starts_at_nearest_north_south_edge(self):
        bbox = (21.0, 21.001, 105.0, 105.001)
        from_north = serpentine_in_bbox(bbox, 20.0, start=(21.0011, 105.0))
        from_south = serpentine_in_bbox(bbox, 20.0, start=(20.9999, 105.0))
        self.assertAlmostEqual(from_north[0][0], bbox[1])
        self.assertAlmostEqual(from_south[0][0], bbox[0])

    def test_replan_strips_do_not_overlap(self):
        pool = [
            (21.0, 105.0),
            (21.001, 105.0),
            (21.0, 105.003),
            (21.001, 105.003),
        ]
        positions = {
            2: (21.0, 105.0),
            3: (21.0, 105.0015),
            4: (21.0, 105.003),
        }
        routes = build_serpentine_remap_routes(pool, (2, 3, 4), positions, 10.0)
        longitude_ranges = sorted(
            (min(point[1] for point in route), max(point[1] for point in route))
            for route in routes.values()
        )
        for left, right in zip(longitude_ranges, longitude_ranges[1:]):
            self.assertLess(left[1], right[0])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.mission_dir = self.temp_dir.name
        routes = {
            1: [(21.0, 105.0), (21.001, 105.0), (21.001, 105.001)],
            2: [(21.0, 105.0003), (21.001, 105.0003), (21.001, 105.0013)],
            3: [(21.0, 105.0006), (21.001, 105.0006), (21.001, 105.0016)],
        }
        for drone_id, route in routes.items():
            plan = build_qgc_plan(route, route[0], altitude=12.0)
            path = os.path.join(self.mission_dir, f"points{drone_id}.plan")
            with open(path, "w", encoding="utf-8") as handle:
                import json

                json.dump(plan, handle)

    def tearDown(self):
        self.temp_dir.cleanup()

    def make_controller(self, **kwargs):
        defaults = dict(
            mission_dir=self.mission_dir,
            uav_ids=(1, 2, 3),
            speed_mps=10.0,
            failed_uav=1,
            failure_progress=0.4,
            strategy="Proposed",
        )
        defaults.update(kwargs)
        return SimulationController(**defaults)

    def mission_bytes(self):
        contents = {}
        for name in os.listdir(self.mission_dir):
            with open(os.path.join(self.mission_dir, name), "rb") as handle:
                contents[name] = handle.read()
        return contents

    def test_step_interpolates_position(self):
        controller = self.make_controller(failure_progress=1.0)
        start = controller.drones[1].position
        controller.start()
        controller.step(5.0)
        current = controller.drones[1].position

        self.assertEqual(controller.status, SimulationStatus.RUNNING)
        self.assertGreater(haversine_m(start[0], start[1], current[0], current[1]), 45.0)
        self.assertLess(haversine_m(start[0], start[1], current[0], current[1]), 55.0)
        self.assertNotEqual(current, controller.drones[1].route[1])

    def test_failure_triggers_replan_without_writing_plans(self):
        controller = self.make_controller(failure_progress=0.05)
        events = []
        controller.on("failure_injected", events.append)
        before = self.mission_bytes()

        controller.start()
        controller.step(2.0)

        self.assertEqual(controller.drones[1].status, DroneStatus.FAILED)
        self.assertIsNotNone(controller.last_replan_result)
        self.assertEqual(len(events), 1)
        self.assertTrue(
            any(
                drone.status in (DroneStatus.FLYING, DroneStatus.DELAYED)
                for drone_id, drone in controller.drones.items()
                if drone_id != 1
            )
        )
        after = self.mission_bytes()
        self.assertEqual(before, after)

    def test_replan_excludes_waypoints_already_covered(self):
        controller = self.make_controller(failure_progress=1.0)
        completed = set()
        expected_remaining = set()
        for drone in controller.drones.values():
            completed.update(drone.original_route[:2])
            expected_remaining.update(drone.original_route[2:])
            drone.segment_index = 2
            drone.position = drone.original_route[1]

        controller.start()
        result = controller.inject_failure(1, "lost_link")

        self.assertIsNotNone(result)
        replanned = {point for route in result.routes.values() for point in route}
        self.assertTrue(replanned)
        self.assertTrue(replanned.issubset(expected_remaining))
        self.assertTrue(replanned.isdisjoint(completed))

    def test_b1_replans_without_caa_delay(self):
        controller = self.make_controller(strategy="B1", failure_progress=0.05)
        controller.start()
        controller.step(2.0)

        result = controller.last_replan_result
        self.assertIsNotNone(result)
        self.assertTrue(all(delay == 0.0 for delay in result.delays.values()))
        self.assertEqual(len(set(result.altitudes.values())), 1)

    def test_caa_ablation_modes(self):
        routes = {
            1: [(21.0, 105.0), (21.001, 105.001)],
            2: [(21.0, 105.001), (21.001, 105.0)],
        }
        common = dict(
            routes=routes,
            base_altitudes={1: 12.0, 2: 12.0},
            speeds={1: 20.0, 2: 20.0},
            battery={1: 80.0, 2: 70.0},
            d_safe=15.0,
            delta_h=5.0,
        )
        from replan_coordinator import apply_collision_avoidance

        _, altitude, altitude_delay = apply_collision_avoidance(
            **common, use_altitude=True, use_delay=False
        )
        _, delay_altitude, delay = apply_collision_avoidance(
            **common, use_altitude=False, use_delay=True
        )
        self.assertGreater(abs(altitude[1] - altitude[2]), 4.0)
        self.assertTrue(all(value == 0.0 for value in altitude_delay.values()))
        self.assertEqual(delay_altitude[1], delay_altitude[2])
        self.assertTrue(any(value > 0.0 for value in delay.values()))

    def test_caa_uses_common_reference_for_heterogeneous_base_altitudes(self):
        from replan_coordinator import apply_collision_avoidance

        routes = {
            1: [(21.0, 105.0), (21.001, 105.001)],
            2: [(21.0, 105.001), (21.001, 105.0)],
            3: [(21.0005, 105.0), (21.0005, 105.001)],
        }
        _, altitudes, _ = apply_collision_avoidance(
            routes=routes,
            base_altitudes={1: 20.0, 2: 15.0, 3: 12.0},
            speeds={1: 2.0, 2: 2.0, 3: 2.0},
            battery={1: 80.0, 2: 70.0, 3: 60.0},
            d_safe=15.0,
            delta_h=5.0,
            use_altitude=True,
            use_delay=False,
        )

        self.assertEqual(altitudes, {1: 20.0, 2: 25.0, 3: 30.0})
        assigned = sorted(altitudes.values())
        self.assertTrue(
            all(right - left >= 4.0 for left, right in zip(assigned, assigned[1:]))
        )

    def test_reset_restores_initial_state(self):
        controller = self.make_controller(failure_progress=0.05)
        initial = controller.positions()
        controller.start()
        controller.step(2.0)
        controller.reset()

        self.assertEqual(controller.status, SimulationStatus.READY)
        self.assertEqual(controller.simulation_time_s, 0.0)
        self.assertFalse(controller.snapshot()["failure_triggered"])
        self.assertEqual(controller.positions(), initial)
        self.assertTrue(
            all(drone.status == DroneStatus.READY for drone in controller.drones.values())
        )

    def test_simulation_finishes(self):
        controller = self.make_controller(
            speed_mps=1000.0,
            failure_progress=1.0,
            strategy="B0",
        )
        finished = []
        controller.on("simulation_finished", finished.append)
        controller.start()
        controller.step(1.0)

        self.assertEqual(controller.status, SimulationStatus.FINISHED)
        self.assertEqual(len(finished), 1)
        metrics = controller.metrics()
        self.assertIsNotNone(metrics)
        self.assertEqual(len(metrics["completion_times_s"]), 3)
        self.assertIsNotNone(metrics["simulation_end_s"])

    def test_metrics_match_offline_harness_for_same_inputs(self):
        controller = self.make_controller(
            strategy="Proposed",
            failure_progress=0.5,
        )
        # Match the harness' progress=0 seed: first coverage waypoint, not home.
        for drone in controller.drones.values():
            drone.position = drone.original_route[0]
        controller.start()
        controller.inject_failure(1, "lost_link")
        metrics = controller.metrics()

        plans = load_plans(self.mission_dir, (1, 2, 3))
        scenario = ScenarioSetup(
            name="S1",
            failed=1,
            progress=0.0,
            battery={1: 80, 2: 80, 3: 80},
            note="shared-input comparison",
        )
        offline = run_strategy(
            strategy="Proposed",
            mission_dir=self.mission_dir,
            plans=plans,
            scenario=scenario,
            cover_radius_m=metrics["cover_radius_m"],
            speed_mps=10.0,
            d_safe_m=15.0,
        )

        self.assertEqual(metrics["eta_pct"], offline["eta_pct"])
        self.assertEqual(metrics["t_fin_s"], offline["t_fin_s"])
        self.assertEqual(metrics["l_max_m"], offline["l_max_m"])
        self.assertEqual(metrics["n_c_after"], int(offline["n_c"]))


if __name__ == "__main__":
    unittest.main()
