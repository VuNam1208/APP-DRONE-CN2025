import csv
import ast
import json
import os
from pathlib import Path
import tempfile
import unittest

from replan_coordinator import build_qgc_plan
from simulation_controller import DroneStatus, SimulationController, SimulationStatus
from simulation_metrics import export_metrics_csv


class OfflineSimulationEndToEndTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.mission_dir = self.temp_dir.name
        routes = {
            1: [(21.0, 105.0), (21.0010, 105.0), (21.0010, 105.0010)],
            2: [(21.0, 105.0002), (21.0010, 105.0002), (21.0010, 105.0012)],
            3: [(21.0, 105.0004), (21.0010, 105.0004), (21.0010, 105.0014)],
            4: [(21.0, 105.0006), (21.0010, 105.0006), (21.0010, 105.0016)],
        }
        self.write_routes(routes)

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_routes(self, routes):
        for drone_id, route in routes.items():
            plan = build_qgc_plan(route, route[0], altitude=12.0)
            with open(
                os.path.join(self.mission_dir, f"points{drone_id}.plan"),
                "w",
                encoding="utf-8",
            ) as handle:
                json.dump(plan, handle)

    def controller(self, strategy="Proposed", progress=0.40, ids=(1, 2, 3, 4)):
        return SimulationController(
            self.mission_dir,
            uav_ids=ids,
            speed_mps=30.0,
            failed_uav=1,
            failure_progress=progress,
            strategy=strategy,
        )

    @staticmethod
    def run_to_finish(controller, max_steps=1000):
        controller.start()
        for _ in range(max_steps):
            controller.step(1.0)
            if controller.status == SimulationStatus.FINISHED:
                return
        raise AssertionError("simulation did not finish")

    def test_b0_b1_and_proposed_complete_at_40_percent(self):
        original = {
            name: Path(self.mission_dir, name).read_bytes()
            for name in os.listdir(self.mission_dir)
        }
        results = {}
        for strategy in ("B0", "B1", "Proposed"):
            with self.subTest(strategy=strategy):
                controller = self.controller(strategy=strategy)
                self.run_to_finish(controller)
                metrics = controller.metrics()
                self.assertTrue(controller.snapshot()["failure_triggered"])
                self.assertEqual(controller.drones[1].status, DroneStatus.FAILED)
                self.assertIsNotNone(metrics)
                self.assertGreater(metrics["pool_pts"], 0)
                self.assertGreater(metrics["route_pts"], 0)
                results[strategy] = metrics

        self.assertLessEqual(
            results["Proposed"]["n_c_after"], results["Proposed"]["n_c_before"]
        )
        current = {
            name: Path(self.mission_dir, name).read_bytes()
            for name in os.listdir(self.mission_dir)
        }
        self.assertEqual(original, current)

    def test_early_failure_and_manual_failure(self):
        early = self.controller(progress=0.25)
        early.start()
        while not early.snapshot()["failure_triggered"]:
            early.step(0.5)
        self.assertGreaterEqual(early.drones[1].progress, 0.25)
        self.assertLess(early.drones[1].progress, 0.35)

        manual = self.controller(progress=0.90)
        manual.start()
        manual.step(0.5)
        manual.inject_failure(1, "low_battery")
        self.assertEqual(manual.drones[1].status, DroneStatus.FAILED)
        self.assertEqual(manual.failure_type, "low_battery")
        self.assertGreaterEqual(manual.metrics()["t_react_s"], 0.01)
        self.assertLess(manual.metrics()["t_react_s"], 3.0)

    def test_pause_resume_and_reset_while_running(self):
        controller = self.controller()
        controller.start()
        controller.step(1.0)
        position = controller.positions()[1]
        controller.pause()
        controller.step(10.0)
        self.assertEqual(controller.positions()[1], position)
        controller.resume()
        controller.step(1.0)
        self.assertNotEqual(controller.positions()[1], position)
        controller.reset()
        self.assertEqual(controller.status, SimulationStatus.READY)
        self.assertEqual(controller.simulation_time_s, 0.0)
        self.assertFalse(controller.snapshot()["failure_triggered"])

    def test_missing_mission_is_reported(self):
        os.remove(os.path.join(self.mission_dir, "points4.plan"))
        with self.assertRaises(FileNotFoundError):
            self.controller()

    def test_more_alive_uavs_than_remaining_strips(self):
        shared = [(21.0, 105.0), (21.0001, 105.0001)]
        self.write_routes({drone_id: shared for drone_id in range(1, 6)})
        controller = self.controller(ids=(1, 2, 3, 4, 5), progress=0.01)
        controller.start()
        controller.inject_failure(1, "lost_link")
        result = controller.last_replan_result
        self.assertIsNotNone(result)
        self.assertLessEqual(len(result.routes), 4)
        self.assertGreater(len(result.routes), 0)

    def test_completed_result_exports_reproducible_csv(self):
        controller = self.controller(strategy="Proposed")
        self.run_to_finish(controller)
        metrics = controller.metrics()
        metrics["configured_failure_progress"] = 0.40
        metrics["playback_x"] = 10.0
        output = os.path.join(self.temp_dir.name, "result.csv")
        export_metrics_csv(metrics, output)

        with open(output, "r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 1)
        required = {
            "strategy",
            "failed_uav",
            "failure_type",
            "eta_pct",
            "t_fin_s",
            "l_max_m",
            "n_c_before",
            "n_c_after",
            "t_react_s",
            "pool_pts",
            "route_pts",
            "completion_times_s",
            "configured_failure_progress",
            "playback_x",
        }
        self.assertTrue(required.issubset(rows[0]))
        self.assertEqual(rows[0]["strategy"], "Proposed")
        self.assertEqual(float(rows[0]["configured_failure_progress"]), 0.40)

    def test_sim_core_has_no_mavsdk_dependency_and_main_has_mode_guard(self):
        root = Path(__file__).resolve().parents[1]
        controller_source = (root / "simulation_controller.py").read_text(encoding="utf-8")
        main_source = (root / "main.py").read_text(encoding="utf-8")
        tree = ast.parse(controller_source)
        imported_modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.append(node.module)
        self.assertFalse(any(name.startswith("mavsdk") for name in imported_modules))
        self.assertIn("MAVSDK access is disabled in Offline SIM mode", main_source)
        self.assertIn(
            'getattr(self, "operation_mode", "LIVE") != "LIVE"', main_source
        )


if __name__ == "__main__":
    unittest.main()
