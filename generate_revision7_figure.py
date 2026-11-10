"""Plot the already-tested ascent counterexample; no new mission experiments."""

import csv
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from evaluate_revision5 import conflict_pairs_3d, profile


def run():
    routes = {1: [(0, 0), (5, 0)], 2: [(10, 0), (15, 0)]}
    actual = {1: profile(routes[1], 22, 22, 0), 2: profile(routes[2], 12, 27, 2)}
    nominal = {1: profile(routes[1], 22, 22, 0), 2: profile(routes[2], 27, 27, 2)}
    assert conflict_pairs_3d(nominal, 15, 4) == 0
    assert conflict_pairs_3d(actual, 15, 4) == 1
    times = np.linspace(0, 20, 2001)
    coordinates = {}
    for drone, vertices in actual.items():
        knots = [vertex[0] for vertex in vertices]
        coordinates[drone] = np.array([
            np.interp(times, knots, [vertex[1][axis] for vertex in vertices])
            for axis in range(3)
        ])
    horizontal = np.linalg.norm(coordinates[1][:2] - coordinates[2][:2], axis=0)
    vertical = np.abs(coordinates[1][2] - coordinates[2][2])
    output = Path("Bai_bao/figures")
    output.mkdir(parents=True, exist_ok=True)
    data_output = Path("results/revision7")
    data_output.mkdir(parents=True, exist_ok=True)
    with (data_output / "ascent_example.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["time_s", "uav1_alt_m", "uav2_alt_m", "horizontal_m", "vertical_m"])
        writer.writerows(zip(times, coordinates[1][2], coordinates[2][2], horizontal, vertical))

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9,
                         "pdf.fonttype": 42, "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(2, 1, figsize=(7.2, 4.3), sharex=True, layout="constrained")
    blue, green, red = "#23618a", "#277349", "#ad3447"
    axes[0].plot(times, coordinates[1][2], color=blue, label="UAV 1: cruise, then hold", linewidth=1.8)
    axes[0].plot(times, coordinates[2][2], color=green, label="UAV 2: ascent, wait, cruise", linewidth=1.8)
    axes[0].axhline(27, color="#666666", linestyle=":", linewidth=1, label="UAV 2 target layer")
    axes[0].set(ylabel="Altitude (m)", ylim=(10, 32))
    axes[0].legend(loc="upper left", ncol=2, fontsize=8, frameon=False)
    axes[0].text(10, 11, "Both separation rules violated: 6 < t < 14 s",
                 ha="center", fontsize=8, color=red)
    axes[1].plot(times, horizontal, color=blue, label="Horizontal distance", linewidth=1.8)
    axes[1].plot(times, vertical, color=green, label="Vertical distance", linewidth=1.8)
    axes[1].axhline(15, color=blue, linestyle="--", linewidth=1, label="Horizontal threshold: 15 m")
    axes[1].axhline(4, color=green, linestyle="--", linewidth=1, label="Vertical threshold: 4 m")
    axes[1].set(xlabel="Time (s)", ylabel="Pairwise distance (m)", ylim=(0, 20), xlim=(0, 20))
    axes[1].legend(loc="upper center", ncol=2, fontsize=8, frameon=False)
    for axis, label in zip(axes, ("(a)", "(b)")):
        axis.axvspan(6, 14, color=red, alpha=0.10, linewidth=0)
        axis.grid(axis="y", alpha=0.18)
        axis.text(-0.08, 1.02, label, transform=axis.transAxes, fontweight="bold")
    for extension in ("pdf", "png"):
        fig.savefig(output / f"fig2_ascent_counterexample.{extension}", dpi=240)
    plt.close(fig)
    metadata = {
        "nominal_conflicting_pairs": 0, "transition_conflicting_pairs": 1,
        "strict_violation_interval_s": [6, 14],
        "interval_endpoints_excluded": True,
        "note": "Figure samples are for drawing only; conflict classification uses the analytic 3D evaluator.",
        "source_hashes": {name: hashlib.sha256(Path(name).read_bytes()).hexdigest()
                          for name in ("generate_revision7_figure.py", "evaluate_revision5.py")},
    }
    (data_output / "figure_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print("Generated PDF/PNG ascent counterexample; nominal pairs=0, transition pairs=1.")


if __name__ == "__main__":
    run()
