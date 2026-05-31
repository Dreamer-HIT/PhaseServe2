#!/usr/bin/env bash
set -euo pipefail

export SWEEP_ROOT=${SWEEP_ROOT:-/root/data/phase_scheduler_results/decode_heavy_1p1d_$(date +%Y%m%d_%H%M%S)}
export SEEDS=${SEEDS:-"0 1"}
export RATES=${RATES:-"0 2"}
export NUM_PROMPTS=${NUM_PROMPTS:-48}
export DATASET_SIZE=${DATASET_SIZE:-${NUM_PROMPTS}}
export POLICIES=${POLICIES:-"fcfs kas bps_kas phase"}
export BASELINE_POLICY=${BASELINE_POLICY:-fcfs}
export PROCESS_NAME=${PROCESS_NAME:-poisson}
export PROMPT_MIX=${PROMPT_MIX:-"64:0.60,256:0.25,512:0.15"}
export OUTPUT_MIX=${OUTPUT_MIX:-"128:0.25,256:0.30,512:0.30,1024:0.15"}
export MAX_TOTAL_TOKENS=${MAX_TOTAL_TOKENS:-1600}
export TIMEOUT_S=${TIMEOUT_S:-1800}
export DATASET_NAME=${DATASET_NAME:-"phaseserve-synthetic-decode-heavy"}

./scripts/run_phase_hetero_sweep.sh
