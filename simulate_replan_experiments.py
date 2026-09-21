#!/usr/bin/env python3
"""
Offline kinematic experiment harness for multi-UAV fault replan.

Produces Table-3 style metrics (eta, T_fin, L_max, N_c, T_react) for:
  S1 lost-link mid-mission, S2 low-battery fail, S3 dense residual
x strategies:
  B0 no replan, B1 serpentine remap without CAA, Proposed remap+CAA

Does NOT overwrite mission/points*.plan (write_plans=False).

Usage:
  source .venv/bin/activate
  python simulate_replan_experiments.py
  python simulate_replan_experiments.py --progress 0.4 --out results/table3_offline.csv
"""

from __future__ import annotations

import argparse
import csv
import os
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from replan_coordinator import (
    ReplanConfig,
    ReplanCoordinator,
    count_conflicts,
    estimate_grid_spacing_m,
    load_waypoints_from_plan,
    remaining_waypoints,
)
from simulation_metrics import (
    coverage_ratio,
    finish_time_s,
    max_path_m,
    residual_pool,
    unique_window,
)

Point = Tuple[float, float]


@dataclass
class ScenarioSetup:
    name: str
    failed: int
    progress: float
    battery: Dict[int, float]
    note: str


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

    coord = ReplanCoordinator(
        mission_dir,
        ReplanConfig(
            enabled=True,
            monitor_indices=tuple(uav_ids),
            remap_mode="serpentine",
            apply_caa=(strategy == "Proposed"),
            write_plans=False,
            speed_mps=speed_mps,
            d_safe_m=d_safe_m,
            grid_spacing_m=0.0,
        ),
        log_fn=lambda _m: None,
    )
    positions = seed_states(coord, plans, scenario.progress, scenario.battery)
    targets = residual_pool(plans, positions, failed, alive)

    t0 = time.perf_counter()
    if strategy == "B0":
        # Fail latch only; alive keep original remaining missions.
        coord.states[failed].failed = True
        coord.states[failed].in_mission = False
        routes = b0_routes(plans, positions, alive)
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
    if scenario.name == "S1":
        t_react_s = round(coord.config.lost_timeout_s + t_compute, 2)
    else:
        t_react_s = round(max(t_compute, 0.01), 2)

    eta = coverage_ratio(targets, routes, cover_radius_m)
    t_fin = finish_time_s(routes, delays, speed_mps)
    l_max = max_path_m(routes)

    return {
        "eta_pct": round(eta, 1),
        "t_fin_s": round(t_fin, 1),
        "l_max_m": round(l_max, 1),
        "n_c": float(n_c),
        "t_react_s": round(t_react_s, 3),
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
        ),
        ScenarioSetup(
            name="S3",
            failed=1,
            progress=max(0.15, progress - 0.15),
            battery={1: 72, 2: 88, 3: 78, 4: 68},
            note="earlier fail → denser residual / higher conflict risk",
        ),
    ]


def main() -> None:
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


if __name__ == "__main__":
    main()
