# Stage 4L OPT-13B ShareGPT Bridge-Budget Results

This directory stores lightweight summaries for the current rollback snapshot.
Raw benchmark JSONL files and server logs are intentionally excluded.

## Workload

- Model: OPT-13B
- Dataset: ShareGPT fixed 128-request seed0 trace
- Serving shape: 1P1D, 2 GPUs
- Arrival: Poisson
- Main PhaseServe code state: bridge-budgeted KAS default

## Important Remote Roots

- Main validation: `/root/data/phase_scheduler_results/layer1_opt13b_sharegpt_bridge_budget_validate_20260530_234341`
- Default smoke: `/root/data/phase_scheduler_results/layer1_opt13b_sharegpt_default_bridge_budget_smoke_20260531_000121`
- High-rate boundary: `/root/data/phase_scheduler_results/layer1_opt13b_sharegpt_default_bridge_budget_highrates_20260531_000620`
- Rate 4.5 FCFS/Phase: `/root/data/phase_scheduler_results/layer1_opt13b_sharegpt_rate45_default_20260531_002356`
- Rate 5 FCFS: `/root/data/phase_scheduler_results/layer1_opt13b_sharegpt_fcfs_rate5_20260531_001956`

## Current Takeaway

The clean seed0 continuous window is global rate `2.0-4.0`, which maps to
per-GPU rate `1.0-2.0` under the 2-GPU 1P1D setup. In that window, TTFT has at
least two `>=20%` improved percentiles at every point, and TPOT also has at
least two `>=20%` improved percentiles at every point.

High-rate checks show TPOT discontinuities at global rate `4.5` and `6.0`, so
global rate `5.0`, `8.0`, and `10.0` are treated as stress/boundary points
rather than a continuous main positive window.
