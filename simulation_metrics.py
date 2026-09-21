"""Shared metrics for offline multi-UAV replan experiments."""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime
from typing import Dict, List, Sequence, Tuple

from replan_coordinator import (
    estimate_grid_spacing_m,
    haversine_m,
    path_length_m,
    remaining_waypoints,
)

Point = Tuple[float, float]


def unique_window(
    points: Sequence[Point], window: int = 12, thresh_m: float = 1.0
) -> List[Point]:
    unique: List[Point] = []
    for point in points:
        if not unique:
            unique.append(point)
            continue
        near = unique[-window:]
        if min(haversine_m(point[0], point[1], q[0], q[1]) for q in near) > thresh_m:
            unique.append(point)
    return unique


def residual_pool(
    plans: Dict[int, List[Point]],
    positions: Dict[int, Point],
    failed: int,
    alive: Sequence[int],
) -> List[Point]:
    pool: List[Point] = list(remaining_waypoints(positions[failed], plans[failed]))
    for drone_id in alive:
        pool.extend(remaining_waypoints(positions[drone_id], plans[drone_id]))
    return unique_window(pool)


def remaining_routes(
    plans: Dict[int, List[Point]],
    positions: Dict[int, Point],
    alive: Sequence[int],
) -> Dict[int, List[Point]]:
    routes = {}
    for drone_id in alive:
        route = remaining_waypoints(positions[drone_id], plans[drone_id])
        if route:
            routes[drone_id] = route
    return routes


def point_covered(
    target: Point, routes: Dict[int, Sequence[Point]], radius_m: float
) -> bool:
    return any(
        haversine_m(target[0], target[1], point[0], point[1]) <= radius_m
        for route in routes.values()
        for point in route
    )


def coverage_ratio(
    targets: Sequence[Point],
    routes: Dict[int, Sequence[Point]],
    radius_m: float,
) -> float:
    if not targets:
        return 100.0
    hit = sum(1 for target in targets if point_covered(target, routes, radius_m))
    return 100.0 * hit / len(targets)


def finish_time_s(
    routes: Dict[int, Sequence[Point]],
    delays: Dict[int, float],
    speed_mps: float,
) -> float:
    if speed_mps <= 0 or not routes:
        return 0.0
    return max(
        float(delays.get(drone_id, 0.0)) + path_length_m(route) / speed_mps
        for drone_id, route in routes.items()
    )


def max_path_m(routes: Dict[int, Sequence[Point]]) -> float:
    if not routes:
        return 0.0
    return max(path_length_m(route) for route in routes.values())


def automatic_coverage_radius(targets: Sequence[Point]) -> float:
    spacing = estimate_grid_spacing_m(targets)
    return max(8.0, 0.6 * spacing)


def calculate_route_metrics(
    targets: Sequence[Point],
    routes: Dict[int, Sequence[Point]],
    delays: Dict[int, float],
    speed_mps: float,
    cover_radius_m: float = 0.0,
) -> Dict[str, float]:
    radius = (
        float(cover_radius_m)
        if cover_radius_m > 0.0
        else automatic_coverage_radius(targets)
    )
    return {
        "eta_pct": round(coverage_ratio(targets, routes, radius), 1),
        "t_fin_s": round(finish_time_s(routes, delays, speed_mps), 1),
        "l_max_m": round(max_path_m(routes), 1),
        "cover_radius_m": round(radius, 3),
        "pool_pts": len(targets),
        "route_pts": sum(len(route) for route in routes.values()),
        "alive": len(routes),
    }


def export_metrics_csv(metrics: dict, output_path: str) -> str:
    """Write one reproducible simulation result row and return its path."""
    if not metrics:
        raise ValueError("No simulation metrics to export")
    output_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    row = dict(metrics)
    row["uav_ids"] = json.dumps(row.get("uav_ids", []), separators=(",", ":"))
    row["completion_times_s"] = json.dumps(
        row.get("completion_times_s", {}), separators=(",", ":"), sort_keys=True
    )
    row["exported_at"] = datetime.now().isoformat(timespec="seconds")
    with open(output_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row.keys()))
        writer.writeheader()
        writer.writerow(row)
    return output_path
