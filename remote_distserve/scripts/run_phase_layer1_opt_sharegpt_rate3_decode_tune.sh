#!/usr/bin/env bash
set -euo pipefail

REPO_DIR=${REPO_DIR:-/root/data/DistServe}
PYTHON=${PYTHON:-/root/data/conda-envs/distserve/bin/python}
MODEL_PATH=${MODEL_PATH:-/root/data/models/opt-13b}
MODEL_NAME=${MODEL_NAME:-opt-13b}
FIXED_DATASET=${FIXED_DATASET:-/root/data/phase_scheduler_results/layer1_opt13b_sharegpt_broad_20260530_173036/datasets/opt13b_sharegpt_seed_0_128.ds}
FIXED_DATASET_METADATA=${FIXED_DATASET_METADATA:-/root/data/phase_scheduler_results/layer1_opt13b_sharegpt_broad_20260530_173036/datasets/opt13b_sharegpt_seed_0_128.metadata.json}
SWEEP_ROOT=${SWEEP_ROOT:-/root/data/phase_scheduler_results/layer1_opt13b_sharegpt_rate3_decode_tune_$(date +%Y%m%d_%H%M%S)}
REQUEST_RATE=${REQUEST_RATE:-3}
NUM_PROMPTS=${NUM_PROMPTS:-128}
DATASET_SIZE=${DATASET_SIZE:-${NUM_PROMPTS}}
PROCESS_NAME=${PROCESS_NAME:-poisson}
MAX_TOTAL_TOKENS=${MAX_TOTAL_TOKENS:-2048}
SLO_TTFT_S=${SLO_TTFT_S:-0.25}
SLO_TPOT_S=${SLO_TPOT_S:-0.10}
SLO_GRID=${SLO_GRID:-"distserve:0.25:0.10,loose:0.50:0.15,wide:1.00:0.20"}
TIMEOUT_S=${TIMEOUT_S:-2400}

run_variant() {
  local name="$1"
  shift
  local result_root="${SWEEP_ROOT}/${name}/rate_${REQUEST_RATE}"
  echo "=== variant=${name} start $(date '+%F %T') ==="
  env "$@" \
    REPO_DIR="${REPO_DIR}" \
    PYTHON="${PYTHON}" \
    MODEL_PATH="${MODEL_PATH}" \
    MODEL_NAME="${MODEL_NAME}" \
    RESULT_ROOT="${result_root}" \
    DATASET="${FIXED_DATASET}" \
    DATASET_METADATA="${FIXED_DATASET_METADATA}" \
    DATASET_GENERATOR="synthetic" \
    TRACE_SOURCE="sharegpt_processed" \
    POLICIES="phase" \
    BASELINE_POLICY="fcfs" \
    PROCESS_NAME="${PROCESS_NAME}" \
    REQUEST_RATE="${REQUEST_RATE}" \
    NUM_PROMPTS="${NUM_PROMPTS}" \
    DATASET_SIZE="${DATASET_SIZE}" \
    MAX_TOTAL_TOKENS="${MAX_TOTAL_TOKENS}" \
    SLO_TTFT_S="${SLO_TTFT_S}" \
    SLO_TPOT_S="${SLO_TPOT_S}" \
    SLO_GRID="${SLO_GRID}" \
    TIMEOUT_S="${TIMEOUT_S}" \
    PHASESERVE_PREFILL_BYPASS_BLOCKED_OLDEST=0 \
    ./scripts/run_phase_hetero_1p1d.sh
  echo "=== variant=${name} done $(date '+%F %T') ==="
}

cd "${REPO_DIR}"
mkdir -p "${SWEEP_ROOT}"

run_variant completion_rem64 \
  PHASESERVE_KAS_BRIDGE_COMPLETION_REMAINING=64

run_variant completion_rem128 \
  PHASESERVE_KAS_BRIDGE_COMPLETION_REMAINING=128

run_variant completion_rem192 \
  PHASESERVE_KAS_BRIDGE_COMPLETION_REMAINING=192

run_variant completion_rem128_quota90 \
  PHASESERVE_KAS_BRIDGE_COMPLETION_REMAINING=128 \
  PHASESERVE_KAS_BRIDGE_COMPLETION_FIRST_DECODE_FRAC=0.90

run_variant completion_rem128_quota75 \
  PHASESERVE_KAS_BRIDGE_COMPLETION_REMAINING=128 \
  PHASESERVE_KAS_BRIDGE_COMPLETION_FIRST_DECODE_FRAC=0.75

run_variant short128 \
  PHASESERVE_KAS_SHORT_OUTPUT_FCFS_THRESHOLD=128

run_variant short160 \
  PHASESERVE_KAS_SHORT_OUTPUT_FCFS_THRESHOLD=160

"${PYTHON}" benchmarks/phase_collect_summaries.py \
  "${SWEEP_ROOT}" \
  --output-csv "${SWEEP_ROOT}/tune_summary.csv" \
  --output-md "${SWEEP_ROOT}/tune_summary.md"

echo "SWEEP_ROOT=${SWEEP_ROOT}"
