"""Generate the report's trajectory example from the experiment coordinator."""

from __future__ import annotations

import os

import matplotlib.pyplot as plt

from replan_coordinator import ReplanConfig, ReplanCoordinator, prepend_route_starts
from simulate_replan_experiments import load_plans, seed_states
from simulation_metrics import residual_pool
from simulation_missions import prepare_adjacent_sim_missions


def build_result(mission_dir, plans, failed, progress, apply_caa):
    coordinator = ReplanCoordinator(
        mission_dir,
        ReplanConfig(
            enabled=True,
            monitor_indices=(1, 2, 3, 4),
            remap_mode="serpentine",
            apply_caa=apply_caa,
            write_plans=False,
            speed_mps=2.0,
            d_safe_m=15.0,
        ),
        log_fn=lambda _message: None,
    )
    batteries = {1: 72, 2: 88, 3: 78, 4: 68}
    positions = seed_states(coordinator, plans, progress, batteries)
    coordinator.states[failed].failed = True
    coordinator.states[failed].in_mission = False
    result = coordinator.build_replan(failed)
    if result is None:
        raise RuntimeError("No replan result for report figure")
    return positions, result


def draw_routes(axis, routes, colors, linewidth=1.6):
    for drone_id, route in routes.items():
        if not route:
            continue
        axis.plot(
            [point[1] for point in route],
            [point[0] for point in route],
            color=colors[drone_id],
            linewidth=linewidth,
            label=f"UAV {drone_id}",
        )


def main():
    root = os.path.dirname(os.path.abspath(__file__))
    owner, mission_dir = prepare_adjacent_sim_missions(os.path.join(root, "mission"))
    try:
        plans = load_plans(mission_dir, (1, 2, 3, 4))
        failed, progress = 2, 0.40
        positions, b1 = build_result(mission_dir, plans, failed, progress, False)
        _, proposed = build_result(mission_dir, plans, failed, progress, True)
        targets = residual_pool(plans, positions, failed, [1, 3, 4])
        colors = {1: "#2563eb", 2: "#dc2626", 3: "#16a34a", 4: "#9333ea"}

        figure, axes = plt.subplots(1, 4, figsize=(12.2, 3.05), constrained_layout=True)
        draw_routes(axes[0], plans, colors)
        axes[0].set_title("(a) Original missions")

        draw_routes(axes[1], plans, {key: "#cbd5e1" for key in plans}, linewidth=1.0)
        axes[1].scatter(
            [point[1] for point in targets], [point[0] for point in targets],
            s=6, color="#f97316", label="Residual",
        )
        axes[1].scatter(
            [positions[failed][1]], [positions[failed][0]], marker="x",
            s=55, linewidth=2.0, color="#dc2626", label="Failure",
        )
        axes[1].set_title("(b) Failure and residual")

        draw_routes(axes[2], prepend_route_starts(b1.routes, positions), colors)
        axes[2].set_title(f"(c) B1 remap, $N_c={b1.conflicts_after}$")

        draw_routes(axes[3], prepend_route_starts(proposed.routes, positions), colors)
        for drone_id, route in proposed.routes.items():
            if route:
                axes[3].annotate(
                    f"h={proposed.altitudes[drone_id]:.0f} m, "
                    f"$\\tau$={proposed.delays[drone_id]:.0f} s",
                    (route[0][1], route[0][0]), fontsize=6,
                )
        axes[3].set_title(f"(d) Proposed, $N_c={proposed.conflicts_after}$")

        for axis in axes:
            axis.grid(True, color="#e2e8f0", linewidth=0.5)
            axis.set_aspect("equal", adjustable="datalim")
            axis.ticklabel_format(useOffset=False)
            axis.tick_params(labelsize=6)
            axis.set_xlabel("Longitude", fontsize=7)
        axes[0].set_ylabel("Latitude", fontsize=7)
        handles, labels = axes[0].get_legend_handles_labels()
        figure.legend(handles, labels, loc="lower center", ncol=4, fontsize=7)
        output = os.path.join(root, "Bai_bao", "figures", "fig2_trajectory.png")
        figure.savefig(output, dpi=240, bbox_inches="tight")
        plt.close(figure)
        print(os.path.relpath(output, root))
    finally:
        owner.cleanup()


if __name__ == "__main__":
    main()
