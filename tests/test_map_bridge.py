import json
import unittest

from PyQt5.QtCore import QCoreApplication

from integrated_map import MapBridge, integrated_map_html


class MapBridgeSimulationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.bridge = MapBridge(object())
        self.commands = []
        self.bridge.simulationCommand.connect(self.commands.append)

    def test_commands_wait_until_map_is_ready(self):
        self.bridge.setSimulationRoutes(
            {1: [(21.0, 105.0), (21.001, 105.001)]}, "initial"
        )
        self.bridge.setSimulationPositions(
            {1: {"position": (21.0, 105.0), "status": "FLYING", "altitude_m": 12}}
        )
        self.assertEqual(self.commands, [])

        self.bridge.notifyMapReady()

        self.assertEqual(len(self.commands), 2)
        routes = json.loads(self.commands[0])
        positions = json.loads(self.commands[1])
        self.assertEqual(routes["action"], "set_routes")
        self.assertEqual(routes["routes"]["1"][1], [21.001, 105.001])
        self.assertEqual(positions["positions"]["1"]["status"], "FLYING")

    def test_live_commands_emit_immediately_after_ready(self):
        self.bridge.notifyMapReady()
        self.bridge.markFailedDrone(2, (21.0, 105.0))
        self.bridge.showSimulationEvent("replan complete")
        self.bridge.fitSimulationBounds()
        self.bridge.clearSimulation()

        actions = [json.loads(command)["action"] for command in self.commands]
        self.assertEqual(
            actions, ["mark_failed", "show_event", "fit_bounds", "clear"]
        )

    def test_rejects_unknown_route_phase(self):
        with self.assertRaises(ValueError):
            self.bridge.setSimulationRoutes({}, "other")

    def test_trail_points_are_sent_incrementally(self):
        self.bridge.notifyMapReady()
        self.bridge.appendSimulationTrail(2, (21.0, 105.0))

        command = json.loads(self.commands[-1])
        self.assertEqual(command["action"], "append_trail")
        self.assertEqual(command["drone_id"], 2)
        self.assertEqual(command["position"], [21.0, 105.0])

    def test_replan_removes_obsolete_future_route_layers(self):
        html = integrated_map_html()
        self.assertIn("if (phase === 'replan')", html)
        self.assertIn("simulationLayers.initial.clearLayers()", html)
        self.assertIn("simulationLayers.failed.clearLayers()", html)
        self.assertIn("simulationLayers.flown.clearLayers()", html)
        self.assertIn("simulationTrailEnabled = false", html)
        self.assertIn("drawSimulationCoverageBoundary(routes)", html)
        self.assertIn("function simulationCoverageRoute(route)", html)
        self.assertIn("simulationCoverageRoute(rawRoute)", html)
        self.assertIn("phase === 'initial' ? simulationCoverageRoute(route) : route", html)
        self.assertIn("splitByLatitude", html)
        self.assertIn("zones[index - 1].centerLat + item.centerLat", html)
        self.assertIn("simulationCoverageLayer.clearLayers()", html)

        self.assertIn("VÙNG UAV", html)
        self.assertIn("L.polygon(boundaryBounds", html)
        self.assertIn("KHU VỰC QUÉT", html)

    def test_basemap_has_fallback_and_visible_failure_notice(self):
        html = integrated_map_html()
        self.assertIn("https://tile.openstreetmap.org/{z}/{x}/{y}.png", html)
        self.assertNotIn("https://{s}.tile.openstreetmap.org/", html)
        self.assertIn("https://a.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png", html)
        self.assertIn("layer.on('tileerror'", html)
        self.assertIn("activeBasemap === layer && loadedThisView === 0", html)
        self.assertIn("sourceIndex + 1 < basemapSources.length", html)
        self.assertIn("Không tải được ảnh nền bản đồ", html)
        self.assertIn("https://www.openstreetmap.org/copyright", html)
        self.assertIn("https://www.openstreetmap.fr/", html)


if __name__ == "__main__":
    unittest.main()
