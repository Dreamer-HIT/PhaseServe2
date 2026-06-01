#!/usr/bin/env bash
set -euo pipefail

PYTHON=${PYTHON:-/root/data/venvs/vllm-0.2.3/bin/python}
REPO_DIR=${REPO_DIR:-/root/data/DistServe}
MODEL_PATH=${MODEL_PATH:-/root/data/models/opt-13b}
MODEL_NAME=${MODEL_NAME:-opt-13b}
DATASET_PREFIX=${DATASET_PREFIX:-opt13b_sharegpt}
DATA_ROOT=${DATA_ROOT:-/root/data/phase_scheduler_results/stage4o_e2e_full_matrix_20260531_234957/opt13b_sharegpt/datasets}
RESULT_ROOT=${RESULT_ROOT:-/root/data/phase_scheduler_results/stage4r_vllm_slo_opt13b_sharegpt_$(date +%Y%m%d_%H%M%S)}
SEEDS=${SEEDS:-"0 1"}
RATES=${RATES:-"0.75 1.0 1.25 1.5 1.75 2.0 2.25 2.5 2.75 3.0"}
NUM_PROMPTS=${NUM_PROMPTS:-128}
DATASET_NUM_PROMPTS=${DATASET_NUM_PROMPTS:-${NUM_PROMPTS}}
PROCESS_NAME=${PROCESS_NAME:-poisson}
MAX_CONNECTIONS=${MAX_CONNECTIONS:-128}
TIMEOUT_S=${TIMEOUT_S:-3600}
MAX_TOTAL_TOKENS=${MAX_TOTAL_TOKENS:-2048}
PORT=${PORT:-8100}
HOST=${HOST:-127.0.0.1}
SLO_TTFT_S=${SLO_TTFT_S:-0.25}
SLO_TPOT_S=${SLO_TPOT_S:-0.10}
GPU_MEMORY_UTILIZATION=${GPU_MEMORY_UTILIZATION:-0.95}
MAX_NUM_BATCHED_TOKENS=${MAX_NUM_BATCHED_TOKENS:-4096}
MAX_NUM_SEQS=${MAX_NUM_SEQS:-128}
TENSOR_PARALLEL_SIZE=${TENSOR_PARALLEL_SIZE:-1}
CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-0}

mkdir -p "${RESULT_ROOT}" /root/data/logs /root/data/tmp
export CUDA_VISIBLE_DEVICES
export TMPDIR=/root/data/tmp
export HF_HOME=${HF_HOME:-/root/data/hf-cache}
export TRANSFORMERS_CACHE=${TRANSFORMERS_CACHE:-/root/data/hf-cache}
cd "${REPO_DIR}"

stop_server() {
  if [[ -f "${RESULT_ROOT}/server.pid" ]]; then
    local pid
    pid=$(cat "${RESULT_ROOT}/server.pid")
    if [[ -n "${pid}" ]] && ps -p "${pid}" >/dev/null 2>&1; then
      kill "${pid}" || true
      sleep 5
      if ps -p "${pid}" >/dev/null 2>&1; then
        kill -9 "${pid}" || true
      fi
    fi
  fi
  "${PYTHON}" - "${PORT}" <<'PY'
import os
import signal
import sys

port = sys.argv[1]
self_pid = os.getpid()
for pid in os.listdir("/proc"):
    if not pid.isdigit() or int(pid) == self_pid:
        continue
    try:
        raw = open(f"/proc/{pid}/cmdline", "rb").read()
    except OSError:
        continue
    cmd = raw.decode("utf-8", "ignore").replace("\x00", " ")
    if "vllm.entrypoints.api_server" in cmd and f"--port {port}" in cmd:
        try:
            os.kill(int(pid), signal.SIGTERM)
        except OSError:
            pass
PY
  sleep 2
}

wait_ready() {
  local log_file="$1"
  for _ in $(seq 1 300); do
    if curl -sS --max-time 2 "http://${HOST}:${PORT}/health" >/dev/null 2>&1; then
      return 0
    fi
    local pid
    pid=$(cat "${RESULT_ROOT}/server.pid")
    if ! ps -p "${pid}" >/dev/null 2>&1; then
      echo "vLLM server exited during startup" >&2
      tail -200 "${log_file}" >&2 || true
      return 1
    fi
    sleep 1
  done
  echo "vLLM server did not become ready" >&2
  tail -200 "${log_file}" >&2 || true
  return 1
}

start_server() {
  local log_file="${RESULT_ROOT}/server.log"
  stop_server
  nohup "${PYTHON}" -m vllm.entrypoints.api_server \
    --host 0.0.0.0 --port "${PORT}" \
    --model "${MODEL_PATH}" \
    --dtype half \
    --tensor-parallel-size "${TENSOR_PARALLEL_SIZE}" \
    --block-size 16 \
    --seed 0 \
    --swap-space 16 \
    --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION}" \
    --max-num-batched-tokens "${MAX_NUM_BATCHED_TOKENS}" \
    --max-num-seqs "${MAX_NUM_SEQS}" \
    > "${log_file}" 2>&1 &
  echo $! > "${RESULT_ROOT}/server.pid"
  wait_ready "${log_file}"
}

collect_summaries() {
  "${PYTHON}" benchmarks/phase_collect_summaries.py \
    "${RESULT_ROOT}" \
    --output-csv "${RESULT_ROOT}/sweep_summary.csv" \
    --output-md "${RESULT_ROOT}/sweep_summary.md"
}

start_server
for seed in ${SEEDS}; do
  dataset="${DATA_ROOT}/${DATASET_PREFIX}_seed_${seed}_${DATASET_NUM_PROMPTS}.ds"
  for rate in ${RATES}; do
    rate_tag=${rate//./p}
    run_dir="${RESULT_ROOT}/seed_${seed}/rate_${rate_tag}/vllm"
    mkdir -p "${run_dir}"
    "${PYTHON}" benchmarks/phase_vllm_benchmark.py \
      --host "${HOST}" --port "${PORT}" \
      --dataset "${dataset}" \
      --num-prompts "${NUM_PROMPTS}" --sample-mode first \
      --request-rate "${rate}" --process-name "${PROCESS_NAME}" \
      --seed "${seed}" \
      --max-connections "${MAX_CONNECTIONS}" --timeout-s "${TIMEOUT_S}" \
      --max-total-tokens "${MAX_TOTAL_TOKENS}" \
      --num-gpus 1 \
      --output "${run_dir}/vllm_hetero.exp" \
      --raw-output "${run_dir}/vllm_hetero.jsonl" \
      --summary-output "${run_dir}/vllm_hetero.summary.json" \
      --label "vllm-${DATASET_PREFIX}" --policy "vllm" --model "${MODEL_NAME}" \
      --endpoint generate \
      --slo-ttft-s "${SLO_TTFT_S}" --slo-tpot-s "${SLO_TPOT_S}"
    collect_summaries
  done
done
stop_server
collect_summaries
echo "RESULT_ROOT=${RESULT_ROOT}"
