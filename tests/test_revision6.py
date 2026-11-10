import unittest

from evaluate_revision6 import bootstrap_interval, mission_means


class RevisionSixTests(unittest.TestCase):
    def test_failures_are_grouped_by_mission(self):
        rows = [{"seed": seed, "failed": failed, "gain_pct": seed * failed}
                for seed in (1, 2) for failed in (1, 2, 3, 4)]
        self.assertEqual(mission_means(rows), [
            {"seed": 1, "gain_mean_pct": 2.5}, {"seed": 2, "gain_mean_pct": 5.0}])

    def test_incomplete_or_duplicate_missions_are_rejected(self):
        rows = [{"seed": 1, "failed": failed, "gain_pct": 1} for failed in (1, 2, 3)]
        with self.assertRaises(ValueError):
            mission_means(rows)
        with self.assertRaises(ValueError):
            mission_means(rows + [rows[0]])

    def test_identical_mission_gains_have_zero_width_interval(self):
        low, high, _ = bootstrap_interval([2.0] * 30, repeats=100)
        self.assertEqual((low, high), (2.0, 2.0))

    def test_resampling_is_reproducible_and_reflects_variation(self):
        result = bootstrap_interval([0.0, 1.0, 4.0, 8.0], repeats=100, seed=3)
        self.assertEqual(result, bootstrap_interval([0.0, 1.0, 4.0, 8.0], repeats=100, seed=3))
        self.assertLess(result[0], result[1])
        self.assertTrue(all(0 <= value <= 8 for value in result[2]))


if __name__ == "__main__":
    unittest.main()
