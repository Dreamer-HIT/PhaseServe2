#!/usr/bin/env python3
import argparse
import asyncio
import json
import math
import random
import sys
import time
from pathlib import Path
from typing import AsyncGenerator, Dict, List, Optional, Tuple

import aiohttp
import numpy as np

sys.path.insert(0, "/root/data/DistServe/evaluation/2-benchmark-serving")
from structs import Dataset, TestRequest, RequestResult  # noqa: E402


PROMPT_BUCKETS = [64, 128, 256, 512, 1024, 2048, math.inf]
OUTPUT_BUCKETS = [16, 64, 128, 256, 512, math.inf]


def percentile(values: List[float], pct: float) -> Optional[float]:
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    rank = (len(values) - 1) * pct / 100.0
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return values[low]
    return values[low] * (high - rank) + values[high] * (rank - low)


def summarize(values: List[float]) -> Dict[str, Optional[float]]:
    values = [v for v in values if v is not None]
    if not values:
        return {
            "count": 0,
            "mean": None,
            "p50": None,
            "p75": None,
            "median": None,
            "p90": None,
            "p95": None,
            "p99": None,
            "max": None,
        }
    return {
        "count": len(values),
        "mean": float(np.mean(values)),
        "p50": percentile(values, 50),
        "p75": percentile(values, 75),
        "median": percentile(values, 50),
        "p90": percentile(values, 90),
        "p95": percentile(values, 95),
        "p99": percentile(values, 99),
        "max": max(values),
    }


def summarize_phase_metrics(path: Optional[str]) -> Dict:
    if not path:
        return {}
    metrics_path = Path(path)
    if not metrics_path.exists():
        return {"path": str(metrics_path), "exists": False}
    records = []
    with metrics_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    by_component = {}
    for component in sorted({r.get("component", "unknown") for r in records}):
        rows = [r for r in records if r.get("component", "unknown") == component]
        dispatch_rows = [r for r in rows if r.get("event") == "dispatch"]
        budgets = [r.get("budget", {}) for r in dispatch_rows]
        controllers = [r.get("controller", {}) for r in dispatch_rows]
        pressures = [b.get("pressures", {}) for b in budgets]
        by_component[component] = {
            "records": len(rows),
            "dispatches": len(dispatch_rows),
            "modes": {
                mode: sum(1 for b in budgets if b.get("mode") == mode)
                for mode in sorted({b.get("mode") for b in budgets if b.get("mode")})
            },
            "regimes": {
                regime: sum(1 for b in budgets if b.get("regime") == regime)
                for regime in sorted({b.get("regime") for b in budgets if b.get("regime")})
            },
            "rho_down": summarize([b.get("rho_down") for b in budgets]),
            "rho_prefill": summarize([b.get("rho_prefill") for b in budgets]),
            "rho_memory": summarize([b.get("rho_memory") for b in budgets]),
            "rho_swap": summarize([b.get("rho_swap") for b in budgets]),
            "rho_scan": summarize([b.get("rho_scan") for b in budgets]),
            "rho_hard": summarize([b.get("rho_hard") for b in budgets]),
            "decode_utility_intensity": summarize([
                b.get("decode_utility_intensity") for b in budgets
            ]),
            "pressure_overshoot": summarize([b.get("pressure_overshoot") for b in budgets]),
            "pressure_potential": summarize([b.get("pressure_potential") for b in budgets]),
            "goodput_capacity": summarize([b.get("goodput_capacity") for b in budgets]),
            "smooth_cost": summarize([b.get("smooth_cost") for b in budgets]),
            "progress_debt": summarize([b.get("progress_debt") for b in budgets]),
            "pressure_injection_prefill": summarize([
                r.get("pressure_injection_prefill", b.get("pressure_injection_prefill"))
                for r, b in zip(dispatch_rows, budgets)
            ]),
            "pressure_injection_decode_swap": summarize([
                r.get("pressure_injection_decode_swap", b.get("pressure_injection_decode_swap"))
                for r, b in zip(dispatch_rows, budgets)
            ]),
            "pressure_bridge": summarize([p.get("bridge") for p in pressures]),
            "pressure_first": summarize([p.get("first") for p in pressures]),
            "pressure_decode": summarize([p.get("decode") for p in pressures]),
            "pressure_kv": summarize([p.get("kv") for p in pressures]),
            "pressure_swap": summarize([p.get("swap") for p in pressures]),
            "pressure_decode_hard": summarize([p.get("decode_hard") for p in pressures]),
            "pressure_kv_hard": summarize([p.get("kv_hard") for p in pressures]),
            "selected": summarize([r.get("selected") for r in dispatch_rows]),
            "sched_time_s": summarize([r.get("sched_time_s") for r in dispatch_rows]),
            "controller_mode_switch_rate": summarize([c.get("mode_switch_rate") for c in controllers]),
            "controller_regime_switch_rate": summarize([c.get("regime_switch_rate") for c in controllers]),
            "controller_budget_delta": summarize([c.get("last_budget_delta") for c in controllers]),
            "controller_intensity_delta": summarize([c.get("last_intensity_delta") for c in controllers]),
            "controller_pressure_overshoot": summarize([c.get("last_pressure_overshoot") for c in controllers]),
            "controller_decode_utility_intensity": summarize([
                c.get("last_decode_utility_intensity") for c in controllers
            ]),
            "controller_ttft_debt_weight": summarize([
                c.get("last_ttft_debt_weight") for c in controllers
            ]),
        }
        if component == "context":
            prefill_budget_ratios = []
            for row, budget in zip(dispatch_rows, budgets):
                max_prefill_tokens = row.get("max_prefill_tokens")
                if max_prefill_tokens:
                    prefill_budget_ratios.append(
                        budget.get("prefill_token_budget") / max(max_prefill_tokens, 1)
                    )
            protected_triggered = sum(1 for r in dispatch_rows if r.get("protected_triggered"))
            protected_selected = sum(
                1 for r in dispatch_rows
                if r.get("protected_triggered") and r.get("protected_selected")
            )
            protected_blocked = sum(1 for r in dispatch_rows if r.get("protected_blocked"))
            protected_bypassed = sum(1 for r in dispatch_rows if r.get("protected_bypassed"))
            protected_feasible_triggers = max(protected_triggered - protected_blocked, 0)
            waiting_waits = [r.get("waiting_waits") or {} for r in dispatch_rows]
            candidate_waits = [r.get("candidate_waits") or {} for r in dispatch_rows]
            selected_waits = [r.get("selected_waits") or {} for r in dispatch_rows]
            by_component[component].update({
                "prefill_token_budget": summarize([b.get("prefill_token_budget") for b in budgets]),
                "prefill_budget_ratio": summarize(prefill_budget_ratios),
                "prefill_block_margin": summarize([b.get("prefill_block_margin") for b in budgets]),
                "forced_oldest": sum(1 for r in dispatch_rows if r.get("forced_oldest")),
                "protected_triggered": protected_triggered,
                "protected_selected": protected_selected,
                "protected_dispatch_ratio": (
                    protected_selected / protected_triggered if protected_triggered else None
                ),
                "protected_feasible_dispatch_ratio": (
                    protected_selected / protected_feasible_triggers
                    if protected_feasible_triggers else None
                ),
                "protected_forced_single": sum(1 for r in dispatch_rows if r.get("protected_forced_single")),
                "protected_blocked": protected_blocked,
                "protected_bypassed": protected_bypassed,
                "protected_bypass_ratio": (
                    protected_bypassed / protected_blocked if protected_blocked else None
                ),
                "protected_feasible_triggers": protected_feasible_triggers,
                "protected_wait_s": summarize([r.get("protected_wait_s") for r in dispatch_rows]),
                "candidate_window": summarize([r.get("candidate_window") for r in dispatch_rows]),
                "candidate_batches": summarize([r.get("candidate_batches") for r in dispatch_rows]),
                "waiting_max_wait_s": summarize([w.get("max_wait_s") for w in waiting_waits]),
                "waiting_long_prompt_count": summarize([w.get("long_prompt_count") for w in waiting_waits]),
                "waiting_long_prompt_max_wait_s": summarize([
                    w.get("long_prompt_max_wait_s") for w in waiting_waits
                ]),
                "candidate_max_wait_s": summarize([w.get("max_wait_s") for w in candidate_waits]),
                "candidate_long_prompt_max_wait_s": summarize([
                    w.get("long_prompt_max_wait_s") for w in candidate_waits
                ]),
                "selected_max_wait_s": summarize([w.get("max_wait_s") for w in selected_waits]),
                "selected_long_prompt_count": summarize([
                    w.get("long_prompt_count") for w in selected_waits
                ]),
                "decode_snapshot_used": sum(1 for r in dispatch_rows if (r.get("decode_snapshot") or {}).get("used")),
                "decode_snapshot_stale": sum(1 for r in dispatch_rows if (r.get("decode_snapshot") or {}).get("stale")),
                "decode_snapshot_age_s": summarize([
                    (r.get("decode_snapshot") or {}).get("age_s")
                    for r in dispatch_rows
                ]),
                "scoring_modes": {
                    mode: sum(1 for r in dispatch_rows if r.get("scoring_mode") == mode)
                    for mode in sorted({r.get("scoring_mode") for r in dispatch_rows if r.get("scoring_mode")})
                },
                "selected_prompt_tokens": summarize([r.get("selected_prompt_tokens") for r in dispatch_rows]),
                "selected_prefill_blocks": summarize([r.get("selected_prefill_blocks") for r in dispatch_rows]),
                "token_fill": summarize([r.get("token_fill") for r in dispatch_rows]),
                "pad_waste": summarize([r.get("pad_waste") for r in dispatch_rows]),
                "block_risk": summarize([r.get("block_risk") for r in dispatch_rows]),
                "pressure_injection_prefill": summarize([
                    r.get("pressure_injection_prefill") for r in dispatch_rows
                ]),
            })
        if component == "decode":
            by_component[component].update({
                "decode_swap_budget_per_iter": summarize([b.get("decode_swap_budget_per_iter") for b in budgets]),
                "decode_scan_limit": summarize([b.get("decode_scan_limit") for b in budgets]),
                "swap_byte_budget": summarize([r.get("swap_byte_budget") for r in dispatch_rows]),
                "swap_byte_budget_ratio": summarize([r.get("swap_byte_budget_ratio") for r in dispatch_rows]),
                "swap_ins": sum(r.get("swap_ins", 0) for r in dispatch_rows),
                "swap_in_bytes": sum(r.get("swap_in_bytes", 0) for r in dispatch_rows),
                "pressure_injection_decode_swap": summarize([
                    r.get("pressure_injection_decode_swap") for r in dispatch_rows
                ]),
                "policy_variants": {
                    variant: sum(1 for r in dispatch_rows if r.get("policy_variant") == variant)
                    for variant in sorted({r.get("policy_variant") for r in dispatch_rows if r.get("policy_variant")})
                },
                "iteration_stall_s": summarize([r.get("iteration_stall_s") for r in dispatch_rows]),
                "resident_admission_ratio": summarize([r.get("resident_admission_ratio") for r in dispatch_rows]),
                "starved_ready": sum(r.get("starved_ready", 0) for r in dispatch_rows),
                "starved_selected": sum(r.get("starved_selected", 0) for r in dispatch_rows),
                "starved_admission_ratio": summarize([r.get("starved_admission_ratio") for r in dispatch_rows]),
                "first_token_ready": sum(r.get("first_token_ready", 0) for r in dispatch_rows),
                "first_token_selected": sum(r.get("first_token_selected", 0) for r in dispatch_rows),
                "first_token_admission_ratio": summarize([
                    r.get("first_token_admission_ratio") for r in dispatch_rows
                ]),
                "handoff_debt_ready": sum(r.get("handoff_debt_ready", 0) for r in dispatch_rows),
                "handoff_debt_selected": sum(r.get("handoff_debt_selected", 0) for r in dispatch_rows),
                "handoff_debt_admission_ratio": summarize([
                    r.get("handoff_debt_admission_ratio") for r in dispatch_rows
                ]),
                "handoff_debt_discount_mean": summarize([
                    r.get("handoff_debt_discount_mean") for r in dispatch_rows
                ]),
                "handoff_debt_selected_discount_mean": summarize([
                    r.get("handoff_debt_selected_discount_mean") for r in dispatch_rows
                ]),
                "handoff_debt_weight": summarize([
                    r.get("handoff_debt_weight") for r in dispatch_rows
                ]),
                "budget_ttft_debt_weight": summarize([
                    r.get("budget_ttft_debt_weight") for r in dispatch_rows
                ]),
                "effective_handoff_debt_weight": summarize([
                    r.get("effective_handoff_debt_weight") for r in dispatch_rows
                ]),
                "handoff_debt_pressure": summarize([
                    r.get("handoff_debt_pressure") for r in dispatch_rows
                ]),
                "kas_intensity": summarize([
                    r.get("kas_intensity") for r in dispatch_rows
                ]),
                "selected_effective_kas_intensity": summarize([
                    r.get("selected_effective_kas_intensity_mean") for r in dispatch_rows
                ]),
                "fcfs_fallback_active": sum(
                    1 for r in dispatch_rows if r.get("fcfs_fallback_active")
                ),
                "fcfs_fallback_intensity_threshold": summarize([
                    r.get("fcfs_fallback_intensity_threshold") for r in dispatch_rows
                ]),
                "short_output_fcfs_threshold": summarize([
                    r.get("short_output_fcfs_threshold") for r in dispatch_rows
                ]),
                "long_output_full_kas_threshold": summarize([
                    r.get("long_output_full_kas_threshold") for r in dispatch_rows
                ]),
                "avg_target_output_len": summarize([
                    r.get("avg_target_output_len") for r in dispatch_rows
                ]),
                "budget_decode_utility_intensity": summarize([
                    r.get("budget_decode_utility_intensity") for r in dispatch_rows
                ]),
                "budget_regimes": {
                    regime: sum(1 for r in dispatch_rows if r.get("budget_regime") == regime)
                    for regime in sorted({
                        r.get("budget_regime") for r in dispatch_rows if r.get("budget_regime")
                    })
                },
                "kas_adaptive_intensity": sum(
                    1 for r in dispatch_rows if r.get("kas_adaptive_intensity")
                ),
                "prefill_gate_active": sum(1 for r in dispatch_rows if r.get("prefill_gate_active")),
                "prefill_gate_pressure": summarize([r.get("prefill_gate_pressure") for r in dispatch_rows]),
                "prefill_gate_first_token_pressure": summarize([
                    r.get("prefill_gate_first_token_pressure") for r in dispatch_rows
                ]),
                "prefill_gate_bridge_pressure": summarize([
                    r.get("prefill_gate_bridge_pressure") for r in dispatch_rows
                ]),
                "prefill_gate_decode_hard_pressure": summarize([
                    r.get("prefill_gate_decode_hard_pressure") for r in dispatch_rows
                ]),
                "policy_skipped": sum(r.get("policy_skipped", 0) for r in dispatch_rows),
                "infeasible_rounds": sum(r.get("infeasible_rounds", 0) for r in dispatch_rows),
                "infeasible_batch_size": sum(r.get("infeasible_batch_size", 0) for r in dispatch_rows),
                "infeasible_token_budget": sum(r.get("infeasible_token_budget", 0) for r in dispatch_rows),
                "infeasible_gpu_append_blocks": sum(r.get("infeasible_gpu_append_blocks", 0) for r in dispatch_rows),
                "infeasible_gpu_swap_blocks": sum(r.get("infeasible_gpu_swap_blocks", 0) for r in dispatch_rows),
                "infeasible_swap_budget": sum(r.get("infeasible_swap_budget", 0) for r in dispatch_rows),
                "max_consecutive_skips": summarize([r.get("max_consecutive_skips") for r in dispatch_rows]),
                "max_consecutive_infeasible": summarize([r.get("max_consecutive_infeasible") for r in dispatch_rows]),
                "eviction_count": sum(r.get("eviction_count", 0) for r in dispatch_rows),
            })
    return {
        "path": str(metrics_path),
        "exists": True,
        "records": len(records),
        "components": by_component,
    }


def event_map(events):
    out = {}
    for event in events or []:
        event_type = event.get("event_type")
        timestamp = event.get("timestamp")
        if event_type is not None and timestamp is not None:
            out[event_type] = timestamp
    return out


def duration(events, begin, end):
    mapped = event_map(events)
    if begin not in mapped or end not in mapped:
        return None
    return mapped[end] - mapped[begin]


def bucket_label(value: int, boundaries: List[float]) -> str:
    lower = 0
    for upper in boundaries:
        if value <= upper:
            if math.isinf(upper):
                return f">{lower}"
            return f"({lower},{int(upper)}]"
        lower = int(upper)
    return f">{lower}"


def parse_phase_rate_schedule(spec: Optional[str]) -> Dict[str, float]:
    if not spec:
        return {}
    schedule = {}
    for item in spec.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" in item:
            name, rate = item.split(":", 1)
        elif "=" in item:
            name, rate = item.split("=", 1)
        else:
            raise ValueError(
                f"Invalid phase rate entry {item!r}; expected phase:rate"
            )
        schedule[name.strip()] = float(rate)
    return schedule


def load_request_metadata(
    path: Optional[str],
    sample_mode: str,
    num_prompts: int,
) -> Tuple[Optional[Dict], Optional[List[Dict]]]:
    if not path:
        return None, None
    metadata_path = Path(path)
    if not metadata_path.exists():
        raise FileNotFoundError(f"request metadata not found: {metadata_path}")
    if sample_mode != "first":
        raise ValueError("--request-metadata currently requires --sample-mode first")
    data = json.loads(metadata_path.read_text(encoding="utf-8"))
    requests = data.get("requests") or []
    if len(requests) < num_prompts:
        raise ValueError(
            f"request metadata has {len(requests)} rows, "
            f"but --num-prompts={num_prompts}"
        )
    return data, requests[:num_prompts]


def request_rate_for_metadata(
    request_meta: Optional[Dict],
    global_rate: float,
    phase_rates: Dict[str, float],
    phase_rate_scale: float,
) -> float:
    if request_meta:
        phase = request_meta.get("phase")
        if phase in phase_rates:
            return phase_rates[phase] * phase_rate_scale
        if request_meta.get("request_rate") is not None:
            return float(request_meta["request_rate"]) * phase_rate_scale
    return global_rate


def sample_interval(process_name: str, request_rate: float, cv: float) -> float:
    if request_rate in [float("inf"), 0.0]:
        return 0.0
    if process_name == "uniform":
        return 1.0 / request_rate
    if process_name in ["gamma", "possion", "poisson"]:
        if process_name in ["possion", "poisson"]:
            cv = 1.0
        shape = 1 / (cv * cv)
        scale = cv * cv / request_rate
        return float(np.random.gamma(shape, scale))
    raise ValueError(f"Unsupported process name: {process_name}")


def request_result_to_record(
    result: RequestResult,
    request_id: int,
    scheduled_at: float,
    request_meta: Optional[Dict] = None,
):
    timestamps = result.token_timestamps or []
    ttft = timestamps[0] - result.start_time if timestamps else None
    if len(timestamps) <= 1:
        tpot = 0.0 if timestamps else None
    else:
        tpot = (timestamps[-1] - timestamps[0]) / (len(timestamps) - 1)
    events = result.lifecycle_events
    decode_exec_s = duration(events, "decoding_begin", "decoding_end")
    latency_s = result.end_time - result.start_time
    output_tokens = max(len(timestamps), 1)
    record = {
        "request_id": request_id,
        "ok": True,
        "prompt_len": result.prompt_len,
        "output_len": result.output_len,
        "scheduled_at": scheduled_at,
        "start_time": result.start_time,
        "end_time": result.end_time,
        "latency_s": latency_s,
        "ttft_s": ttft,
        "tpot_s": tpot,
        "e2e_per_output_token_s": latency_s / max(result.output_len, 1),
        "decode_per_output_token_s": (
            decode_exec_s / output_tokens if decode_exec_s is not None else None
        ),
        "num_token_timestamps": len(timestamps),
        "token_timestamps": timestamps,
        "lifecycle_events": events,
        "context_queue_s": duration(events, "issued", "context_begin"),
        "context_exec_s": duration(events, "context_begin", "context_end"),
        "bridge_queue_s": duration(events, "context_end", "migration_begin"),
        "migration_s": duration(events, "migration_begin", "migration_end"),
        "decode_queue_s": duration(events, "migration_end", "decoding_begin"),
        "decode_exec_s": decode_exec_s,
        "prompt_bucket": bucket_label(result.prompt_len, PROMPT_BUCKETS),
        "output_bucket": bucket_label(result.output_len, OUTPUT_BUCKETS),
    }
    if request_meta:
        record.update({
            "workload_phase": request_meta.get("phase"),
            "workload_phase_index": request_meta.get("phase_index"),
            "phase_request_index": request_meta.get("phase_request_index"),
            "phase_request_rate": request_meta.get("request_rate"),
            "phase_prompt_mix": request_meta.get("prompt_mix"),
            "phase_output_mix": request_meta.get("output_mix"),
        })
    return record


def failure_record(
    request: TestRequest,
    request_id: int,
    scheduled_at: float,
    start: float,
    error: str,
    request_meta: Optional[Dict] = None,
):
    end = time.perf_counter()
    record = {
        "request_id": request_id,
        "ok": False,
        "prompt_len": request.prompt_len,
        "output_len": request.output_len,
        "scheduled_at": scheduled_at,
        "start_time": start,
        "end_time": end,
        "latency_s": end - start,
        "error": error,
        "prompt_bucket": bucket_label(request.prompt_len, PROMPT_BUCKETS),
        "output_bucket": bucket_label(request.output_len, OUTPUT_BUCKETS),
    }
    if request_meta:
        record.update({
            "workload_phase": request_meta.get("phase"),
            "workload_phase_index": request_meta.get("phase_index"),
            "phase_request_index": request_meta.get("phase_request_index"),
            "phase_request_rate": request_meta.get("request_rate"),
            "phase_prompt_mix": request_meta.get("prompt_mix"),
            "phase_output_mix": request_meta.get("output_mix"),
        })
    return record


async def get_request(
    input_items: List[Tuple[TestRequest, Optional[Dict]]],
    process_name: str,
    request_rate: float,
    cv: float,
    phase_rates: Optional[Dict[str, float]] = None,
    phase_rate_scale: float = 1.0,
) -> AsyncGenerator[Tuple[TestRequest, Optional[Dict]], None]:
    phase_rates = phase_rates or {}
    item_rates = [
        request_rate_for_metadata(meta, request_rate, phase_rates, phase_rate_scale)
        for _, meta in input_items
    ]
    for idx, item in enumerate(input_items):
        yield item
        if idx + 1 < len(input_items):
            interval = sample_interval(process_name, item_rates[idx + 1], cv)
            if interval > 0:
                await asyncio.sleep(interval)


async def send_request(
    session,
    api_url: str,
    request: TestRequest,
    request_id: int,
    scheduled_at: float,
    max_total_tokens: int,
    request_meta: Optional[Dict] = None,
):
    payload = {
        "prompt": request.prompt,
        "n": 1,
        "best_of": 1,
        "use_beam_search": False,
        "temperature": 0.0,
        "top_p": 1.0,
        "top_k": -1,
        "max_tokens": request.output_len,
        "ignore_eos": True,
        "stream": False,
    }
    start = time.perf_counter()
    try:
        if max_total_tokens > 0 and request.prompt_len + request.output_len > max_total_tokens:
            raise ValueError(
                f"request total tokens {request.prompt_len + request.output_len} "
                f"exceeds --max-total-tokens={max_total_tokens}"
            )
        async with session.post(api_url, json=payload) as response:
            body = await response.read()
        end = time.perf_counter()
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}: {body[:200]!r}")
        output = json.loads(body.decode("utf-8"))
        if "error" in output:
            raise RuntimeError(output["error"])
        result = RequestResult(
            request.prompt_len,
            request.output_len,
            start,
            end,
            token_timestamps=output["timestamps"],
            lifetime_events=output.get("lifetime_events", None),
        )
        return request_result_to_record(result, request_id, scheduled_at, request_meta)
    except Exception as exc:
        return failure_record(request, request_id, scheduled_at, start, repr(exc), request_meta)


async def benchmark(args):
    dataset = Dataset.load(args.dataset)
    random.seed(args.seed)
    np.random.seed(args.seed)
    if args.num_prompts > len(dataset.reqs):
        raise ValueError(
            f"--num-prompts={args.num_prompts} exceeds dataset size {len(dataset.reqs)}"
        )
    if args.sample_mode == "first":
        requests = dataset.reqs[: args.num_prompts]
    else:
        requests = random.sample(dataset.reqs, args.num_prompts)
    request_metadata_data, request_metadata = load_request_metadata(
        args.request_metadata, args.sample_mode, args.num_prompts
    )
    args.request_metadata_profile = (
        request_metadata_data.get("profile") if request_metadata_data else None
    )
    args.request_metadata_phases = (
        request_metadata_data.get("phases") if request_metadata_data else None
    )
    phase_rates = parse_phase_rate_schedule(args.phase_rate_schedule)
    if request_metadata:
        for meta in request_metadata:
            phase = meta.get("phase")
            if phase in phase_rates:
                meta["request_rate"] = phase_rates[phase] * args.phase_rate_scale
            elif meta.get("request_rate") is not None:
                meta["request_rate"] = float(meta["request_rate"]) * args.phase_rate_scale
    input_items = list(zip(requests, request_metadata or [None] * len(requests)))
    api_url = f"http://{args.host}:{args.port}/generate"
    timeout = aiohttp.ClientTimeout(total=args.timeout_s)
    connector = aiohttp.TCPConnector(limit=args.max_connections)
    tasks = []
    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        async for request, request_meta in get_request(
            input_items,
            args.process_name,
            args.request_rate,
            args.request_cv,
            phase_rates=phase_rates,
            phase_rate_scale=args.phase_rate_scale,
        ):
            scheduled_at = time.perf_counter()
            request_id = len(tasks)
            tasks.append(
                asyncio.create_task(
                    send_request(
                        session,
                        api_url,
                        request,
                        request_id,
                        scheduled_at,
                        args.max_total_tokens,
                        request_meta,
                    )
                )
            )
        return await asyncio.gather(*tasks)


def compatible_exp_record(record):
    return {
        "prompt_len": record["prompt_len"],
        "output_len": record["output_len"],
        "start_time": record["start_time"],
        "end_time": record["end_time"],
        "token_timestamps": record["token_timestamps"],
        "lifecycle_events": record.get("lifecycle_events", None),
    }


def summarize_records(records, args, wall_time_s):
    ok = [r for r in records if r.get("ok")]
    failed = [r for r in records if not r.get("ok")]
    slo_completed = [
        r for r in ok
        if (args.slo_ttft_s is None or r.get("ttft_s") is not None and r["ttft_s"] <= args.slo_ttft_s)
        and (args.slo_tpot_s is None or r.get("tpot_s") is not None and r["tpot_s"] <= args.slo_tpot_s)
    ]

    def is_slo_good(record):
        return (
            record.get("ok")
            and (args.slo_ttft_s is None or record.get("ttft_s") is not None and record["ttft_s"] <= args.slo_ttft_s)
            and (args.slo_tpot_s is None or record.get("tpot_s") is not None and record["tpot_s"] <= args.slo_tpot_s)
        )

    def summarize_bucket_rows(all_rows, completed_rows):
        good_rows = [r for r in completed_rows if is_slo_good(r)]
        failed_rows = [r for r in all_rows if not r.get("ok")]
        return {
            "count": len(completed_rows),
            "submitted": len(all_rows),
            "completed": len(completed_rows),
            "failed": len(failed_rows),
            "goodput": len(good_rows),
            "slo_attainment_completed": (
                len(good_rows) / len(completed_rows) if completed_rows else None
            ),
            "slo_attainment_submitted": (
                len(good_rows) / len(all_rows) if all_rows else None
            ),
            "prompt_len": summarize([r.get("prompt_len") for r in completed_rows]),
            "output_len": summarize([r.get("output_len") for r in completed_rows]),
            "ttft_s": summarize([r.get("ttft_s") for r in completed_rows]),
            "tpot_s": summarize([r.get("tpot_s") for r in completed_rows]),
            "latency_s": summarize([r.get("latency_s") for r in completed_rows]),
            "e2e_per_output_token_s": summarize([
                r.get("e2e_per_output_token_s") for r in completed_rows
            ]),
            "decode_per_output_token_s": summarize([
                r.get("decode_per_output_token_s") for r in completed_rows
            ]),
            "context_queue_s": summarize([r.get("context_queue_s") for r in completed_rows]),
            "context_exec_s": summarize([r.get("context_exec_s") for r in completed_rows]),
            "bridge_queue_s": summarize([r.get("bridge_queue_s") for r in completed_rows]),
            "migration_s": summarize([r.get("migration_s") for r in completed_rows]),
            "decode_queue_s": summarize([r.get("decode_queue_s") for r in completed_rows]),
            "decode_exec_s": summarize([r.get("decode_exec_s") for r in completed_rows]),
        }

    bucket_summary = {}
    for bucket_key in ["prompt_bucket", "output_bucket"]:
        bucket_summary[bucket_key] = {}
        for bucket in sorted({r[bucket_key] for r in records}):
            all_rows = [r for r in records if r[bucket_key] == bucket]
            completed_rows = [r for r in ok if r[bucket_key] == bucket]
            bucket_summary[bucket_key][bucket] = summarize_bucket_rows(all_rows, completed_rows)
    if any(r.get("workload_phase") is not None for r in records):
        bucket_summary["workload_phase"] = {}
        for phase in sorted({r.get("workload_phase") for r in records if r.get("workload_phase")}):
            all_rows = [r for r in records if r.get("workload_phase") == phase]
            completed_rows = [r for r in ok if r.get("workload_phase") == phase]
            bucket_summary["workload_phase"][phase] = summarize_bucket_rows(all_rows, completed_rows)

    phase_rates = [r.get("phase_request_rate") for r in records if r.get("phase_request_rate")]
    effective_offered_req_s = None
    if phase_rates:
        effective_offered_req_s = len(phase_rates) / sum(1.0 / r for r in phase_rates if r > 0)

    return {
        "throughput": {
            "offered_req_s": (
                effective_offered_req_s
                if effective_offered_req_s is not None
                else args.request_rate if args.request_rate not in [float("inf"), 0.0] else None
            ),
            "submitted_req_s": len(records) / wall_time_s if wall_time_s > 0 else None,
            "completed_req_s": len(ok) / wall_time_s if wall_time_s > 0 else None,
            "goodput_req_s": len(slo_completed) / wall_time_s if wall_time_s > 0 else None,
            "per_gpu_completed_req_s": (
                len(ok) / wall_time_s / args.num_gpus
                if wall_time_s > 0 and args.num_gpus > 0 else None
            ),
            "per_gpu_goodput_req_s": (
                len(slo_completed) / wall_time_s / args.num_gpus
                if wall_time_s > 0 and args.num_gpus > 0 else None
            ),
            "input_tokens_s": (
                sum(r["prompt_len"] for r in ok) / wall_time_s
                if wall_time_s > 0 else None
            ),
            "requested_output_tokens_s": (
                sum(r["output_len"] for r in ok) / wall_time_s
                if wall_time_s > 0 else None
            ),
            "generated_output_tokens_s": (
                sum(r.get("num_token_timestamps", 0) for r in ok) / wall_time_s
                if wall_time_s > 0 else None
            ),
            "total_generated_tokens_s": (
                sum(r["prompt_len"] + r.get("num_token_timestamps", 0) for r in ok) / wall_time_s
                if wall_time_s > 0 else None
            ),
            "num_gpus": args.num_gpus,
        },
        "metadata": {
            "label": args.label,
            "policy": args.policy,
            "model": args.model,
            "dataset": args.dataset,
            "output": args.output,
            "raw_output": args.raw_output,
            "summary_output": args.summary_output,
            "num_prompts": args.num_prompts,
            "sample_mode": args.sample_mode,
            "request_rate": args.request_rate,
            "request_cv": args.request_cv,
            "process_name": args.process_name,
            "request_metadata": args.request_metadata,
            "request_metadata_profile": getattr(args, "request_metadata_profile", None),
            "request_metadata_phases": getattr(args, "request_metadata_phases", None),
            "phase_rate_schedule": args.phase_rate_schedule,
            "phase_rate_scale": args.phase_rate_scale,
            "seed": args.seed,
            "max_connections": args.max_connections,
            "timeout_s": args.timeout_s,
            "max_total_tokens": args.max_total_tokens,
            "num_gpus": args.num_gpus,
            "slo_ttft_s": args.slo_ttft_s,
            "slo_tpot_s": args.slo_tpot_s,
            "phase_metrics": args.phase_metrics,
        },
        "wall_time_s": wall_time_s,
        "submitted": len(records),
        "completed": len(ok),
        "failed": len(failed),
        "goodput": len(slo_completed),
        "throughput_req_s": len(ok) / wall_time_s if wall_time_s > 0 else None,
        "goodput_req_s": len(slo_completed) / wall_time_s if wall_time_s > 0 else None,
        "failure_rate": len(failed) / len(records) if records else None,
        "slo_attainment_completed": len(slo_completed) / len(ok) if ok else None,
        "slo_attainment_submitted": len(slo_completed) / len(records) if records else None,
        "latency_s": summarize([r.get("latency_s") for r in ok]),
        "ttft_s": summarize([r.get("ttft_s") for r in ok]),
        "tpot_s": summarize([r.get("tpot_s") for r in ok]),
        "context_queue_s": summarize([r.get("context_queue_s") for r in ok]),
        "context_exec_s": summarize([r.get("context_exec_s") for r in ok]),
        "bridge_queue_s": summarize([r.get("bridge_queue_s") for r in ok]),
        "migration_s": summarize([r.get("migration_s") for r in ok]),
        "decode_queue_s": summarize([r.get("decode_queue_s") for r in ok]),
        "decode_exec_s": summarize([r.get("decode_exec_s") for r in ok]),
        "buckets": bucket_summary,
        "errors": [r for r in failed[:20]],
        "phase_metrics": summarize_phase_metrics(args.phase_metrics),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--num-prompts", type=int, default=16)
    parser.add_argument("--sample-mode", choices=["random", "first"], default="random")
    parser.add_argument("--request-rate", type=float, default=2.0)
    parser.add_argument("--request-cv", type=float, default=1.0)
    parser.add_argument("--process-name", choices=["uniform", "gamma", "possion", "poisson"], default="uniform")
    parser.add_argument(
        "--request-metadata",
        help="Optional JSON sidecar with per-request workload phase metadata",
    )
    parser.add_argument(
        "--phase-rate-schedule",
        help="Optional comma-separated phase:rate entries overriding global --request-rate",
    )
    parser.add_argument(
        "--phase-rate-scale",
        type=float,
        default=1.0,
        help="Multiplier applied to --phase-rate-schedule or metadata request rates",
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-connections", type=int, default=16)
    parser.add_argument("--timeout-s", type=float, default=3600)
    parser.add_argument("--max-total-tokens", type=int, default=2048, help="0 disables the check")
    parser.add_argument("--num-gpus", type=int, default=1, help="Used for per-GPU throughput/goodput")
    parser.add_argument("--output", required=True)
    parser.add_argument("--raw-output")
    parser.add_argument("--summary-output")
    parser.add_argument("--label", default="benchmark")
    parser.add_argument("--policy", default="unknown")
    parser.add_argument("--model", default="unknown")
    parser.add_argument("--slo-ttft-s", type=float)
    parser.add_argument("--slo-tpot-s", type=float)
    parser.add_argument(
        "--phase-metrics",
        help="Optional PHASESERVE_METRICS_PATH JSONL file to summarize with the benchmark output",
    )
    args = parser.parse_args()

    start = time.time()
    records = asyncio.run(benchmark(args))
    end = time.time()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as f:
        json.dump([compatible_exp_record(r) for r in records if r.get("ok")], f)

    raw_output = Path(args.raw_output) if args.raw_output else output_path.with_suffix(".jsonl")
    raw_output.parent.mkdir(parents=True, exist_ok=True)
    with raw_output.open("w") as f:
        for record in sorted(records, key=lambda x: x["request_id"]):
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    args.raw_output = str(raw_output)
    summary_output = (
        Path(args.summary_output)
        if args.summary_output
        else output_path.with_suffix(".summary.json")
    )
    args.summary_output = str(summary_output)
    summary = summarize_records(records, args, end - start)
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Total time: {end - start:.2f} s")
    print(f"Completed: {summary['completed']}/{summary['submitted']} requests")
    print(
        "Throughput submitted/completed/goodput: "
        f"{summary['throughput']['submitted_req_s']:.2f}/"
        f"{summary['throughput']['completed_req_s']:.2f}/"
        f"{summary['throughput']['goodput_req_s']:.2f} requests/s"
    )
    print(
        "Token throughput input/generated/total: "
        f"{summary['throughput']['input_tokens_s']:.2f}/"
        f"{summary['throughput']['generated_output_tokens_s']:.2f}/"
        f"{summary['throughput']['total_generated_tokens_s']:.2f} tokens/s"
    )
    print(
        "TTFT median/p90/p95/p99: "
        f"{summary['ttft_s']['median']}/{summary['ttft_s']['p90']}/"
        f"{summary['ttft_s']['p95']}/{summary['ttft_s']['p99']}"
    )
    print(
        "TPOT median/p90/p95/p99: "
        f"{summary['tpot_s']['median']}/{summary['tpot_s']['p90']}/"
        f"{summary['tpot_s']['p95']}/{summary['tpot_s']['p99']}"
    )
    if args.slo_ttft_s is not None or args.slo_tpot_s is not None:
        print(
            "SLO attainment completed/submitted: "
            f"{summary['slo_attainment_completed']}/{summary['slo_attainment_submitted']}"
        )
    print(f"Output: {output_path}")
    print(f"Raw output: {raw_output}")
    print(f"Summary: {summary_output}")


if __name__ == "__main__":
    main()
