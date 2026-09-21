import json
import unittest

from PyQt5.QtCore import QCoreApplication

from integrated_map import MapBridge


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


if __name__ == "__main__":
    unittest.main()
