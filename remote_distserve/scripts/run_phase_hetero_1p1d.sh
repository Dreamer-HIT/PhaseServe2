#!/usr/bin/env bash
set -euo pipefail

REPO_DIR=${REPO_DIR:-/root/data/DistServe}
PYTHON=${PYTHON:-/root/data/conda-envs/distserve/bin/python}
MODEL_PATH=${MODEL_PATH:-/root/data/models/llama2-13b-hf}
DATA_ROOT=${DATA_ROOT:-/root/data}
DISTSERVE_CACHE=${DISTSERVE_CACHE:-${DATA_ROOT}/distserve-cache}
TMPDIR=${TMPDIR:-${DATA_ROOT}/tmp}
TEMP=${TEMP:-${TMPDIR}}
TMP=${TMP:-${TMPDIR}}
RAY_TMPDIR=${RAY_TMPDIR:-${DATA_ROOT}/ray-tmp}
if [[ -z "${MODEL_NAME:-}" ]]; then
  model_dir_name=$(basename "${MODEL_PATH}")
  case "${model_dir_name}" in
    *opt*13b*|*OPT*13B*)
      MODEL_NAME="opt-13b"
      ;;
    *llama*13b*|*Llama*13b*|*LLaMA*13B*)
      MODEL_NAME="llama2-13b"
      ;;
    *)
      MODEL_NAME="${model_dir_name}"
      ;;
  esac
fi
RESULT_ROOT=${RESULT_ROOT:-/root/data/phase_scheduler_results/hetero_1p1d_$(date +%Y%m%d_%H%M%S)}
DATASET=${DATASET:-${RESULT_ROOT}/hetero_synthetic.marshal}
DATASET_METADATA=${DATASET_METADATA:-}
DATASET_GENERATOR=${DATASET_GENERATOR:-synthetic}
NUM_PROMPTS=${NUM_PROMPTS:-48}
DATASET_SIZE=${DATASET_SIZE:-${NUM_PROMPTS}}
DATASET_SEED=${DATASET_SEED:-0}
BENCHMARK_SEED=${BENCHMARK_SEED:-${DATASET_SEED}}
REQUEST_RATE=${REQUEST_RATE:-0}
PROCESS_NAME=${PROCESS_NAME:-uniform}
MAX_CONNECTIONS=${MAX_CONNECTIONS:-${NUM_PROMPTS}}
TIMEOUT_S=${TIMEOUT_S:-1200}
MAX_TOTAL_TOKENS=${MAX_TOTAL_TOKENS:-1600}
GPU_MEMORY_UTILIZATION=${GPU_MEMORY_UTILIZATION:-0.85}
SWAP_SPACE=${SWAP_SPACE:-8}
BLOCK_SIZE=${BLOCK_SIZE:-16}
MAX_NUM_BLOCKS_PER_REQ=${MAX_NUM_BLOCKS_PER_REQ:-256}
CONTEXT_MAX_BATCH_SIZE=${CONTEXT_MAX_BATCH_SIZE:-8}
CONTEXT_MAX_TOKENS_PER_BATCH=${CONTEXT_MAX_TOKENS_PER_BATCH:-2048}
DECODING_MAX_BATCH_SIZE=${DECODING_MAX_BATCH_SIZE:-8}
DECODING_MAX_TOKENS_PER_BATCH=${DECODING_MAX_TOKENS_PER_BATCH:-65536}
PORT=${PORT:-8000}
HOST=${HOST:-127.0.0.1}
SLO_TTFT_S=${SLO_TTFT_S:-10}
SLO_TPOT_S=${SLO_TPOT_S:-1}
POLICIES=${POLICIES:-"phase fcfs"}
PROMPT_MIX=${PROMPT_MIX:-"64:0.50,256:0.30,512:0.20"}
OUTPUT_MIX=${OUTPUT_MIX:-"64:0.30,128:0.30,256:0.20,512:0.15,1024:0.05"}
DATASET_NAME=${DATASET_NAME:-"phaseserve-synthetic-heterogeneous"}
REGIME_PROFILE=${REGIME_PROFILE:-regime_shift_v1}
PHASE_REQUEST_COUNTS=${PHASE_REQUEST_COUNTS:-"24,24,24,24"}
PHASE_RATE_SCHEDULE=${PHASE_RATE_SCHEDULE:-}
PHASE_RATE_SCALE=${PHASE_RATE_SCALE:-1.0}
TRACE_INPUT=${TRACE_INPUT:-}
TRACE_SOURCE=${TRACE_SOURCE:-generic}
TRACE_SAMPLE_MODE=${TRACE_SAMPLE_MODE:-random}
TRACE_PROMPT_FIELD=${TRACE_PROMPT_FIELD:-}
TRACE_OUTPUT_FIELD=${TRACE_OUTPUT_FIELD:-}
TRACE_PROMPT_LEN_FIELD=${TRACE_PROMPT_LEN_FIELD:-prompt_len}
TRACE_OUTPUT_LEN_FIELD=${TRACE_OUTPUT_LEN_FIELD:-output_len}
TRACE_MIN_PROMPT_TOKENS=${TRACE_MIN_PROMPT_TOKENS:-1}
TRACE_MAX_PROMPT_TOKENS=${TRACE_MAX_PROMPT_TOKENS:-4096}
TRACE_MIN_OUTPUT_TOKENS=${TRACE_MIN_OUTPUT_TOKENS:-1}
TRACE_MAX_OUTPUT_TOKENS=${TRACE_MAX_OUTPUT_TOKENS:-1024}
TRACE_MAX_TOTAL_TOKENS=${TRACE_MAX_TOTAL_TOKENS:-0}
TRACE_DEFAULT_OUTPUT_LEN=${TRACE_DEFAULT_OUTPUT_LEN:-128}
TRACE_LENGTH_ONLY_PROMPTS=${TRACE_LENGTH_ONLY_PROMPTS:-0}
PHASESERVE_PBC_RHO_LOW=${PHASESERVE_PBC_RHO_LOW:-0.45}
PHASESERVE_PBC_RHO_HIGH=${PHASESERVE_PBC_RHO_HIGH:-0.65}
PHASESERVE_PBC_MIN_PREFILL_FRAC=${PHASESERVE_PBC_MIN_PREFILL_FRAC:-0.75}
PHASESERVE_PBC_DECODE_QUEUE_TARGET=${PHASESERVE_PBC_DECODE_QUEUE_TARGET:-4}
PHASESERVE_PBC_SWAP_TARGET=${PHASESERVE_PBC_SWAP_TARGET:-1}
PHASESERVE_DECODE_MAX_SWAPINS=${PHASESERVE_DECODE_MAX_SWAPINS:-1}
PHASESERVE_DECODE_SWAP_BUDGET_BYTES=${PHASESERVE_DECODE_SWAP_BUDGET_BYTES:-0}
PHASESERVE_PRESSURE_SNAPSHOT_MAX_AGE_S=${PHASESERVE_PRESSURE_SNAPSHOT_MAX_AGE_S:-2}

mkdir -p "${RESULT_ROOT}" "${DATA_ROOT}/logs" "${DISTSERVE_CACHE}" "${TMPDIR}" "${RAY_TMPDIR}"
export DISTSERVE_CACHE TMPDIR TEMP TMP RAY_TMPDIR
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
  local metadata_path="${DATASET_METADATA}"
  if [[ -z "${metadata_path}" && ( "${DATASET_GENERATOR}" == "regime_shift" || "${DATASET_GENERATOR}" == "trace" ) ]]; then
    metadata_path="${DATASET}.metadata.json"
    DATASET_METADATA="${metadata_path}"
  fi
  if [[ -f "${DATASET}" && ( "${DATASET_GENERATOR}" != "regime_shift" && "${DATASET_GENERATOR}" != "trace" || -f "${metadata_path}" ) ]]; then
    echo "Using existing dataset: ${DATASET}"
    if [[ -n "${metadata_path}" && -f "${metadata_path}" ]]; then
      echo "Using existing request metadata: ${metadata_path}"
    fi
    return 0
  fi
  if [[ "${DATASET_GENERATOR}" == "regime_shift" ]]; then
    "${PYTHON}" benchmarks/phase_make_regime_shift_dataset.py \
      --tokenizer "${MODEL_PATH}" \
      --output "${DATASET}" \
      --metadata-output "${metadata_path}" \
      --seed "${DATASET_SEED}" \
      --profile "${REGIME_PROFILE}" \
      --phase-request-counts "${PHASE_REQUEST_COUNTS}" \
      --name "${DATASET_NAME}"
  elif [[ "${DATASET_GENERATOR}" == "trace" ]]; then
    if [[ -z "${TRACE_INPUT}" ]]; then
      echo "TRACE_INPUT is required when DATASET_GENERATOR=trace" >&2
      return 1
    fi
    local trace_args=(
      --input "${TRACE_INPUT}"
      --tokenizer "${MODEL_PATH}"
      --output "${DATASET}"
      --metadata-output "${metadata_path}"
      --source "${TRACE_SOURCE}"
      --num-requests "${DATASET_SIZE}"
      --seed "${DATASET_SEED}"
      --sample-mode "${TRACE_SAMPLE_MODE}"
      --prompt-len-field "${TRACE_PROMPT_LEN_FIELD}"
      --output-len-field "${TRACE_OUTPUT_LEN_FIELD}"
      --min-prompt-tokens "${TRACE_MIN_PROMPT_TOKENS}"
      --max-prompt-tokens "${TRACE_MAX_PROMPT_TOKENS}"
      --min-output-tokens "${TRACE_MIN_OUTPUT_TOKENS}"
      --max-output-tokens "${TRACE_MAX_OUTPUT_TOKENS}"
      --max-total-tokens "${TRACE_MAX_TOTAL_TOKENS}"
      --default-output-len "${TRACE_DEFAULT_OUTPUT_LEN}"
      --name "${DATASET_NAME}"
    )
    if [[ -n "${TRACE_PROMPT_FIELD}" ]]; then
      trace_args+=(--prompt-field "${TRACE_PROMPT_FIELD}")
    fi
    if [[ -n "${TRACE_OUTPUT_FIELD}" ]]; then
      trace_args+=(--output-field "${TRACE_OUTPUT_FIELD}")
    fi
    if [[ "${TRACE_LENGTH_ONLY_PROMPTS}" == "1" ]]; then
      trace_args+=(--length-only-prompts)
    fi
    "${PYTHON}" benchmarks/phase_make_trace_dataset.py "${trace_args[@]}"
  else
    "${PYTHON}" benchmarks/phase_make_synthetic_dataset.py \
      --tokenizer "${MODEL_PATH}" \
      --output "${DATASET}" \
      --num-requests "${DATASET_SIZE}" \
      --seed "${DATASET_SEED}" \
      --prompt-mix "${PROMPT_MIX}" \
      --output-mix "${OUTPUT_MIX}" \
      --name "${DATASET_NAME}"
  fi
}

start_server() {
  local policy="$1"
  local run_dir="$2"
  local log_file="${run_dir}/server.log"
  local pid_file="${run_dir}/server.pid"
  local context_policy="fcfs"
  local decode_policy="fcfs"
  local emit_phase_metrics=0
  local dynamic_pbc=0
  local prefill_scoring_mode="default"

  case "${policy}" in
    fcfs)
      context_policy="fcfs"
      decode_policy="fcfs"
      ;;
    bps)
      context_policy="phase"
      decode_policy="fcfs"
      emit_phase_metrics=1
      ;;
    spf|shortest_prefill|shortest-prompt-first)
      context_policy="shortest-prefill"
      decode_policy="fcfs"
      ;;
    bps_bucket_only|bucket_only)
      context_policy="phase"
      decode_policy="fcfs"
      emit_phase_metrics=1
      prefill_scoring_mode="bucket_only"
      ;;
    bps_no_oldest_bonus|no_oldest_bonus)
      context_policy="phase"
      decode_policy="fcfs"
      emit_phase_metrics=1
      prefill_scoring_mode="no_oldest_bonus"
      ;;
    bps_age_bonus|age_bonus)
      context_policy="phase"
      decode_policy="fcfs"
      emit_phase_metrics=1
      prefill_scoring_mode="age_bonus"
      ;;
    kas)
      context_policy="fcfs"
      decode_policy="kv-aware-las"
      emit_phase_metrics=1
      ;;
    pure_las|pure-las)
      context_policy="fcfs"
      decode_policy="pure-las"
      emit_phase_metrics=1
      ;;
    kv_unaware_las|kv-unaware-las)
      context_policy="fcfs"
      decode_policy="kv-unaware-las"
      emit_phase_metrics=1
      ;;
    bps_kas)
      context_policy="phase"
      decode_policy="kv-aware-las"
      emit_phase_metrics=1
      ;;
    bps_pbc)
      context_policy="phase"
      decode_policy="fcfs"
      emit_phase_metrics=1
      dynamic_pbc=1
      ;;
    kas_pbc)
      context_policy="fcfs"
      decode_policy="kv-aware-las"
      emit_phase_metrics=1
      dynamic_pbc=1
      ;;
    phase|full)
      context_policy="phase"
      decode_policy="phase"
      emit_phase_metrics=1
      dynamic_pbc=1
      ;;
    *)
      echo "Unknown policy: ${policy}" >&2
      return 1
      ;;
  esac

  if [[ "${emit_phase_metrics}" == "1" ]]; then
    export PHASESERVE_METRICS_PATH="${run_dir}/phase_metrics.jsonl"
    export PHASESERVE_PRESSURE_SNAPSHOT_PATH="${run_dir}/pressure_snapshot.json"
    export PHASESERVE_PRESSURE_SNAPSHOT_MAX_AGE_S
    export PHASESERVE_PBC_RHO_LOW
    export PHASESERVE_PBC_RHO_HIGH
    export PHASESERVE_PBC_MIN_PREFILL_FRAC
    export PHASESERVE_PBC_DECODE_QUEUE_TARGET
    export PHASESERVE_PBC_SWAP_TARGET
    export PHASESERVE_DECODE_MAX_SWAPINS
    export PHASESERVE_DECODE_SWAP_BUDGET_BYTES
    export PHASESERVE_PREFILL_SCORING_MODE="${prefill_scoring_mode}"
    rm -f "${PHASESERVE_PRESSURE_SNAPSHOT_PATH}" "${PHASESERVE_PRESSURE_SNAPSHOT_PATH}".*.tmp
    if [[ "${dynamic_pbc}" == "1" ]]; then
      unset PHASESERVE_PBC_DISABLE_DYNAMIC || true
    else
      export PHASESERVE_PBC_DISABLE_DYNAMIC=1
    fi
  else
    unset PHASESERVE_METRICS_PATH || true
    unset PHASESERVE_PRESSURE_SNAPSHOT_PATH || true
    unset PHASESERVE_PRESSURE_SNAPSHOT_MAX_AGE_S || true
    unset PHASESERVE_PBC_DISABLE_DYNAMIC || true
    unset PHASESERVE_DECODE_SWAP_BUDGET_BYTES || true
    unset PHASESERVE_PREFILL_SCORING_MODE || true
  fi

  nohup "${PYTHON}" -m distserve.api_server.distserve_api_server \
    --host 0.0.0.0 --port "${PORT}" \
    --model "${MODEL_PATH}" \
    --tokenizer "${MODEL_PATH}" \
    --context-tensor-parallel-size 1 --context-pipeline-parallel-size 1 \
    --decoding-tensor-parallel-size 1 --decoding-pipeline-parallel-size 1 \
    --block-size "${BLOCK_SIZE}" --max-num-blocks-per-req "${MAX_NUM_BLOCKS_PER_REQ}" \
    --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION}" --swap-space "${SWAP_SPACE}" \
    --context-sched-policy "${context_policy}" \
    --context-max-batch-size "${CONTEXT_MAX_BATCH_SIZE}" --context-max-tokens-per-batch "${CONTEXT_MAX_TOKENS_PER_BATCH}" \
    --decoding-sched-policy "${decode_policy}" \
    --decoding-max-batch-size "${DECODING_MAX_BATCH_SIZE}" --decoding-max-tokens-per-batch "${DECODING_MAX_TOKENS_PER_BATCH}" \
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
  if [[ -f "${run_dir}/phase_metrics.jsonl" || "${policy}" != "fcfs" ]]; then
    phase_metrics_arg=(--phase-metrics "${run_dir}/phase_metrics.jsonl")
  fi
  local request_metadata_arg=()
  if [[ -n "${DATASET_METADATA}" && -f "${DATASET_METADATA}" ]]; then
    request_metadata_arg=(--request-metadata "${DATASET_METADATA}")
  fi
  local phase_rate_arg=(--phase-rate-scale "${PHASE_RATE_SCALE}")
  if [[ -n "${PHASE_RATE_SCHEDULE}" ]]; then
    phase_rate_arg=(--phase-rate-schedule "${PHASE_RATE_SCHEDULE}" --phase-rate-scale "${PHASE_RATE_SCALE}")
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
    --label "${policy}-hetero-1p1d" --policy "${policy}" --model "${MODEL_NAME}" \
    --slo-ttft-s "${SLO_TTFT_S}" --slo-tpot-s "${SLO_TPOT_S}" \
    "${request_metadata_arg[@]}" \
    "${phase_rate_arg[@]}" \
    "${phase_metrics_arg[@]}"
}

make_dataset
for policy in ${POLICIES}; do
  run_policy "${policy}"
done
stop_server "${RESULT_ROOT}/last_server.pid"

"${PYTHON}" benchmarks/phase_collect_summaries.py \
  "${RESULT_ROOT}" \
  --output-csv "${RESULT_ROOT}/summary.csv" \
  --output-md "${RESULT_ROOT}/summary.md"

echo "RESULT_ROOT=${RESULT_ROOT}"
