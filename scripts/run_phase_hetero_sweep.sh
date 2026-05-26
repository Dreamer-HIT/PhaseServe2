#!/usr/bin/env bash
set -euo pipefail

REPO_DIR=${REPO_DIR:-/root/data/DistServe}
PYTHON=${PYTHON:-/root/data/conda-envs/distserve/bin/python}
SWEEP_ROOT=${SWEEP_ROOT:-/root/data/phase_scheduler_results/hetero_1p1d_sweep_$(date +%Y%m%d_%H%M%S)}
SEEDS=${SEEDS:-"0 1"}
RATES=${RATES:-"0 1 2"}
NUM_PROMPTS=${NUM_PROMPTS:-48}
DATASET_SIZE=${DATASET_SIZE:-${NUM_PROMPTS}}
PROCESS_NAME=${PROCESS_NAME:-poisson}
POLICIES=${POLICIES:-"phase fcfs"}
PROMPT_MIX=${PROMPT_MIX:-"64:0.50,256:0.30,512:0.20"}
OUTPUT_MIX=${OUTPUT_MIX:-"64:0.30,128:0.30,256:0.20,512:0.15,1024:0.05"}
DATASET_NAME=${DATASET_NAME:-"phaseserve-synthetic-heterogeneous"}

mkdir -p "${SWEEP_ROOT}"
cd "${REPO_DIR}"

for seed in ${SEEDS}; do
  for rate in ${RATES}; do
    rate_tag=${rate//./p}
    run_root="${SWEEP_ROOT}/seed_${seed}/rate_${rate_tag}"
    dataset="${SWEEP_ROOT}/datasets/hetero_seed_${seed}.marshal"
    echo "=== seed=${seed} rate=${rate} run_root=${run_root} ==="
    RESULT_ROOT="${run_root}" \
      DATASET="${dataset}" \
      DATASET_SEED="${seed}" \
      BENCHMARK_SEED="${seed}" \
      NUM_PROMPTS="${NUM_PROMPTS}" \
      DATASET_SIZE="${DATASET_SIZE}" \
      REQUEST_RATE="${rate}" \
      PROCESS_NAME="${PROCESS_NAME}" \
      POLICIES="${POLICIES}" \
      PROMPT_MIX="${PROMPT_MIX}" \
      OUTPUT_MIX="${OUTPUT_MIX}" \
      DATASET_NAME="${DATASET_NAME}" \
      ./scripts/run_phase_hetero_1p1d.sh
  done
done

"${PYTHON}" benchmarks/phase_collect_summaries.py \
  "${SWEEP_ROOT}" \
  --output-csv "${SWEEP_ROOT}/sweep_summary.csv" \
  --output-md "${SWEEP_ROOT}/sweep_summary.md"

"${PYTHON}" benchmarks/phase_analyze_sweep.py \
  "${SWEEP_ROOT}" \
  --output-prefix "${SWEEP_ROOT}/sweep_analysis"

echo "SWEEP_ROOT=${SWEEP_ROOT}"
