#!/usr/bin/env python3
import argparse
import concurrent.futures
import http.client
import json
import math
import statistics
import time
import urllib.error
import urllib.request
from pathlib import Path


def percentile(values, pct):
    if not values:
        return None
    values = sorted(values)
    if len(values) == 1:
        return values[0]
    rank = (len(values) - 1) * pct / 100.0
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return values[int(rank)]
    return values[low] * (high - rank) + values[high] * (rank - low)


def summarize(values):
    values = [v for v in values if v is not None]
    if not values:
        return {}
    return {
        "count": len(values),
        "mean": statistics.mean(values),
        "p50": percentile(values, 50),
        "p90": percentile(values, 90),
        "p95": percentile(values, 95),
        "p99": percentile(values, 99),
        "max": max(values),
    }


def event_map(events):
    out = {}
    for event in events or []:
        out[event.get("event_type")] = event.get("timestamp")
    return out


def make_prompt(target_words, idx):
    base = (
        "You are evaluating a distributed LLM serving scheduler. "
        "Explain the scheduling tradeoff clearly and continue the pattern. "
    )
    filler = " latency throughput prefill decode cache fairness"
    words = (base + (filler * max(1, target_words // 6))).split()
    words = words[:target_words]
    return f"Request {idx}. " + " ".join(words)


def make_workload(num_requests):
    # Skew both prompt and output lengths. The actual tokenizer length is model
    # dependent, but this preserves the intended short/medium/long ordering.
    prompt_words = [32, 64, 96, 128, 192, 256, 384, 512]
    max_tokens = [8, 16, 24, 32, 8, 24, 16, 32]
    workload = []
    for i in range(num_requests):
        workload.append({
            "id": i,
            "prompt_words": prompt_words[i % len(prompt_words)],
            "max_tokens": max_tokens[i % len(max_tokens)],
            "prompt": make_prompt(prompt_words[i % len(prompt_words)], i),
        })
    return workload


def post_request(url, item, timeout_s):
    payload = {
        "prompt": item["prompt"],
        "stream": False,
        "temperature": 0.0,
        "ignore_eos": True,
        "max_tokens": item["max_tokens"],
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    client_start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read()
        client_end = time.time()
        data = json.loads(raw.decode("utf-8"))
        events = event_map(data.get("lifetime_events", []))
        timestamps = data.get("timestamps", [])
        issued = events.get("issued")
        context_begin = events.get("context_begin")
        context_end = events.get("context_end")
        migration_begin = events.get("migration_begin")
        migration_end = events.get("migration_end")
        decoding_begin = events.get("decoding_begin")
        decoding_end = events.get("decoding_end")
        output_tokens = len(timestamps)
        return {
            "id": item["id"],
            "ok": True,
            "prompt_words": item["prompt_words"],
            "max_tokens": item["max_tokens"],
            "output_tokens": output_tokens,
            "client_e2e_s": client_end - client_start,
            "ttft_s": context_end - issued if issued and context_end else None,
            "context_queue_s": context_begin - issued if issued and context_begin else None,
            "context_exec_s": context_end - context_begin if context_begin and context_end else None,
            "bridge_s": migration_begin - context_end if context_end and migration_begin else None,
            "migration_s": migration_end - migration_begin if migration_begin and migration_end else None,
            "decode_queue_s": decoding_begin - migration_end if migration_end and decoding_begin else None,
            "decode_exec_s": decoding_end - decoding_begin if decoding_begin and decoding_end else None,
            "tpot_s": (
                (timestamps[-1] - timestamps[0]) / (len(timestamps) - 1)
                if len(timestamps) > 1 else None
            ),
            "events": data.get("lifetime_events", []),
        }
    except (
        urllib.error.URLError,
        TimeoutError,
        json.JSONDecodeError,
        http.client.HTTPException,
        ConnectionError,
    ) as exc:
        client_end = time.time()
        return {
            "id": item["id"],
            "ok": False,
            "prompt_words": item["prompt_words"],
            "max_tokens": item["max_tokens"],
            "client_e2e_s": client_end - client_start,
            "error": repr(exc),
        }


def run(args):
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    workload = make_workload(args.num_requests)
    results = []
    start = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = []
        for item in workload:
            futures.append(pool.submit(post_request, args.url, item, args.timeout_s))
            if args.arrival_rate > 0:
                time.sleep(1.0 / args.arrival_rate)
        for fut in concurrent.futures.as_completed(futures):
            result = fut.result()
            results.append(result)
            status = "ok" if result.get("ok") else "ERR"
            print(
                f"[{status}] id={result['id']} prompt_words={result['prompt_words']} "
                f"max_tokens={result['max_tokens']} e2e={result.get('client_e2e_s'):.3f}s"
            )
    end = time.time()
    results = sorted(results, key=lambda x: x["id"])

    raw_path = output_dir / f"{args.label}_raw.jsonl"
    with raw_path.open("w") as f:
        for row in results:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    ok = [r for r in results if r.get("ok")]
    summary = {
        "label": args.label,
        "url": args.url,
        "num_requests": args.num_requests,
        "concurrency": args.concurrency,
        "arrival_rate": args.arrival_rate,
        "wall_time_s": end - start,
        "ok": len(ok),
        "failed": len(results) - len(ok),
        "client_e2e_s": summarize([r.get("client_e2e_s") for r in ok]),
        "ttft_s": summarize([r.get("ttft_s") for r in ok]),
        "tpot_s": summarize([r.get("tpot_s") for r in ok]),
        "context_queue_s": summarize([r.get("context_queue_s") for r in ok]),
        "context_exec_s": summarize([r.get("context_exec_s") for r in ok]),
        "decode_queue_s": summarize([r.get("decode_queue_s") for r in ok]),
        "decode_exec_s": summarize([r.get("decode_exec_s") for r in ok]),
    }

    summary_path = output_dir / f"{args.label}_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"RAW={raw_path}")
    print(f"SUMMARY={summary_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000/generate")
    parser.add_argument("--label", required=True)
    parser.add_argument("--output-dir", default="/root/data/phase_scheduler_results")
    parser.add_argument("--num-requests", type=int, default=24)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--arrival-rate", type=float, default=4.0)
    parser.add_argument("--timeout-s", type=float, default=180.0)
    run(parser.parse_args())
