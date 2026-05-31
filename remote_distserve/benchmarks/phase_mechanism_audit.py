#!/usr/bin/env python3
import argparse
import csv
import json
from pathlib import Path
from statistics import mean


PERCENTILES = ["median", "p90", "p95", "p99"]
PERCENTILE_LABELS = {
    "median": "p50",
    "p90": "p90",
    "p95": "p95",
    "p99": "p99",
}


def load_json(path):
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def nested(data, *keys, default=None):
    cur = data
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def summary_mean(component, key):
    return nested(component, key, "mean")


def summary_value(component, key, stat):
    return nested(component, key, stat)


def ratio_improvement(baseline, treatment):
    if baseline in (None, 0) or treatment is None:
        return None
    return (1.0 - treatment / baseline) * 100.0


def throughput_improvement(baseline_summary, phase_summary):
    base = nested(baseline_summary, "throughput", "completed_req_s")
    phase = nested(phase_summary, "throughput", "completed_req_s")
    if base in (None, 0) or phase is None:
        return None
    return (phase / base - 1.0) * 100.0


def share(counts, key):
    total = sum(v for v in (counts or {}).values() if isinstance(v, (int, float)))
    if total <= 0:
        return None
    return 100.0 * counts.get(key, 0) / total


def parse_run(spec):
    parts = spec.split(":", 2)
    if len(parts) != 3:
        raise ValueError("--run expects seed:rate:path")
    seed, rate, path = parts
    return int(seed), float(rate), Path(path)


def load_run(seed, rate, run_root):
    fcfs = load_json(run_root / "fcfs" / "fcfs_hetero.summary.json")
    phase = load_json(run_root / "phase" / "phase_hetero.summary.json")
    phase_metrics = phase.get("phase_metrics") or {}
    components = phase_metrics.get("components") or {}
    context = components.get("context") or {}
    decode = components.get("decode") or {}
    row = {
        "seed": seed,
        "rate": rate,
        "run_root": str(run_root),
        "submitted": phase.get("submitted"),
        "completed": phase.get("completed"),
        "slo_fcfs": fcfs.get("slo_attainment_submitted"),
        "slo_phase": phase.get("slo_attainment_submitted"),
        "slo_delta_pp": (
            (phase.get("slo_attainment_submitted") - fcfs.get("slo_attainment_submitted")) * 100.0
            if phase.get("slo_attainment_submitted") is not None
            and fcfs.get("slo_attainment_submitted") is not None
            else None
        ),
        "throughput_fcfs": nested(fcfs, "throughput", "completed_req_s"),
        "throughput_phase": nested(phase, "throughput", "completed_req_s"),
        "throughput_improvement_pct": throughput_improvement(fcfs, phase),
        "context_records": context.get("records"),
        "decode_records": decode.get("records"),
        "context_first_token_limited_share_pct": share(context.get("regimes"), "FIRST_TOKEN_LIMITED"),
        "context_mixed_slo_share_pct": share(context.get("regimes"), "MIXED_SLO"),
        "context_decode_heavy_share_pct": share(context.get("regimes"), "DECODE_HEAVY"),
        "decode_first_token_limited_share_pct": share(decode.get("regimes"), "FIRST_TOKEN_LIMITED"),
        "decode_mixed_slo_share_pct": share(decode.get("regimes"), "MIXED_SLO"),
        "decode_decode_heavy_share_pct": share(decode.get("regimes"), "DECODE_HEAVY"),
        "context_prefill_budget_ratio_mean": summary_mean(context, "prefill_budget_ratio"),
        "context_prefill_budget_ratio_p50": summary_value(context, "prefill_budget_ratio", "p50"),
        "context_pressure_bridge_mean": summary_mean(context, "pressure_bridge"),
        "context_pressure_decode_mean": summary_mean(context, "pressure_decode"),
        "context_pressure_kv_mean": summary_mean(context, "pressure_kv"),
        "context_pressure_first_mean": summary_mean(context, "pressure_first"),
        "context_pressure_decode_hard_mean": summary_mean(context, "pressure_decode_hard"),
        "context_pressure_kv_hard_mean": summary_mean(context, "pressure_kv_hard"),
        "context_pressure_injection_prefill_mean": summary_mean(context, "pressure_injection_prefill"),
        "context_pressure_injection_prefill_p99": summary_value(
            context, "pressure_injection_prefill", "p99"
        ),
        "context_candidate_max_wait_p95_s": summary_value(context, "candidate_max_wait_s", "p95"),
        "context_waiting_long_prompt_max_wait_p95_s": summary_value(
            context, "waiting_long_prompt_max_wait_s", "p95"
        ),
        "context_regime_switch_rate_mean": summary_mean(context, "controller_regime_switch_rate"),
        "context_mode_switch_rate_mean": summary_mean(context, "controller_mode_switch_rate"),
        "decode_budget_utility_intensity_mean": summary_mean(
            decode, "budget_decode_utility_intensity"
        ),
        "decode_selected_effective_kas_intensity_mean": summary_mean(
            decode, "selected_effective_kas_intensity"
        ),
        "decode_kas_intensity_mean": summary_mean(decode, "kas_intensity"),
        "decode_pressure_decode_mean": summary_mean(decode, "pressure_decode"),
        "decode_pressure_bridge_mean": summary_mean(decode, "pressure_bridge"),
        "decode_pressure_kv_mean": summary_mean(decode, "pressure_kv"),
        "decode_pressure_first_mean": summary_mean(decode, "pressure_first"),
        "decode_pressure_decode_hard_mean": summary_mean(decode, "pressure_decode_hard"),
        "decode_pressure_kv_hard_mean": summary_mean(decode, "pressure_kv_hard"),
        "decode_pressure_potential_mean": summary_mean(decode, "pressure_potential"),
        "decode_pressure_overshoot_mean": summary_mean(decode, "pressure_overshoot"),
        "decode_resident_admission_ratio_mean": summary_mean(decode, "resident_admission_ratio"),
        "decode_starved_admission_ratio_mean": summary_mean(decode, "starved_admission_ratio"),
        "decode_max_consecutive_skips_p95": summary_value(decode, "max_consecutive_skips", "p95"),
        "decode_max_consecutive_skips_max": summary_value(decode, "max_consecutive_skips", "max"),
        "decode_swap_ins": decode.get("swap_ins"),
        "decode_swap_in_bytes": decode.get("swap_in_bytes"),
        "decode_infeasible_rounds": sum(
            decode.get(key, 0) or 0
            for key in [
                "infeasible_batch_size",
                "infeasible_gpu_append_blocks",
                "infeasible_gpu_swap_blocks",
                "infeasible_swap_budget",
                "infeasible_token_budget",
            ]
        ),
    }
    for metric in ["ttft_s", "tpot_s"]:
        for pct in PERCENTILES:
            label = PERCENTILE_LABELS[pct]
            fcfs_value = nested(fcfs, metric, pct)
            phase_value = nested(phase, metric, pct)
            row[f"{metric}_{label}_fcfs"] = fcfs_value
            row[f"{metric}_{label}_phase"] = phase_value
            row[f"{metric}_{label}_improvement_pct"] = ratio_improvement(fcfs_value, phase_value)
    return row


def fmt(value, digits=3, suffix=""):
    if value is None:
        return ""
    if isinstance(value, int):
        return f"{value}{suffix}"
    return f"{value:.{digits}f}{suffix}"


def fmt_signed(value, digits=1, suffix="%"):
    if value is None:
        return ""
    return f"{value:+.{digits}f}{suffix}"


def write_csv(rows, output):
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with Path(output).open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def average_rows(rows):
    out = []
    rates = sorted({row["rate"] for row in rows})
    numeric_keys = [
        key for key, value in rows[0].items()
        if isinstance(value, (int, float)) and key not in {"seed", "rate"}
    ]
    for rate in rates:
        group = [row for row in rows if row["rate"] == rate]
        item = {"rate": rate, "n": len(group)}
        for key in numeric_keys:
            values = [row[key] for row in group if isinstance(row.get(key), (int, float))]
            item[key] = mean(values) if values else None
        out.append(item)
    return out


def write_markdown(rows, output):
    avg = average_rows(rows)
    lines = []
    lines.append("# Phase Mechanism Audit")
    lines.append("")
    lines.append("Positive improvement means Phase latency is lower than FCFS.")
    lines.append("")
    lines.append("## End-To-End By Run")
    lines.append("")
    lines.append(
        "| seed | rate | TTFT p50 | TTFT p90 | TTFT p95 | TTFT p99 | "
        "TPOT p50 | TPOT p90 | TPOT p95 | TPOT p99 | SLO delta | throughput |"
    )
    lines.append("|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in rows:
        lines.append(
            "| {seed} | {rate} | {ttft50} | {ttft90} | {ttft95} | {ttft99} | "
            "{tpot50} | {tpot90} | {tpot95} | {tpot99} | {slo} | {thr} |".format(
                seed=row["seed"],
                rate=fmt(row["rate"], 0),
                ttft50=fmt_signed(row["ttft_s_p50_improvement_pct"]),
                ttft90=fmt_signed(row["ttft_s_p90_improvement_pct"]),
                ttft95=fmt_signed(row["ttft_s_p95_improvement_pct"]),
                ttft99=fmt_signed(row["ttft_s_p99_improvement_pct"]),
                tpot50=fmt_signed(row["tpot_s_p50_improvement_pct"]),
                tpot90=fmt_signed(row["tpot_s_p90_improvement_pct"]),
                tpot95=fmt_signed(row["tpot_s_p95_improvement_pct"]),
                tpot99=fmt_signed(row["tpot_s_p99_improvement_pct"]),
                slo=fmt_signed(row["slo_delta_pp"], 2, " pp"),
                thr=fmt_signed(row["throughput_improvement_pct"]),
            )
        )
    lines.append("")
    lines.append("## Average By Rate")
    lines.append("")
    lines.append(
        "| rate | n | TTFT p50 | TTFT p90 | TTFT p95 | TTFT p99 | "
        "TPOT p50 | TPOT p90 | TPOT p95 | TPOT p99 | SLO delta | throughput |"
    )
    lines.append("|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in avg:
        lines.append(
            "| {rate} | {n} | {ttft50} | {ttft90} | {ttft95} | {ttft99} | "
            "{tpot50} | {tpot90} | {tpot95} | {tpot99} | {slo} | {thr} |".format(
                rate=fmt(row["rate"], 0),
                n=row["n"],
                ttft50=fmt_signed(row["ttft_s_p50_improvement_pct"]),
                ttft90=fmt_signed(row["ttft_s_p90_improvement_pct"]),
                ttft95=fmt_signed(row["ttft_s_p95_improvement_pct"]),
                ttft99=fmt_signed(row["ttft_s_p99_improvement_pct"]),
                tpot50=fmt_signed(row["tpot_s_p50_improvement_pct"]),
                tpot90=fmt_signed(row["tpot_s_p90_improvement_pct"]),
                tpot95=fmt_signed(row["tpot_s_p95_improvement_pct"]),
                tpot99=fmt_signed(row["tpot_s_p99_improvement_pct"]),
                slo=fmt_signed(row["slo_delta_pp"], 2, " pp"),
                thr=fmt_signed(row["throughput_improvement_pct"]),
            )
        )
    lines.append("")
    lines.append("## Mechanism By Run")
    lines.append("")
    lines.append(
        "| seed | rate | ctx FTL | dec DH | prefill budget | dec intensity | "
        "eff KAS | dec pressure | bridge pressure | KV pressure | hard pressure | max skips p95 |"
    )
    lines.append("|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in rows:
        hard = max(
            row.get("context_pressure_decode_hard_mean") or 0.0,
            row.get("context_pressure_kv_hard_mean") or 0.0,
            row.get("decode_pressure_decode_hard_mean") or 0.0,
            row.get("decode_pressure_kv_hard_mean") or 0.0,
        )
        lines.append(
            "| {seed} | {rate} | {ctx_ftl} | {dec_dh} | {prefill} | {intensity} | "
            "{eff_kas} | {dec_p} | {bridge_p} | {kv_p} | {hard_p} | {skips} |".format(
                seed=row["seed"],
                rate=fmt(row["rate"], 0),
                ctx_ftl=fmt(row["context_first_token_limited_share_pct"], 1, "%"),
                dec_dh=fmt(row["decode_decode_heavy_share_pct"], 1, "%"),
                prefill=fmt(row["context_prefill_budget_ratio_mean"], 3),
                intensity=fmt(row["decode_budget_utility_intensity_mean"], 3),
                eff_kas=fmt(row["decode_selected_effective_kas_intensity_mean"], 3),
                dec_p=fmt(row["decode_pressure_decode_mean"], 3),
                bridge_p=fmt(row["decode_pressure_bridge_mean"], 3),
                kv_p=fmt(row["decode_pressure_kv_mean"], 3),
                hard_p=fmt(hard, 3),
                skips=fmt(row["decode_max_consecutive_skips_p95"], 1),
            )
        )
    lines.append("")
    lines.append("## Mechanism Average By Rate")
    lines.append("")
    lines.append(
        "| rate | ctx FTL | dec DH | prefill budget | dec intensity | eff KAS | "
        "dec pressure | bridge pressure | KV pressure | SLO delta |"
    )
    lines.append("|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in avg:
        lines.append(
            "| {rate} | {ctx_ftl} | {dec_dh} | {prefill} | {intensity} | {eff_kas} | "
            "{dec_p} | {bridge_p} | {kv_p} | {slo} |".format(
                rate=fmt(row["rate"], 0),
                ctx_ftl=fmt(row["context_first_token_limited_share_pct"], 1, "%"),
                dec_dh=fmt(row["decode_decode_heavy_share_pct"], 1, "%"),
                prefill=fmt(row["context_prefill_budget_ratio_mean"], 3),
                intensity=fmt(row["decode_budget_utility_intensity_mean"], 3),
                eff_kas=fmt(row["decode_selected_effective_kas_intensity_mean"], 3),
                dec_p=fmt(row["decode_pressure_decode_mean"], 3),
                bridge_p=fmt(row["decode_pressure_bridge_mean"], 3),
                kv_p=fmt(row["decode_pressure_kv_mean"], 3),
                slo=fmt_signed(row["slo_delta_pp"], 2, " pp"),
            )
        )
    lines.append("")
    Path(output).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--run",
        action="append",
        required=True,
        help="Run entry formatted as seed:rate:/path/to/rate_root",
    )
    parser.add_argument("--output-md", required=True)
    parser.add_argument("--output-csv", required=True)
    args = parser.parse_args()

    rows = []
    for spec in args.run:
        rows.append(load_run(*parse_run(spec)))
    rows.sort(key=lambda row: (row["rate"], row["seed"]))
    write_csv(rows, args.output_csv)
    write_markdown(rows, args.output_md)
    print(f"rows={len(rows)}")
    print(f"markdown={args.output_md}")
    print(f"csv={args.output_csv}")


if __name__ == "__main__":
    main()
