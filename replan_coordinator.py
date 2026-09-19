"""
Re-planning coordinator for multi-UAV coverage missions.

When one UAV fails (lost link / low battery / failsafe), remaining coverage is
remapped for alive UAVs:
  - remap_mode="serpentine" (default): pool ALL remaining waypoints → split by
    longitude into balanced point-groups → lawnmower/serpentine in each group's
    bbox → altitude/time collision avoidance
  - remap_mode="waypoints": legacy redistribute unfinished WPs only
"""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

Point = Tuple[float, float]  # (lat, lon)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6378000.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def path_length_m(points: Sequence[Point]) -> float:
    if len(points) < 2:
        return 0.0
    total = 0.0
    for i in range(len(points) - 1):
        total += haversine_m(points[i][0], points[i][1], points[i + 1][0], points[i + 1][1])
    return total


def load_waypoints_from_plan(plan_path: str) -> List[Point]:
    if not os.path.isfile(plan_path):
        return []
    with open(plan_path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    points: List[Point] = []
    for item in data.get("mission", {}).get("items", []):
        command = item.get("command")
        params = item.get("params") or []
        if command in (16, 22) and len(params) >= 6:
            lat = params[4]
            lon = params[5]
            if lat is None or lon is None:
                continue
            points.append((float(lat), float(lon)))
    return points


def build_qgc_plan(route: Sequence[Point], home: Point, altitude: float, in_air: bool = False) -> dict:
    items = []
    for index, point in enumerate(route, start=1):
        # TAKEOFF only for cold-start plans; mid-air replan must use waypoints.
        if in_air:
            command = 16
        else:
            command = 22 if index == 1 else 16
        items.append(
            {
                "AMSLAltAboveTerrain": None,
                "Altitude": altitude,
                "AltitudeMode": 1,
                "autoContinue": True,
                "command": command,
                "doJumpId": index,
                "frame": 3,
                "params": [0, 0, 0, None, float(point[0]), float(point[1]), altitude],
                "type": "SimpleItem",
            }
        )
    items.append(
        {
            "autoContinue": True,
            "command": 20,
            "doJumpId": len(items) + 1,
            "frame": 2,
            "params": [0, 0, 0, 0, 0, 0, 0],
            "type": "SimpleItem",
        }
    )
    return {
        "fileType": "Plan",
        "geoFence": {"circles": [], "polygons": [], "version": 2},
        "groundStation": "QGroundControl",
        "mission": {
            "cruiseSpeed": 5,
            "hoverSpeed": 1,
            "firmwareType": 12,
            "globalPlanAltitudeMode": 1,
            "items": items,
            "plannedHomePosition": [float(home[0]), float(home[1]), None],
            "vehicleType": 2,
            "version": 2,
        },
        "rallyPoints": {"points": [], "version": 2},
        "version": 1,
    }


def nearest_waypoint_index(position: Point, waypoints: Sequence[Point]) -> int:
    if not waypoints:
        return 0
    distances = [haversine_m(position[0], position[1], wp[0], wp[1]) for wp in waypoints]
    return int(min(range(len(distances)), key=lambda i: distances[i]))


def remaining_waypoints(position: Optional[Point], waypoints: Sequence[Point]) -> List[Point]:
    if not waypoints:
        return []
    if position is None:
        return list(waypoints)
    index = nearest_waypoint_index(position, waypoints)
    # Keep current nearest and everything after it as unfinished work.
    return list(waypoints[index:])


def split_points_balanced(points: Sequence[Point], parts: int) -> List[List[Point]]:
    if parts <= 0:
        return []
    if not points:
        return [[] for _ in range(parts)]
    if parts == 1:
        return [list(points)]

    # Sort by longitude then latitude to create spatial strips.
    ordered = sorted(points, key=lambda p: (p[1], p[0]))
    chunk_size = int(math.ceil(len(ordered) / parts))
    groups: List[List[Point]] = []
    for i in range(parts):
        start = i * chunk_size
        end = min(len(ordered), (i + 1) * chunk_size)
        groups.append(ordered[start:end])
    while len(groups) < parts:
        groups.append([])
    return groups[:parts]


def order_path_from_start(start: Point, points: Sequence[Point]) -> List[Point]:
    if not points:
        return [start]
    remaining = list(points)
    path = [start]
    while remaining:
        last = path[-1]
        nearest_idx = min(
            range(len(remaining)),
            key=lambda i: haversine_m(last[0], last[1], remaining[i][0], remaining[i][1]),
        )
        path.append(remaining.pop(nearest_idx))
    # Drop duplicated start if first coverage point equals start.
    if len(path) >= 2 and haversine_m(path[0][0], path[0][1], path[1][0], path[1][1]) < 1.0:
        return path[1:]
    return path


def estimate_positions(
    route: Sequence[Point],
    speed_mps: float,
    sample_dt: float,
    start_delay_s: float = 0.0,
) -> List[Tuple[float, Point]]:
    if len(route) < 2 or speed_mps <= 0:
        return [(start_delay_s, route[0])] if route else []
    samples: List[Tuple[float, Point]] = []
    distance_acc = 0.0
    samples.append((start_delay_s, route[0]))
    for i in range(len(route) - 1):
        a = route[i]
        b = route[i + 1]
        seg = haversine_m(a[0], a[1], b[0], b[1])
        if seg < 1e-3:
            continue
        steps = max(1, int(math.ceil(seg / max(speed_mps * sample_dt, 1e-3))))
        for step in range(1, steps + 1):
            ratio = step / steps
            lat = a[0] + (b[0] - a[0]) * ratio
            lon = a[1] + (b[1] - a[1]) * ratio
            t = start_delay_s + (distance_acc + seg * ratio) / speed_mps
            samples.append((t, (lat, lon)))
        distance_acc += seg
    return samples


def count_conflicts(
    routes: Dict[int, Sequence[Point]],
    altitudes: Dict[int, float],
    speeds: Dict[int, float],
    delays: Dict[int, float],
    d_safe: float,
    sample_dt: float = 1.0,
    alt_clearance_m: float = 4.0,
) -> int:
    """Count pairwise predicted conflicts.

    Pairs with vertical separation >= alt_clearance_m are treated as conflict-free.
    Default clearance is 4 m so that nominal Δh=5 m bands skip horizontal checks.
    """
    ids = list(routes.keys())
    sampled = {
        drone_id: estimate_positions(routes[drone_id], speeds.get(drone_id, 2.0), sample_dt, delays.get(drone_id, 0.0))
        for drone_id in ids
    }
    conflicts = 0
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a_id, b_id = ids[i], ids[j]
            if abs(altitudes.get(a_id, 0.0) - altitudes.get(b_id, 0.0)) >= alt_clearance_m:
                continue
            for t_a, p_a in sampled[a_id]:
                for t_b, p_b in sampled[b_id]:
                    if abs(t_a - t_b) > sample_dt:
                        continue
                    if haversine_m(p_a[0], p_a[1], p_b[0], p_b[1]) < d_safe:
                        conflicts += 1
                        break
                else:
                    continue
                break
    return conflicts


def apply_collision_avoidance(
    routes: Dict[int, List[Point]],
    base_altitudes: Dict[int, float],
    speeds: Dict[int, float],
    battery: Dict[int, float],
    d_safe: float,
    delta_h: float,
    tau0: float = 2.0,
    max_delay_iters: int = 4,
) -> Tuple[Dict[int, List[Point]], Dict[int, float], Dict[int, float]]:
    """Return routes, altitudes, start_delays after heuristic conflict resolution.

    Prefer altitude + time separation. Do NOT laterally shift coverage waypoints.
    Vertical clearance used in conflict checks is max(1, Δh - 1) m.
    """
    drone_ids = sorted(routes.keys(), key=lambda i: battery.get(i, 0.0), reverse=True)
    altitudes = {i: float(base_altitudes.get(i, 10.0)) for i in drone_ids}
    delays = {i: 0.0 for i in drone_ids}
    adjusted = {i: list(routes[i]) for i in drone_ids}
    alt_clearance = max(1.0, float(delta_h) - 1.0)

    for rank, drone_id in enumerate(drone_ids):
        altitudes[drone_id] = base_altitudes.get(drone_id, 10.0) + rank * delta_h
        delays[drone_id] = rank * float(tau0)

    # If prediction still conflicts, increase time separation (max max_delay_iters).
    for _ in range(max_delay_iters):
        if count_conflicts(
            adjusted, altitudes, speeds, delays, d_safe, alt_clearance_m=alt_clearance
        ) == 0:
            break
        for rank, drone_id in enumerate(drone_ids):
            delays[drone_id] += 1.0 + rank

    return adjusted, altitudes, delays


def merge_own_and_share_routes(
    start: Point,
    own_points: Sequence[Point],
    share_points: Sequence[Point],
) -> List[Point]:
    """Keep original remaining order; append failed-share with NN from the tail."""
    route: List[Point] = []
    for point in own_points:
        if not route or haversine_m(route[-1][0], route[-1][1], point[0], point[1]) > 1.0:
            route.append(point)

    if share_points:
        seed = route[-1] if route else start
        share_ordered = order_path_from_start(seed, list(share_points))
        # order_path_from_start prefixes seed; drop it when merging.
        if share_ordered and haversine_m(share_ordered[0][0], share_ordered[0][1], seed[0], seed[1]) < 1.0:
            share_ordered = share_ordered[1:]
        for point in share_ordered:
            if not route or haversine_m(route[-1][0], route[-1][1], point[0], point[1]) > 1.0:
                route.append(point)

    if not route:
        return [start]
    # If drone is far from first remaining waypoint, keep first WP as-is
    # (autopilot will transit there). No need to inject GPS noise as a WP.
    return route


def _meters_to_dlat(meters: float) -> float:
    return meters / 111320.0


def _meters_to_dlon(meters: float, lat: float) -> float:
    return meters / (111320.0 * max(0.2, math.cos(math.radians(lat))))


def estimate_grid_spacing_m(points: Sequence[Point], default: float = 12.0) -> float:
    """Estimate survey lane spacing from remaining waypoints.

    Prefer median nearest-neighbor distance (robust for reduced QGC plans).
    Use latitude-row gaps only when clear multi-point rows are detected.
    """
    if len(points) < 2:
        return default

    # Use a prefix sample: residual pools are concatenated by UAV, and the
    # densest survey strip (often later in the list) still appears enough in
    # the first ~120 points for a stable median on our mission files.
    sample = list(points[: min(120, len(points))])
    nn: List[float] = []
    for i, p in enumerate(sample):
        best = float("inf")
        for j, q in enumerate(sample):
            if i == j:
                continue
            d = haversine_m(p[0], p[1], q[0], q[1])
            if 1.0 < d < best:
                best = d
        if best < float("inf"):
            nn.append(best)
    nn_med = sorted(nn)[len(nn) // 2] if nn else default

    # Optional row-gap estimate when points form clear horizontal lanes.
    lats = sorted(p[0] for p in sample)
    rows: List[float] = [lats[0]]
    for lat in lats[1:]:
        if abs(lat - rows[-1]) * 111320.0 > 2.5:
            rows.append(lat)
    row_gaps: List[float] = []
    if len(rows) >= 3:
        for i in range(len(rows) - 1):
            gap = abs(rows[i + 1] - rows[i]) * 111320.0
            if gap >= 5.0:
                row_gaps.append(gap)
    row_med = sorted(row_gaps)[len(row_gaps) // 2] if row_gaps else None

    # If row spacing is credible (not tiny jitter), blend toward it.
    if row_med is not None and row_med >= max(8.0, 0.6 * nn_med):
        chosen = row_med
    else:
        chosen = nn_med
    return float(max(5.0, min(40.0, chosen)))


def adapt_spacing_for_budget(
    pool_points: Sequence[Point],
    parts: int,
    spacing_m: float,
    max_points_per_uav: int = 250,
) -> float:
    """Increase spacing if serpentine would create too many waypoints."""
    if not pool_points or parts <= 0:
        return spacing_m
    min_lat, max_lat, min_lon, max_lon = bounding_box(pool_points)
    mid_lat = (min_lat + max_lat) / 2.0
    height_m = max(1.0, abs(max_lat - min_lat) * 111320.0)
    width_m = max(
        1.0,
        abs(max_lon - min_lon) * 111320.0 * max(0.2, math.cos(math.radians(mid_lat))),
    )
    spacing = max(5.0, float(spacing_m))
    for _ in range(12):
        # Rough lawnmower count for one equal strip.
        strip_w = width_m / parts
        rows = max(1, int(math.ceil(height_m / spacing)))
        cols = max(1, int(math.ceil(strip_w / spacing)))
        est = rows * (cols + 1)
        if est <= max_points_per_uav:
            break
        spacing = min(40.0, spacing * 1.3)
    return spacing


def bounding_box(points: Sequence[Point]) -> Tuple[float, float, float, float]:
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    return min(lats), max(lats), min(lons), max(lons)


def pad_bbox(
    bbox: Tuple[float, float, float, float], pad_m: float
) -> Tuple[float, float, float, float]:
    min_lat, max_lat, min_lon, max_lon = bbox
    mid_lat = (min_lat + max_lat) / 2.0
    dlat = _meters_to_dlat(pad_m)
    dlon = _meters_to_dlon(pad_m, mid_lat)
    return min_lat - dlat, max_lat + dlat, min_lon - dlon, max_lon + dlon


def split_bbox_lon_strips(
    bbox: Tuple[float, float, float, float], parts: int
) -> List[Tuple[float, float, float, float]]:
    """Split bounding box into equal longitude strips (west → east)."""
    min_lat, max_lat, min_lon, max_lon = bbox
    if parts <= 1:
        return [bbox]
    width = (max_lon - min_lon) / parts
    if abs(width) < 1e-12:
        return [bbox for _ in range(parts)]
    strips = []
    for i in range(parts):
        lon0 = min_lon + i * width
        lon1 = min_lon + (i + 1) * width if i < parts - 1 else max_lon
        strips.append((min_lat, max_lat, lon0, lon1))
    return strips


def split_points_lon_groups(points: Sequence[Point], parts: int) -> List[List[Point]]:
    """Split coverage points into longitude groups with balanced counts."""
    if parts <= 0:
        return []
    if not points:
        return [[] for _ in range(parts)]
    ordered = sorted(points, key=lambda p: (p[1], p[0]))
    if parts == 1:
        return [list(ordered)]
    chunk = int(math.ceil(len(ordered) / parts))
    groups: List[List[Point]] = []
    for i in range(parts):
        start = i * chunk
        end = min(len(ordered), (i + 1) * chunk)
        groups.append(ordered[start:end])
    while len(groups) < parts:
        groups.append([])
    return groups[:parts]


def serpentine_in_bbox(
    bbox: Tuple[float, float, float, float],
    spacing_m: float,
    start: Optional[Point] = None,
) -> List[Point]:
    """Generate lawnmower/serpentine waypoints inside a lat/lon bounding box."""
    min_lat, max_lat, min_lon, max_lon = bbox
    if max_lat < min_lat or max_lon < min_lon:
        mid = ((min_lat + max_lat) / 2.0, (min_lon + max_lon) / 2.0)
        return [mid]

    # Degenerate thin box → single pass / point.
    height_m = abs(max_lat - min_lat) * 111320.0
    width_m = abs(max_lon - min_lon) * 111320.0 * max(
        0.2, math.cos(math.radians((min_lat + max_lat) / 2.0))
    )
    if height_m < 1.0 and width_m < 1.0:
        return [((min_lat + max_lat) / 2.0, (min_lon + max_lon) / 2.0)]

    mid_lat = (min_lat + max_lat) / 2.0
    dlat = _meters_to_dlat(max(spacing_m, 1.0))
    dlon = _meters_to_dlon(max(spacing_m, 1.0), mid_lat)

    # Build horizontal rows from south to north.
    rows: List[float] = []
    lat = min_lat
    guard = 0
    while lat <= max_lat + 1e-12 and guard < 5000:
        rows.append(min(lat, max_lat))
        lat += dlat
        guard += 1
    if not rows:
        rows = [mid_lat]
    elif abs(rows[-1] - max_lat) > dlat * 0.25:
        rows.append(max_lat)

    # Choose whether first row goes west→east or east→west based on start lon.
    go_east = True
    if start is not None:
        dist_west = abs(start[1] - min_lon)
        dist_east = abs(start[1] - max_lon)
        go_east = dist_west <= dist_east

    path: List[Point] = []
    for row_lat in rows:
        if go_east:
            left, right = min_lon, max_lon
            path.append((row_lat, left))
            lon = left + dlon
            while lon < right - 1e-12:
                path.append((row_lat, lon))
                lon += dlon
            if abs(path[-1][1] - right) > 1e-8:
                path.append((row_lat, right))
        else:
            left, right = min_lon, max_lon
            path.append((row_lat, right))
            lon = right - dlon
            while lon > left + 1e-12:
                path.append((row_lat, lon))
                lon -= dlon
            if abs(path[-1][1] - left) > 1e-8:
                path.append((row_lat, left))
        go_east = not go_east

    cleaned: List[Point] = []
    for point in path:
        if not cleaned or haversine_m(cleaned[-1][0], cleaned[-1][1], point[0], point[1]) > 0.5:
            cleaned.append(point)
    return cleaned


def build_serpentine_remap_routes(
    pool_points: Sequence[Point],
    alive_ids: Sequence[int],
    drone_positions: Dict[int, Point],
    spacing_m: float,
) -> Dict[int, List[Point]]:
    """Remap remaining coverage: split points by lon → bbox/strip → serpentine."""
    if not pool_points or not alive_ids:
        return {}

    candidates = [i for i in alive_ids if i in drone_positions]
    if not candidates:
        return {}

    # Do not create more strips than remaining points (avoids empty groups).
    n_parts = min(len(candidates), len(pool_points))
    if n_parts < 1:
        return {}

    # If fewer strips than candidates, keep UAVs closest to coverage centroid.
    if n_parts < len(candidates):
        clat = sum(p[0] for p in pool_points) / len(pool_points)
        clon = sum(p[1] for p in pool_points) / len(pool_points)
        candidates = sorted(
            candidates,
            key=lambda i: haversine_m(
                drone_positions[i][0], drone_positions[i][1], clat, clon
            ),
        )[:n_parts]

    # Assign west→east by current longitude.
    ordered_uavs = sorted(candidates, key=lambda i: (drone_positions[i][1], i))
    groups = split_points_lon_groups(pool_points, len(ordered_uavs))
    routes: Dict[int, List[Point]] = {}
    for drone_id, group in zip(ordered_uavs, groups):
        if not group:
            continue
        bbox = pad_bbox(bounding_box(group), pad_m=max(0.5, spacing_m * 0.1))
        start = drone_positions.get(drone_id)
        route = serpentine_in_bbox(bbox, spacing_m, start=start)
        if start is not None and route:
            if haversine_m(start[0], start[1], route[0][0], route[0][1]) < 1.0:
                route = route[1:] or route
        if route:
            routes[drone_id] = route
    return routes


@dataclass
class ReplanConfig:
    enabled: bool = False
    monitor_indices: Tuple[int, ...] = (1, 2, 3, 4, 5)
    lost_timeout_s: float = 3.0
    battery_min_percent: float = 25.0
    d_safe_m: float = 15.0
    delta_h_m: float = 5.0
    tau0_s: float = 2.0  # start-delay step by battery rank
    speed_mps: float = 2.0  # nominal speed for conflict prediction
    max_delay_iters: int = 4  # CAA delay-increase loops
    apply_caa: bool = True  # False = B1 remap without altitude/time separation
    write_plans: bool = True  # False = dry-run for offline experiments
    # "serpentine": remap all remaining coverage via bbox strips + lawnmower.
    # "waypoints": legacy redistribute unfinished WPs only.
    remap_mode: str = "serpentine"
    local_only: bool = False  # ignored when remap_mode == "serpentine"
    grid_spacing_m: float = 0.0  # 0 = auto-estimate from remaining points
    cooldown_s: float = 15.0


@dataclass
class DroneLiveState:
    connected: bool = False
    last_telemetry_s: float = 0.0
    lat: Optional[float] = None
    lon: Optional[float] = None
    alt_rel: float = 0.0
    battery_percent: float = 100.0
    mode: str = ""
    in_mission: bool = False
    failed: bool = False


@dataclass
class ReplanResult:
    failed_index: int
    alive_indices: List[int]
    routes: Dict[int, List[Point]]
    altitudes: Dict[int, float]
    delays: Dict[int, float]
    plan_files: Dict[int, str]
    remaining_points: int
    conflicts_before: int
    conflicts_after: int
    message: str


class ReplanCoordinator:
    def __init__(
        self,
        mission_dir: str,
        config: Optional[ReplanConfig] = None,
        log_fn: Optional[Callable[[str], None]] = None,
    ):
        self.mission_dir = mission_dir
        self.config = config or ReplanConfig()
        self.log_fn = log_fn or (lambda msg: print(msg))
        self.states: Dict[int, DroneLiveState] = {
            i: DroneLiveState() for i in range(1, 7)
        }
        self._last_replan_s = 0.0
        self._replan_in_progress = False
        self.failed_history: List[int] = []

    def set_enabled(self, enabled: bool) -> None:
        self.config.enabled = enabled
        self.log(f"[REPLAN] Auto-replan {'ENABLED' if enabled else 'DISABLED'}")

    def log(self, message: str) -> None:
        self.log_fn(message)

    def mark_connected(self, index: int, connected: bool = True, clear_failed: bool = False) -> None:
        state = self.states[index]
        state.connected = connected
        if connected:
            state.last_telemetry_s = time.time()
            if clear_failed:
                state.failed = False

    def mark_in_mission(self, index: int, active: bool = True) -> None:
        self.states[index].in_mission = active

    def update_position(self, index: int, lat: float, lon: float, alt_rel: float = 0.0) -> None:
        state = self.states[index]
        state.lat = lat
        state.lon = lon
        state.alt_rel = alt_rel
        state.last_telemetry_s = time.time()
        state.connected = True

    def update_battery(self, index: int, percent: float) -> None:
        state = self.states[index]
        # Expect 0..100 from UI/telemetry adapter in main.py.
        # Do NOT refresh last_telemetry_s here: battery-only traffic must not
        # mask a lost-link / lost-control condition based on position age.
        state.battery_percent = max(0.0, min(float(percent), 100.0))

    def update_mode(self, index: int, mode: str) -> None:
        state = self.states[index]
        # Mode changes are useful for failsafe detect, but alone should not
        # reset the lost-link timer (position stream is the heartbeat).
        state.mode = str(mode)

    def plan_path(self, index: int) -> str:
        return os.path.join(self.mission_dir, f"points{index}.plan")

    def replan_plan_path(self, index: int) -> str:
        return os.path.join(self.mission_dir, f"replan_points{index}.plan")

    def detect_failures(self) -> List[int]:
        now = time.time()
        failed: List[int] = []
        for index in self.config.monitor_indices:
            state = self.states[index]
            if state.failed:
                continue
            if not state.connected and state.last_telemetry_s <= 0:
                continue

            lost = (
                state.last_telemetry_s > 0
                and (now - state.last_telemetry_s) > self.config.lost_timeout_s
            )
            low_battery = state.battery_percent <= self.config.battery_min_percent
            mode_up = state.mode.upper()
            failsafe = any(token in mode_up for token in ("RTL", "RETURN", "LAND", "FAILSAFE"))

            # Lost link: only while drone was active in air/mission.
            lost_fail = lost and (state.in_mission or state.alt_rel > 1.0)
            # Low battery / RTL-Land: require in_mission to avoid false trigger
            # when a healthy UAV finishes mission and returns home.
            energy_or_mode_fail = state.in_mission and (low_battery or failsafe)

            if lost_fail or energy_or_mode_fail:
                reason = []
                if lost_fail:
                    reason.append("lost_link")
                if low_battery and state.in_mission:
                    reason.append(f"low_battery({state.battery_percent:.1f}%)")
                if failsafe and state.in_mission:
                    reason.append(f"mode={state.mode}")
                state.failed = True
                state.in_mission = False
                failed.append(index)
                self.failed_history.append(index)
                self.log(f"[REPLAN] UAV {index} FAIL detected: {', '.join(reason)}")
        return failed

    def _collect_remaining_for_index(self, index: int) -> List[Point]:
        waypoints = load_waypoints_from_plan(self.plan_path(index))
        state = self.states[index]
        position = (state.lat, state.lon) if state.lat is not None and state.lon is not None else None
        return remaining_waypoints(position, waypoints)

    def build_replan(self, failed_index: int) -> Optional[ReplanResult]:
        alive = [
            i
            for i in self.config.monitor_indices
            if i != failed_index and not self.states[i].failed and self.states[i].connected
        ]
        # Fallback: allow assigned drones that have a known position even if
        # connected flag was lost briefly, as long as they are not failed.
        if not alive:
            alive = [
                i
                for i in self.config.monitor_indices
                if i != failed_index
                and not self.states[i].failed
                and self.states[i].lat is not None
                and self.states[i].lon is not None
            ]
        if not alive:
            self.log("[REPLAN] No alive UAVs available for reallocation.")
            return None

        failed_remain = self._collect_remaining_for_index(failed_index)
        if len(failed_remain) < 1 and self.config.remap_mode != "serpentine":
            self.log(f"[REPLAN] Failed UAV {failed_index} has no remaining points.")
            return None

        # ---- Mode B: remap all remaining coverage (bbox + serpentine) ----
        if self.config.remap_mode == "serpentine":
            # Serpentine assignment needs GPS; drop connected-but-unknown UAVs.
            alive = [
                i
                for i in alive
                if self.states[i].lat is not None and self.states[i].lon is not None
            ]
            if not alive:
                self.log("[REPLAN] No alive UAVs with GPS for serpentine remap.")
                return None

            pool: List[Point] = list(failed_remain)
            for index in alive:
                pool.extend(self._collect_remaining_for_index(index))
            # Deduplicate near-identical points (O(n) window).
            unique: List[Point] = []
            for point in pool:
                if not unique:
                    unique.append(point)
                    continue
                window = unique[-12:]
                if min(haversine_m(point[0], point[1], q[0], q[1]) for q in window) > 1.0:
                    unique.append(point)
            pool = unique
            if len(pool) < 2:
                self.log(
                    f"[REPLAN] Not enough remaining coverage points to remap ({len(pool)})."
                )
                return None

            spacing = self.config.grid_spacing_m
            if spacing <= 0:
                spacing = estimate_grid_spacing_m(pool)
            # Match strip count used by mapper (cannot exceed |pool|).
            n_parts = min(len(alive), len(pool))
            spacing = adapt_spacing_for_budget(pool, n_parts, spacing)
            positions = {
                i: (self.states[i].lat, self.states[i].lon)
                for i in alive
            }
            assigned = build_serpentine_remap_routes(pool, alive, positions, spacing)
            if not assigned:
                self.log("[REPLAN] Serpentine remap produced no routes.")
                return None
            self.log(
                f"[REPLAN] Serpentine remap | pool={len(pool)} pts | "
                f"spacing={spacing:.1f}m | strips={len(assigned)} | alive={list(assigned.keys())}"
            )
            return self._finalize_replan(
                failed_index=failed_index,
                assigned=assigned,
                failed_remain_count=len(failed_remain),
                pool_count=len(pool),
                mode_tag="serpentine-remap",
            )

        # ---- Mode A (legacy): redistribute unfinished waypoints ----
        if len(failed_remain) < 1:
            self.log(f"[REPLAN] Failed UAV {failed_index} has no remaining points.")
            return None

        if self.config.local_only:
            # Keep each alive UAV's own unfinished work, and add a share of
            # the failed UAV remaining points. Do NOT replace their mission.
            own_remaining = {i: self._collect_remaining_for_index(i) for i in alive}
            share_groups = split_points_balanced(failed_remain, len(alive))
        else:
            remain = list(failed_remain)
            for index in alive:
                remain.extend(self._collect_remaining_for_index(index))
            if len(remain) < 2:
                self.log(f"[REPLAN] Not enough remaining points to replan ({len(remain)}).")
                return None
            own_remaining = {i: [] for i in alive}
            share_groups = split_points_balanced(remain, len(alive))

        # Assign failed-share groups to nearest alive UAV.
        assigned_share: Dict[int, List[Point]] = {i: [] for i in alive}
        used = set()
        for drone_id in alive:
            state = self.states[drone_id]
            if state.lat is None or state.lon is None:
                continue
            best_g = None
            best_d = float("inf")
            for g_idx, group in enumerate(share_groups):
                if g_idx in used or not group:
                    continue
                entry = min(group, key=lambda p: haversine_m(state.lat, state.lon, p[0], p[1]))
                dist = haversine_m(state.lat, state.lon, entry[0], entry[1])
                if dist < best_d:
                    best_d = dist
                    best_g = g_idx
            if best_g is None:
                continue
            used.add(best_g)
            assigned_share[drone_id] = list(share_groups[best_g])

        for g_idx, group in enumerate(share_groups):
            if g_idx in used or not group:
                continue
            drone_id = min(alive, key=lambda i: path_length_m(assigned_share.get(i, [])))
            assigned_share[drone_id] = list(assigned_share.get(drone_id, [])) + list(group)

        assigned: Dict[int, List[Point]] = {}
        for drone_id in alive:
            state = self.states[drone_id]
            if state.lat is None or state.lon is None:
                continue
            start = (state.lat, state.lon)
            route = merge_own_and_share_routes(
                start,
                own_remaining.get(drone_id, []),
                assigned_share.get(drone_id, []),
            )
            if len(route) < 1:
                continue
            assigned[drone_id] = route

        if not assigned:
            self.log("[REPLAN] Failed to assign routes.")
            return None

        return self._finalize_replan(
            failed_index=failed_index,
            assigned=assigned,
            failed_remain_count=len(failed_remain),
            pool_count=sum(len(v) for v in assigned.values()),
            mode_tag="waypoint-redistribute",
        )

    def _finalize_replan(
        self,
        failed_index: int,
        assigned: Dict[int, List[Point]],
        failed_remain_count: int,
        pool_count: int,
        mode_tag: str,
    ) -> ReplanResult:
        total_points = sum(len(v) for v in assigned.values())
        base_alts = {}
        speeds = {}
        battery = {}
        for drone_id in assigned:
            # Prefer current relative height if already airborne (>=5 m);
            # otherwise use 10 m default relative mission altitude.
            ui_alt = float(self.states[drone_id].alt_rel or 0.0)
            base_alts[drone_id] = ui_alt if ui_alt >= 5.0 else 10.0
            speeds[drone_id] = float(self.config.speed_mps)
            battery[drone_id] = self.states[drone_id].battery_percent

        alt_clearance = max(1.0, float(self.config.delta_h_m) - 1.0)
        conflicts_before = count_conflicts(
            assigned,
            base_alts,
            speeds,
            {i: 0.0 for i in assigned},
            self.config.d_safe_m,
            alt_clearance_m=alt_clearance,
        )
        if self.config.apply_caa:
            routes, altitudes, delays = apply_collision_avoidance(
                assigned,
                base_alts,
                speeds,
                battery,
                self.config.d_safe_m,
                self.config.delta_h_m,
                tau0=self.config.tau0_s,
                max_delay_iters=self.config.max_delay_iters,
            )
        else:
            # B1: remap geometry only — same base altitude, no start stagger.
            routes = {i: list(assigned[i]) for i in assigned}
            altitudes = dict(base_alts)
            delays = {i: 0.0 for i in assigned}
        conflicts_after = count_conflicts(
            routes,
            altitudes,
            speeds,
            delays,
            self.config.d_safe_m,
            alt_clearance_m=alt_clearance,
        )

        plan_files: Dict[int, str] = {}
        if self.config.write_plans:
            os.makedirs(self.mission_dir, exist_ok=True)
            backup_dir = os.path.join(self.mission_dir, "backup_before_replan")
            os.makedirs(backup_dir, exist_ok=True)
            for drone_id, route in routes.items():
                if len(route) < 1:
                    continue
                home = route[0]
                plan = build_qgc_plan(route, home, altitudes[drone_id], in_air=True)
                out_path = self.replan_plan_path(drone_id)
                with open(out_path, "w", encoding="utf-8") as handle:
                    json.dump(plan, handle, ensure_ascii=False, indent=4)
                active_path = self.plan_path(drone_id)
                # Backup original mission once before overwrite.
                if os.path.isfile(active_path):
                    backup_path = os.path.join(backup_dir, f"points{drone_id}.plan")
                    if not os.path.isfile(backup_path):
                        try:
                            with open(active_path, "r", encoding="utf-8") as src, open(
                                backup_path, "w", encoding="utf-8"
                            ) as dst:
                                dst.write(src.read())
                            self.log(
                                f"[REPLAN] backed up original {os.path.basename(active_path)} -> backup_before_replan/"
                            )
                        except Exception:
                            pass
                    else:
                        # Keep a rolling snapshot of the file being replaced.
                        snap = os.path.join(
                            backup_dir, f"points{drone_id}.before_last_replan.plan"
                        )
                        try:
                            with open(active_path, "r", encoding="utf-8") as src, open(
                                snap, "w", encoding="utf-8"
                            ) as dst:
                                dst.write(src.read())
                        except Exception:
                            pass
                with open(active_path, "w", encoding="utf-8") as handle:
                    json.dump(plan, handle, ensure_ascii=False, indent=4)
                plan_files[drone_id] = out_path

        caa_tag = "caa" if self.config.apply_caa else "no-caa"
        message = (
            f"Replanned ({mode_tag}/{caa_tag}) after UAV {failed_index} fail | "
            f"alive={list(assigned.keys())} | failed_pts={failed_remain_count} "
            f"pool/routes={pool_count}/{total_points} | "
            f"conflicts {conflicts_before}->{conflicts_after}"
        )
        self.log(f"[REPLAN] {message}")
        return ReplanResult(
            failed_index=failed_index,
            alive_indices=list(assigned.keys()),
            routes=routes,
            altitudes=altitudes,
            delays=delays,
            plan_files=plan_files,
            remaining_points=pool_count,
            conflicts_before=conflicts_before,
            conflicts_after=conflicts_after,
            message=message,
        )

    def can_replan_now(self) -> bool:
        if not self.config.enabled:
            return False
        if self._replan_in_progress:
            return False
        if time.time() - self._last_replan_s < self.config.cooldown_s:
            return False
        return True

    def begin_replan(self) -> None:
        self._replan_in_progress = True

    def end_replan(self) -> None:
        self._replan_in_progress = False
        self._last_replan_s = time.time()
