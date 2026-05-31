#!/usr/bin/env python3
import argparse
import csv
import json
from pathlib import Path


METRIC_FIELDS = [
    ("latency_s", "median"),
    ("latency_s", "p75"),
    ("latency_s", "p90"),
    ("latency_s", "p95"),
    ("latency_s", "p99"),
    ("ttft_s", "median"),
    ("ttft_s", "p75"),
    ("ttft_s", "p90"),
    ("ttft_s", "p95"),
    ("ttft_s", "p99"),
    ("tpot_s", "median"),
    ("tpot_s", "p75"),
    ("tpot_s", "p90"),
    ("tpot_s", "p95"),
    ("tpot_s", "p99"),
    ("context_queue_s", "median"),
    ("context_exec_s", "median"),
    ("bridge_queue_s", "median"),
    ("migration_s", "median"),
    ("decode_queue_s", "median"),
    ("decode_exec_s", "median"),
]


def flatten_summary(path: Path):
    data = json.loads(path.read_text())
    metadata = data.get("metadata", {})
    row = {
        "path": str(path),
        "label": metadata.get("label"),
        "policy": metadata.get("policy"),
        "model": metadata.get("model"),
        "dataset": metadata.get("dataset"),
        "request_rate": metadata.get("request_rate"),
        "process_name": metadata.get("process_name"),
        "num_prompts": metadata.get("num_prompts"),
        "seed": metadata.get("seed"),
        "num_gpus": metadata.get("num_gpus"),
        "submitted": data.get("submitted"),
        "completed": data.get("completed"),
        "failed": data.get("failed"),
        "goodput": data.get("goodput"),
        "throughput_req_s": data.get("throughput_req_s"),
        "goodput_req_s": data.get("goodput_req_s"),
        "slo_attainment_completed": data.get("slo_attainment_completed"),
        "slo_attainment_submitted": data.get("slo_attainment_submitted"),
    }
    throughput = data.get("throughput") or {}
    for key in [
        "offered_req_s",
        "submitted_req_s",
        "completed_req_s",
        "goodput_req_s",
        "per_gpu_completed_req_s",
        "per_gpu_goodput_req_s",
        "input_tokens_s",
        "requested_output_tokens_s",
        "generated_output_tokens_s",
        "total_generated_tokens_s",
    ]:
        row[f"throughput_{key}"] = throughput.get(key)
    for metric, stat in METRIC_FIELDS:
        row[f"{metric}_{stat}"] = (data.get(metric) or {}).get(stat)
    phase_components = (data.get("phase_metrics") or {}).get("components") or {}
    decode = phase_components.get("decode") or {}
    context = phase_components.get("context") or {}
    row["phase_decode_swap_ins"] = decode.get("swap_ins")
    row["phase_decode_evictions"] = decode.get("eviction_count")
    row["phase_decode_scan_mean"] = (decode.get("decode_scan_limit") or {}).get("mean")
    row["phase_decode_selected_mean"] = (decode.get("selected") or {}).get("mean")
    row["phase_decode_starved_ready"] = decode.get("starved_ready")
    row["phase_decode_starved_selected"] = decode.get("starved_selected")
    row["phase_decode_starved_admission_ratio_mean"] = (decode.get("starved_admission_ratio") or {}).get("mean")
    row["phase_decode_first_token_ready"] = decode.get("first_token_ready")
    row["phase_decode_first_token_selected"] = decode.get("first_token_selected")
    row["phase_decode_first_token_admission_ratio_mean"] = (
        decode.get("first_token_admission_ratio") or {}
    ).get("mean")
    row["phase_decode_handoff_debt_ready"] = decode.get("handoff_debt_ready")
    row["phase_decode_handoff_debt_selected"] = decode.get("handoff_debt_selected")
    row["phase_decode_handoff_debt_admission_ratio_mean"] = (
        decode.get("handoff_debt_admission_ratio") or {}
    ).get("mean")
    row["phase_decode_handoff_debt_discount_mean"] = (
        decode.get("handoff_debt_discount_mean") or {}
    ).get("mean")
    row["phase_decode_handoff_debt_selected_discount_mean"] = (
        decode.get("handoff_debt_selected_discount_mean") or {}
    ).get("mean")
    row["phase_decode_handoff_debt_weight_mean"] = (
        decode.get("handoff_debt_weight") or {}
    ).get("mean")
    row["phase_decode_budget_ttft_debt_weight_mean"] = (
        decode.get("budget_ttft_debt_weight") or {}
    ).get("mean")
    row["phase_decode_effective_handoff_debt_weight_mean"] = (
        decode.get("effective_handoff_debt_weight") or {}
    ).get("mean")
    row["phase_decode_handoff_debt_pressure_mean"] = (
        decode.get("handoff_debt_pressure") or {}
    ).get("mean")
    row["phase_decode_kas_intensity_mean"] = (
        decode.get("kas_intensity") or {}
    ).get("mean")
    row["phase_decode_selected_effective_kas_intensity_mean"] = (
        decode.get("selected_effective_kas_intensity") or {}
    ).get("mean")
    row["phase_decode_fcfs_fallback_active"] = decode.get("fcfs_fallback_active")
    row["phase_decode_fcfs_fallback_threshold_mean"] = (
        decode.get("fcfs_fallback_intensity_threshold") or {}
    ).get("mean")
    row["phase_decode_short_output_fcfs_threshold_mean"] = (
        decode.get("short_output_fcfs_threshold") or {}
    ).get("mean")
    row["phase_decode_long_output_full_kas_threshold_mean"] = (
        decode.get("long_output_full_kas_threshold") or {}
    ).get("mean")
    row["phase_decode_avg_target_output_len_mean"] = (
        decode.get("avg_target_output_len") or {}
    ).get("mean")
    row["phase_decode_budget_decode_utility_intensity_mean"] = (
        decode.get("budget_decode_utility_intensity") or {}
    ).get("mean")
    row["phase_decode_decode_utility_intensity_mean"] = (
        decode.get("decode_utility_intensity") or {}
    ).get("mean")
    row["phase_decode_regime_counts"] = json.dumps(decode.get("regimes") or {}, sort_keys=True)
    row["phase_decode_budget_regime_counts"] = json.dumps(
        decode.get("budget_regimes") or {},
        sort_keys=True,
    )
    row["phase_decode_regime_switch_rate_mean"] = (
        decode.get("controller_regime_switch_rate") or {}
    ).get("mean")
    row["phase_decode_intensity_delta_mean"] = (
        decode.get("controller_intensity_delta") or {}
    ).get("mean")
    row["phase_decode_controller_decode_utility_intensity_mean"] = (
        decode.get("controller_decode_utility_intensity") or {}
    ).get("mean")
    row["phase_decode_controller_ttft_debt_weight_mean"] = (
        decode.get("controller_ttft_debt_weight") or {}
    ).get("mean")
    row["phase_decode_kas_adaptive_intensity"] = decode.get("kas_adaptive_intensity")
    row["phase_decode_prefill_gate_active"] = decode.get("prefill_gate_active")
    row["phase_decode_prefill_gate_pressure_mean"] = (
        decode.get("prefill_gate_pressure") or {}
    ).get("mean")
    row["phase_decode_prefill_gate_hard_mean"] = (
        decode.get("prefill_gate_decode_hard_pressure") or {}
    ).get("mean")
    row["phase_decode_policy_skipped"] = decode.get("policy_skipped")
    row["phase_decode_infeasible_rounds"] = decode.get("infeasible_rounds")
    row["phase_decode_infeasible_gpu_append_blocks"] = decode.get("infeasible_gpu_append_blocks")
    row["phase_decode_infeasible_gpu_swap_blocks"] = decode.get("infeasible_gpu_swap_blocks")
    row["phase_decode_infeasible_swap_budget"] = decode.get("infeasible_swap_budget")
    row["phase_decode_max_skip_max"] = (decode.get("max_consecutive_skips") or {}).get("max")
    row["phase_decode_max_infeasible_max"] = (decode.get("max_consecutive_infeasible") or {}).get("max")
    row["phase_decode_mode_switch_rate_mean"] = (decode.get("controller_mode_switch_rate") or {}).get("mean")
    row["phase_decode_budget_delta_mean"] = (decode.get("controller_budget_delta") or {}).get("mean")
    row["phase_decode_pressure_overshoot_mean"] = (decode.get("pressure_overshoot") or {}).get("mean")
    row["phase_decode_pressure_potential_mean"] = (decode.get("pressure_potential") or {}).get("mean")
    row["phase_decode_goodput_capacity_mean"] = (decode.get("goodput_capacity") or {}).get("mean")
    row["phase_decode_smooth_cost_mean"] = (decode.get("smooth_cost") or {}).get("mean")
    row["phase_decode_progress_debt_mean"] = (decode.get("progress_debt") or {}).get("mean")
    row["phase_decode_pressure_injection_swap_mean"] = (
        decode.get("pressure_injection_decode_swap") or {}
    ).get("mean")
    row["phase_decode_pressure_decode_hard_mean"] = (decode.get("pressure_decode_hard") or {}).get("mean")
    row["phase_decode_pressure_kv_hard_mean"] = (decode.get("pressure_kv_hard") or {}).get("mean")
    row["phase_decode_rho_prefill_mean"] = (decode.get("rho_prefill") or {}).get("mean")
    row["phase_decode_rho_memory_mean"] = (decode.get("rho_memory") or {}).get("mean")
    row["phase_decode_rho_swap_mean"] = (decode.get("rho_swap") or {}).get("mean")
    row["phase_decode_rho_scan_mean"] = (decode.get("rho_scan") or {}).get("mean")
    row["phase_decode_rho_hard_mean"] = (decode.get("rho_hard") or {}).get("mean")
    row["phase_decode_pressure_first_mean"] = (decode.get("pressure_first") or {}).get("mean")
    row["phase_decode_swap_byte_budget_mean"] = (decode.get("swap_byte_budget") or {}).get("mean")
    row["phase_decode_swap_byte_budget_ratio_mean"] = (decode.get("swap_byte_budget_ratio") or {}).get("mean")
    row["phase_context_prefill_budget_mean"] = (context.get("prefill_token_budget") or {}).get("mean")
    row["phase_context_prefill_budget_ratio_mean"] = (context.get("prefill_budget_ratio") or {}).get("mean")
    row["phase_context_prefill_block_margin_mean"] = (context.get("prefill_block_margin") or {}).get("mean")
    row["phase_context_decode_utility_intensity_mean"] = (
        context.get("decode_utility_intensity") or {}
    ).get("mean")
    row["phase_context_controller_ttft_debt_weight_mean"] = (
        context.get("controller_ttft_debt_weight") or {}
    ).get("mean")
    row["phase_context_regime_counts"] = json.dumps(context.get("regimes") or {}, sort_keys=True)
    row["phase_context_regime_switch_rate_mean"] = (
        context.get("controller_regime_switch_rate") or {}
    ).get("mean")
    row["phase_context_intensity_delta_mean"] = (
        context.get("controller_intensity_delta") or {}
    ).get("mean")
    row["phase_context_mode_switch_rate_mean"] = (context.get("controller_mode_switch_rate") or {}).get("mean")
    row["phase_context_budget_delta_mean"] = (context.get("controller_budget_delta") or {}).get("mean")
    row["phase_context_pressure_overshoot_mean"] = (context.get("pressure_overshoot") or {}).get("mean")
    row["phase_context_pressure_potential_mean"] = (context.get("pressure_potential") or {}).get("mean")
    row["phase_context_goodput_capacity_mean"] = (context.get("goodput_capacity") or {}).get("mean")
    row["phase_context_smooth_cost_mean"] = (context.get("smooth_cost") or {}).get("mean")
    row["phase_context_progress_debt_mean"] = (context.get("progress_debt") or {}).get("mean")
    row["phase_context_pressure_injection_prefill_mean"] = (
        context.get("pressure_injection_prefill") or {}
    ).get("mean")
    row["phase_context_pressure_decode_hard_mean"] = (context.get("pressure_decode_hard") or {}).get("mean")
    row["phase_context_pressure_kv_hard_mean"] = (context.get("pressure_kv_hard") or {}).get("mean")
    row["phase_context_rho_prefill_mean"] = (context.get("rho_prefill") or {}).get("mean")
    row["phase_context_rho_memory_mean"] = (context.get("rho_memory") or {}).get("mean")
    row["phase_context_rho_swap_mean"] = (context.get("rho_swap") or {}).get("mean")
    row["phase_context_rho_scan_mean"] = (context.get("rho_scan") or {}).get("mean")
    row["phase_context_rho_hard_mean"] = (context.get("rho_hard") or {}).get("mean")
    row["phase_context_pressure_first_mean"] = (context.get("pressure_first") or {}).get("mean")
    row["phase_context_selected_mean"] = (context.get("selected") or {}).get("mean")
    row["phase_context_selected_prefill_blocks_mean"] = (context.get("selected_prefill_blocks") or {}).get("mean")
    row["phase_context_token_fill_mean"] = (context.get("token_fill") or {}).get("mean")
    row["phase_context_pad_waste_mean"] = (context.get("pad_waste") or {}).get("mean")
    row["phase_context_block_risk_mean"] = (context.get("block_risk") or {}).get("mean")
    row["phase_context_forced_oldest"] = context.get("forced_oldest")
    row["phase_context_protected_triggered"] = context.get("protected_triggered")
    row["phase_context_protected_selected"] = context.get("protected_selected")
    row["phase_context_protected_dispatch_ratio"] = context.get("protected_dispatch_ratio")
    row["phase_context_protected_feasible_triggers"] = context.get("protected_feasible_triggers")
    row["phase_context_protected_feasible_dispatch_ratio"] = context.get("protected_feasible_dispatch_ratio")
    row["phase_context_protected_forced_single"] = context.get("protected_forced_single")
    row["phase_context_protected_blocked"] = context.get("protected_blocked")
    row["phase_context_protected_bypassed"] = context.get("protected_bypassed")
    row["phase_context_protected_bypass_ratio"] = context.get("protected_bypass_ratio")
    row["phase_context_protected_wait_p99"] = (context.get("protected_wait_s") or {}).get("p99")
    row["phase_context_waiting_max_wait_max"] = (context.get("waiting_max_wait_s") or {}).get("max")
    row["phase_context_long_prompt_waiting_mean"] = (context.get("waiting_long_prompt_count") or {}).get("mean")
    row["phase_context_long_prompt_max_wait_max"] = (context.get("waiting_long_prompt_max_wait_s") or {}).get("max")
    row["phase_context_candidate_max_wait_p99"] = (context.get("candidate_max_wait_s") or {}).get("p99")
    row["phase_context_selected_max_wait_p99"] = (context.get("selected_max_wait_s") or {}).get("p99")
    row["phase_context_selected_long_prompt_mean"] = (context.get("selected_long_prompt_count") or {}).get("mean")
    row["phase_context_decode_snapshot_used"] = context.get("decode_snapshot_used")
    row["phase_context_decode_snapshot_stale"] = context.get("decode_snapshot_stale")
    row["phase_context_decode_snapshot_age_mean"] = (context.get("decode_snapshot_age_s") or {}).get("mean")
    return row


def write_markdown(rows, output_path: Path):
    columns = [
        "label",
        "policy",
        "request_rate",
        "completed",
        "failed",
        "throughput_completed_req_s",
        "throughput_goodput_req_s",
        "throughput_per_gpu_goodput_req_s",
        "slo_attainment_submitted",
        "ttft_s_median",
        "ttft_s_p75",
        "ttft_s_p99",
        "tpot_s_median",
        "tpot_s_p75",
        "tpot_s_p99",
        "latency_s_median",
        "latency_s_p99",
        "phase_decode_swap_ins",
        "phase_decode_evictions",
        "phase_decode_scan_mean",
        "phase_decode_selected_mean",
        "phase_decode_starved_ready",
        "phase_decode_starved_selected",
        "phase_decode_starved_admission_ratio_mean",
        "phase_decode_first_token_ready",
        "phase_decode_first_token_selected",
        "phase_decode_first_token_admission_ratio_mean",
        "phase_decode_handoff_debt_ready",
        "phase_decode_handoff_debt_selected",
        "phase_decode_handoff_debt_admission_ratio_mean",
        "phase_decode_handoff_debt_discount_mean",
        "phase_decode_handoff_debt_selected_discount_mean",
        "phase_decode_handoff_debt_weight_mean",
        "phase_decode_budget_ttft_debt_weight_mean",
        "phase_decode_effective_handoff_debt_weight_mean",
        "phase_decode_handoff_debt_pressure_mean",
        "phase_decode_kas_intensity_mean",
        "phase_decode_selected_effective_kas_intensity_mean",
        "phase_decode_fcfs_fallback_active",
        "phase_decode_fcfs_fallback_threshold_mean",
        "phase_decode_short_output_fcfs_threshold_mean",
        "phase_decode_long_output_full_kas_threshold_mean",
        "phase_decode_avg_target_output_len_mean",
        "phase_decode_budget_decode_utility_intensity_mean",
        "phase_decode_decode_utility_intensity_mean",
        "phase_decode_regime_counts",
        "phase_decode_regime_switch_rate_mean",
        "phase_decode_controller_ttft_debt_weight_mean",
        "phase_decode_kas_adaptive_intensity",
        "phase_decode_prefill_gate_active",
        "phase_decode_prefill_gate_pressure_mean",
        "phase_decode_prefill_gate_hard_mean",
        "phase_decode_policy_skipped",
        "phase_decode_infeasible_rounds",
        "phase_decode_max_skip_max",
        "phase_decode_max_infeasible_max",
        "phase_decode_pressure_overshoot_mean",
        "phase_decode_pressure_potential_mean",
        "phase_decode_pressure_injection_swap_mean",
        "phase_decode_pressure_decode_hard_mean",
        "phase_decode_pressure_kv_hard_mean",
        "phase_decode_pressure_first_mean",
        "phase_decode_rho_memory_mean",
        "phase_decode_rho_swap_mean",
        "phase_decode_rho_hard_mean",
        "phase_decode_swap_byte_budget_mean",
        "phase_decode_swap_byte_budget_ratio_mean",
        "phase_context_prefill_budget_mean",
        "phase_context_prefill_budget_ratio_mean",
        "phase_context_prefill_block_margin_mean",
        "phase_context_decode_utility_intensity_mean",
        "phase_context_controller_ttft_debt_weight_mean",
        "phase_context_regime_counts",
        "phase_context_regime_switch_rate_mean",
        "phase_context_mode_switch_rate_mean",
        "phase_context_budget_delta_mean",
        "phase_context_pressure_overshoot_mean",
        "phase_context_pressure_potential_mean",
        "phase_context_pressure_injection_prefill_mean",
        "phase_context_pressure_decode_hard_mean",
        "phase_context_pressure_kv_hard_mean",
        "phase_context_pressure_first_mean",
        "phase_context_rho_prefill_mean",
        "phase_context_rho_memory_mean",
        "phase_context_rho_hard_mean",
        "phase_context_token_fill_mean",
        "phase_context_pad_waste_mean",
        "phase_context_block_risk_mean",
        "phase_context_protected_triggered",
        "phase_context_protected_selected",
        "phase_context_protected_dispatch_ratio",
        "phase_context_protected_feasible_dispatch_ratio",
        "phase_context_protected_feasible_triggers",
        "phase_context_protected_forced_single",
        "phase_context_protected_blocked",
        "phase_context_protected_bypassed",
        "phase_context_protected_bypass_ratio",
        "phase_context_protected_wait_p99",
        "phase_context_waiting_max_wait_max",
        "phase_context_long_prompt_waiting_mean",
        "phase_context_long_prompt_max_wait_max",
        "phase_context_selected_long_prompt_mean",
        "phase_context_decode_snapshot_used",
    ]
    with output_path.open("w") as f:
        f.write("| " + " | ".join(columns) + " |\n")
        f.write("|" + "|".join(["---"] * len(columns)) + "|\n")
        for row in rows:
            values = []
            for column in columns:
                value = row.get(column)
                if isinstance(value, float):
                    value = f"{value:.6g}"
                values.append("" if value is None else str(value))
            f.write("| " + " | ".join(values) + " |\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", help="summary json files or directories")
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--output-md")
    args = parser.parse_args()

    paths = []
    for item in args.inputs:
        path = Path(item)
        if path.is_dir():
            paths.extend(sorted(path.rglob("*.summary.json")))
        else:
            paths.append(path)
    rows = [flatten_summary(path) for path in paths]
    rows.sort(key=lambda row: (str(row.get("policy")), float(row.get("request_rate") or 0), str(row.get("label"))))

    output_csv = Path(args.output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else []
    with output_csv.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    if args.output_md:
        output_md = Path(args.output_md)
        output_md.parent.mkdir(parents=True, exist_ok=True)
        write_markdown(rows, output_md)

    print(f"Collected {len(rows)} summaries")
    print(f"CSV: {output_csv}")
    if args.output_md:
        print(f"Markdown: {args.output_md}")


if __name__ == "__main__":
    main()
