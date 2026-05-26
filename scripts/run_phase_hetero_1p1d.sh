#!/usr/bin/env bash
set -euo pipefail

REPO_DIR=${REPO_DIR:-/root/data/DistServe}
PYTHON=${PYTHON:-/root/data/conda-envs/distserve/bin/python}
MODEL_PATH=${MODEL_PATH:-/root/data/models/nous-llama2-7b-hf}
RESULT_ROOT=${RESULT_ROOT:-/root/data/phase_scheduler_results/hetero_1p1d_$(date +%Y%m%d_%H%M%S)}
DATASET=${DATASET:-${RESULT_ROOT}/hetero_synthetic.marshal}
NUM_PROMPTS=${NUM_PROMPTS:-48}
DATASET_SIZE=${DATASET_SIZE:-${NUM_PROMPTS}}
DATASET_SEED=${DATASET_SEED:-0}
BENCHMARK_SEED=${BENCHMARK_SEED:-${DATASET_SEED}}
REQUEST_RATE=${REQUEST_RATE:-0}
PROCESS_NAME=${PROCESS_NAME:-uniform}
MAX_CONNECTIONS=${MAX_CONNECTIONS:-${NUM_PROMPTS}}
TIMEOUT_S=${TIMEOUT_S:-1200}
MAX_TOTAL_TOKENS=${MAX_TOTAL_TOKENS:-1600}
GPU_MEMORY_UTILIZATION=${GPU_MEMORY_UTILIZATION:-0.38}
SWAP_SPACE=${SWAP_SPACE:-8}
PORT=${PORT:-8000}
HOST=${HOST:-127.0.0.1}
SLO_TTFT_S=${SLO_TTFT_S:-10}
SLO_TPOT_S=${SLO_TPOT_S:-1}
PHASESERVE_PBC_RHO_LOW=${PHASESERVE_PBC_RHO_LOW:-0.20}
PHASESERVE_PBC_RHO_HIGH=${PHASESERVE_PBC_RHO_HIGH:-0.40}
PHASESERVE_PBC_DECODE_QUEUE_TARGET=${PHASESERVE_PBC_DECODE_QUEUE_TARGET:-4}
PHASESERVE_PBC_SWAP_TARGET=${PHASESERVE_PBC_SWAP_TARGET:-1}
PHASESERVE_DECODE_MAX_SWAPINS=${PHASESERVE_DECODE_MAX_SWAPINS:-1}

mkdir -p "${RESULT_ROOT}" /root/data/logs
cd "${REPO_DIR}"

stop_server() {
  local pid_file="$1"
  if [[ -f "${pid_file}" ]]; then
    local pid
    pid=$(cat "${pid_file}")
    if [[ -n "${pid}" ]] && ps -p "${pid}" >/dev/null 2>&1; then
      kill "${pid}" || true
      sleep 4
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
    if (
        "distserve.api_server.distserve_api_server" in cmd
        and "--port" in cmd
        and f"--port {port}" in cmd
    ):
        try:
            os.kill(int(pid), signal.SIGTERM)
        except OSError:
            pass
PY
  sleep 2
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
    if (
        "distserve.api_server.distserve_api_server" in cmd
        and "--port" in cmd
        and f"--port {port}" in cmd
    ):
        try:
            os.kill(int(pid), signal.SIGKILL)
        except OSError:
            pass
PY
  ray stop --force >/dev/null 2>&1 || true
  sleep 3
}

wait_ready() {
  local pid_file="$1"
  local log_file="$2"
  for _ in $(seq 1 180); do
    if curl -sS --max-time 2 "http://${HOST}:${PORT}/docs" >/dev/null 2>&1; then
      return 0
    fi
    local pid
    pid=$(cat "${pid_file}")
    if ! ps -p "${pid}" >/dev/null 2>&1; then
      echo "server exited during startup" >&2
      tail -180 "${log_file}" >&2 || true
      return 1
    fi
    sleep 1
  done
  echo "server did not become ready" >&2
  tail -180 "${log_file}" >&2 || true
  return 1
}

make_dataset() {
  if [[ -f "${DATASET}" ]]; then
    echo "Using existing dataset: ${DATASET}"
    return 0
  fi
  "${PYTHON}" benchmarks/phase_make_synthetic_dataset.py \
    --tokenizer "${MODEL_PATH}" \
    --output "${DATASET}" \
    --num-requests "${DATASET_SIZE}" \
    --seed "${DATASET_SEED}"
}

start_server() {
  local policy="$1"
  local run_dir="$2"
  local log_file="${run_dir}/server.log"
  local pid_file="${run_dir}/server.pid"
  local context_policy="fcfs"
  local decode_policy="fcfs"
  if [[ "${policy}" == "phase" ]]; then
    context_policy="phase"
    decode_policy="phase"
    export PHASESERVE_METRICS_PATH="${run_dir}/phase_metrics.jsonl"
    export PHASESERVE_PBC_RHO_LOW
    export PHASESERVE_PBC_RHO_HIGH
    export PHASESERVE_PBC_DECODE_QUEUE_TARGET
    export PHASESERVE_PBC_SWAP_TARGET
    export PHASESERVE_DECODE_MAX_SWAPINS
  else
    unset PHASESERVE_METRICS_PATH || true
  fi

  nohup "${PYTHON}" -m distserve.api_server.distserve_api_server \
    --host 0.0.0.0 --port "${PORT}" \
    --model "${MODEL_PATH}" \
    --tokenizer "${MODEL_PATH}" \
    --context-tensor-parallel-size 1 --context-pipeline-parallel-size 1 \
    --decoding-tensor-parallel-size 1 --decoding-pipeline-parallel-size 1 \
    --block-size 16 --max-num-blocks-per-req 256 \
    --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION}" --swap-space "${SWAP_SPACE}" \
    --context-sched-policy "${context_policy}" \
    --context-max-batch-size 8 --context-max-tokens-per-batch 2048 \
    --decoding-sched-policy "${decode_policy}" \
    --decoding-max-batch-size 8 --decoding-max-tokens-per-batch 65536 \
    > "${log_file}" 2>&1 &
  echo $! > "${pid_file}"
  wait_ready "${pid_file}" "${log_file}"
}

run_policy() {
  local policy="$1"
  local run_dir="${RESULT_ROOT}/${policy}"
  mkdir -p "${run_dir}"
  stop_server "${RESULT_ROOT}/last_server.pid"
  start_server "${policy}" "${run_dir}"
  cp "${run_dir}/server.pid" "${RESULT_ROOT}/last_server.pid"

  local phase_metrics_arg=()
  if [[ "${policy}" == "phase" ]]; then
    phase_metrics_arg=(--phase-metrics "${run_dir}/phase_metrics.jsonl")
  fi

  "${PYTHON}" benchmarks/phase_native_benchmark.py \
    --host "${HOST}" --port "${PORT}" \
    --dataset "${DATASET}" \
    --num-prompts "${NUM_PROMPTS}" --sample-mode first \
    --request-rate "${REQUEST_RATE}" --process-name "${PROCESS_NAME}" \
    --seed "${BENCHMARK_SEED}" \
    --max-connections "${MAX_CONNECTIONS}" --timeout-s "${TIMEOUT_S}" \
    --max-total-tokens "${MAX_TOTAL_TOKENS}" \
    --num-gpus 2 \
    --output "${run_dir}/${policy}_hetero.exp" \
    --raw-output "${run_dir}/${policy}_hetero.jsonl" \
    --summary-output "${run_dir}/${policy}_hetero.summary.json" \
    --label "${policy}-hetero-1p1d" --policy "${policy}" --model llama2-7b \
    --slo-ttft-s "${SLO_TTFT_S}" --slo-tpot-s "${SLO_TPOT_S}" \
    "${phase_metrics_arg[@]}"
}

make_dataset
run_policy phase
run_policy fcfs
stop_server "${RESULT_ROOT}/last_server.pid"

"${PYTHON}" benchmarks/phase_collect_summaries.py \
  "${RESULT_ROOT}" \
  --output-csv "${RESULT_ROOT}/summary.csv" \
  --output-md "${RESULT_ROOT}/summary.md"

echo "RESULT_ROOT=${RESULT_ROOT}"
