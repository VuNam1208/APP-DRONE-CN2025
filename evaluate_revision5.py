"""Continuous spatial matching, paired gains and 3D CAA sensitivity.

Reuses saved revision-2 missions/progress. No mission files are modified.
"""

from __future__ import annotations

import csv
import hashlib
import itertools
import json
import math
import platform
import statistics
from pathlib import Path

import shapely
from shapely.geometry import LineString
from shapely.ops import unary_union

from evaluate_revision2 import plan_routes, write_csv
from replan_coordinator import (
    apply_collision_avoidance, assign_contiguous_residual_segments,
    haversine_m, path_length_m,
)


def local_xy(point):
    return ((point[1] - 105.8) * math.pi / 180 * 6371000 * math.cos(math.radians(21)),
            (point[0] - 21) * math.pi / 180 * 6371000)


def spatial_retention(original, flown, tolerance):
    """Length within a union of continuous polyline buffers (64 arcs/quadrant)."""
    geometry = unary_union([LineString(route).buffer(tolerance, resolution=64)
                            for route in flown.values() if len(route) > 1])
    lines = [LineString(route) for route in original.values() if len(route) > 1]
    length = sum(line.length for line in lines)
    if not length:
        return None
    return 100 * sum(line.intersection(geometry).length for line in lines) / length


def profile(route, initial_z, target_z, delay, bias=0.0, climb_speed=1.0):
    """Time-stamped XYZ vertices: climb while holding XY, wait, then cruise."""
    x, y = route[0]
    vertices = [(0.0, (x, y, initial_z + bias))]
    now = abs(target_z - initial_z) / climb_speed
    if now:
        vertices.append((now, (x, y, target_z + bias)))
    if delay:
        now += delay
        vertices.append((now, (x, y, target_z + bias)))
    for a, b in zip(route, route[1:]):
        distance = math.dist(a, b)
        if distance:
            now += distance / 2.0
            vertices.append((now, (*b, target_z + bias)))
    return vertices


def conflict_pairs_3d(profiles, horizontal, vertical):
    """Exact interval overlap for piecewise-linear XYZ and strict thresholds.

    Vehicles remain at their final positions until the shared horizon. The
    vertical inequality restricts the overlap; horizontal closest approach is
    minimized on that restricted interval. No temporal sampling is used.
    """
    horizon = max(vertices[-1][0] for vertices in profiles.values())
    legs = {}
    for drone, vertices in profiles.items():
        vertices = list(vertices)
        if vertices[-1][0] < horizon:
            vertices.append((horizon, vertices[-1][1]))
        legs[drone] = [(t0, t1, p0, tuple((b - a) / (t1 - t0) for a, b in zip(p0, p1)))
                       for (t0, p0), (t1, p1) in zip(vertices, vertices[1:]) if t1 > t0]
    count = 0
    for first, second in itertools.combinations(legs, 2):
        i = j = 0
        left, right = legs[first], legs[second]
        while i < len(left) and j < len(right):
            a, b = left[i], right[j]
            start, end = max(a[0], b[0]), min(a[1], b[1])
            if end > start:
                relative = [a[2][k] + a[3][k] * (start - a[0]) -
                            b[2][k] - b[3][k] * (start - b[0]) for k in range(3)]
                velocity = [a[3][k] - b[3][k] for k in range(3)]
                lo, hi = 0.0, end - start
                z, vz = relative[2], velocity[2]
                if abs(vz) < 1e-12:
                    if abs(z) >= vertical:
                        lo, hi = 1.0, 0.0
                else:
                    bounds = sorted(((-vertical - z) / vz, (vertical - z) / vz))
                    lo, hi = max(lo, bounds[0]), min(hi, bounds[1])
                if lo < hi:
                    rx, ry = relative[:2]
                    vx, vy = velocity[:2]
                    vv = vx * vx + vy * vy
                    closest = lo if vv < 1e-12 else max(lo, min(hi, -(rx * vx + ry * vy) / vv))
                    if (rx + vx * closest) ** 2 + (ry + vy * closest) ** 2 < horizontal ** 2:
                        count += 1
                        break
            if a[1] <= b[1]:
                i += 1
            else:
                j += 1
    return count


def run():
    source, output = Path("results/revision2"), Path("results/revision5")
    output.mkdir(parents=True, exist_ok=True)
    missions = {entry["seed"]: {int(key): [tuple(p) for p in route] for key, route in entry["routes"].items()}
                for entry in json.loads((source / "independent_missions.json").read_text(encoding="utf-8"))}
    with (source / "independent_raw.csv").open(encoding="utf-8") as handle:
        saved = list(csv.DictReader(handle))
    geometry_rows, gain_rows, caa_cases, range_rows = [], [], [], []
    for seed, failed in sorted({(int(row["seed"]), int(row["failed"])) for row in saved}):
        case = {row["strategy"]: row for row in saved if int(row["seed"]) == seed and int(row["failed"]) == failed}
        plans = missions[seed]
        progress = json.loads(case["B1"]["progress_json"])
        remaining = {drone: route[int((len(route) - 2) * progress[str(drone)]):] for drone, route in plans.items()}
        original_xy = {drone: [local_xy(point) for point in route] for drone, route in remaining.items()}
        for strategy in ("B1", "Connector-first", "Greedy"):
            flown, _ = plan_routes(remaining, failed, strategy)
            xy = {drone: [local_xy(point) for point in route] for drone, route in flown.items()}
            for tolerance in (0.25, 1.0, 2.0):
                geometry_rows.append({"seed": seed, "failed": failed, "strategy": strategy,
                                      "tolerance_m": tolerance,
                                      "spatial_retention_pct": spatial_retention(original_xy, xy, tolerance)})
            if strategy == "B1" and seed < min(missions) + 12:
                caa_cases.append((seed, failed, flown, xy))
        own = [path_length_m(route) for drone, route in remaining.items() if drone != failed]
        own_mean = statistics.mean(own)
        own_routes = {drone: route for drone, route in remaining.items() if drone != failed}
        positions = {drone: route[0] for drone, route in own_routes.items()}
        homes = {drone: (21.0, 105.8) for drone in own_routes}
        for budget, adaptive in itertools.product((2000, 4000), (False, True)):
            shares = assign_contiguous_residual_segments(
                remaining[failed], list(own_routes), own_routes, positions,
                adaptive_segment_count=adaptive,
                range_budgets_m={drone: budget for drone in own_routes},
                return_homes=homes,
            )
            if shares is not None:
                for drone in own_routes:
                    route = [positions[drone]] + own_routes[drone] + shares[drone]
                    required = path_length_m(route) + haversine_m(*route[-1], *homes[drone])
                    assert required <= 0.8 * budget + 1e-7
                assert all(any(a == x and b == y or a == y and b == x
                               for share in shares.values() for x, y in zip(share, share[1:]))
                           for a, b in zip(remaining[failed], remaining[failed][1:]))
            range_rows.append({"seed": seed, "failed": failed, "budget_m": budget,
                               "adaptive": int(adaptive), "feasible": int(shares is not None),
                               "baseline_feasible": int(case["B1"][f"range_{budget}m_feasible"])})
        gain_rows.append({"seed": seed, "failed": failed,
                          "gain_pct": 100 * (1 - float(case["B1"]["t_fin_s"]) / float(case["Connector-first"]["t_fin_s"])),
                          "own_load_cv": statistics.pstdev(own) / own_mean,
                          "failed_to_mean_own": path_length_m(remaining[failed]) / own_mean,
                          "b1_time_s": float(case["B1"]["t_fin_s"]),
                          "connector_time_s": float(case["Connector-first"]["t_fin_s"])})
    write_csv(output / "spatial_raw.csv", geometry_rows)
    spatial_summary = []
    for strategy, tolerance in itertools.product(("B1", "Connector-first", "Greedy"), (0.25, 1.0, 2.0)):
        values = [row["spatial_retention_pct"] for row in geometry_rows if row["strategy"] == strategy and row["tolerance_m"] == tolerance]
        spatial_summary.append({"strategy": strategy, "tolerance_m": tolerance,
                                "mean_pct": statistics.mean(values), "min_pct": min(values), "max_pct": max(values)})
    write_csv(output / "spatial_summary.csv", spatial_summary)
    write_csv(output / "gain_cases.csv", gain_rows)
    gain_missions = []
    for seed in missions:
        subset = [row for row in gain_rows if row["seed"] == seed]
        gain_missions.append({"seed": seed, **{key: statistics.mean(row[key] for row in subset)
                                              for key in ("gain_pct", "own_load_cv", "failed_to_mean_own")}})
    write_csv(output / "gain_missions.csv", gain_missions)
    write_csv(output / "range_raw.csv", range_rows)
    range_summary = []
    for budget, adaptive in itertools.product((2000, 4000), (0, 1)):
        subset = [row for row in range_rows if row["budget_m"] == budget and row["adaptive"] == adaptive]
        range_summary.append({"budget_m": budget, "adaptive": adaptive, "cases": len(subset),
                              "baseline_feasible": sum(row["baseline_feasible"] for row in subset),
                              "constrained_feasible": sum(row["feasible"] for row in subset),
                              "rescued": sum(row["feasible"] and not row["baseline_feasible"] for row in subset)})
    write_csv(output / "range_summary.csv", range_summary)
    print("Spatial matching and paired analysis complete", flush=True)
    sensitivity = []
    schedule_cache = {}
    for spacing, clearance, tau, initial, bias_size in itertools.product(
            (0.0, 2.0, 4.0, 5.0, 8.0), (4.0, 6.0), (0.0, 2.0, 5.0), ("equal", "mixed"), (0.0, 1.0)):
        for seed, failed, flown, xy in caa_cases:
            ids = sorted(flown)
            starts = {drone: (12.0 if initial == "equal" else 12.0 + 5 * (len(ids) - rank - 1))
                      for rank, drone in enumerate(ids)}
            # Call the unchanged application CAA. Its nominal vertical threshold
            # is max(1, spacing-1); independent evaluation thresholds vary here.
            schedule_key = (seed, failed, spacing, tau, initial)
            if schedule_key not in schedule_cache:
                _, targets, delays = apply_collision_avoidance(
                    flown, starts, {drone: 2.0 for drone in ids},
                    {drone: 100 - rank for rank, drone in enumerate(ids)},
                    15.0, spacing, tau0=tau)
                schedule_cache[schedule_key] = (targets, delays)
            targets, delays = schedule_cache[schedule_key]
            nominal = {drone: profile(xy[drone], targets[drone], targets[drone], delays[drone]) for drone in ids}
            transitioned = {drone: profile(xy[drone], starts[drone], targets[drone], delays[drone],
                                           bias_size * (1 if rank % 2 else -1)) for rank, drone in enumerate(ids)}
            steady_pairs = conflict_pairs_3d(nominal, 15.0, clearance)
            transition_pairs = conflict_pairs_3d(transitioned, 15.0, clearance)
            sensitivity.append({"seed": seed, "failed": failed, "spacing_m": spacing,
                                "clearance_m": clearance, "tau0_s": tau, "initial": initial,
                                "bias_m": bias_size, "steady_pairs": steady_pairs,
                                "transition_pairs": transition_pairs})
    write_csv(output / "caa_raw.csv", sensitivity)
    caa_summary = []
    keys = ("spacing_m", "clearance_m", "tau0_s", "initial", "bias_m")
    groups = {}
    for row in sensitivity:
        groups.setdefault(tuple(row[key] for key in keys), []).append(row)
    for group, subset in groups.items():
        caa_summary.append({**dict(zip(keys, group)), "cases": len(subset),
                            "steady_violations": sum(row["steady_pairs"] > 0 for row in subset),
                            "transition_violations": sum(row["transition_pairs"] > 0 for row in subset),
                            "new_violations": sum(row["steady_pairs"] == 0 and row["transition_pairs"] > 0 for row in subset)})
    write_csv(output / "caa_summary.csv", caa_summary)
    mission_gains = [row["gain_pct"] for row in gain_missions]
    gain_values = [row["gain_pct"] for row in gain_rows]
    metadata = {"python": platform.python_version(), "shapely": shapely.__version__,
                "source_hashes": {name: hashlib.sha256(Path(name).read_bytes()).hexdigest()
                                  for name in ("evaluate_revision5.py", "evaluate_revision2.py", "replan_coordinator.py")},
                "input_hashes": {name: hashlib.sha256((source / name).read_bytes()).hexdigest()
                                 for name in ("independent_missions.json", "independent_raw.csv")},
                "spatial_cases": len(gain_rows), "caa_cases": len(caa_cases), "caa_evaluations": len(sensitivity),
                "positive_gain_cases": sum(value > 1e-9 for value in gain_values),
                "zero_gain_cases": sum(abs(value) <= 1e-9 for value in gain_values),
                "negative_gain_cases": sum(value < -1e-9 for value in gain_values),
                "mission_gain_mean_pct": statistics.mean(mission_gains),
                "mission_gain_median_pct": statistics.median(mission_gains),
                "mission_gain_min_pct": min(mission_gains), "mission_gain_max_pct": max(mission_gains),
                "max_gain_case": max(gain_rows, key=lambda row: row["gain_pct"]),
                "mission_gain_cv_correlation": statistics.correlation(mission_gains, [row["own_load_cv"] for row in gain_missions]),
                "mission_gain_failedload_correlation": statistics.correlation(mission_gains, [row["failed_to_mean_own"] for row in gain_missions]),
                "climb_speed_mps": 1.0, "cruise_speed_mps": 2.0,
                "geometry_note": "Local planar coordinates; 64-segment-per-quadrant polygonal buffer; no sensor model.",
                "caa_note": "Unchanged nominal CAA, threshold max(1, spacing-1); independent evaluation threshold 4/6m. Climb at t=0, delay after reaching layer, final hold; constant alternating altitude biases, not stochastic tracking errors."}
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    table = [r"\begin{tabular}{lrrr}", r"\toprule", r"Phương án & $\varepsilon=0{,}25$ m & $\varepsilon=1$ m & $\varepsilon=2$ m \\", r"\midrule"]
    for strategy in ("B1", "Connector-first", "Greedy"):
        values = [row["mean_pct"] for row in spatial_summary if row["strategy"] == strategy]
        table.append(strategy + " & " + " & ".join(f"{value:.1f}" for value in values) + r" \\")
    table.extend([r"\bottomrule", r"\end{tabular}"])
    (output / "spatial_table.tex").write_text("\n".join(table) + "\n", encoding="utf-8")
    table = [r"\begin{tabular}{rrrrrr}", r"\toprule",
             r"$\Delta h$ (m) & $h_{\rm clear}$ (m) & $\tau_0$ (s) & Tĩnh & Chuyển tầng & Lệch $\pm1$ m \\", r"\midrule"]
    for spacing, clearance, tau in itertools.product((0.0, 2.0, 4.0, 5.0, 8.0), (4.0,), (0.0, 2.0, 5.0)):
        selected = [row for row in caa_summary if row["spacing_m"] == spacing and row["clearance_m"] == clearance
                    and row["tau0_s"] == tau and row["initial"] == "mixed"]
        unbiased = next(row for row in selected if row["bias_m"] == 0)
        biased = next(row for row in selected if row["bias_m"] == 1)
        table.append(f"{spacing:g} & {clearance:g} & {tau:g} & {unbiased['steady_violations']}/48 & "
                     f"{unbiased['transition_violations']}/48 & {biased['transition_violations']}/48 " + r"\\")
    table.extend([r"\bottomrule", r"\end{tabular}"])
    (output / "caa_table.tex").write_text("\n".join(table) + "\n", encoding="utf-8")
    print(json.dumps({"spatial": spatial_summary, "range": range_summary, "metadata": metadata}, indent=2))


if __name__ == "__main__":
    run()
