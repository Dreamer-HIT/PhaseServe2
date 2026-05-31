#!/usr/bin/env bash
set -euo pipefail

export SWEEP_ROOT=${SWEEP_ROOT:-/root/data/phase_scheduler_results/regime_shift_1p1d_$(date +%Y%m%d_%H%M%S)}
export SEEDS=${SEEDS:-"0 1"}
export RATES=${RATES:-"1.0"}
export NUM_PROMPTS=${NUM_PROMPTS:-96}
export DATASET_SIZE=${DATASET_SIZE:-${NUM_PROMPTS}}
export DATASET_GENERATOR=regime_shift
export REGIME_PROFILE=${REGIME_PROFILE:-regime_shift_v1}
export PHASE_REQUEST_COUNTS=${PHASE_REQUEST_COUNTS:-"24,24,24,24"}
export PROCESS_NAME=${PROCESS_NAME:-poisson}
export POLICIES=${POLICIES:-"fcfs bps kas bps_kas phase"}
export BASELINE_POLICY=${BASELINE_POLICY:-bps_kas}
export DATASET_NAME=${DATASET_NAME:-"phaseserve-synthetic-regime-shift"}
export PHASE_RATE_SCHEDULE=${PHASE_RATE_SCHEDULE:-"prefill_skew:6,decode_heavy:3,mixed_slo:4,prefill_recovery:6"}
export MAX_TOTAL_TOKENS=${MAX_TOTAL_TOKENS:-2600}
export TIMEOUT_S=${TIMEOUT_S:-2400}
export SLO_TTFT_S=${SLO_TTFT_S:-10}
export SLO_TPOT_S=${SLO_TPOT_S:-1}

./scripts/run_phase_hetero_sweep.sh
