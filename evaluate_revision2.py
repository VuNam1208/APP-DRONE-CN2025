"""Independent synthetic missions and route-fidelity checks for revision 2.

Uses the application's planner without writing flight plans. Edge fidelity is
a geometric proxy, not a sensor-coverage or flight-safety measurement.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import random
import statistics
import time
from pathlib import Path

from replan_coordinator import (
    ReplanConfig, ReplanCoordinator, assign_contiguous_residual_segments,
    haversine_m, path_length_m, prepend_route_starts,
)


def generate_mission(seed: int, count: int = 4):
    rng = random.Random(seed)
    width = rng.uniform(100, 450)
    spacing = rng.uniform(8, 22)
    angle = rng.uniform(0, 2 * math.pi)
    routes = {}
    offset = 0.0

    def geo(x, y):
        east = x * math.cos(angle) - y * math.sin(angle)
        north = x * math.sin(angle) + y * math.cos(angle)
        return (21.0 + north / 111320, 105.8 + east / (111320 * math.cos(math.radians(21))))

    for drone in range(1, count + 1):
        lanes = rng.randint(4, 12)
        route = []
        # Independently sampled endpoints change the zone shape and leg lengths.
        for lane in range(lanes):
            left = rng.uniform(0, 0.2 * width)
            right = width * rng.uniform(0.65, 1.0)
            samples = rng.randint(1, 4)
            xs = [left + (right - left) * i / samples for i in range(samples + 1)]
            if lane % 2:
                xs.reverse()
            route.extend(geo(x, offset + lane * spacing) for x in xs)
        if rng.choice((False, True)):
            route.reverse()
        routes[drone] = route
        offset += (lanes + rng.uniform(1, 3)) * spacing
    return routes, {"width_m": width, "spacing_m": spacing, "angle_rad": angle}


def edge_key(a, b):
    return tuple(sorted((tuple(a), tuple(b))))


def fidelity_metrics(original, flown):
    """Length-weighted undirected edge retention; exact copied coordinates."""
    required = [(a, b) for route in original.values() for a, b in zip(route, route[1:])]
    flown_edges = [(a, b) for route in flown.values() for a, b in zip(route, route[1:])]
    required_keys = {edge_key(a, b) for a, b in required}
    flown_keys = {edge_key(a, b) for a, b in flown_edges}
    total = sum(haversine_m(*a, *b) for a, b in required)
    retained = sum(haversine_m(*a, *b) for a, b in required if edge_key(a, b) in flown_keys)
    length = sum(path_length_m(route) for route in flown.values())
    nonoriginal = sum(haversine_m(*a, *b) for a, b in flown_edges if edge_key(a, b) not in required_keys)
    points = {point for route in flown.values() for point in route}
    targets = [point for route in original.values() for point in route]
    return {
        "eta_pct": 100 * sum(point in points for point in targets) / len(targets),
        "edge_retention_pct": 100 * retained / total if total else 100.0,
        "nonoriginal_pct": 100 * nonoriginal / length if length else 0.0,
    }


def plan_routes(remaining, failed, strategy):
    coordinator = ReplanCoordinator("", ReplanConfig(
        monitor_indices=tuple(remaining), remap_mode="waypoints",
        local_only=strategy != "Greedy", contiguous_failed_handoff=strategy != "Greedy",
        assignment_objective="connector" if strategy == "Connector-first" else "makespan",
        apply_caa=False, write_plans=False,
    ), log_fn=lambda message: None)
    positions = {}
    for drone, route in remaining.items():
        positions[drone] = route[0]
        coordinator.update_position(drone, *route[0], 12.0)
        coordinator.mark_connected(drone, True)
        coordinator.set_remaining_waypoints(drone, route)
    coordinator.states[failed].failed = True
    started = time.perf_counter()
    result = coordinator.build_replan(failed)
    elapsed = time.perf_counter() - started
    if result is None:
        raise RuntimeError("Planner returned no result")
    return prepend_route_starts(result.routes, positions), elapsed


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run(output: Path, missions: int, seed: int):
    output.mkdir(parents=True, exist_ok=True)
    raw, specifications, paired = [], [], []
    for mission_index in range(missions):
        mission_seed = seed + mission_index
        plans, parameters = generate_mission(mission_seed)
        rng = random.Random(mission_seed + 100000)
        specifications.append({"seed": mission_seed, "parameters": parameters, "routes": plans})
        for failed in plans:
            progress = {drone: rng.uniform(0.2, 0.8) for drone in plans}
            remaining = {drone: route[int((len(route) - 2) * progress[drone]):] for drone, route in plans.items()}
            by_strategy = {}
            # Alternate order to reduce systematic timing bias.
            strategies = ["B1", "Connector-first", "Greedy"]
            if (mission_index + failed) % 2:
                strategies.reverse()
            for strategy in strategies:
                flown, elapsed = plan_routes(remaining, failed, strategy)
                lengths = [path_length_m(route) for route in flown.values()]
                row = {
                    "seed": mission_seed, "failed": failed, "strategy": strategy,
                    "progress_json": json.dumps(progress, sort_keys=True),
                    **fidelity_metrics(remaining, flown),
                    "t_fin_s": max(lengths) / 2, "imbalance": max(lengths) / statistics.mean(lengths),
                    "compute_s": elapsed,
                }
                # Illustrative range budgets, not calibrated battery capacities.
                # Includes straight-line RTL and 20% reserve (range / 0.8).
                required = [
                    (path_length_m(route) + haversine_m(*route[-1], 21.0, 105.8)) / 0.8
                    for route in flown.values()
                ]
                for budget in (1000, 2000, 4000):
                    row[f"range_{budget}m_feasible"] = int(max(required) <= budget)
                raw.append(row)
                by_strategy[strategy] = row
            paired.append({
                "seed": mission_seed, "failed": failed,
                "b1_greedy_time_ratio": by_strategy["B1"]["t_fin_s"] / by_strategy["Greedy"]["t_fin_s"],
                "b1_connector_gain_pct": 100 * (1 - by_strategy["B1"]["t_fin_s"] / by_strategy["Connector-first"]["t_fin_s"]),
            })
    write_csv(output / "independent_raw.csv", raw)
    write_csv(output / "independent_paired.csv", paired)
    summary = []
    metrics = ["eta_pct", "edge_retention_pct", "nonoriginal_pct", "t_fin_s", "imbalance", "compute_s",
               "range_1000m_feasible", "range_2000m_feasible", "range_4000m_feasible"]
    for strategy in ("B1", "Connector-first", "Greedy"):
        subset = [row for row in raw if row["strategy"] == strategy]
        summary.append({"strategy": strategy, "missions": missions, "configurations": len(subset),
                        **{metric: statistics.mean(row[metric] for row in subset) for metric in metrics}})
    write_csv(output / "independent_summary.csv", summary)
    # Mission, rather than failure scenario, is the statistical unit.
    mission_gains = [statistics.mean(row["b1_connector_gain_pct"] for row in paired if row["seed"] == seed + i)
                     for i in range(missions)]
    scaling = []
    for helpers in range(2, 7):
        plans, _ = generate_mission(seed, helpers + 1)
        own = {drone: route for drone, route in plans.items() if drone != 1}
        positions = {drone: route[0] for drone, route in own.items()}
        for repeat in range(3):
            started = time.perf_counter()
            assign_contiguous_residual_segments(plans[1], list(own), own, positions)
            scaling.append({"helpers": helpers, "candidates": math.factorial(helpers) * 2 ** helpers,
                            "repeat": repeat, "assignment_s": time.perf_counter() - started})
    write_csv(output / "scaling_raw.csv", scaling)
    (output / "independent_missions.json").write_text(json.dumps(specifications, indent=2), encoding="utf-8")
    metadata = {"seed": seed, "missions": missions, "python": platform.python_version(),
                "platform": platform.platform(), "speed_mps": 2, "caa": False,
                "source_hashes": {name: hashlib.sha256(Path(name).read_bytes()).hexdigest()
                                  for name in ("evaluate_revision2.py", "replan_coordinator.py")},
                "mean_paired_time_ratio": statistics.mean(row["b1_greedy_time_ratio"] for row in paired),
                "mission_connector_gain_mean_pct": statistics.mean(mission_gains),
                "mission_connector_gain_min_pct": min(mission_gains),
                "mission_connector_gain_max_pct": max(mission_gains),
                "limitations": "Synthetic geometry; exact edges; no sensor, energy calibration, CAA, or SITL."}
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    table = [r"\begin{tabular}{lrrrrr}", r"\toprule",
             r"Phương án & $\eta$ (\%) & $\rho_E$ (\%) & $\delta_E$ (\%) & $T_{\rm fin}$ (s) & $I_L$ \\", r"\midrule"]
    for row in summary:
        table.append(f"{row['strategy']} & {row['eta_pct']:.1f} & {row['edge_retention_pct']:.1f} & "
                     f"{row['nonoriginal_pct']:.1f} & {row['t_fin_s']:.1f} & {row['imbalance']:.3f} " + r"\\")
    table.extend([r"\bottomrule", r"\end{tabular}"])
    (output / "independent_table.tex").write_text("\n".join(table) + "\n", encoding="utf-8")
    print(json.dumps({"summary": summary, "metadata": metadata,
                      "scaling_mean_s": {m: statistics.mean(row["assignment_s"] for row in scaling if row["helpers"] == m)
                                         for m in range(2, 7)}}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--missions", type=int, default=30)
    parser.add_argument("--seed", type=int, default=20261008)
    parser.add_argument("--out", type=Path, default=Path("results/revision2"))
    args = parser.parse_args()
    if args.missions < 2:
        parser.error("--missions must be at least 2")
    run(args.out, args.missions, args.seed)
