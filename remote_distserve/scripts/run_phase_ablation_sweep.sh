#!/usr/bin/env bash
set -euo pipefail

export SWEEP_ROOT=${SWEEP_ROOT:-/root/data/phase_scheduler_results/hetero_1p1d_ablation_$(date +%Y%m%d_%H%M%S)}
export SEEDS=${SEEDS:-"0 1"}
export RATES=${RATES:-"0 4"}
export POLICIES=${POLICIES:-"fcfs bps kas bps_kas phase"}

./scripts/run_phase_hetero_sweep.sh
