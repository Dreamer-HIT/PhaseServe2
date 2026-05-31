#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${TRACE_INPUT:-}" ]]; then
  echo "TRACE_INPUT must point to a ShareGPT/LongBench/length-trace file" >&2
  exit 1
fi

DATASET_GENERATOR=${DATASET_GENERATOR:-trace}
POLICIES=${POLICIES:-fcfs}
BASELINE_POLICY=${BASELINE_POLICY:-fcfs}
PROCESS_NAME=${PROCESS_NAME:-poisson}
TRACE_SAMPLE_MODE=${TRACE_SAMPLE_MODE:-random}
TRACE_LENGTH_ONLY_PROMPTS=${TRACE_LENGTH_ONLY_PROMPTS:-0}
SEEDS=${SEEDS:-"0 1"}
RATES=${RATES:-"0.5 1 1.5 2 2.5 3"}
NUM_PROMPTS=${NUM_PROMPTS:-256}
DATASET_SIZE=${DATASET_SIZE:-${NUM_PROMPTS}}
SLO_GRID=${SLO_GRID:-"tight:1.0:0.10,medium:1.5:0.20,loose:2.0:0.30"}

export DATASET_GENERATOR
export POLICIES
export BASELINE_POLICY
export PROCESS_NAME
export TRACE_SAMPLE_MODE
export TRACE_LENGTH_ONLY_PROMPTS
export SEEDS
export RATES
export NUM_PROMPTS
export DATASET_SIZE
export SLO_GRID

./scripts/run_phase_hetero_sweep.sh
