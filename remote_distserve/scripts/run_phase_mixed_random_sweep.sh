#!/usr/bin/env bash
set -euo pipefail

export SWEEP_ROOT=${SWEEP_ROOT:-/root/data/phase_scheduler_results/mixed_random_1p1d_$(date +%Y%m%d_%H%M%S)}
export SEEDS=${SEEDS:-"0 1"}
export RATES=${RATES:-"4 6 8"}
export NUM_PROMPTS=${NUM_PROMPTS:-96}
export DATASET_SIZE=${DATASET_SIZE:-${NUM_PROMPTS}}
export DATASET_GENERATOR=synthetic
export PROCESS_NAME=${PROCESS_NAME:-poisson}
export POLICIES=${POLICIES:-"fcfs phase"}
export BASELINE_POLICY=${BASELINE_POLICY:-fcfs}
export DATASET_NAME=${DATASET_NAME:-"phaseserve-synthetic-mixed-random"}
export PROMPT_MIX=${PROMPT_MIX:-"64:0.18,128:0.12,256:0.15,512:0.20,1024:0.22,1536:0.13"}
export OUTPUT_MIX=${OUTPUT_MIX:-"32:0.18,64:0.15,128:0.17,256:0.25,512:0.25"}
export MAX_TOTAL_TOKENS=${MAX_TOTAL_TOKENS:-2200}
export TIMEOUT_S=${TIMEOUT_S:-3000}
export SLO_TTFT_S=${SLO_TTFT_S:-10}
export SLO_TPOT_S=${SLO_TPOT_S:-1}

./scripts/run_phase_hetero_sweep.sh
