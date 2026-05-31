#!/usr/bin/env bash
set -euo pipefail

export SWEEP_ROOT=${SWEEP_ROOT:-/root/data/phase_scheduler_results/mixed_regime_1p1d_$(date +%Y%m%d_%H%M%S)}
export SEEDS=${SEEDS:-"0 1"}
export RATES=${RATES:-"6 8 10"}
export NUM_PROMPTS=${NUM_PROMPTS:-96}
export DATASET_SIZE=${DATASET_SIZE:-${NUM_PROMPTS}}
export DATASET_GENERATOR=regime_shift
export REGIME_PROFILE=${REGIME_PROFILE:-cross_skew_v1}
export PHASE_REQUEST_COUNTS=${PHASE_REQUEST_COUNTS:-"${NUM_PROMPTS}"}
export PROCESS_NAME=${PROCESS_NAME:-poisson}
export POLICIES=${POLICIES:-"fcfs phase"}
export BASELINE_POLICY=${BASELINE_POLICY:-fcfs}
export DATASET_NAME=${DATASET_NAME:-"phaseserve-synthetic-mixed-regime"}
export PHASE_RATE_SCHEDULE=${PHASE_RATE_SCHEDULE:-}
export MAX_TOTAL_TOKENS=${MAX_TOTAL_TOKENS:-2600}
export TIMEOUT_S=${TIMEOUT_S:-2400}
export SLO_TTFT_S=${SLO_TTFT_S:-10}
export SLO_TPOT_S=${SLO_TPOT_S:-1}

./scripts/run_phase_hetero_sweep.sh
