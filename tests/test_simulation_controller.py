import os
import tempfile
import unittest

from replan_coordinator import build_qgc_plan, haversine_m
from simulation_controller import (
    DroneStatus,
    SimulationController,
    SimulationStatus,
)
from simulate_replan_experiments import ScenarioSetup, load_plans, run_strategy


class SimulationControllerTests(unittest.TestCase):
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

    def test_b1_replans_without_caa_delay(self):
        controller = self.make_controller(strategy="B1", failure_progress=0.05)
        controller.start()
        controller.step(2.0)

        result = controller.last_replan_result
        self.assertIsNotNone(result)
        self.assertTrue(all(delay == 0.0 for delay in result.delays.values()))
        self.assertEqual(len(set(result.altitudes.values())), 1)

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
