#!/usr/bin/env bash
set -euo pipefail

export SWEEP_ROOT=${SWEEP_ROOT:-/root/data/phase_scheduler_results/prefill_skew_1p1d_$(date +%Y%m%d_%H%M%S)}
export SEEDS=${SEEDS:-"0 1"}
export RATES=${RATES:-"0 6 10"}
export NUM_PROMPTS=${NUM_PROMPTS:-96}
export DATASET_SIZE=${DATASET_SIZE:-${NUM_PROMPTS}}
export PROCESS_NAME=${PROCESS_NAME:-poisson}
export POLICIES=${POLICIES:-"fcfs bps"}
export PROMPT_MIX=${PROMPT_MIX:-"64:0.45,512:0.25,1024:0.20,1536:0.10"}
export OUTPUT_MIX=${OUTPUT_MIX:-"32:0.60,64:0.30,128:0.10"}
export DATASET_NAME=${DATASET_NAME:-"phaseserve-synthetic-prefill-skew"}
export MAX_TOTAL_TOKENS=${MAX_TOTAL_TOKENS:-1800}
export SLO_TTFT_S=${SLO_TTFT_S:-10}
export SLO_TPOT_S=${SLO_TPOT_S:-1}

./scripts/run_phase_hetero_sweep.sh
