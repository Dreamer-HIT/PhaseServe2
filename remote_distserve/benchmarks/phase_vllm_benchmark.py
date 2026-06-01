#!/usr/bin/env python3
"""Benchmark vLLM on PhaseServe/DistServe matched trace datasets.

The script intentionally mirrors ``phase_native_benchmark.py`` for metric
definitions, but obtains token timestamps from a vLLM streaming endpoint.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import math
import marshal
import random
import time
from pathlib import Path
from typing import AsyncGenerator, Dict, List, Optional, Tuple

import aiohttp
import numpy as np


PROMPT_BUCKETS = [64, 128, 256, 512, 1024, 2048, math.inf]
OUTPUT_BUCKETS = [16, 64, 128, 256, 512, math.inf]


@dataclasses.dataclass
class TestRequest:
    prompt: str
    prompt_len: int
    output_len: int


@dataclasses.dataclass
class Dataset:
    dataset_name: str
    reqs: List[TestRequest]

    @staticmethod
    def load(input_path: str):
        loaded_data = marshal.load(open(input_path, "rb"))
        return Dataset(
            loaded_data["dataset_name"],
            [TestRequest(req[0], req[1], req[2]) for req in loaded_data["reqs"]],
        )


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


def bucket_label(value: int, boundaries: List[float]) -> str:
    lower = 0
    for upper in boundaries:
        if value <= upper:
            if math.isinf(upper):
                return f">{lower}"
            return f"({lower},{int(upper)}]"
        lower = int(upper)
    return f">{lower}"


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


async def get_request(
    input_requests: List[TestRequest],
    process_name: str,
    request_rate: float,
    cv: float,
) -> AsyncGenerator[TestRequest, None]:
    for idx, request in enumerate(input_requests):
        yield request
        if idx + 1 < len(input_requests):
            interval = sample_interval(process_name, request_rate, cv)
            if interval > 0:
                await asyncio.sleep(interval)


def ok_record(
    request: TestRequest,
    request_id: int,
    scheduled_at: float,
    start: float,
    end: float,
    token_timestamps: List[float],
    generated_text: str,
):
    ttft = token_timestamps[0] - start if token_timestamps else None
    if len(token_timestamps) <= 1:
        tpot = 0.0 if token_timestamps else None
    else:
        tpot = (token_timestamps[-1] - token_timestamps[0]) / (len(token_timestamps) - 1)
    latency_s = end - start
    return {
        "request_id": request_id,
        "ok": True,
        "prompt_len": request.prompt_len,
        "output_len": request.output_len,
        "scheduled_at": scheduled_at,
        "start_time": start,
        "end_time": end,
        "latency_s": latency_s,
        "ttft_s": ttft,
        "tpot_s": tpot,
        "e2e_per_output_token_s": latency_s / max(request.output_len, 1),
        "decode_per_output_token_s": tpot,
        "num_token_timestamps": len(token_timestamps),
        "token_timestamps": token_timestamps,
        "generated_text_len": len(generated_text),
        "prompt_bucket": bucket_label(request.prompt_len, PROMPT_BUCKETS),
        "output_bucket": bucket_label(request.output_len, OUTPUT_BUCKETS),
    }


def failure_record(
    request: TestRequest,
    request_id: int,
    scheduled_at: float,
    start: float,
    error: str,
):
    end = time.perf_counter()
    return {
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


async def send_openai_stream_request(
    session: aiohttp.ClientSession,
    api_url: str,
    model: str,
    request: TestRequest,
    request_id: int,
    scheduled_at: float,
    max_total_tokens: int,
    ignore_eos: bool,
):
    payload = {
        "model": model,
        "prompt": request.prompt,
        "max_tokens": request.output_len,
        "temperature": 0.0,
        "top_p": 1.0,
        "stream": True,
    }
    if ignore_eos:
        payload["ignore_eos"] = True
    start = time.perf_counter()
    token_timestamps: List[float] = []
    generated_chunks: List[str] = []
    try:
        if max_total_tokens > 0 and request.prompt_len + request.output_len > max_total_tokens:
            raise ValueError(
                f"request total tokens {request.prompt_len + request.output_len} "
                f"exceeds --max-total-tokens={max_total_tokens}"
            )
        async with session.post(api_url, json=payload) as response:
            if response.status != 200:
                body = await response.read()
                raise RuntimeError(f"HTTP {response.status}: {body[:300]!r}")
            buffer = ""
            async for chunk in response.content.iter_any():
                now = time.perf_counter()
                buffer += chunk.decode("utf-8", "ignore")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if data == "[DONE]":
                        continue
                    obj = json.loads(data)
                    choice = (obj.get("choices") or [{}])[0]
                    text = choice.get("text") or ""
                    if text:
                        token_timestamps.append(now)
                        generated_chunks.append(text)
        end = time.perf_counter()
        if not token_timestamps:
            raise RuntimeError("stream completed without token chunks")
        return ok_record(
            request,
            request_id,
            scheduled_at,
            start,
            end,
            token_timestamps,
            "".join(generated_chunks),
        )
    except Exception as exc:  # noqa: BLE001
        return failure_record(request, request_id, scheduled_at, start, repr(exc))


async def send_generate_request(
    session: aiohttp.ClientSession,
    api_url: str,
    request: TestRequest,
    request_id: int,
    scheduled_at: float,
    max_total_tokens: int,
):
    payload = {
        "prompt": request.prompt,
        "n": 1,
        "best_of": 1,
        "use_beam_search": False,
        "temperature": 0.0,
        "top_p": 1.0,
        "max_tokens": request.output_len,
        "ignore_eos": True,
        "stream": True,
    }
    start = time.perf_counter()
    token_timestamps: List[float] = []
    previous_generated = ""
    try:
        if max_total_tokens > 0 and request.prompt_len + request.output_len > max_total_tokens:
            raise ValueError(
                f"request total tokens {request.prompt_len + request.output_len} "
                f"exceeds --max-total-tokens={max_total_tokens}"
            )
        async with session.post(api_url, json=payload) as response:
            if response.status != 200:
                body = await response.read()
                raise RuntimeError(f"HTTP {response.status}: {body[:300]!r}")
            buffer = b""
            async for chunk in response.content.iter_any():
                now = time.perf_counter()
                buffer += chunk
                while b"\0" in buffer:
                    raw, buffer = buffer.split(b"\0", 1)
                    raw = raw.strip()
                    if not raw:
                        continue
                    output = json.loads(raw.decode("utf-8"))
                    if "error" in output:
                        raise RuntimeError(output["error"])
                    text = (output.get("text") or [""])[0]
                    generated = text[len(request.prompt):] if text.startswith(request.prompt) else text
                    if len(generated) > len(previous_generated):
                        token_timestamps.append(now)
                        previous_generated = generated
        end = time.perf_counter()
        if not token_timestamps:
            raise RuntimeError("stream completed without token chunks")
        return ok_record(
            request,
            request_id,
            scheduled_at,
            start,
            end,
            token_timestamps,
            previous_generated,
        )
    except Exception as exc:  # noqa: BLE001
        return failure_record(request, request_id, scheduled_at, start, repr(exc))


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

    if args.endpoint == "openai":
        api_url = f"http://{args.host}:{args.port}/v1/completions"
    else:
        api_url = f"http://{args.host}:{args.port}/generate"
    timeout = aiohttp.ClientTimeout(total=args.timeout_s)
    connector = aiohttp.TCPConnector(limit=args.max_connections)
    tasks = []
    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        async for request in get_request(
            requests,
            args.process_name,
            args.request_rate,
            args.request_cv,
        ):
            scheduled_at = time.perf_counter()
            request_id = len(tasks)
            if args.endpoint == "openai":
                task = send_openai_stream_request(
                    session,
                    api_url,
                    args.served_model_name,
                    request,
                    request_id,
                    scheduled_at,
                    args.max_total_tokens,
                    args.ignore_eos,
                )
            else:
                task = send_generate_request(
                    session,
                    api_url,
                    request,
                    request_id,
                    scheduled_at,
                    args.max_total_tokens,
                )
            tasks.append(asyncio.create_task(task))
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

    def is_slo_good(record):
        return (
            record.get("ok")
            and (
                args.slo_ttft_s is None
                or record.get("ttft_s") is not None
                and record["ttft_s"] <= args.slo_ttft_s
            )
            and (
                args.slo_tpot_s is None
                or record.get("tpot_s") is not None
                and record["tpot_s"] <= args.slo_tpot_s
            )
        )

    slo_completed = [r for r in ok if is_slo_good(r)]
    return {
        "throughput": {
            "offered_req_s": args.request_rate
            if args.request_rate not in [float("inf"), 0.0]
            else None,
            "submitted_req_s": len(records) / wall_time_s if wall_time_s > 0 else None,
            "completed_req_s": len(ok) / wall_time_s if wall_time_s > 0 else None,
            "goodput_req_s": len(slo_completed) / wall_time_s if wall_time_s > 0 else None,
            "per_gpu_completed_req_s": (
                len(ok) / wall_time_s / args.num_gpus
                if wall_time_s > 0 and args.num_gpus > 0
                else None
            ),
            "per_gpu_goodput_req_s": (
                len(slo_completed) / wall_time_s / args.num_gpus
                if wall_time_s > 0 and args.num_gpus > 0
                else None
            ),
            "input_tokens_s": (
                sum(r["prompt_len"] for r in ok) / wall_time_s if wall_time_s > 0 else None
            ),
            "requested_output_tokens_s": (
                sum(r["output_len"] for r in ok) / wall_time_s if wall_time_s > 0 else None
            ),
            "generated_output_tokens_s": (
                sum(r.get("num_token_timestamps", 0) for r in ok) / wall_time_s
                if wall_time_s > 0
                else None
            ),
            "total_generated_tokens_s": (
                sum(r["prompt_len"] + r.get("num_token_timestamps", 0) for r in ok)
                / wall_time_s
                if wall_time_s > 0
                else None
            ),
            "num_gpus": args.num_gpus,
        },
        "metadata": {
            "label": args.label,
            "policy": args.policy,
            "model": args.model,
            "served_model_name": args.served_model_name,
            "dataset": args.dataset,
            "output": args.output,
            "raw_output": args.raw_output,
            "summary_output": args.summary_output,
            "num_prompts": args.num_prompts,
            "sample_mode": args.sample_mode,
            "request_rate": args.request_rate,
            "request_cv": args.request_cv,
            "process_name": args.process_name,
            "seed": args.seed,
            "max_connections": args.max_connections,
            "timeout_s": args.timeout_s,
            "max_total_tokens": args.max_total_tokens,
            "num_gpus": args.num_gpus,
            "slo_ttft_s": args.slo_ttft_s,
            "slo_tpot_s": args.slo_tpot_s,
            "endpoint": args.endpoint,
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
        "decode_per_output_token_s": summarize(
            [r.get("decode_per_output_token_s") for r in ok]
        ),
        "errors": [r for r in failed[:20]],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--num-prompts", type=int, default=16)
    parser.add_argument("--sample-mode", choices=["random", "first"], default="first")
    parser.add_argument("--request-rate", type=float, default=2.0)
    parser.add_argument("--request-cv", type=float, default=1.0)
    parser.add_argument(
        "--process-name",
        choices=["uniform", "gamma", "possion", "poisson"],
        default="poisson",
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-connections", type=int, default=16)
    parser.add_argument("--timeout-s", type=float, default=3600)
    parser.add_argument("--max-total-tokens", type=int, default=2048, help="0 disables the check")
    parser.add_argument("--num-gpus", type=int, default=1, help="Used for per-GPU throughput/goodput")
    parser.add_argument("--output", required=True)
    parser.add_argument("--raw-output")
    parser.add_argument("--summary-output")
    parser.add_argument("--label", default="vllm-benchmark")
    parser.add_argument("--policy", default="vllm")
    parser.add_argument("--model", default="unknown")
    parser.add_argument("--served-model-name", default="model")
    parser.add_argument("--slo-ttft-s", type=float)
    parser.add_argument("--slo-tpot-s", type=float)
    parser.add_argument("--endpoint", choices=["openai", "generate"], default="openai")
    parser.add_argument("--ignore-eos", action="store_true", default=True)
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
