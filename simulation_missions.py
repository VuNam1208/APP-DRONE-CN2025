"""Prepare adjacent coverage lanes for the offline map simulation."""

from __future__ import annotations

import json
import math
import os
import tempfile
from typing import Tuple

from replan_coordinator import build_qgc_plan, load_waypoints_from_plan


def _serpentine_route(
    north: float,
    south: float,
    west: float,
    east: float,
    spacing_m: float,
    home: tuple[float, float],
) -> list[tuple[float, float]]:
    """Create parallel survey legs; spacing is cross-track distance."""
    center_lat = (north + south) / 2.0
    lat_step = spacing_m / 111320.0
    lon_inset = (spacing_m / 2.0) / (
        111320.0 * max(0.2, math.cos(math.radians(center_lat)))
    )
    west_inset = min((west + east) / 2.0, west + lon_inset)
    east_inset = max((west + east) / 2.0, east - lon_inset)
    first_lat = north - lat_step / 2.0
    last_lat = south + lat_step / 2.0
    if first_lat < last_lat:
        rows = [center_lat]
    else:
        row_count = int(math.floor((first_lat - last_lat) / lat_step)) + 1
        rows = [first_lat - index * lat_step for index in range(row_count)]
    if abs(home[0] - south) < abs(home[0] - north):
        rows.reverse()

    route: list[tuple[float, float]] = []
    start_west = abs(home[1] - west_inset) <= abs(home[1] - east_inset)
    for index, latitude in enumerate(rows):
        west_first = start_west if index % 2 == 0 else not start_west
        if west_first:
            route.extend(((latitude, west_inset), (latitude, east_inset)))
        else:
            route.extend(((latitude, east_inset), (latitude, west_inset)))
    return route


def prepare_adjacent_sim_missions(
    source_dir: str,
    scale_factor: float = 1.5,
    grid_spacing_m: float = 10.0,
    layout: str = "adjacent",
) -> Tuple[tempfile.TemporaryDirectory, str]:
    """Build four adjacent missions with a map-aligned coverage spacing.

    The source QGC plans are read only. The returned TemporaryDirectory owner
    must stay alive for the entire simulation and be cleaned up afterward.
    """
    if scale_factor <= 0.0:
        raise ValueError("scale_factor must be positive")
    if grid_spacing_m <= 0.0:
        raise ValueError("grid_spacing_m must be positive")
    if layout not in {"adjacent", "rotated", "elongated"}:
        raise ValueError(f"Unknown simulation layout: {layout}")
    source_routes = {}
    common_home = None
    for drone_id in (1, 2, 3):
        path = os.path.join(source_dir, f"points{drone_id}.plan")
        if drone_id == 1:
            with open(path, "r", encoding="utf-8") as handle:
                source_plan = json.load(handle)
            planned_home = source_plan.get("mission", {}).get("plannedHomePosition")
            if planned_home and len(planned_home) >= 2:
                common_home = (float(planned_home[0]), float(planned_home[1]))
        route = load_waypoints_from_plan(path)
        if len(route) < 2:
            raise ValueError(f"Missing or short source mission: {path}")
        source_routes[drone_id] = route

    all_points = [point for route in source_routes.values() for point in route]
    center_lat = sum(point[0] for point in all_points) / len(all_points)
    center_lon = sum(point[1] for point in all_points) / len(all_points)
    if common_home is None:
        common_home = source_routes[1][0]
    common_home = (
        center_lat + (common_home[0] - center_lat) * scale_factor,
        center_lon + (common_home[1] - center_lon) * scale_factor,
    )
    source_routes = {
        drone_id: [
            (
                center_lat + (lat - center_lat) * scale_factor,
                center_lon + (lon - center_lon) * scale_factor,
            )
            for lat, lon in route
        ]
        for drone_id, route in source_routes.items()
    }

    north_step = source_routes[2][0][0] - source_routes[3][0][0]
    if north_step <= 0:
        raise ValueError("UAV 1-3 missions are not ordered north to south")

    # Extend the source footprint by one adjacent lane, then regenerate all
    # routes through the same grid/path functions used by the real map UI.
    fourth_template = [
        (lat - north_step, lon) for lat, lon in source_routes[3]
    ]
    templates = {**source_routes, 4: fourth_template}
    centers = {
        drone_id: sum(point[0] for point in route) / len(route)
        for drone_id, route in templates.items()
    }
    ordered_ids = sorted(templates, key=lambda drone_id: centers[drone_id], reverse=True)
    all_template_points = [point for route in templates.values() for point in route]
    north_edge = max(point[0] for point in all_template_points)
    south_edge = min(point[0] for point in all_template_points)
    west_edge = min(point[1] for point in all_template_points)
    east_edge = max(point[1] for point in all_template_points)

    generated_routes = {}
    for index, drone_id in enumerate(ordered_ids):
        zone_north = (
            north_edge
            if index == 0
            else (centers[ordered_ids[index - 1]] + centers[drone_id]) / 2.0
        )
        zone_south = (
            south_edge
            if index == len(ordered_ids) - 1
            else (centers[drone_id] + centers[ordered_ids[index + 1]]) / 2.0
        )
        route = _serpentine_route(
            zone_north,
            zone_south,
            west_edge,
            east_edge,
            grid_spacing_m,
            common_home,
        )
        if len(route) < 2:
            raise ValueError(f"Grid spacing produced no route for UAV {drone_id}")
        generated_routes[drone_id] = route

    if layout != "adjacent":
        points = [point for route in generated_routes.values() for point in route]
        pivot_lat = sum(point[0] for point in points) / len(points)
        pivot_lon = sum(point[1] for point in points) / len(points)
        cos_lat = max(0.2, math.cos(math.radians(pivot_lat)))
        angle = math.radians(35.0 if layout == "rotated" else 0.0)
        scale_x, scale_y = ((1.0, 1.0) if layout == "rotated" else (2.0, 0.5))

        def transform(point: tuple[float, float]) -> tuple[float, float]:
            x = (point[1] - pivot_lon) * 111320.0 * cos_lat * scale_x
            y = (point[0] - pivot_lat) * 111320.0 * scale_y
            tx = x * math.cos(angle) - y * math.sin(angle)
            ty = x * math.sin(angle) + y * math.cos(angle)
            return (
                pivot_lat + ty / 111320.0,
                pivot_lon + tx / (111320.0 * cos_lat),
            )

        generated_routes = {
            drone_id: [transform(point) for point in route]
            for drone_id, route in generated_routes.items()
        }
        common_home = transform(common_home)

    temporary = tempfile.TemporaryDirectory(prefix="app_drone_sim_")
    try:
        for drone_id in (1, 2, 3, 4):
            route = generated_routes[drone_id]
            plan = build_qgc_plan(route, common_home, altitude=12.0)
            with open(
                os.path.join(temporary.name, f"points{drone_id}.plan"),
                "w",
                encoding="utf-8",
            ) as handle:
                json.dump(plan, handle, ensure_ascii=False, indent=2)
    except Exception:
        temporary.cleanup()
        raise
    return temporary, temporary.name
