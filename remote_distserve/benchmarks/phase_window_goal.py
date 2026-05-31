#!/usr/bin/env python3
import argparse
import json
from collections import defaultdict
from pathlib import Path


PERCENTILES = [
    ("median", "p50"),
    ("p90", "p90"),
    ("p95", "p95"),
    ("p99", "p99"),
]


def iter_summary_paths(inputs):
    for item in inputs:
        path = Path(item)
        if path.is_dir():
            yield from sorted(path.rglob("*.summary.json"))
        elif path.name.endswith(".summary.json"):
            yield path


def metric(summary, group, stat):
    return (summary.get(group) or {}).get(stat)


def load_rows(inputs):
    rows = []
    for path in iter_summary_paths(inputs):
        data = json.loads(path.read_text())
        meta = data.get("metadata") or {}
        policy = meta.get("policy")
        if policy not in {"fcfs", "phase"}:
            continue
        row = {
            "path": str(path),
            "policy": policy,
            "rate": float(meta.get("request_rate")),
            "seed": meta.get("seed", 0),
            "num_gpus": int(meta.get("num_gpus") or 2),
            "completed": data.get("completed"),
            "failed": data.get("failed"),
        }
        for stat, label in PERCENTILES:
            row[f"ttft_{label}"] = metric(data, "ttft_s", stat)
            row[f"tpot_{label}"] = metric(data, "tpot_s", stat)
        rows.append(row)
    return rows


def improvement_pct(base, new):
    if base in (None, 0) or new is None:
        return None
    return (1.0 - new / base) * 100.0


def fmt_imps(imps, keys):
    return "/".join("NA" if imps[k] is None else f"{imps[k]:.1f}" for k in keys)


def build_rows(rows, threshold):
    grouped = {}
    for row in rows:
        key = (row["seed"], row["rate"], row["policy"])
        grouped[key] = row

    out = []
    for seed in sorted({row["seed"] for row in rows}):
        rates = sorted({row["rate"] for row in rows if row["seed"] == seed})
        for rate in rates:
            base = grouped.get((seed, rate, "fcfs"))
            phase = grouped.get((seed, rate, "phase"))
            if not base or not phase:
                continue
            num_gpus = phase.get("num_gpus") or base.get("num_gpus") or 2
            imps = {}
            for prefix in ["ttft", "tpot"]:
                for _, label in PERCENTILES:
                    key = f"{prefix}_{label}"
                    imps[key] = improvement_pct(base.get(key), phase.get(key))
            ttft_keys = [f"ttft_{label}" for _, label in PERCENTILES]
            tpot_keys = [f"tpot_{label}" for _, label in PERCENTILES]
            ttft_wins = sum(1 for key in ttft_keys if imps[key] is not None and imps[key] >= threshold)
            tpot_wins = sum(1 for key in tpot_keys if imps[key] is not None and imps[key] >= threshold)
            out.append({
                "seed": seed,
                "global_rate": rate,
                "per_gpu_rate": rate / num_gpus,
                "ttft_wins": ttft_wins,
                "tpot_wins": tpot_wins,
                "pass": ttft_wins >= 2 and tpot_wins >= 2,
                "ttft_imps": fmt_imps(imps, ttft_keys),
                "tpot_imps": fmt_imps(imps, tpot_keys),
            })
    return out


def find_windows(rows, window_len, step):
    by_seed = defaultdict(set)
    for row in rows:
        if row["pass"]:
            by_seed[row["seed"]].add(round(row["per_gpu_rate"], 6))

    windows = defaultdict(list)
    n_points = int(round(window_len / step)) + 1
    for seed, points in by_seed.items():
        for start in sorted(points):
            wanted = [round(start + i * step, 6) for i in range(n_points)]
            if all(point in points for point in wanted):
                windows[seed].append((wanted[0], wanted[-1]))
    return windows


def main():
    parser = argparse.ArgumentParser(
        description="Check PhaseServe continuous per-GPU rate improvement windows."
    )
    parser.add_argument("inputs", nargs="+", help="Summary JSON files or directories.")
    parser.add_argument("--threshold", type=float, default=20.0)
    parser.add_argument("--window-len", type=float, default=2.0)
    parser.add_argument("--step", type=float, default=0.5)
    args = parser.parse_args()

    rows = build_rows(load_rows(args.inputs), args.threshold)
    print("seed global_rate per_gpu_rate ttft_wins tpot_wins pass ttft_imp[p50/p90/p95/p99] tpot_imp[p50/p90/p95/p99]")
    for row in rows:
        print(
            f"{row['seed']} {row['global_rate']:.3g} {row['per_gpu_rate']:.3g} "
            f"{row['ttft_wins']} {row['tpot_wins']} {row['pass']} "
            f"{row['ttft_imps']} {row['tpot_imps']}"
        )

    windows = find_windows(rows, args.window_len, args.step)
    print("windows:")
    if not windows:
        print("  none")
    for seed in sorted(windows):
        for start, end in windows[seed]:
            print(f"  seed={seed}: {start:.3g}-{end:.3g}")


if __name__ == "__main__":
    main()
