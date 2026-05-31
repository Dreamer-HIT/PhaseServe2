#!/usr/bin/env python3
import argparse
import json
import marshal
from pathlib import Path


def prompt_size(req) -> int:
    if isinstance(req, tuple):
        return int(req[1])
    return int(req.get("prompt_len") or len(req.get("prompt", "")))


def output_len(req) -> int:
    if isinstance(req, tuple):
        return int(req[2])
    return int(req.get("output_len") or req.get("max_tokens"))


def percentile(values, q: float):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[int(q * (len(ordered) - 1))]


def bucket(value: int, edges):
    for edge in edges:
        if value <= edge:
            return f"<= {edge}"
    return f"> {edges[-1]}"


def build_order(reqs):
    idxs = list(range(len(reqs)))
    by_prompt = sorted(idxs, key=lambda i: prompt_size(reqs[i]), reverse=True)
    by_output = sorted(idxs, key=lambda i: output_len(reqs[i]), reverse=True)
    by_short_prompt_long_output = sorted(
        idxs,
        key=lambda i: (prompt_size(reqs[i]), -output_len(reqs[i])),
    )
    sources = [by_prompt, by_output, by_short_prompt_long_output]
    used = set()
    ordered = []
    while len(ordered) < len(reqs):
        progressed = False
        for source in sources:
            while source and source[0] in used:
                source.pop(0)
            if not source:
                continue
            idx = source.pop(0)
            used.add(idx)
            ordered.append(idx)
            progressed = True
            if len(ordered) >= len(reqs):
                break
        if not progressed:
            break
    return ordered


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Create a ShareGPT-derived mixed-order trace by keeping the same "
            "request multiset and reordering long-prompt, long-output, and "
            "short-prompt/long-output requests into alternating pressure waves."
        )
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--metadata-output", type=Path)
    parser.add_argument("--num-requests", type=int, default=128)
    parser.add_argument("--min-output-tokens", type=int, default=1)
    parser.add_argument("--max-output-tokens", type=int, default=0)
    parser.add_argument("--max-total-tokens", type=int, default=0)
    parser.add_argument("--name", default="sharegpt-firstN-mixed-order")
    args = parser.parse_args()

    with args.input.open("rb") as f:
        data = marshal.load(f)
    source_reqs = []
    dropped = {
        "min_output": 0,
        "max_output": 0,
        "max_total": 0,
    }
    for req in data["reqs"]:
        req_output_len = output_len(req)
        req_prompt_len = prompt_size(req)
        if req_output_len < args.min_output_tokens:
            dropped["min_output"] += 1
            continue
        if args.max_output_tokens > 0 and req_output_len > args.max_output_tokens:
            dropped["max_output"] += 1
            continue
        if args.max_total_tokens > 0 and req_prompt_len + req_output_len > args.max_total_tokens:
            dropped["max_total"] += 1
            continue
        source_reqs.append(req)
        if len(source_reqs) >= args.num_requests:
            break
    ordered = build_order(source_reqs)
    selected = [source_reqs[i] for i in ordered]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("wb") as f:
        marshal.dump({"dataset_name": args.name, "reqs": selected}, f)

    prompt_lengths = [prompt_size(req) for req in selected]
    output_lengths = [output_len(req) for req in selected]
    request_rows = []
    for index, req in enumerate(selected):
        req_prompt_len = prompt_size(req)
        req_output_len = output_len(req)
        request_rows.append({
            "source_index": index,
            "phase": "sharegpt_mixed_order",
            "phase_index": 0,
            "phase_request_index": index,
            "request_rate": None,
            "prompt_len": req_prompt_len,
            "output_len": req_output_len,
            "prompt_bucket": bucket(req_prompt_len, [64, 128, 256, 512, 1024, 2048, 4096]),
            "output_bucket": bucket(req_output_len, [16, 64, 128, 256, 512, 1024]),
        })
    metadata = {
        "source": str(args.input),
        "output": str(args.output),
        "name": args.name,
        "num_requests": len(selected),
        "filters": {
            "min_output_tokens": args.min_output_tokens,
            "max_output_tokens": args.max_output_tokens,
            "max_total_tokens": args.max_total_tokens,
            "dropped_before_selection": dropped,
        },
        "construction": (
            "first N ShareGPT requests after filters; reordered by interleaving "
            "long-prompt, long-output, and short-prompt/long-output requests"
        ),
        "prompt_tokens": {
            "min": min(prompt_lengths) if prompt_lengths else None,
            "p50": percentile(prompt_lengths, 0.50),
            "p90": percentile(prompt_lengths, 0.90),
            "max": max(prompt_lengths) if prompt_lengths else None,
        },
        "output_tokens": {
            "min": min(output_lengths) if output_lengths else None,
            "p50": percentile(output_lengths, 0.50),
            "p90": percentile(output_lengths, 0.90),
            "max": max(output_lengths) if output_lengths else None,
        },
        "requests": request_rows,
    }
    metadata_output = args.metadata_output or args.output.with_suffix(".metadata.json")
    metadata_output.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
