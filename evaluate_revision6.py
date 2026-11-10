"""Mission-level uncertainty for paired gains already measured in revision 5."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import platform
import random
import statistics
from pathlib import Path


def mission_means(rows):
    groups = {}
    for row in rows:
        seed = int(row["seed"])
        failed = int(row["failed"])
        cases = groups.setdefault(seed, {})
        value = float(row["gain_pct"])
        if failed in cases or not math.isfinite(value):
            raise ValueError("Duplicate failure case or non-finite paired gain")
        cases[failed] = value
    if not groups or any(set(cases) != {1, 2, 3, 4} for cases in groups.values()):
        raise ValueError("Each mission must contain exactly four distinct failure cases")
    return [{"seed": seed, "gain_mean_pct": statistics.mean(groups[seed].values())}
            for seed in sorted(groups)]


def bootstrap_interval(values, repeats=20000, seed=20261008):
    if len(values) < 2 or repeats < 40 or not all(math.isfinite(value) for value in values):
        raise ValueError("Require finite mission means and at least 40 resamples")
    rng = random.Random(seed)
    means = [statistics.mean(rng.choices(values, k=len(values))) for _ in range(repeats)]
    quantiles = statistics.quantiles(means, n=40, method="inclusive")
    return quantiles[0], quantiles[-1], means


def run():
    source = Path("results/revision5/gain_cases.csv")
    with source.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    missions = mission_means(rows)
    values = [row["gain_mean_pct"] for row in missions]
    low, high, resamples = bootstrap_interval(values)
    leave_one_out = [statistics.mean(values[:index] + values[index + 1:]) for index in range(len(values))]
    output = Path("results/revision6")
    output.mkdir(parents=True, exist_ok=True)
    summary = {
        "missions": len(missions), "failure_cases": len(rows),
        "mean_gain_pct": statistics.mean(values), "median_mission_gain_pct": statistics.median(values),
        "bootstrap_95_low_pct": low, "bootstrap_95_high_pct": high,
        "leave_one_out_min_pct": min(leave_one_out), "leave_one_out_max_pct": max(leave_one_out),
        "bootstrap_repeats": 20000, "bootstrap_seed": 20261008,
        "method": "Mission-cluster percentile bootstrap; inclusive linear quantiles at 2.5% and 97.5%.",
        "estimand": "Mean of four paired relative completion-time gains per independently generated mission.",
        "scope": "Conditional on the adjacent-survey mission generator and failure-progress sampling; no sensor or real-flight inference.",
        "python": platform.python_version(),
        "input_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with (output / "mission_gains.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(missions[0]))
        writer.writeheader()
        writer.writerows(missions)
    with (output / "bootstrap_means.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["resample", "mean_gain_pct"])
        writer.writerows(enumerate(resamples, start=1))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    run()
