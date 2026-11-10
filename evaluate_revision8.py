"""3D admission rates from saved data and interleaved assignment timing."""

import csv
import hashlib
import json
import platform
import random
import statistics
import time
from pathlib import Path

from evaluate_revision2 import write_csv
from replan_coordinator import assign_contiguous_residual_segments


def read_csv(path):
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def run():
    source, output = Path("results/revision5"), Path("results/revision8")
    output.mkdir(parents=True, exist_ok=True)
    caa = read_csv(source / "caa_raw.csv")
    keys = ("spacing_m", "clearance_m", "tau0_s", "initial", "bias_m")
    groups = {}
    for row in caa:
        groups.setdefault(tuple(row[key] for key in keys), []).append(row)
    acceptance = []
    for key, subset in groups.items():
        assert len(subset) == 48
        assert len({(row["seed"], row["failed"]) for row in subset}) == 48
        accepted = sum(int(row["transition_pairs"]) == 0 for row in subset)
        acceptance.append({**dict(zip(keys, key)), "cases": len(subset),
                           "accepted": accepted, "rejected": len(subset) - accepted,
                           "acceptance_pct": 100 * accepted / len(subset)})
    write_csv(output / "acceptance_summary.csv", acceptance)
    selected = [row for row in acceptance if row["spacing_m"] == "5.0"
                and row["clearance_m"] == "4.0" and row["tau0_s"] == "2.0"]
    write_csv(output / "acceptance_nominal.csv", selected)

    mission_path = Path("results/revision2/independent_missions.json")
    raw_path = Path("results/revision2/independent_raw.csv")
    missions = {entry["seed"]: {int(key): [tuple(p) for p in route] for key, route in entry["routes"].items()}
                for entry in json.loads(mission_path.read_text(encoding="utf-8"))}
    variants = [("Fixed", None, False), ("Budget-2000-fixed", 2000, False),
                ("Budget-2000-adaptive", 2000, True), ("Budget-4000-fixed", 4000, False),
                ("Budget-4000-adaptive", 4000, True)]
    previous = {(int(row["seed"]), int(row["failed"]), int(row["budget_m"]), int(row["adaptive"])):
                int(row["feasible"]) for row in read_csv(source / "range_raw.csv")}
    cases = []
    for row in read_csv(raw_path):
        if row["strategy"] != "B1":
            continue
        seed, failed = int(row["seed"]), int(row["failed"])
        progress = json.loads(row["progress_json"])
        remaining = {drone: route[int((len(route) - 2) * progress[str(drone)]):]
                     for drone, route in missions[seed].items()}
        own = {drone: route for drone, route in remaining.items() if drone != failed}
        positions = {drone: route[0] for drone, route in own.items()}
        calls = {}
        for name, budget, adaptive in variants:
            kwargs = {"adaptive_segment_count": adaptive}
            if budget is not None:
                kwargs.update(range_budgets_m={drone: budget for drone in own},
                              return_homes={drone: (21.0, 105.8) for drone in own})
            calls[name] = (remaining[failed], list(own), own, positions, kwargs)
        cases.append((seed, failed, calls))
    assert len(cases) == 120
    for name, _, _ in variants:
        failed_route, alive, own, positions, kwargs = cases[0][2][name]
        assign_contiguous_residual_segments(failed_route, alive, own, positions, **kwargs)
    rng = random.Random(20261008)
    timings = []
    for repeat in range(5):
        for seed, failed, calls in cases:
            order = list(variants)
            rng.shuffle(order)
            for order_index, (name, budget, adaptive) in enumerate(order):
                failed_route, alive, own, positions, kwargs = calls[name]
                started = time.perf_counter_ns()
                result = assign_contiguous_residual_segments(failed_route, alive, own, positions, **kwargs)
                elapsed_ms = (time.perf_counter_ns() - started) / 1e6
                if budget is not None:
                    assert int(result is not None) == previous[(seed, failed, budget, int(adaptive))]
                timings.append({"seed": seed, "failed": failed, "repeat": repeat,
                                "order": order_index, "variant": name,
                                "elapsed_ms": elapsed_ms, "feasible": int(result is not None)})
        print(f"Timing repeat {repeat + 1}/5 completed", flush=True)
    write_csv(output / "timing_raw.csv", timings)
    summary = []
    baseline = {(seed, failed): statistics.mean(row["elapsed_ms"] for row in timings
                                             if row["seed"] == seed and row["failed"] == failed
                                             and row["variant"] == "Fixed") for seed, failed, _ in cases}
    for name, _, _ in variants:
        subset = [row for row in timings if row["variant"] == name]
        values = [row["elapsed_ms"] for row in subset]
        case_ratios = [statistics.mean(row["elapsed_ms"] for row in subset
                                      if row["seed"] == seed and row["failed"] == failed) / baseline[(seed, failed)]
                       for seed, failed, _ in cases]
        summary.append({"variant": name, "calls": len(values), "cases": 120,
                        "mean_ms": statistics.mean(values), "median_ms": statistics.median(values),
                        "p95_ms": statistics.quantiles(values, n=20, method="inclusive")[-1],
                        "max_ms": max(values), "paired_mean_ratio": statistics.mean(case_ratios),
                        "feasible_cases": sum(row["feasible"] for row in subset if row["repeat"] == 0)})
    write_csv(output / "timing_summary.csv", summary)
    labels = {"Fixed": "Không ngân sách, cố định", "Budget-2000-fixed": "2000 m, cố định",
              "Budget-2000-adaptive": "2000 m, thích nghi", "Budget-4000-fixed": "4000 m, cố định",
              "Budget-4000-adaptive": "4000 m, thích nghi"}
    table = [r"\begin{tabular}{lrrrr}", r"\toprule",
             r"Biến thể & TB (ms) & P95 (ms) & Cực đại (ms) & Tỷ số theo cặp \\", r"\midrule"]
    for row in summary:
        table.append(f"{labels[row['variant']]} & {row['mean_ms']:.2f} & {row['p95_ms']:.2f} & "
                     f"{row['max_ms']:.2f} & {row['paired_mean_ratio']:.2f} " + r"\\")
    table.extend([r"\bottomrule", r"\end{tabular}"])
    (output / "timing_table.tex").write_text("\n".join(table) + "\n", encoding="utf-8")
    files = [Path(__file__), Path("replan_coordinator.py"), source / "caa_raw.csv",
             source / "range_raw.csv", mission_path, raw_path]
    metadata = {"python": platform.python_version(), "platform": platform.platform(),
                "repeats": 5, "order_seed": 20261008, "warmup_calls": 5,
                "timing_scope": "Assignment only, includes feasibility checks and unsuccessful searches; excludes preparation, CSV, CAA and transmission.",
                "acceptance_scope": "Offline 3D check only, no schedule repair and no joint energy/range or full-mission-completion claim.",
                "sha256": {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}}
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps({"acceptance": selected, "timing": summary}, indent=2))


if __name__ == "__main__":
    run()
