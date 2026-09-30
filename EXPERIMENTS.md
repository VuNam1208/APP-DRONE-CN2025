# Reproducible Offline Experiments

The app and report runner use the same deterministic four-lane mission. UAVs
1-3 come from `mission/points1..3.plan`, scaled 1.5x around their shared
center; UAV4 is an adjacent translated copy of scaled UAV3. Source mission
files are never modified.

Generate the report dataset (30 timing repetitions per row):

```powershell
python simulate_replan_experiments.py --repeats 30 --out-prefix results/report_experiment
```

Generate a robustness matrix over failure progress and failed UAV:

```powershell
python simulate_replan_experiments.py --progresses 0.25,0.40,0.60 --failed-uavs 1,2,3,4 --repeats 10 --out-prefix results/robustness
```

Outputs:

- `*_raw.csv`: one row per run with configuration and provenance.
- `*_summary.csv`: mean, median, standard deviation, min and max timing.
- `*_metadata.json`: mission hash, Git revision and experiment settings.
- `*_table.tex`: generated table included by `Bai_bao/main.tex`.

`t_detect_s` is the configured detection delay. `t_compute_s` is measured wall
time for route generation. `t_react_s = t_detect_s + t_compute_s`; it does not
include real telemetry, mission upload, autopilot or radio latency. These are
point-kinematic simulations, not PX4 SITL or flight tests.
