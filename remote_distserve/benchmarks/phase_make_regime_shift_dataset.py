#!/usr/bin/env python3
import argparse
import json
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


PROFILES = {
    "cross_skew_v1": [
        {
            "name": "mixed_regime",
            "pair_mix": (
                "1536x32:0.18,1024x64:0.17,"
                "64x1024:0.18,256x512:0.17,"
                "512x256:0.15,64x32:0.15"
            ),
            "base_rate": 1.0,
        },
    ],
    "cross_decode_v1": [
        {
            "name": "mixed_decode_regime",
            "pair_mix": (
                "64x1024:0.28,256x512:0.22,512x512:0.15,"
                "1536x32:0.15,1024x64:0.10,64x32:0.10"
            ),
            "base_rate": 1.0,
        },
    ],
    "regime_shift_v1": [
        {
            "name": "prefill_skew",
            "prompt_mix": "64:0.45,512:0.25,1024:0.20,1536:0.10",
            "output_mix": "32:0.60,64:0.30,128:0.10",
            "base_rate": 6.0,
        },
        {
            "name": "decode_heavy",
            "prompt_mix": "64:0.60,256:0.25,512:0.15",
            "output_mix": "128:0.25,256:0.30,512:0.30,1024:0.15",
            "base_rate": 3.0,
        },
        {
            "name": "mixed_slo",
            "prompt_mix": "64:0.35,512:0.30,1024:0.20,1536:0.15",
            "output_mix": "64:0.20,128:0.30,512:0.30,1024:0.20",
            "base_rate": 4.0,
        },
        {
            "name": "prefill_recovery",
            "prompt_mix": "64:0.45,512:0.25,1024:0.20,1536:0.10",
            "output_mix": "32:0.60,64:0.30,128:0.10",
            "base_rate": 6.0,
        },
    ],
}


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


def parse_pair_mix(spec: str):
    mix = []
    total = 0.0
    for item in spec.split(","):
        pair, weight = item.split(":")
        prompt_len, output_len = pair.lower().split("x")
        weight = float(weight)
        mix.append(((int(prompt_len), int(output_len)), weight))
        total += weight
    if total <= 0:
        raise ValueError("pair mix weights must sum to a positive value")
    return [(value, weight / total) for value, weight in mix]


def parse_counts(spec: str, phases):
    counts = [int(item) for item in spec.split(",") if item.strip()]
    if len(counts) == 1:
        return counts * len(phases)
    if len(counts) != len(phases):
        raise ValueError(
            f"--phase-request-counts has {len(counts)} entries, "
            f"expected 1 or {len(phases)}"
        )
    return counts


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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tokenizer", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--metadata-output", required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--profile", choices=sorted(PROFILES), default="regime_shift_v1")
    parser.add_argument(
        "--phase-request-counts",
        default="24,24,24,24",
        help="Comma-separated request counts; one value applies to all phases",
    )
    parser.add_argument("--name", default="phaseserve-synthetic-regime-shift")
    parser.add_argument("--no-shuffle-within-phase", action="store_true")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer, use_fast=True)
    phases = PROFILES[args.profile]
    counts = parse_counts(args.phase_request_counts, phases)

    prompt_cache = {}
    request_meta_pairs = []
    for phase_index, (phase, count) in enumerate(zip(phases, counts)):
        pair_mix = parse_pair_mix(phase["pair_mix"]) if phase.get("pair_mix") else None
        prompt_mix = parse_mix(phase["prompt_mix"]) if phase.get("prompt_mix") else None
        output_mix = parse_mix(phase["output_mix"]) if phase.get("output_mix") else None
        phase_pairs = []
        for phase_request_index in range(count):
            if pair_mix is not None:
                prompt_len, output_len = choose_from_mix(rng, pair_mix)
            else:
                prompt_len = choose_from_mix(rng, prompt_mix)
                output_len = choose_from_mix(rng, output_mix)
            if prompt_len not in prompt_cache:
                prompt_cache[prompt_len] = make_prompt(tokenizer, prompt_len)
            prompt = prompt_cache[prompt_len]
            actual_prompt_len = len(tokenizer.encode(prompt, add_special_tokens=False))
            request = TestRequest(prompt, actual_prompt_len, output_len)
            metadata = {
                "phase": phase["name"],
                "phase_index": phase_index,
                "phase_request_index": phase_request_index,
                "prompt_mix": phase.get("prompt_mix"),
                "output_mix": phase.get("output_mix"),
                "pair_mix": phase.get("pair_mix"),
                "request_rate": phase["base_rate"],
                "prompt_len": actual_prompt_len,
                "output_len": output_len,
            }
            phase_pairs.append((request, metadata))
        if not args.no_shuffle_within_phase:
            rng.shuffle(phase_pairs)
            for idx, (_, metadata) in enumerate(phase_pairs):
                metadata["phase_request_index"] = idx
        request_meta_pairs.extend(phase_pairs)

    requests = [request for request, _ in request_meta_pairs]
    metadata_rows = [metadata for _, metadata in request_meta_pairs]

    output_path = Path(args.output)
    metadata_path = Path(args.metadata_output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    Dataset(args.name, requests).dump(str(output_path))
    metadata_path.write_text(
        json.dumps(
            {
                "name": args.name,
                "profile": args.profile,
                "phases": [
                    {
                        "name": phase["name"],
                        "phase_index": idx,
                        "count": count,
                        "prompt_mix": phase.get("prompt_mix"),
                        "output_mix": phase.get("output_mix"),
                        "pair_mix": phase.get("pair_mix"),
                        "base_rate": phase["base_rate"],
                    }
                    for idx, (phase, count) in enumerate(zip(phases, counts))
                ],
                "requests": metadata_rows,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(f"Wrote {len(requests)} requests to {output_path}")
    print(f"Wrote request metadata to {metadata_path}")
    for phase in phases:
        rows = [row for row in metadata_rows if row["phase"] == phase["name"]]
        prompt_counts = {}
        output_counts = {}
        for row in rows:
            prompt_counts[row["prompt_len"]] = prompt_counts.get(row["prompt_len"], 0) + 1
            output_counts[row["output_len"]] = output_counts.get(row["output_len"], 0) + 1
        print(
            f"{phase['name']}: prompts={dict(sorted(prompt_counts.items()))} "
            f"outputs={dict(sorted(output_counts.items()))} "
            f"base_rate={phase['base_rate']}"
        )


if __name__ == "__main__":
    main()
