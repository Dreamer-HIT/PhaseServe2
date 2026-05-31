#!/usr/bin/env python3
import argparse
import json
import random
import sys
from pathlib import Path
from typing import List

sys.path.insert(0, "/root/data/DistServe/evaluation/2-benchmark-serving")
from structs import Dataset  # noqa: E402


def bucket(value: int, boundaries: List[int]) -> str:
    low = 0
    for high in boundaries:
        if value <= high:
            return f"({low},{high}]"
        low = high
    return f">{boundaries[-1]}"


def percentile(values: List[int], q: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((len(ordered) - 1) * q)))
    return ordered[index]


def summarize(values: List[int]) -> dict:
    return {
        "min": min(values),
        "p50": percentile(values, 0.50),
        "p90": percentile(values, 0.90),
        "p99": percentile(values, 0.99),
        "max": max(values),
        "avg": sum(values) / len(values),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sample a fixed random subset from a DistServe .ds dataset."
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--metadata-output", required=True)
    parser.add_argument("--num-requests", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--name", default="phaseserve-sampled-distserve-dataset")
    parser.add_argument("--source", default="sharegpt_processed")
    args = parser.parse_args()

    dataset = Dataset.load(args.input)
    if args.num_requests > len(dataset.reqs):
        raise ValueError(
            f"--num-requests={args.num_requests} exceeds dataset size {len(dataset.reqs)}"
        )

    rng = random.Random(args.seed)
    source_indices = rng.sample(range(len(dataset.reqs)), args.num_requests)
    requests = [dataset.reqs[index] for index in source_indices]

    output_path = Path(args.output)
    metadata_path = Path(args.metadata_output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    Dataset(args.name, requests).dump(str(output_path))

    rows = []
    for request_index, (source_index, request) in enumerate(zip(source_indices, requests)):
        rows.append({
            "source_index": source_index,
            "phase": args.source,
            "phase_index": 0,
            "phase_request_index": request_index,
            "request_rate": None,
            "prompt_len": request.prompt_len,
            "output_len": request.output_len,
            "prompt_bucket": bucket(request.prompt_len, [64, 128, 256, 512, 1024, 2048, 4096]),
            "output_bucket": bucket(request.output_len, [16, 64, 128, 256, 512, 1024]),
        })

    prompt_lens = [request.prompt_len for request in requests]
    output_lens = [request.output_len for request in requests]
    metadata = {
        "name": args.name,
        "source": args.source,
        "input": args.input,
        "sample_mode": "random_subset_from_processed",
        "seed": args.seed,
        "num_requests": len(requests),
        "prompt_tokens": summarize(prompt_lens),
        "output_tokens": summarize(output_lens),
        "phases": [{
            "name": args.source,
            "phase_index": 0,
            "count": len(requests),
            "base_rate": None,
        }],
        "requests": rows,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Wrote {len(requests)} requests to {output_path}")
    print(f"Wrote metadata to {metadata_path}")
    print(f"Prompt tokens: {metadata['prompt_tokens']}")
    print(f"Output tokens: {metadata['output_tokens']}")


if __name__ == "__main__":
    main()
