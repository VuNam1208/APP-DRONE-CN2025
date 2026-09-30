import json
import os
import tempfile
import unittest

from replan_coordinator import build_qgc_plan, haversine_m, load_waypoints_from_plan, path_length_m
from simulation_missions import prepare_adjacent_sim_missions


class AdjacentMissionTests(unittest.TestCase):
    def test_transformed_layouts_have_distinct_geometry(self):
        source_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "mission")
        hashes = []
        for layout in ("adjacent", "rotated", "elongated"):
            owner, mission_dir = prepare_adjacent_sim_missions(source_dir, layout=layout)
            try:
                routes = [
                    load_waypoints_from_plan(os.path.join(mission_dir, f"points{i}.plan"))
                    for i in (1, 2, 3, 4)
                ]
                self.assertTrue(all(len(route) >= 2 for route in routes))
                hashes.append(tuple(routes[0][:2]))
            finally:
                owner.cleanup()
        self.assertEqual(len(set(hashes)), 3)

    def test_fourth_lane_is_adjacent_and_source_is_unchanged(self):
        with tempfile.TemporaryDirectory() as source_dir:
            routes = {
                1: [(21.002, 105.0), (21.002, 105.001)],
                2: [(21.0015, 105.0), (21.0015, 105.001)],
                3: [(21.001, 105.0), (21.001, 105.001)],
            }
            for drone_id, route in routes.items():
                path = os.path.join(source_dir, f"points{drone_id}.plan")
                with open(path, "w", encoding="utf-8") as handle:
                    json.dump(build_qgc_plan(route, route[0], 12.0), handle)
            original = {}
            for name in os.listdir(source_dir):
                with open(os.path.join(source_dir, name), "rb") as handle:
                    original[name] = handle.read()

            temporary, sim_dir = prepare_adjacent_sim_missions(source_dir)
            try:
                generated = {
                    drone_id: load_waypoints_from_plan(
                        os.path.join(sim_dir, f"points{drone_id}.plan")
                    )
                    for drone_id in range(1, 5)
                }
                self.assertTrue(all(len(route) >= 2 for route in generated.values()))
                centers = [
                    sum(point[0] for point in generated[drone_id])
                    / len(generated[drone_id])
                    for drone_id in range(1, 5)
                ]
                self.assertEqual(centers, sorted(centers, reverse=True))
                for route in generated.values():
                    segment_lengths = [
                        haversine_m(*start, *end)
                        for start, end in zip(route, route[1:])
                    ]
                    if len(route) > 2:
                        self.assertTrue(
                            any(abs(distance - 10.0) < 0.75 for distance in segment_lengths)
                        )
                self.assertFalse(os.path.exists(os.path.join(source_dir, "points4.plan")))
                for name, contents in original.items():
                    with open(os.path.join(source_dir, name), "rb") as handle:
                        self.assertEqual(handle.read(), contents)
            finally:
                temporary.cleanup()


if __name__ == "__main__":
    unittest.main()
