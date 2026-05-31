#!/usr/bin/env python3
import argparse
import csv
import json
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


def parse_grid(spec: str) -> List[Tuple[str, float, float]]:
    out = []
    for item in spec.split(","):
        item = item.strip()
        if not item:
            continue
        parts = item.split(":")
        if len(parts) != 3:
            raise ValueError(
                f"Invalid SLO grid entry {item!r}; expected label:ttft_s:tpot_s"
            )
        label, ttft_s, tpot_s = parts
        out.append((label, float(ttft_s), float(tpot_s)))
    if not out:
        raise ValueError("SLO grid must contain at least one entry")
    return out


def read_json(path: Path) -> Dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def read_records(path: Path) -> List[Dict]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def iter_summaries(root: Path) -> Iterable[Path]:
    yield from sorted(root.rglob("*.summary.json"))


def maybe_int(value):
    try:
        if value is None:
            return None
        as_float = float(value)
        as_int = int(as_float)
        return as_int if as_float == as_int else value
    except (TypeError, ValueError):
        return value


def run_row(summary_path: Path, summary: Dict, records: List[Dict], grid_entry) -> Dict:
    label, ttft_s, tpot_s = grid_entry
    meta = summary.get("metadata") or {}
    submitted = len(records)
    completed_rows = [r for r in records if r.get("ok")]
    good_rows = [
        r
        for r in completed_rows
        if r.get("ttft_s") is not None
        and r.get("tpot_s") is not None
        and r["ttft_s"] <= ttft_s
        and r["tpot_s"] <= tpot_s
    ]
    wall_time_s = summary.get("wall_time_s") or 0.0
    num_gpus = meta.get("num_gpus") or (summary.get("throughput") or {}).get("num_gpus")
    goodput_req_s = len(good_rows) / wall_time_s if wall_time_s else None
    return {
        "slo_label": label,
        "slo_ttft_s": ttft_s,
        "slo_tpot_s": tpot_s,
        "model": meta.get("model"),
        "policy": meta.get("policy"),
        "seed": maybe_int(meta.get("seed")),
        "rate": meta.get("request_rate"),
        "summary_path": str(summary_path),
        "raw_output": meta.get("raw_output"),
        "submitted": submitted,
        "completed": len(completed_rows),
        "goodput": len(good_rows),
        "slo_attainment_submitted": len(good_rows) / submitted if submitted else None,
        "slo_attainment_completed": (
            len(good_rows) / len(completed_rows) if completed_rows else None
        ),
        "wall_time_s": wall_time_s,
        "goodput_req_s": goodput_req_s,
        "per_gpu_goodput_req_s": (
            goodput_req_s / num_gpus if goodput_req_s is not None and num_gpus else None
        ),
    }


def aggregate(rows: List[Dict]) -> List[Dict]:
    groups = {}
    for row in rows:
        key = (
            row.get("slo_label"),
            row.get("slo_ttft_s"),
            row.get("slo_tpot_s"),
            row.get("rate"),
            row.get("policy"),
        )
        groups.setdefault(key, []).append(row)

    out = []
    for key, group in sorted(groups.items(), key=lambda kv: tuple(str(x) for x in kv[0])):
        slo_label, slo_ttft_s, slo_tpot_s, rate, policy = key
        def mean(field):
            vals = [r.get(field) for r in group if r.get(field) is not None]
            return sum(vals) / len(vals) if vals else None

        out.append({
            "slo_label": slo_label,
            "slo_ttft_s": slo_ttft_s,
            "slo_tpot_s": slo_tpot_s,
            "rate": rate,
            "policy": policy,
            "n": len(group),
            "goodput_req_s_mean": mean("goodput_req_s"),
            "per_gpu_goodput_req_s_mean": mean("per_gpu_goodput_req_s"),
            "slo_attainment_submitted_mean": mean("slo_attainment_submitted"),
            "slo_attainment_completed_mean": mean("slo_attainment_completed"),
        })
    return out


def write_csv(path: Path, rows: List[Dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row.keys()})
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def fmt(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def write_md(path: Path, title: str, rows: List[Dict], columns: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write(f"# {title}\n\n")
        if not rows:
            f.write("No rows.\n")
            return
        f.write("| " + " | ".join(columns) + " |\n")
        f.write("|" + "|".join("---" for _ in columns) + "|\n")
        for row in rows:
            f.write("| " + " | ".join(fmt(row.get(c)) for c in columns) + " |\n")


def main():
    parser = argparse.ArgumentParser(
        description="Recompute SLO attainment/goodput over a grid from raw per-request JSONL."
    )
    parser.add_argument("root", type=Path)
    parser.add_argument(
        "--grid",
        default="tight:1.0:0.10,medium:1.5:0.20,loose:2.0:0.30",
        help="Comma-separated label:ttft_s:tpot_s entries",
    )
    parser.add_argument("--output-prefix", type=Path)
    args = parser.parse_args()

    grid = parse_grid(args.grid)
    output_prefix = args.output_prefix or args.root / "slo_grid"
    rows = []
    skipped = []
    for summary_path in iter_summaries(args.root):
        summary = read_json(summary_path)
        meta = summary.get("metadata") or {}
        raw_output = meta.get("raw_output")
        if not raw_output:
            skipped.append((summary_path, "missing raw_output"))
            continue
        raw_path = Path(raw_output)
        if not raw_path.exists():
            skipped.append((summary_path, f"missing raw file {raw_path}"))
            continue
        records = read_records(raw_path)
        for entry in grid:
            rows.append(run_row(summary_path, summary, records, entry))

    grouped = aggregate(rows)
    write_csv(output_prefix.with_suffix(".csv"), rows)
    write_csv(Path(str(output_prefix) + ".grouped.csv"), grouped)
    write_md(
        output_prefix.with_suffix(".md"),
        "SLO Grid Per Run",
        rows,
        [
            "slo_label", "slo_ttft_s", "slo_tpot_s", "model", "policy",
            "seed", "rate", "submitted", "completed", "goodput",
            "slo_attainment_submitted", "goodput_req_s",
        ],
    )
    write_md(
        Path(str(output_prefix) + ".grouped.md"),
        "SLO Grid Grouped Means",
        grouped,
        [
            "slo_label", "slo_ttft_s", "slo_tpot_s", "rate", "policy", "n",
            "slo_attainment_submitted_mean", "goodput_req_s_mean",
            "per_gpu_goodput_req_s_mean",
        ],
    )

    print(f"Rows: {len(rows)}")
    print(f"Grouped rows: {len(grouped)}")
    print(f"Output prefix: {output_prefix}")
    if skipped:
        print(f"Skipped summaries: {len(skipped)}")
        for path, reason in skipped[:10]:
            print(f"- {path}: {reason}")


if __name__ == "__main__":
    main()
