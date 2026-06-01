#!/usr/bin/env bash
set -euo pipefail

REPO_DIR=${REPO_DIR:-/root/data/DistServe}
PYTHON=${PYTHON:-/root/data/conda-envs/distserve/bin/python}
SOURCE_DATASET=${SOURCE_DATASET:-/root/data/datasets/distserve_eval/processed/opt13b_sharegpt.ds}
MODEL_PATH=${MODEL_PATH:-/root/data/models/opt-13b}
MODEL_NAME=${MODEL_NAME:-opt-13b}
SWEEP_ROOT=${SWEEP_ROOT:-/root/data/phase_scheduler_results/layer1_opt13b_sharegpt_broad_$(date +%Y%m%d_%H%M%S)}
MAIN_SWEEP_ROOT=${SWEEP_ROOT}
SEEDS=${SEEDS:-"0 1"}
RATES=${RATES:-"1 2 4 6 8 10 12 16 20 0"}
NUM_PROMPTS=${NUM_PROMPTS:-128}
DATASET_SIZE=${DATASET_SIZE:-${NUM_PROMPTS}}
POLICIES=${POLICIES:-"fcfs phase"}
BASELINE_POLICY=${BASELINE_POLICY:-fcfs}
PROCESS_NAME=${PROCESS_NAME:-poisson}
MAX_TOTAL_TOKENS=${MAX_TOTAL_TOKENS:-2048}
SLO_TTFT_S=${SLO_TTFT_S:-0.25}
SLO_TPOT_S=${SLO_TPOT_S:-0.10}
SLO_GRID=${SLO_GRID:-"distserve:0.25:0.10,loose:0.50:0.15,wide:1.00:0.20"}
TIMEOUT_S=${TIMEOUT_S:-2400}

mkdir -p "${MAIN_SWEEP_ROOT}/datasets"
cd "${REPO_DIR}"

for seed in ${SEEDS}; do
  dataset="${MAIN_SWEEP_ROOT}/datasets/opt13b_sharegpt_seed_${seed}_${NUM_PROMPTS}.ds"
  metadata="${MAIN_SWEEP_ROOT}/datasets/opt13b_sharegpt_seed_${seed}_${NUM_PROMPTS}.metadata.json"
  "${PYTHON}" benchmarks/phase_sample_distserve_dataset.py \
    --input "${SOURCE_DATASET}" \
    --output "${dataset}" \
    --metadata-output "${metadata}" \
    --num-requests "${DATASET_SIZE}" \
    --seed "${seed}" \
    --name "layer1-opt13b-sharegpt-random${NUM_PROMPTS}-seed${seed}" \
    --source "sharegpt_processed"

  seed_root="${MAIN_SWEEP_ROOT}/seed_${seed}_sweep"
  SWEEP_ROOT="${seed_root}" \
    SEEDS="${seed}" \
    RATES="${RATES}" \
    NUM_PROMPTS="${NUM_PROMPTS}" \
    DATASET_SIZE="${DATASET_SIZE}" \
    FIXED_DATASET="${dataset}" \
    FIXED_DATASET_METADATA="${metadata}" \
    DATASET_GENERATOR="synthetic" \
    MODEL_PATH="${MODEL_PATH}" \
    MODEL_NAME="${MODEL_NAME}" \
    POLICIES="${POLICIES}" \
    BASELINE_POLICY="${BASELINE_POLICY}" \
    PROCESS_NAME="${PROCESS_NAME}" \
    MAX_TOTAL_TOKENS="${MAX_TOTAL_TOKENS}" \
    SLO_TTFT_S="${SLO_TTFT_S}" \
    SLO_TPOT_S="${SLO_TPOT_S}" \
    SLO_GRID="${SLO_GRID}" \
    TIMEOUT_S="${TIMEOUT_S}" \
    ./scripts/run_phase_hetero_sweep.sh
done

"${PYTHON}" benchmarks/phase_collect_summaries.py \
  "${MAIN_SWEEP_ROOT}" \
  --output-csv "${MAIN_SWEEP_ROOT}/sweep_summary.csv" \
  --output-md "${MAIN_SWEEP_ROOT}/sweep_summary.md"

"${PYTHON}" benchmarks/phase_analyze_sweep.py \
  "${MAIN_SWEEP_ROOT}" \
  --output-prefix "${MAIN_SWEEP_ROOT}/sweep_analysis" \
  --baseline-policy "${BASELINE_POLICY}"

"${PYTHON}" benchmarks/phase_slo_grid.py \
  "${MAIN_SWEEP_ROOT}" \
  --grid "${SLO_GRID}" \
  --output-prefix "${MAIN_SWEEP_ROOT}/slo_grid"

echo "SWEEP_ROOT=${MAIN_SWEEP_ROOT}"
