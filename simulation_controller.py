"""Offline multi-UAV mission simulation.

The controller is deliberately independent from PyQt, JavaScript and MAVSDK.
Call ``step(dt)`` from any scheduler and subscribe to events with ``on``.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from replan_coordinator import (
    ReplanConfig,
    ReplanCoordinator,
    ReplanResult,
    count_conflicts,
    haversine_m,
    load_waypoints_from_plan,
    path_length_m,
)
from simulation_metrics import calculate_route_metrics, remaining_routes, residual_pool

Point = Tuple[float, float]
EventCallback = Callable[[dict], None]


class SimulationStatus(str, Enum):
    READY = "READY"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    FINISHED = "FINISHED"


class DroneStatus(str, Enum):
    READY = "READY"
    FLYING = "FLYING"
    PAUSED = "PAUSED"
    FAILED = "FAILED"
    DELAYED = "DELAYED"
    FINISHED = "FINISHED"


@dataclass
class DroneSimulationState:
    drone_id: int
    original_route: List[Point]
    route: List[Point]
    speed_mps: float
    battery_percent: float = 80.0
    altitude_m: float = 12.0
    status: DroneStatus = DroneStatus.READY
    segment_index: int = 0
    segment_offset_m: float = 0.0
    distance_flown_m: float = 0.0
    delay_remaining_s: float = 0.0
    position: Optional[Point] = None
    finished_time_s: Optional[float] = None

    def __post_init__(self) -> None:
        if self.route and self.position is None:
            self.position = self.route[0]

    @property
    def original_length_m(self) -> float:
        return path_length_m(self.original_route)

    @property
    def progress(self) -> float:
        total = self.original_length_m
        if total <= 0.0:
            return 1.0 if self.status == DroneStatus.FINISHED else 0.0
        return min(1.0, self.distance_flown_m / total)


class SimulationController:
    """Deterministic point-kinematic simulator for coverage missions."""

    EVENTS = (
        "state_changed",
        "positions_updated",
        "failure_injected",
        "replan_completed",
        "simulation_finished",
    )
    STRATEGIES = ("B0", "B1", "Proposed")
    FAILURE_TYPES = ("lost_link", "low_battery")

    def __init__(
        self,
        mission_dir: str,
        uav_ids: Iterable[int] = (1, 2, 3, 4),
        speed_mps: float = 2.0,
        failed_uav: int = 1,
        failure_progress: float = 0.40,
        failure_type: str = "lost_link",
        strategy: str = "Proposed",
        d_safe_m: float = 15.0,
    ) -> None:
        if speed_mps <= 0:
            raise ValueError("speed_mps must be positive")
        if not 0.0 <= failure_progress <= 1.0:
            raise ValueError("failure_progress must be between 0 and 1")
        if strategy not in self.STRATEGIES:
            raise ValueError(f"Unknown strategy: {strategy}")
        if failure_type not in self.FAILURE_TYPES:
            raise ValueError(f"Unknown failure type: {failure_type}")

        self.mission_dir = os.path.abspath(mission_dir)
        self.uav_ids = tuple(int(i) for i in uav_ids)
        if not self.uav_ids:
            raise ValueError("At least one UAV is required")
        if failed_uav not in self.uav_ids:
            raise ValueError("failed_uav must be present in uav_ids")

        self.speed_mps = float(speed_mps)
        self.failed_uav = int(failed_uav)
        self.failure_progress = float(failure_progress)
        self.failure_type = failure_type
        self.strategy = strategy
        self.d_safe_m = float(d_safe_m)

        self.status = SimulationStatus.READY
        self.simulation_time_s = 0.0
        self.failure_time_s: Optional[float] = None
        self.replan_compute_s: Optional[float] = None
        self.last_replan_result: Optional[ReplanResult] = None
        self.last_metrics: Optional[dict] = None
        self._failure_triggered = False
        self._finished_emitted = False
        self._callbacks: Dict[str, List[EventCallback]] = {
            event: [] for event in self.EVENTS
        }
        self.drones: Dict[int, DroneSimulationState] = {}
        self._load_missions()

    def on(self, event: str, callback: EventCallback) -> None:
        if event not in self._callbacks:
            raise ValueError(f"Unknown simulation event: {event}")
        self._callbacks[event].append(callback)

    def start(self) -> None:
        if self.status == SimulationStatus.FINISHED:
            raise RuntimeError("Reset the simulation before starting it again")
        if self.status == SimulationStatus.RUNNING:
            return
        self.status = SimulationStatus.RUNNING
        for drone in self.drones.values():
            if drone.status in (DroneStatus.READY, DroneStatus.PAUSED):
                drone.status = DroneStatus.FLYING
        self._emit_state_changed()

    def pause(self) -> None:
        if self.status != SimulationStatus.RUNNING:
            return
        self.status = SimulationStatus.PAUSED
        for drone in self.drones.values():
            if drone.status == DroneStatus.FLYING:
                drone.status = DroneStatus.PAUSED
        self._emit_state_changed()

    def resume(self) -> None:
        if self.status != SimulationStatus.PAUSED:
            return
        self.start()

    def reset(self) -> None:
        self.status = SimulationStatus.READY
        self.simulation_time_s = 0.0
        self.failure_time_s = None
        self.replan_compute_s = None
        self.last_replan_result = None
        self.last_metrics = None
        self._failure_triggered = False
        self._finished_emitted = False
        self._load_missions()
        self._emit_state_changed()
        self._emit("positions_updated", self.snapshot())

    def step(self, dt_s: float) -> Dict[int, Point]:
        if dt_s < 0:
            raise ValueError("dt_s must be non-negative")
        if self.status != SimulationStatus.RUNNING or dt_s == 0:
            return self.positions()

        self.simulation_time_s += float(dt_s)
        for drone in self.drones.values():
            self._advance_drone(drone, float(dt_s))

        failed_state = self.drones[self.failed_uav]
        if not self._failure_triggered and failed_state.progress >= self.failure_progress:
            self.inject_failure(self.failed_uav, self.failure_type)

        self._emit("positions_updated", self.snapshot())
        self._finish_if_complete()
        return self.positions()

    def inject_failure(
        self,
        drone_id: Optional[int] = None,
        failure_type: Optional[str] = None,
    ) -> Optional[ReplanResult]:
        if self._failure_triggered:
            return self.last_replan_result
        drone_id = self.failed_uav if drone_id is None else int(drone_id)
        failure_type = self.failure_type if failure_type is None else failure_type
        if drone_id not in self.drones:
            raise ValueError(f"Unknown UAV: {drone_id}")
        if failure_type not in self.FAILURE_TYPES:
            raise ValueError(f"Unknown failure type: {failure_type}")

        self.failed_uav = drone_id
        self.failure_type = failure_type
        self._failure_triggered = True
        self.failure_time_s = self.simulation_time_s
        failed = self.drones[drone_id]
        failed.status = DroneStatus.FAILED
        if failure_type == "low_battery":
            failed.battery_percent = 20.0

        self._emit(
            "failure_injected",
            {
                "drone_id": drone_id,
                "failure_type": failure_type,
                "simulation_time_s": self.simulation_time_s,
                "position": failed.position,
            },
        )

        started = time.perf_counter()
        result = self._apply_strategy(drone_id)
        self.replan_compute_s = time.perf_counter() - started
        self.last_replan_result = result
        self.last_metrics = self._calculate_metrics(result)
        self._emit(
            "replan_completed",
            {
                "strategy": self.strategy,
                "result": result,
                "compute_time_s": self.replan_compute_s,
                "snapshot": self.snapshot(),
            },
        )
        self._finish_if_complete()
        return result

    def positions(self) -> Dict[int, Point]:
        return {
            drone_id: drone.position
            for drone_id, drone in self.drones.items()
            if drone.position is not None
        }

    def snapshot(self) -> dict:
        return {
            "status": self.status.value,
            "simulation_time_s": self.simulation_time_s,
            "failure_triggered": self._failure_triggered,
            "drones": {
                drone_id: {
                    "position": drone.position,
                    "altitude_m": drone.altitude_m,
                    "status": drone.status.value,
                    "progress": drone.progress,
                    "distance_flown_m": drone.distance_flown_m,
                    "delay_remaining_s": drone.delay_remaining_s,
                    "finished_time_s": drone.finished_time_s,
                }
                for drone_id, drone in self.drones.items()
            },
        }

    def metrics(self) -> Optional[dict]:
        if self.last_metrics is None:
            return None
        metrics = dict(self.last_metrics)
        metrics["completion_times_s"] = {
            drone_id: drone.finished_time_s
            for drone_id, drone in self.drones.items()
            if drone.finished_time_s is not None
        }
        metrics["simulation_end_s"] = (
            self.simulation_time_s
            if self.status == SimulationStatus.FINISHED
            else None
        )
        return metrics

    def _load_missions(self) -> None:
        drones: Dict[int, DroneSimulationState] = {}
        for drone_id in self.uav_ids:
            path = os.path.join(self.mission_dir, f"points{drone_id}.plan")
            route = load_waypoints_from_plan(path)
            if not route:
                raise FileNotFoundError(f"Missing or empty mission plan: {path}")
            drones[drone_id] = DroneSimulationState(
                drone_id=drone_id,
                original_route=list(route),
                route=list(route),
                speed_mps=self.speed_mps,
            )
        self.drones = drones

    def _advance_drone(self, drone: DroneSimulationState, dt_s: float) -> None:
        if drone.status in (DroneStatus.FAILED, DroneStatus.FINISHED):
            return
        if drone.status == DroneStatus.DELAYED:
            consumed = min(dt_s, drone.delay_remaining_s)
            drone.delay_remaining_s -= consumed
            dt_s -= consumed
            if drone.delay_remaining_s > 1e-9:
                return
            drone.status = DroneStatus.FLYING
        if drone.status != DroneStatus.FLYING or dt_s <= 0.0:
            return

        remaining_distance = drone.speed_mps * dt_s
        while remaining_distance > 1e-9 and drone.segment_index < len(drone.route) - 1:
            start = drone.route[drone.segment_index]
            end = drone.route[drone.segment_index + 1]
            segment_length = haversine_m(start[0], start[1], end[0], end[1])
            if segment_length <= 1e-9:
                drone.segment_index += 1
                drone.segment_offset_m = 0.0
                drone.position = end
                continue

            available = segment_length - drone.segment_offset_m
            travelled = min(remaining_distance, available)
            drone.segment_offset_m += travelled
            drone.distance_flown_m += travelled
            remaining_distance -= travelled

            ratio = min(1.0, drone.segment_offset_m / segment_length)
            drone.position = (
                start[0] + (end[0] - start[0]) * ratio,
                start[1] + (end[1] - start[1]) * ratio,
            )
            if drone.segment_offset_m >= segment_length - 1e-9:
                drone.segment_index += 1
                drone.segment_offset_m = 0.0
                drone.position = end

        if drone.segment_index >= len(drone.route) - 1:
            drone.status = DroneStatus.FINISHED
            drone.position = drone.route[-1]
            if drone.finished_time_s is None:
                drone.finished_time_s = self.simulation_time_s

    def _calculate_metrics(self, result: Optional[ReplanResult]) -> dict:
        plans = {
            drone_id: list(drone.original_route)
            for drone_id, drone in self.drones.items()
        }
        positions = self.positions()
        alive = [drone_id for drone_id in self.uav_ids if drone_id != self.failed_uav]
        targets = residual_pool(plans, positions, self.failed_uav, alive)

        if result is None:
            routes = remaining_routes(plans, positions, alive)
            altitudes = {drone_id: 12.0 for drone_id in routes}
            delays = {drone_id: 0.0 for drone_id in routes}
            speeds = {drone_id: self.speed_mps for drone_id in routes}
            conflicts_before = count_conflicts(
                routes,
                altitudes,
                speeds,
                delays,
                self.d_safe_m,
                alt_clearance_m=4.0,
            )
            conflicts_after = conflicts_before
        else:
            routes = result.routes
            delays = result.delays
            conflicts_before = result.conflicts_before
            conflicts_after = result.conflicts_after

        metrics = calculate_route_metrics(
            targets,
            routes,
            delays,
            self.speed_mps,
        )
        reaction_s = float(self.replan_compute_s or 0.0)
        if self.failure_type == "lost_link":
            reaction_s += 3.0
        else:
            reaction_s = max(0.01, reaction_s)
        metrics.update(
            {
                "strategy": self.strategy,
                "failed_uav": self.failed_uav,
                "failure_type": self.failure_type,
                "failure_progress": round(self.drones[self.failed_uav].progress, 6),
                "failure_time_s": self.failure_time_s,
                "speed_mps": self.speed_mps,
                "d_safe_m": self.d_safe_m,
                "n_c_before": int(conflicts_before),
                "n_c_after": int(conflicts_after),
                "t_react_s": round(reaction_s, 3),
                "uav_ids": list(self.uav_ids),
            }
        )
        return metrics

    def _apply_strategy(self, failed_id: int) -> Optional[ReplanResult]:
        if self.strategy == "B0":
            return None

        coordinator = ReplanCoordinator(
            self.mission_dir,
            ReplanConfig(
                enabled=True,
                monitor_indices=self.uav_ids,
                remap_mode="serpentine",
                apply_caa=self.strategy == "Proposed",
                write_plans=False,
                speed_mps=self.speed_mps,
                d_safe_m=self.d_safe_m,
            ),
            log_fn=lambda _message: None,
        )
        for drone_id, drone in self.drones.items():
            if drone.position is None:
                continue
            coordinator.update_position(
                drone_id, drone.position[0], drone.position[1], drone.altitude_m
            )
            coordinator.update_battery(drone_id, drone.battery_percent)
            coordinator.mark_in_mission(drone_id, drone_id != failed_id)
            coordinator.states[drone_id].failed = drone_id == failed_id
        if self.failure_type == "lost_link":
            coordinator.states[failed_id].connected = False
        else:
            coordinator.update_battery(failed_id, 20.0)

        result = coordinator.build_replan(failed_id)
        if result is None:
            return None
        for drone_id, route in result.routes.items():
            drone = self.drones[drone_id]
            start = drone.position
            new_route = list(route)
            if start is not None and (
                not new_route
                or haversine_m(start[0], start[1], new_route[0][0], new_route[0][1]) > 0.5
            ):
                new_route.insert(0, start)
            drone.route = new_route
            drone.segment_index = 0
            drone.segment_offset_m = 0.0
            drone.altitude_m = float(result.altitudes.get(drone_id, drone.altitude_m))
            drone.delay_remaining_s = float(result.delays.get(drone_id, 0.0))
            drone.status = (
                DroneStatus.DELAYED
                if drone.delay_remaining_s > 0.0
                else DroneStatus.FLYING
            )
        return result

    def _finish_if_complete(self) -> None:
        active = [
            drone
            for drone in self.drones.values()
            if drone.status != DroneStatus.FAILED
        ]
        if active and all(drone.status == DroneStatus.FINISHED for drone in active):
            self.status = SimulationStatus.FINISHED
            if not self._finished_emitted:
                self._finished_emitted = True
                self._emit_state_changed()
                self._emit("simulation_finished", self.snapshot())

    def _emit_state_changed(self) -> None:
        self._emit("state_changed", self.snapshot())

    def _emit(self, event: str, payload: dict) -> None:
        for callback in tuple(self._callbacks[event]):
            callback(payload)
