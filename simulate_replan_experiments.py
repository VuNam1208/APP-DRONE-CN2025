#!/usr/bin/env python3
"""
Offline kinematic experiment harness for multi-UAV fault replan.

Produces Table-3 style metrics (eta, T_fin, L_max, N_c, T_react) for:
  S1 lost-link mid-mission, S2 low-battery fail, S3 dense residual
x strategies:
  B0 no replan, B1 contiguous residual handoff without CAA,
  Proposed contiguous residual handoff + CAA

Does NOT overwrite mission/points*.plan (write_plans=False).

Usage:
  source .venv/bin/activate
  python simulate_replan_experiments.py
  python simulate_replan_experiments.py --progress 0.4 --out results/table3_offline.csv
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from replan_coordinator import (
    ReplanConfig,
    ReplanCoordinator,
    count_conflicts,
    count_conflicts_continuous,
    estimate_grid_spacing_m,
    load_waypoints_from_plan,
    path_length_m,
    prepend_route_starts,
    remaining_waypoints,
)
from simulation_metrics import (
    coverage_ratio,
    finish_time_s,
    max_path_m,
    residual_pool,
    unique_window,
)
from simulation_missions import prepare_adjacent_sim_missions

Point = Tuple[float, float]


@dataclass
class ScenarioSetup:
    name: str
    failed: int
    progress: float
    battery: Dict[int, float]
    note: str
    failure_type: str = "lost_link"


def load_plans(mission_dir: str, indices: Sequence[int]) -> Dict[int, List[Point]]:
    plans: Dict[int, List[Point]] = {}
    for i in indices:
        path = os.path.join(mission_dir, f"points{i}.plan")
        plans[i] = load_waypoints_from_plan(path)
        if not plans[i]:
            raise FileNotFoundError(f"Missing/empty plan: {path}")
    return plans


def seed_states(
    coord: ReplanCoordinator,
    plans: Dict[int, List[Point]],
    progress: float,
    battery: Dict[int, float],
    alt_rel: float = 12.0,
) -> Dict[int, Point]:
    positions: Dict[int, Point] = {}
    for i, wps in plans.items():
        idx = max(0, int(len(wps) * progress) - 1) if progress > 0 else 0
        idx = min(idx, len(wps) - 1)
        lat, lon = wps[idx]
        positions[i] = (lat, lon)
        coord.update_position(i, lat, lon, alt_rel)
        coord.update_battery(i, float(battery.get(i, 80.0)))
        coord.mark_connected(i, True, clear_failed=True)
        coord.mark_in_mission(i, True)
        coord.states[i].failed = False
    return positions


def exact_remaining_by_progress(
    plans: Dict[int, List[Point]], progress: float
) -> Dict[int, List[Point]]:
    """Return deterministic unfinished suffixes without nearest-lane ambiguity."""
    remaining: Dict[int, List[Point]] = {}
    for drone_id, route in plans.items():
        index = max(0, int(len(route) * progress) - 1) if progress > 0 else 0
        index = min(index, len(route) - 1)
        remaining[drone_id] = list(route[index:])
    return remaining


def b0_routes(
    plans: Dict[int, List[Point]],
    positions: Dict[int, Point],
    alive: Sequence[int],
) -> Dict[int, List[Point]]:
    routes: Dict[int, List[Point]] = {}
    for i in alive:
        rem = remaining_waypoints(positions[i], plans[i])
        if rem:
            routes[i] = rem
    return routes


def run_strategy(
    strategy: str,
    mission_dir: str,
    plans: Dict[int, List[Point]],
    scenario: ScenarioSetup,
    cover_radius_m: float,
    speed_mps: float,
    d_safe_m: float,
) -> Dict[str, float]:
    uav_ids = sorted(plans.keys())
    failed = scenario.failed
    alive = [i for i in uav_ids if i != failed]
    exact_remaining = exact_remaining_by_progress(plans, scenario.progress)
    residual_targets = []
    for drone_id in [failed] + alive:
        residual_targets.extend(exact_remaining[drone_id])
    targets = unique_window(residual_targets)

    adjacent_handoff = strategy != "Greedy" and scenario.progress > 0.0

    coord = ReplanCoordinator(
        mission_dir,
        ReplanConfig(
            enabled=True,
            monitor_indices=tuple(uav_ids),
            remap_mode="waypoints" if (strategy == "Greedy" or adjacent_handoff) else "serpentine",
            local_only=adjacent_handoff,
            contiguous_failed_handoff=adjacent_handoff,
            adaptive_segment_count=strategy == "Adaptive-C",
            assignment_objective=(
                "connector" if strategy == "Connector-first" else "makespan"
            ),
            apply_caa=(strategy in ("Altitude-only", "Delay-only", "Proposed")),
            caa_mode={
                "Altitude-only": "altitude",
                "Delay-only": "delay",
                "Proposed": "both",
            }.get(strategy, "both"),
            write_plans=False,
            speed_mps=speed_mps,
            d_safe_m=d_safe_m,
            grid_spacing_m=0.0,
        ),
        log_fn=lambda _m: None,
    )
    positions = seed_states(coord, plans, scenario.progress, scenario.battery)
    for drone_id, route in exact_remaining.items():
        coord.set_remaining_waypoints(drone_id, route)

    t0 = time.perf_counter()
    if strategy == "B0":
        # Fail latch only; alive keep original remaining missions.
        coord.states[failed].failed = True
        coord.states[failed].in_mission = False
        routes = {
            drone_id: list(exact_remaining[drone_id])
            for drone_id in alive
            if exact_remaining[drone_id]
        }
        altitudes = {i: 12.0 for i in routes}
        delays = {i: 0.0 for i in routes}
        speeds = {i: speed_mps for i in routes}
        n_c = count_conflicts(
            routes,
            altitudes,
            speeds,
            delays,
            d_safe_m,
            alt_clearance_m=4.0,
        )
        t_compute = time.perf_counter() - t0
    else:
        coord.states[failed].failed = True
        coord.states[failed].in_mission = False
        result = coord.build_replan(failed)
        t_compute = time.perf_counter() - t0
        if result is None or not result.routes:
            raise RuntimeError(f"{strategy} produced no routes for {scenario.name}")
        routes = result.routes
        altitudes = result.altitudes
        delays = result.delays
        n_c = int(result.conflicts_after)

    # T_react: S1 includes lost-link timeout; others are decision latency only.
    t_detect_s = coord.config.lost_timeout_s if scenario.failure_type == "lost_link" else 0.0
    t_react_s = t_detect_s + t_compute

    eta = coverage_ratio(targets, routes, cover_radius_m)
    operational_routes = prepend_route_starts(routes, positions)
    n_c_independent = count_conflicts_continuous(
        operational_routes,
        altitudes,
        {i: speed_mps for i in operational_routes},
        delays,
        d_safe_m,
        alt_clearance_m=4.0,
    )
    t_fin = finish_time_s(operational_routes, delays, speed_mps)
    l_max = max_path_m(operational_routes)
    route_lengths = [path_length_m(route) for route in operational_routes.values()]
    l_mean = statistics.fmean(route_lengths) if route_lengths else 0.0

    return {
        "eta_pct": round(eta, 1),
        "t_fin_s": round(t_fin, 1),
        "l_max_m": round(l_max, 1),
        "l_mean_m": round(l_mean, 1),
        "load_ratio": round(l_max / l_mean, 3) if l_mean > 0.0 else 0.0,
        "n_c": float(n_c),
        "n_c_independent": float(n_c_independent),
        "t_react_s": round(t_react_s, 3),
        "t_detect_s": round(t_detect_s, 3),
        "t_compute_s": t_compute,
        "pool_pts": float(len(targets)),
        "route_pts": float(sum(len(r) for r in routes.values())),
        "alive": float(len(routes)),
    }


def build_scenarios(progress: float) -> List[ScenarioSetup]:
    # Shared mid-mission progress; batteries differ by scenario.
    return [
        ScenarioSetup(
            name="S1",
            failed=1,
            progress=progress,
            battery={1: 70, 2: 80, 3: 75, 4: 65},
            note="lost-link mid coverage (T_react includes T_lost)",
        ),
        ScenarioSetup(
            name="S2",
            failed=1,
            progress=progress,
            battery={1: 20, 2: 85, 3: 70, 4: 60},
            note="low-battery fail while in-mission",
            failure_type="low_battery",
        ),
        ScenarioSetup(
            name="S3",
            failed=1,
            progress=max(0.15, progress - 0.15),
            battery={1: 72, 2: 88, 3: 78, 4: 68},
            failure_type="early_failure",
            note="earlier fail → denser residual / higher conflict risk",
        ),
    ]


def legacy_main() -> None:
    parser = argparse.ArgumentParser(description="Offline replan experiment harness")
    parser.add_argument(
        "--mission-dir",
        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "mission"),
    )
    parser.add_argument("--progress", type=float, default=0.40, help="fail progress fraction")
    parser.add_argument("--speed", type=float, default=2.0, help="nominal speed m/s")
    parser.add_argument("--d-safe", type=float, default=15.0)
    parser.add_argument(
        "--cover-radius",
        type=float,
        default=0.0,
        help="coverage match radius (m); 0 = auto ~0.6*lane spacing",
    )
    parser.add_argument(
        "--out",
        default=os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "results",
            "table3_offline.csv",
        ),
    )
    parser.add_argument("--uavs", default="1,2,3,4")
    args = parser.parse_args()

    indices = [int(x) for x in args.uavs.split(",") if x.strip()]
    plans = load_plans(args.mission_dir, indices)

    # Work on an isolated temp copy so experiments never touch mission/*.plan.
    import shutil
    import tempfile

    work_dir = tempfile.mkdtemp(prefix="replan_exp_")
    try:
        for i in indices:
            src = os.path.join(args.mission_dir, f"points{i}.plan")
            shutil.copy2(src, os.path.join(work_dir, f"points{i}.plan"))

        # Auto coverage radius from residual spacing of a mid-mission pool.
        probe_progress = args.progress
        probe_pos = {}
        for i, wps in plans.items():
            idx = max(0, int(len(wps) * probe_progress) - 1)
            probe_pos[i] = wps[min(idx, len(wps) - 1)]
        probe_pool = residual_pool(plans, probe_pos, failed=1, alive=[i for i in indices if i != 1])
        spacing = estimate_grid_spacing_m(probe_pool)
        cover_r = args.cover_radius if args.cover_radius > 0 else max(8.0, 0.6 * spacing)

        scenarios = build_scenarios(args.progress)
        strategies = ["B0", "B1", "Proposed"]
        rows: List[Dict[str, object]] = []

        print("=" * 72)
        print("Offline kinematic replan experiments (not PX4 SITL dynamics)")
        print(f"mission={args.mission_dir} (work_copy={work_dir})")
        print(f"UAVs={indices} progress={args.progress} speed={args.speed} m/s")
        print(f"d_safe={args.d_safe} m | cover_radius={cover_r:.1f} m | pool_probe={len(probe_pool)} pts")
        print("=" * 72)
        header = f"{'Scen':<5} {'Strat':<10} {'η%':>7} {'T_fin':>9} {'L_max':>9} {'N_c':>5} {'T_react':>9}"
        print(header)
        print("-" * len(header))

        for scen in scenarios:
            for strat in strategies:
                if scen.name == "S3" and strat == "B0":
                    continue  # matches paper Table 3 rows
                metrics = run_strategy(
                    strategy=strat,
                    mission_dir=work_dir,
                    plans=plans,
                    scenario=scen,
                    cover_radius_m=cover_r,
                    speed_mps=args.speed,
                    d_safe_m=args.d_safe,
                )
                row = {
                    "scenario": scen.name,
                    "strategy": strat,
                    "eta_pct": f"{metrics['eta_pct']:.1f}",
                    "t_fin_s": f"{metrics['t_fin_s']:.1f}",
                    "l_max_m": f"{metrics['l_max_m']:.1f}",
                    "n_c": int(metrics["n_c"]),
                    "t_react_s": f"{metrics['t_react_s']:.2f}",
                    "pool_pts": int(metrics["pool_pts"]),
                    "route_pts": int(metrics["route_pts"]),
                    "note": scen.note,
                }
                rows.append(row)
                print(
                    f"{scen.name:<5} {strat:<10} {metrics['eta_pct']:>7.1f} "
                    f"{metrics['t_fin_s']:>9.1f} {metrics['l_max_m']:>9.1f} "
                    f"{int(metrics['n_c']):>5} {metrics['t_react_s']:>9.2f}"
                )

        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "scenario",
                    "strategy",
                    "eta_pct",
                    "t_fin_s",
                    "l_max_m",
                    "n_c",
                    "t_react_s",
                    "pool_pts",
                    "route_pts",
                    "note",
                ],
            )
            writer.writeheader()
            writer.writerows(rows)

        print("-" * len(header))
        print(f"Wrote {args.out}")
        print(
            "Ghi chú: η = % residual WP nằm trong bán kính cover của quỹ đạo sau chiến lược; "
            "T_fin = max(delay + length/v); N_c = xung đột dự báo; "
            "T_react(S1) gồm T_lost=3s. Đây là mô phỏng động học điểm, chưa thay PX4 SITL."
        )
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def _mission_hash(mission_dir: str, indices: Sequence[int]) -> str:
    digest = hashlib.sha256()
    for drone_id in indices:
        path = os.path.join(mission_dir, f"points{drone_id}.plan")
        digest.update(f"points{drone_id}.plan\0".encode("ascii"))
        with open(path, "rb") as handle:
            digest.update(handle.read())
    return digest.hexdigest()[:16]


def _code_hash(root: str) -> str:
    digest = hashlib.sha256()
    for name in (
        "replan_coordinator.py",
        "simulation_metrics.py",
        "simulation_missions.py",
        "simulate_replan_experiments.py",
    ):
        digest.update(f"{name}\0".encode("ascii"))
        with open(os.path.join(root, name), "rb") as handle:
            digest.update(handle.read())
    return digest.hexdigest()[:16]


def _git_revision() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _write_csv(path: str, rows: List[Dict[str, object]]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _summarize(raw_rows: List[Dict[str, object]]) -> List[Dict[str, object]]:
    groups: Dict[Tuple[object, ...], List[Dict[str, object]]] = {}
    keys = ("scenario", "strategy", "failed_uav", "failure_progress")
    for row in raw_rows:
        groups.setdefault(tuple(row[key] for key in keys), []).append(row)
    summary = []
    for group_key, rows in groups.items():
        compute = [float(row["t_compute_s"]) for row in rows]
        react = [float(row["t_react_s"]) for row in rows]
        first = rows[0]
        ordered_compute = sorted(compute)
        p95_index = max(0, math.ceil(0.95 * len(ordered_compute)) - 1)
        summary.append(
            {
                **dict(zip(keys, group_key)),
                "runs": len(rows),
                "eta_pct": first["eta_pct"],
                "t_fin_s": first["t_fin_s"],
                "l_max_m": first["l_max_m"],
                "l_mean_m": first.get("l_mean_m", 0.0),
                "load_ratio": first.get("load_ratio", 0.0),
                "n_c": first["n_c"],
                "n_c_independent": first.get("n_c_independent", first["n_c"]),
                "t_detect_s": first["t_detect_s"],
                "t_compute_mean_s": round(statistics.fmean(compute), 6),
                "t_compute_median_s": round(statistics.median(compute), 6),
                "t_compute_std_s": round(statistics.stdev(compute), 6) if len(compute) > 1 else 0.0,
                "t_compute_min_s": round(min(compute), 6),
                "t_compute_max_s": round(max(compute), 6),
                "t_compute_p95_s": round(ordered_compute[p95_index], 6),
                "t_react_mean_s": round(statistics.fmean(react), 6),
                "pool_pts": first["pool_pts"],
                "route_pts": first["route_pts"],
                "mission_hash": first["mission_hash"],
                "code_hash": first["code_hash"],
                "git_revision": first["git_revision"],
            }
        )
    return summary


def _write_latex(path: str, rows: List[Dict[str, object]]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    lines = [
        "% Generated by simulate_replan_experiments.py; do not edit manually.",
        "\\begin{tabular}{@{}llrrrrr@{}}",
        "\\toprule",
        "Scenario & Strategy & $\\eta$ (\\%) & $T_{fin}$ (s) & $L_{max}$ (m) & $N_c$ & $T_{react}$ (s) \\\\",
        "\\midrule",
    ]
    for row in rows:
        lines.append(
            f"{row['scenario']} & {row['strategy']} & {float(row['eta_pct']):.1f} & "
            f"{float(row['t_fin_s']):.1f} & {float(row['l_max_m']):.1f} & "
            f"{int(row['n_c'])} & {float(row['t_react_mean_s']):.3f} \\\\"
        )
    lines.extend(["\\bottomrule", "\\end{tabular}", ""])
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    root = os.path.dirname(os.path.abspath(__file__))
    parser = argparse.ArgumentParser(description="Reproducible offline replan experiments")
    parser.add_argument("--mission-dir", default=os.path.join(root, "mission"))
    parser.add_argument(
        "--mission-layout",
        choices=("adjacent", "rotated", "elongated", "source"),
        default="adjacent",
    )
    parser.add_argument("--progresses", default="0.40")
    parser.add_argument("--failed-uavs", default="1")
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--speed", type=float, default=2.0)
    parser.add_argument("--d-safe", type=float, default=15.0)
    parser.add_argument("--cover-radius", type=float, default=0.0)
    parser.add_argument("--out-prefix", default=os.path.join(root, "results", "report_experiment"))
    parser.add_argument(
        "--strategies",
        default="B0,B1,Proposed",
        help="comma-separated: B0,Greedy,Connector-first,Fixed-C,Adaptive-C,B1,Altitude-only,Delay-only,Proposed",
    )
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be at least 1")

    mission_owner = None
    mission_dir = args.mission_dir
    if args.mission_layout != "source":
        mission_owner, mission_dir = prepare_adjacent_sim_missions(
            args.mission_dir, layout=args.mission_layout
        )
    indices = [1, 2, 3, 4]
    try:
        plans = load_plans(mission_dir, indices)
        mission_hash = _mission_hash(mission_dir, indices)
        code_hash = _code_hash(root)
        revision = _git_revision()
        progresses = [float(value) for value in args.progresses.split(",")]
        failed_uavs = [int(value) for value in args.failed_uavs.split(",")]
        strategies = [value.strip() for value in args.strategies.split(",") if value.strip()]
        valid_strategies = {
            "B0", "Greedy", "Connector-first", "Fixed-C", "Adaptive-C", "B1", "Altitude-only", "Delay-only", "Proposed"
        }
        unknown = set(strategies) - valid_strategies
        if unknown:
            parser.error(f"unknown strategies: {sorted(unknown)}")
        raw_rows: List[Dict[str, object]] = []
        run_id = 0
        for progress in progresses:
            probe_positions = {
                drone_id: route[min(max(0, int(len(route) * progress) - 1), len(route) - 1)]
                for drone_id, route in plans.items()
            }
            probe_pool = residual_pool(plans, probe_positions, 1, [2, 3, 4])
            spacing = estimate_grid_spacing_m(probe_pool)
            cover_radius = args.cover_radius or max(8.0, 0.6 * spacing)
            for failed_uav in failed_uavs:
                if failed_uav not in indices:
                    parser.error(f"unknown failed UAV: {failed_uav}")
                scenarios = build_scenarios(progress)
                for scenario in scenarios:
                    scenario.failed = failed_uav
                    for strategy in strategies:
                        if scenario.name == "S3" and strategy == "B0":
                            continue
                        for repeat in range(1, args.repeats + 1):
                            run_id += 1
                            metrics = run_strategy(
                                strategy, mission_dir, plans, scenario,
                                cover_radius, args.speed, args.d_safe,
                            )
                            raw_rows.append(
                                {
                                    "run_id": run_id,
                                    "repeat": repeat,
                                    "scenario": scenario.name,
                                    "strategy": strategy,
                                    "failed_uav": failed_uav,
                                    "failure_type": scenario.failure_type,
                                    "failure_progress": scenario.progress,
                                    "speed_mps": args.speed,
                                    "d_safe_m": args.d_safe,
                                    "cover_radius_m": round(cover_radius, 3),
                                    "uav_count": len(indices),
                                    "eta_pct": metrics["eta_pct"],
                                    "t_fin_s": metrics["t_fin_s"],
                                    "l_max_m": metrics["l_max_m"],
                                    "l_mean_m": metrics["l_mean_m"],
                                    "load_ratio": metrics["load_ratio"],
                                    "n_c": int(metrics["n_c"]),
                                    "n_c_independent": int(metrics["n_c_independent"]),
                                    "t_detect_s": metrics["t_detect_s"],
                                    "t_compute_s": round(metrics["t_compute_s"], 9),
                                    "t_react_s": round(metrics["t_detect_s"] + metrics["t_compute_s"], 9),
                                    "pool_pts": int(metrics["pool_pts"]),
                                    "route_pts": int(metrics["route_pts"]),
                                    "mission_layout": args.mission_layout,
                                    "mission_hash": mission_hash,
                                    "code_hash": code_hash,
                                    "git_revision": revision,
                                    "status": "ok",
                                }
                            )
        summary = _summarize(raw_rows)
        raw_path = args.out_prefix + "_raw.csv"
        summary_path = args.out_prefix + "_summary.csv"
        latex_path = args.out_prefix + "_table.tex"
        metadata_path = args.out_prefix + "_metadata.json"
        _write_csv(raw_path, raw_rows)
        _write_csv(summary_path, summary)
        _write_latex(latex_path, summary)
        with open(metadata_path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "model": "offline point-kinematic simulation",
                    "not_sitl": True,
                    "mission_layout": args.mission_layout,
                    "mission_hash": mission_hash,
                    "code_hash": code_hash,
                    "git_revision": revision,
                    "repeats": args.repeats,
                    "progresses": progresses,
                    "failed_uavs": failed_uavs,
                    "speed_mps": args.speed,
                    "d_safe_m": args.d_safe,
                    "raw_csv": os.path.basename(raw_path),
                    "summary_csv": os.path.basename(summary_path),
                },
                handle,
                ensure_ascii=False,
                indent=2,
            )
        print(f"Completed {len(raw_rows)} runs; mission={mission_hash}; git={revision}")
        print(f"Raw: {raw_path}")
        print(f"Summary: {summary_path}")
        print(f"LaTeX: {latex_path}")
    finally:
        if mission_owner is not None:
            mission_owner.cleanup()


if __name__ == "__main__":
    main()
