#!/usr/bin/env python3
import argparse
import csv
import json
from pathlib import Path


METRIC_FIELDS = [
    ("latency_s", "median"),
    ("latency_s", "p90"),
    ("latency_s", "p95"),
    ("latency_s", "p99"),
    ("ttft_s", "median"),
    ("ttft_s", "p90"),
    ("ttft_s", "p95"),
    ("ttft_s", "p99"),
    ("tpot_s", "median"),
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
    row["phase_decode_max_skip_max"] = (decode.get("max_consecutive_skips") or {}).get("max")
    row["phase_decode_mode_switch_rate_mean"] = (decode.get("controller_mode_switch_rate") or {}).get("mean")
    row["phase_decode_budget_delta_mean"] = (decode.get("controller_budget_delta") or {}).get("mean")
    row["phase_decode_pressure_overshoot_mean"] = (decode.get("pressure_overshoot") or {}).get("mean")
    row["phase_decode_rho_prefill_mean"] = (decode.get("rho_prefill") or {}).get("mean")
    row["phase_decode_rho_memory_mean"] = (decode.get("rho_memory") or {}).get("mean")
    row["phase_decode_rho_swap_mean"] = (decode.get("rho_swap") or {}).get("mean")
    row["phase_decode_rho_scan_mean"] = (decode.get("rho_scan") or {}).get("mean")
    row["phase_context_prefill_budget_mean"] = (context.get("prefill_token_budget") or {}).get("mean")
    row["phase_context_prefill_budget_ratio_mean"] = (context.get("prefill_budget_ratio") or {}).get("mean")
    row["phase_context_prefill_block_margin_mean"] = (context.get("prefill_block_margin") or {}).get("mean")
    row["phase_context_mode_switch_rate_mean"] = (context.get("controller_mode_switch_rate") or {}).get("mean")
    row["phase_context_budget_delta_mean"] = (context.get("controller_budget_delta") or {}).get("mean")
    row["phase_context_pressure_overshoot_mean"] = (context.get("pressure_overshoot") or {}).get("mean")
    row["phase_context_rho_prefill_mean"] = (context.get("rho_prefill") or {}).get("mean")
    row["phase_context_rho_memory_mean"] = (context.get("rho_memory") or {}).get("mean")
    row["phase_context_rho_swap_mean"] = (context.get("rho_swap") or {}).get("mean")
    row["phase_context_rho_scan_mean"] = (context.get("rho_scan") or {}).get("mean")
    row["phase_context_selected_mean"] = (context.get("selected") or {}).get("mean")
    row["phase_context_forced_oldest"] = context.get("forced_oldest")
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
        "ttft_s_p99",
        "tpot_s_median",
        "tpot_s_p99",
        "latency_s_median",
        "latency_s_p99",
        "phase_decode_swap_ins",
        "phase_decode_evictions",
        "phase_decode_scan_mean",
        "phase_decode_selected_mean",
        "phase_decode_pressure_overshoot_mean",
        "phase_decode_rho_memory_mean",
        "phase_decode_rho_swap_mean",
        "phase_context_prefill_budget_mean",
        "phase_context_prefill_budget_ratio_mean",
        "phase_context_prefill_block_margin_mean",
        "phase_context_mode_switch_rate_mean",
        "phase_context_budget_delta_mean",
        "phase_context_pressure_overshoot_mean",
        "phase_context_rho_prefill_mean",
        "phase_context_rho_memory_mean",
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
