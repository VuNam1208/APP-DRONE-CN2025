import tempfile
import unittest

from simulate_replan_experiments import _summarize, _write_latex


class ExperimentReportingTests(unittest.TestCase):
    def test_summary_reports_timing_distribution(self):
        base = {
            "scenario": "S1",
            "strategy": "Proposed",
            "failed_uav": 1,
            "failure_progress": 0.4,
            "eta_pct": 100.0,
            "t_fin_s": 10.0,
            "l_max_m": 20.0,
            "n_c": 0,
            "t_detect_s": 3.0,
            "pool_pts": 5,
            "route_pts": 8,
            "mission_hash": "abc",
            "code_hash": "code",
            "git_revision": "def",
        }
        rows = [
            {**base, "t_compute_s": 0.01, "t_react_s": 3.01},
            {**base, "t_compute_s": 0.03, "t_react_s": 3.03},
        ]
        summary = _summarize(rows)[0]
        self.assertEqual(summary["runs"], 2)
        self.assertAlmostEqual(summary["t_compute_mean_s"], 0.02)
        self.assertAlmostEqual(summary["t_compute_median_s"], 0.02)
        self.assertGreater(summary["t_compute_std_s"], 0.0)
        self.assertAlmostEqual(summary["t_react_mean_s"], 3.02)

    def test_latex_table_is_generated_from_summary(self):
        row = {
            "scenario": "S1",
            "strategy": "Proposed",
            "eta_pct": 100.0,
            "t_fin_s": 10.0,
            "l_max_m": 20.0,
            "n_c": 0,
            "t_react_mean_s": 3.02,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = directory + "/table.tex"
            _write_latex(path, [row])
            with open(path, encoding="utf-8") as handle:
                output = handle.read()
        self.assertIn("S1 & Proposed & 100.0", output)
        self.assertIn("3.020", output)


if __name__ == "__main__":
    unittest.main()
