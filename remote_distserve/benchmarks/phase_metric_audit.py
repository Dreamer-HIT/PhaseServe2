#!/usr/bin/env python3
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


DEFAULT_METRICS = [
    "ttft_p50",
    "ttft_p75",
    "ttft_p90",
    "ttft_p95",
    "ttft_p99",
    "tpot_p50",
    "tpot_p75",
    "tpot_p90",
    "tpot_p95",
    "tpot_p99",
]


def collect_summary_paths(inputs):
    paths = []
    for item in inputs:
        path = Path(item)
        if path.is_dir():
            paths.extend(path.rglob("*.summary.json"))
        else:
            paths.append(path)
    return sorted(path for path in paths if path.name.endswith(".summary.json"))


def metric_value(summary, metric):
    group, pct = metric.split("_", 1)
    key = f"{group}_s"
    return (summary.get(key) or {}).get(pct)


def load_rows(inputs, metrics):
    rows = []
    for path in collect_summary_paths(inputs):
        data = json.loads(path.read_text())
        metadata = data.get("metadata", {})
        row = {
            "path": str(path),
            "policy": metadata.get("policy"),
            "rate": float(metadata.get("request_rate") or 0.0),
            "seed": int(metadata.get("seed") or 0),
            "completed": data.get("completed"),
            "failed": data.get("failed"),
            "slo_attainment_submitted": data.get("slo_attainment_submitted"),
            "goodput_req_s": data.get("goodput_req_s"),
            "output_tok_s": (data.get("throughput") or {}).get("generated_output_tokens_s"),
        }
        for metric in metrics:
            row[metric] = metric_value(data, metric)
        rows.append(row)
    return rows


def mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def ratio_rows(rows, metrics, baseline_policy):
    by_key = defaultdict(dict)
    for row in rows:
        by_key[(row["rate"], row["seed"])][row["policy"]] = row
    out = []
    for (rate, seed), pair in sorted(by_key.items()):
        baseline = pair.get(baseline_policy)
        if baseline is None:
            continue
        for policy, row in sorted(pair.items()):
            if policy == baseline_policy:
                continue
            for metric in metrics:
                target_value = row.get(metric)
                baseline_value = baseline.get(metric)
                ratio = (
                    None
                    if target_value is None or baseline_value in [None, 0]
                    else target_value / baseline_value
                )
                out.append({
                    "rate": rate,
                    "seed": seed,
                    "policy": policy,
                    "baseline": baseline_policy,
                    "metric": metric,
                    "target_value": target_value,
                    "baseline_value": baseline_value,
                    "delta": (
                        None
                        if target_value is None or baseline_value is None
                        else target_value - baseline_value
                    ),
                    "ratio": ratio,
                    "improved": ratio is not None and ratio < 1.0,
                })
    return out


def rate_summary(ratios, min_seed_fraction):
    groups = defaultdict(list)
    for row in ratios:
        groups[(row["policy"], row["metric"], row["rate"])].append(row)
    out = []
    for (policy, metric, rate), group in sorted(groups.items()):
        valid = [r for r in group if r["ratio"] is not None]
        improved = [r for r in valid if r["improved"]]
        seed_fraction = len(improved) / len(valid) if valid else None
        mean_ratio = mean([r["ratio"] for r in valid])
        out.append({
            "policy": policy,
            "metric": metric,
            "rate": rate,
            "n": len(valid),
            "seeds_improved": len(improved),
            "seed_fraction": seed_fraction,
            "mean_ratio": mean_ratio,
            "mean_improvement_pct": (
                None if mean_ratio is None else (1.0 - mean_ratio) * 100.0
            ),
            "candidate": (
                mean_ratio is not None
                and mean_ratio < 1.0
                and seed_fraction is not None
                and seed_fraction >= min_seed_fraction
            ),
        })
    return out


def candidate_windows(rate_rows, min_len):
    groups = defaultdict(list)
    for row in rate_rows:
        groups[(row["policy"], row["metric"])].append(row)
    windows = []
    for (policy, metric), rows in sorted(groups.items()):
        rows = sorted(rows, key=lambda r: r["rate"])
        current = []
        for row in rows:
            if row["candidate"]:
                current.append(row)
            else:
                if len(current) >= min_len:
                    windows.append(make_window(policy, metric, current))
                current = []
        if len(current) >= min_len:
            windows.append(make_window(policy, metric, current))
    return windows


def make_window(policy, metric, rows):
    ratios = [r["mean_ratio"] for r in rows]
    return {
        "policy": policy,
        "metric": metric,
        "start_rate": rows[0]["rate"],
        "end_rate": rows[-1]["rate"],
        "num_rates": len(rows),
        "rates": ",".join(str(r["rate"]) for r in rows),
        "mean_ratio": mean(ratios),
        "best_ratio": min(ratios),
        "mean_improvement_pct": mean([r["mean_improvement_pct"] for r in rows]),
        "min_seed_fraction": min(r["seed_fraction"] for r in rows),
    }


def write_csv(path, rows):
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


def write_markdown(path, rate_rows, windows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        f.write("# Metric Audit\n\n")
        f.write("Latency ratios are target policy divided by baseline; lower is better.\n\n")
        f.write("## Candidate Windows\n\n")
        cols = [
            "policy", "metric", "start_rate", "end_rate", "num_rates",
            "rates", "mean_ratio", "best_ratio", "mean_improvement_pct",
            "min_seed_fraction",
        ]
        f.write("| " + " | ".join(cols) + " |\n")
        f.write("|" + "|".join(["---"] * len(cols)) + "|\n")
        for row in windows:
            f.write("| " + " | ".join(fmt(row.get(c)) for c in cols) + " |\n")
        f.write("\n## Per-Rate Summary\n\n")
        cols = [
            "policy", "metric", "rate", "n", "seeds_improved",
            "seed_fraction", "mean_ratio", "mean_improvement_pct", "candidate",
        ]
        f.write("| " + " | ".join(cols) + " |\n")
        f.write("|" + "|".join(["---"] * len(cols)) + "|\n")
        for row in rate_rows:
            f.write("| " + " | ".join(fmt(row.get(c)) for c in cols) + " |\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+")
    parser.add_argument("--baseline-policy", default="fcfs")
    parser.add_argument("--metrics", default=",".join(DEFAULT_METRICS))
    parser.add_argument("--min-seed-fraction", type=float, default=1.0)
    parser.add_argument("--min-window-len", type=int, default=2)
    parser.add_argument("--output-prefix", required=True)
    args = parser.parse_args()

    metrics = [item.strip() for item in args.metrics.split(",") if item.strip()]
    rows = load_rows(args.inputs, metrics)
    ratios = ratio_rows(rows, metrics, args.baseline_policy)
    rate_rows = rate_summary(ratios, args.min_seed_fraction)
    windows = candidate_windows(rate_rows, args.min_window_len)

    prefix = Path(args.output_prefix)
    write_csv(prefix.with_suffix(".runs.csv"), rows)
    write_csv(prefix.with_suffix(".ratios.csv"), ratios)
    write_csv(prefix.with_suffix(".rate_summary.csv"), rate_rows)
    write_csv(prefix.with_suffix(".windows.csv"), windows)
    write_markdown(prefix.with_suffix(".md"), rate_rows, windows)
    print(f"Runs: {len(rows)}")
    print(f"Ratio rows: {len(ratios)}")
    print(f"Candidate windows: {len(windows)}")
    print(f"Output prefix: {prefix}")


if __name__ == "__main__":
    main()
