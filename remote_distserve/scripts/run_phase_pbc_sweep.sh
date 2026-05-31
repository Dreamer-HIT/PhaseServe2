#!/usr/bin/env bash
set -euo pipefail

export SWEEP_ROOT=${SWEEP_ROOT:-/root/data/phase_scheduler_results/cross_stage_pbc_$(date +%Y%m%d_%H%M%S)}
export SEEDS=${SEEDS:-"0 1"}
export RATES=${RATES:-"0 4"}
export NUM_PROMPTS=${NUM_PROMPTS:-48}
export DATASET_SIZE=${DATASET_SIZE:-${NUM_PROMPTS}}
export POLICIES=${POLICIES:-"bps_kas phase"}
export PROCESS_NAME=${PROCESS_NAME:-poisson}
export BASELINE_POLICY=${BASELINE_POLICY:-bps_kas}

./scripts/run_phase_hetero_sweep.sh
