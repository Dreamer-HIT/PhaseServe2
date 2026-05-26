#!/usr/bin/env python3
import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path


METRICS = [
    "goodput_req_s",
    "throughput_req_s",
    "throughput_completed_req_s",
    "throughput_generated_output_tokens_s",
    "throughput_total_generated_tokens_s",
    "slo_attainment_submitted",
    "ttft_p50",
    "ttft_p90",
    "ttft_p95",
    "ttft_p99",
    "tpot_p50",
    "tpot_p90",
    "tpot_p95",
    "tpot_p99",
    "latency_p99",
]

BUCKET_METRICS = [
    "submitted",
    "completed",
    "failed",
    "goodput",
    "slo_attainment_submitted",
    "ttft_p50",
    "ttft_p90",
    "ttft_p95",
    "ttft_p99",
    "tpot_p50",
    "tpot_p90",
    "tpot_p95",
    "tpot_p99",
    "latency_p99",
    "context_queue_p90",
    "context_queue_p99",
    "context_exec_p90",
    "context_exec_p99",
    "decode_queue_p90",
    "decode_queue_p99",
    "decode_exec_p90",
    "decode_exec_p99",
]


def mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def std(values):
    values = [v for v in values if v is not None]
    if len(values) <= 1:
        return 0.0 if values else None
    mu = mean(values)
    return math.sqrt(sum((v - mu) ** 2 for v in values) / (len(values) - 1))


def stderr(values):
    values = [v for v in values if v is not None]
    if not values:
        return None
    return std(values) / math.sqrt(len(values))


def load_summary(path: Path):
    data = json.loads(path.read_text())
    metadata = data.get("metadata", {})
    throughput = data.get("throughput") or {}
    phase_components = (data.get("phase_metrics") or {}).get("components") or {}
    decode = phase_components.get("decode") or {}
    context = phase_components.get("context") or {}
    return {
        "path": str(path),
        "policy": metadata.get("policy"),
        "rate": float(metadata.get("request_rate") or 0.0),
        "seed": int(metadata.get("seed") or 0),
        "completed": data.get("completed"),
        "failed": data.get("failed"),
        "goodput_req_s": data.get("goodput_req_s"),
        "throughput_req_s": data.get("throughput_req_s"),
        "throughput_completed_req_s": throughput.get("completed_req_s"),
        "throughput_generated_output_tokens_s": throughput.get("generated_output_tokens_s"),
        "throughput_total_generated_tokens_s": throughput.get("total_generated_tokens_s"),
        "slo_attainment_submitted": data.get("slo_attainment_submitted"),
        "ttft_p50": (data.get("ttft_s") or {}).get("p50"),
        "ttft_p90": (data.get("ttft_s") or {}).get("p90"),
        "ttft_p95": (data.get("ttft_s") or {}).get("p95"),
        "ttft_p99": (data.get("ttft_s") or {}).get("p99"),
        "tpot_p50": (data.get("tpot_s") or {}).get("p50"),
        "tpot_p90": (data.get("tpot_s") or {}).get("p90"),
        "tpot_p95": (data.get("tpot_s") or {}).get("p95"),
        "tpot_p99": (data.get("tpot_s") or {}).get("p99"),
        "latency_p99": (data.get("latency_s") or {}).get("p99"),
        "phase_decode_swap_ins": decode.get("swap_ins"),
        "phase_decode_evictions": decode.get("eviction_count"),
        "phase_decode_scan_mean": (decode.get("decode_scan_limit") or {}).get("mean"),
        "phase_decode_selected_mean": (decode.get("selected") or {}).get("mean"),
        "phase_decode_mode_switch_rate_mean": (decode.get("controller_mode_switch_rate") or {}).get("mean"),
        "phase_decode_budget_delta_mean": (decode.get("controller_budget_delta") or {}).get("mean"),
        "phase_context_prefill_budget_mean": (context.get("prefill_token_budget") or {}).get("mean"),
        "phase_context_prefill_budget_ratio_mean": (context.get("prefill_budget_ratio") or {}).get("mean"),
        "phase_context_mode_switch_rate_mean": (context.get("controller_mode_switch_rate") or {}).get("mean"),
        "phase_context_budget_delta_mean": (context.get("controller_budget_delta") or {}).get("mean"),
        "phase_context_decode_snapshot_used": context.get("decode_snapshot_used"),
        "phase_context_decode_snapshot_stale": context.get("decode_snapshot_stale"),
        "phase_context_decode_snapshot_age_mean": (context.get("decode_snapshot_age_s") or {}).get("mean"),
    }


def collect_summary_paths(inputs):
    paths = []
    for item in inputs:
        path = Path(item)
        if path.is_dir():
            paths.extend(path.rglob("*.summary.json"))
        else:
            paths.append(path)
    return sorted(path for path in paths if path.name.endswith(".summary.json"))


def collect_rows(inputs):
    return [load_summary(path) for path in collect_summary_paths(inputs)]


def stat_value(stats, stat):
    return (stats or {}).get(stat)


def load_bucket_rows(path: Path):
    data = json.loads(path.read_text())
    metadata = data.get("metadata", {})
    rows = []
    for bucket_type, buckets in (data.get("buckets") or {}).items():
        for bucket, summary in (buckets or {}).items():
            row = {
                "path": str(path),
                "policy": metadata.get("policy"),
                "rate": float(metadata.get("request_rate") or 0.0),
                "seed": int(metadata.get("seed") or 0),
                "bucket_type": bucket_type,
                "bucket": bucket,
                "submitted": summary.get("submitted", summary.get("count")),
                "completed": summary.get("completed", summary.get("count")),
                "failed": summary.get("failed"),
                "goodput": summary.get("goodput"),
                "slo_attainment_submitted": summary.get("slo_attainment_submitted"),
            }
            for metric in [
                "ttft_s",
                "tpot_s",
                "latency_s",
                "context_queue_s",
                "context_exec_s",
                "decode_queue_s",
                "decode_exec_s",
            ]:
                prefix = metric[:-2] if metric.endswith("_s") else metric
                stats = summary.get(metric) or {}
                row[f"{prefix}_p50"] = stat_value(stats, "p50")
                row[f"{prefix}_p90"] = stat_value(stats, "p90")
                row[f"{prefix}_p95"] = stat_value(stats, "p95")
                row[f"{prefix}_p99"] = stat_value(stats, "p99")
            rows.append(row)
    return rows


def collect_bucket_rows(inputs):
    rows = []
    for path in collect_summary_paths(inputs):
        rows.extend(load_bucket_rows(path))
    return rows


def grouped_rows(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[(row["rate"], row["policy"])].append(row)

    out = []
    for (rate, policy), group in sorted(groups.items()):
        entry = {
            "rate": rate,
            "policy": policy,
            "n": len(group),
            "seeds": ",".join(str(r["seed"]) for r in sorted(group, key=lambda x: x["seed"])),
        }
        for metric in METRICS:
            values = [r.get(metric) for r in group]
            entry[f"{metric}_mean"] = mean(values)
            entry[f"{metric}_std"] = std(values)
            entry[f"{metric}_stderr"] = stderr(values)
        out.append(entry)
    return out


def paired_delta_rows(rows, baseline_policy):
    by_key = defaultdict(dict)
    for row in rows:
        by_key[(row["rate"], row["seed"])][row["policy"]] = row
    out = []
    for (rate, seed), pair in sorted(by_key.items()):
        baseline = pair.get(baseline_policy)
        if baseline is None:
            continue
        for policy, target in sorted(pair.items()):
            if policy == baseline_policy:
                continue
            entry = {"rate": rate, "seed": seed, "policy": policy, "baseline": baseline_policy}
            for metric in METRICS:
                target_value = target.get(metric)
                baseline_value = baseline.get(metric)
                entry[f"{metric}_delta"] = (
                    None if target_value is None or baseline_value is None else target_value - baseline_value
                )
                entry[f"{metric}_ratio"] = (
                    None if target_value is None or baseline_value in [None, 0] else target_value / baseline_value
                )
            out.append(entry)
    return out


def summarize_paired(deltas):
    groups = defaultdict(list)
    for row in deltas:
        groups[(row["rate"], row["policy"], row["baseline"])].append(row)
    out = []
    for (rate, policy, baseline), group in sorted(groups.items()):
        entry = {"rate": rate, "policy": policy, "baseline": baseline, "n": len(group)}
        for metric in METRICS:
            values = [r.get(f"{metric}_delta") for r in group]
            ratios = [r.get(f"{metric}_ratio") for r in group]
            entry[f"{metric}_delta_mean"] = mean(values)
            entry[f"{metric}_delta_std"] = std(values)
            entry[f"{metric}_ratio_mean"] = mean(ratios)
        out.append(entry)
    return out


def grouped_bucket_rows(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[(row["bucket_type"], row["bucket"], row["rate"], row["policy"])].append(row)

    out = []
    for (bucket_type, bucket, rate, policy), group in sorted(groups.items()):
        entry = {
            "bucket_type": bucket_type,
            "bucket": bucket,
            "rate": rate,
            "policy": policy,
            "n": len(group),
            "seeds": ",".join(str(r["seed"]) for r in sorted(group, key=lambda x: x["seed"])),
        }
        for metric in BUCKET_METRICS:
            values = [r.get(metric) for r in group]
            entry[f"{metric}_mean"] = mean(values)
            entry[f"{metric}_std"] = std(values)
            entry[f"{metric}_stderr"] = stderr(values)
        out.append(entry)
    return out


def paired_bucket_delta_rows(rows, baseline_policy):
    by_key = defaultdict(dict)
    for row in rows:
        by_key[(row["bucket_type"], row["bucket"], row["rate"], row["seed"])][row["policy"]] = row
    out = []
    for (bucket_type, bucket, rate, seed), pair in sorted(by_key.items()):
        baseline = pair.get(baseline_policy)
        if baseline is None:
            continue
        for policy, target in sorted(pair.items()):
            if policy == baseline_policy:
                continue
            entry = {
                "bucket_type": bucket_type,
                "bucket": bucket,
                "rate": rate,
                "seed": seed,
                "policy": policy,
                "baseline": baseline_policy,
            }
            for metric in BUCKET_METRICS:
                target_value = target.get(metric)
                baseline_value = baseline.get(metric)
                entry[f"{metric}_delta"] = (
                    None if target_value is None or baseline_value is None else target_value - baseline_value
                )
                entry[f"{metric}_ratio"] = (
                    None if target_value is None or baseline_value in [None, 0] else target_value / baseline_value
                )
            out.append(entry)
    return out


def summarize_bucket_paired(deltas):
    groups = defaultdict(list)
    for row in deltas:
        groups[(row["bucket_type"], row["bucket"], row["rate"], row["policy"], row["baseline"])].append(row)
    out = []
    for (bucket_type, bucket, rate, policy, baseline), group in sorted(groups.items()):
        entry = {
            "bucket_type": bucket_type,
            "bucket": bucket,
            "rate": rate,
            "policy": policy,
            "baseline": baseline,
            "n": len(group),
        }
        for metric in BUCKET_METRICS:
            values = [r.get(f"{metric}_delta") for r in group]
            ratios = [r.get(f"{metric}_ratio") for r in group]
            entry[f"{metric}_delta_mean"] = mean(values)
            entry[f"{metric}_delta_std"] = std(values)
            entry[f"{metric}_ratio_mean"] = mean(ratios)
        out.append(entry)
    return out


def write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row.keys()})
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def fmt(value):
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def write_markdown(path: Path, grouped, paired):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        f.write("# Sweep Summary\n\n")
        f.write("## Grouped Means\n\n")
        cols = [
            "rate", "policy", "n",
            "goodput_req_s_mean", "slo_attainment_submitted_mean",
            "throughput_generated_output_tokens_s_mean",
            "ttft_p50_mean", "ttft_p90_mean", "ttft_p99_mean",
            "tpot_p50_mean", "tpot_p90_mean", "tpot_p99_mean",
            "goodput_req_s_std", "tpot_p99_std",
        ]
        f.write("| " + " | ".join(cols) + " |\n")
        f.write("|" + "|".join(["---"] * len(cols)) + "|\n")
        for row in grouped:
            f.write("| " + " | ".join(fmt(row.get(c)) for c in cols) + " |\n")
        f.write("\n## Paired Policy Minus Baseline\n\n")
        cols = [
            "rate", "policy", "baseline", "n",
            "goodput_req_s_delta_mean", "slo_attainment_submitted_delta_mean",
            "throughput_generated_output_tokens_s_ratio_mean",
            "ttft_p90_delta_mean", "ttft_p99_delta_mean",
            "tpot_p90_delta_mean", "tpot_p99_delta_mean",
            "goodput_req_s_ratio_mean", "tpot_p90_ratio_mean", "tpot_p99_ratio_mean",
        ]
        f.write("| " + " | ".join(cols) + " |\n")
        f.write("|" + "|".join(["---"] * len(cols)) + "|\n")
        for row in paired:
            f.write("| " + " | ".join(fmt(row.get(c)) for c in cols) + " |\n")


def write_bucket_markdown(path: Path, grouped, paired):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        f.write("# Bucket Sweep Summary\n\n")
        f.write(
            "Prompt buckets are intended to test BPS/TTFT effects; "
            "output buckets are intended to test KAS/TPOT effects.\n\n"
        )
        f.write("## Bucket Grouped Means\n\n")
        cols = [
            "bucket_type", "bucket", "rate", "policy", "n",
            "completed_mean", "slo_attainment_submitted_mean",
            "ttft_p50_mean", "ttft_p90_mean", "ttft_p99_mean",
            "tpot_p50_mean", "tpot_p90_mean", "tpot_p99_mean",
            "context_queue_p90_mean", "decode_queue_p90_mean",
        ]
        f.write("| " + " | ".join(cols) + " |\n")
        f.write("|" + "|".join(["---"] * len(cols)) + "|\n")
        for row in grouped:
            f.write("| " + " | ".join(fmt(row.get(c)) for c in cols) + " |\n")

        f.write("\n## Bucket Paired Policy Minus Baseline\n\n")
        cols = [
            "bucket_type", "bucket", "rate", "policy", "baseline", "n",
            "slo_attainment_submitted_delta_mean",
            "ttft_p90_delta_mean", "ttft_p99_delta_mean",
            "tpot_p90_delta_mean", "tpot_p99_delta_mean",
            "ttft_p99_ratio_mean", "tpot_p99_ratio_mean",
        ]
        f.write("| " + " | ".join(cols) + " |\n")
        f.write("|" + "|".join(["---"] * len(cols)) + "|\n")
        for row in paired:
            f.write("| " + " | ".join(fmt(row.get(c)) for c in cols) + " |\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+")
    parser.add_argument("--output-prefix", required=True)
    parser.add_argument("--baseline-policy", default="fcfs")
    args = parser.parse_args()

    rows = collect_rows(args.inputs)
    grouped = grouped_rows(rows)
    deltas = paired_delta_rows(rows, args.baseline_policy)
    paired = summarize_paired(deltas)
    bucket_rows = collect_bucket_rows(args.inputs)
    bucket_grouped = grouped_bucket_rows(bucket_rows)
    bucket_deltas = paired_bucket_delta_rows(bucket_rows, args.baseline_policy)
    bucket_paired = summarize_bucket_paired(bucket_deltas)

    prefix = Path(args.output_prefix)
    write_csv(prefix.with_suffix(".runs.csv"), rows)
    write_csv(prefix.with_suffix(".grouped.csv"), grouped)
    write_csv(prefix.with_suffix(".paired.csv"), deltas)
    write_csv(prefix.with_suffix(".paired_summary.csv"), paired)
    write_markdown(prefix.with_suffix(".md"), grouped, paired)
    write_csv(prefix.with_suffix(".bucket_runs.csv"), bucket_rows)
    write_csv(prefix.with_suffix(".bucket_grouped.csv"), bucket_grouped)
    write_csv(prefix.with_suffix(".bucket_paired.csv"), bucket_deltas)
    write_csv(prefix.with_suffix(".bucket_paired_summary.csv"), bucket_paired)
    write_bucket_markdown(prefix.with_suffix(".bucket.md"), bucket_grouped, bucket_paired)
    print(f"Runs: {len(rows)}")
    print(f"Bucket rows: {len(bucket_rows)}")
    print(f"Output prefix: {prefix}")


if __name__ == "__main__":
    main()
