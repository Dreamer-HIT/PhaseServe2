#!/usr/bin/env python3
import argparse
import random
import sys
from pathlib import Path

from transformers import AutoTokenizer

sys.path.insert(0, "/root/data/DistServe/evaluation/2-benchmark-serving")
from structs import Dataset, TestRequest  # noqa: E402


PROMPT_TEXT = (
    "In a distributed large language model serving system, the scheduler must "
    "balance prefill work, decode work, key value cache residency, migration "
    "latency, and service level objectives for interactive applications. "
)


def make_prompt(tokenizer, target_len: int) -> str:
    text = PROMPT_TEXT
    while len(tokenizer.encode(text, add_special_tokens=False)) < target_len:
        text += PROMPT_TEXT
    token_ids = tokenizer.encode(text, add_special_tokens=False)[:target_len]
    return tokenizer.decode(token_ids, skip_special_tokens=True)


def choose_from_mix(rng: random.Random, mix):
    draw = rng.random()
    cumulative = 0.0
    for value, weight in mix:
        cumulative += weight
        if draw <= cumulative:
            return value
    return mix[-1][0]


def parse_mix(spec: str):
    mix = []
    total = 0.0
    for item in spec.split(","):
        value, weight = item.split(":")
        weight = float(weight)
        mix.append((int(value), weight))
        total += weight
    if total <= 0:
        raise ValueError("mix weights must sum to a positive value")
    return [(value, weight / total) for value, weight in mix]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tokenizer", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--num-requests", type=int, default=48)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--prompt-mix",
        default="64:0.50,256:0.30,512:0.20",
        help="Comma-separated token_len:weight entries",
    )
    parser.add_argument(
        "--output-mix",
        default="64:0.30,128:0.30,256:0.20,512:0.15,1024:0.05",
        help="Comma-separated output_len:weight entries",
    )
    parser.add_argument("--name", default="phaseserve-synthetic-heterogeneous")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer, use_fast=True)
    prompt_mix = parse_mix(args.prompt_mix)
    output_mix = parse_mix(args.output_mix)

    prompt_cache = {}
    requests = []
    for _ in range(args.num_requests):
        prompt_len = choose_from_mix(rng, prompt_mix)
        output_len = choose_from_mix(rng, output_mix)
        if prompt_len not in prompt_cache:
            prompt_cache[prompt_len] = make_prompt(tokenizer, prompt_len)
        prompt = prompt_cache[prompt_len]
        actual_prompt_len = len(tokenizer.encode(prompt, add_special_tokens=False))
        requests.append(TestRequest(prompt, actual_prompt_len, output_len))

    rng.shuffle(requests)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    Dataset(args.name, requests).dump(str(output_path))

    prompt_counts = {}
    output_counts = {}
    for request in requests:
        prompt_counts[request.prompt_len] = prompt_counts.get(request.prompt_len, 0) + 1
        output_counts[request.output_len] = output_counts.get(request.output_len, 0) + 1
    print(f"Wrote {len(requests)} requests to {output_path}")
    print(f"Prompt lengths: {dict(sorted(prompt_counts.items()))}")
    print(f"Output lengths: {dict(sorted(output_counts.items()))}")


if __name__ == "__main__":
    main()
