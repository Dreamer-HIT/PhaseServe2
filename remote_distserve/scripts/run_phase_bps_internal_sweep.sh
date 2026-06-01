#!/usr/bin/env bash
set -euo pipefail

export SWEEP_ROOT=${SWEEP_ROOT:-/root/data/phase_scheduler_results/prefill_skew_bps_internal_$(date +%Y%m%d_%H%M%S)}
export POLICIES=${POLICIES:-"fcfs bps bps_bucket_only bps_no_oldest_bonus bps_age_bonus"}

./scripts/run_phase_prefill_skew_sweep.sh
