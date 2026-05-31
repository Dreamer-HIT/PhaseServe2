# PhaseServe Experiment Scripts

The scripts in this directory are intended to be run from the DistServe checkout on the remote server, usually `/root/data/DistServe`.

## Main Entrypoints

- `run_phase_hetero_1p1d.sh`: single 1P1D run for one model, dataset, policy set, and rate.
- `run_phase_hetero_sweep.sh`: seed/rate sweep wrapper around the single-run script.
- `run_phase_layer1_opt_sharegpt_broad.sh`: current OPT-13B + ShareGPT broad end-to-end sweep.
- `run_phase_ablation_sweep.sh`: component ablation sweep.

## Workload-Specific Sweeps

- `run_phase_prefill_skew_sweep.sh`: synthetic prefill-pressure workload.
- `run_phase_decode_heavy_sweep.sh`: synthetic decode-pressure workload.
- `run_phase_mixed_regime_sweep.sh`: mixed-regime workload.
- `run_phase_regime_shift_sweep.sh`: phase-shift workload.
- `run_phase_trace_baseline_sweep.sh`: trace-derived baseline sweep.

## Archive

`archive/` contains one-off tuning scripts tied to old datasets or temporary parameter searches. They are kept for traceability, but should not be used as canonical experiment entrypoints.
