#!/usr/bin/env python3
import argparse
import csv
import json
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from transformers import AutoTokenizer

sys.path.insert(0, "/root/data/DistServe/evaluation/2-benchmark-serving")
from structs import Dataset, TestRequest  # noqa: E402


PROMPT_TEXT = (
    "In a distributed large language model serving system, the scheduler must "
    "balance prefill work, decode work, key value cache residency, migration "
    "latency, and service level objectives for interactive applications. "
)


def read_records(path: Path) -> List[Dict[str, Any]]:
    if path.is_dir():
        records: List[Dict[str, Any]] = []
        for child in sorted(path.rglob("*")):
            if child.suffix.lower() in [".json", ".jsonl", ".csv", ".tsv"]:
                records.extend(read_records(child))
        return records
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        records = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ["data", "train", "validation", "test", "records", "examples"]:
                value = data.get(key)
                if isinstance(value, list):
                    return value
            if all(isinstance(value, dict) for value in data.values()):
                return list(data.values())
        raise ValueError(f"Unsupported JSON structure in {path}")
    if suffix in [".csv", ".tsv"]:
        delimiter = "\t" if suffix == ".tsv" else ","
        with path.open("r", encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f, delimiter=delimiter))
    raise ValueError(f"Unsupported trace format: {path.suffix}")


def nested_get(record: Dict[str, Any], path: str) -> Any:
    current: Any = record
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def first_field(record: Dict[str, Any], fields: Iterable[str]) -> Any:
    for field in fields:
        value = nested_get(record, field)
        if value not in [None, ""]:
            return value
    return None


def text_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        parts = [text_value(item) for item in value]
        parts = [part for part in parts if part]
        return "\n".join(parts) if parts else None
    if isinstance(value, dict):
        for key in ["value", "content", "text", "answer", "summary", "output"]:
            if key in value:
                return text_value(value[key])
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def parse_int(value: Any) -> Optional[int]:
    if value in [None, ""]:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def message_role(message: Dict[str, Any]) -> str:
    role = message.get("from", message.get("role", message.get("user", "")))
    return str(role).lower()


def message_content(message: Dict[str, Any]) -> Optional[str]:
    return text_value(first_field(message, ["value", "content", "text"]))


def extract_sharegpt(record: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    conversations = first_field(record, ["conversations", "conversation", "messages"])
    if isinstance(conversations, list):
        pending_prompt = None
        for message in conversations:
            if not isinstance(message, dict):
                continue
            role = message_role(message)
            content = message_content(message)
            if not content:
                continue
            if role in ["human", "user", "prompter"]:
                pending_prompt = content
            elif role in ["gpt", "assistant", "model"] and pending_prompt:
                return pending_prompt, content
    prompt = text_value(first_field(record, ["prompt", "instruction", "input", "question"]))
    output = text_value(first_field(record, ["response", "answer", "output", "completion"]))
    return prompt, output


def extract_longbench(record: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    context = text_value(first_field(record, ["context", "passage", "document", "article"]))
    query = text_value(first_field(record, ["input", "question", "query", "prompt"]))
    parts = [part for part in [context, query] if part]
    prompt = "\n\n".join(parts) if parts else None
    output = text_value(first_field(record, ["answers", "answer", "summary", "output"]))
    return prompt, output


def extract_generic(
    record: Dict[str, Any],
    prompt_field: Optional[str],
    output_field: Optional[str],
) -> Tuple[Optional[str], Optional[str]]:
    prompt_fields = [prompt_field] if prompt_field else []
    prompt_fields += ["prompt", "input", "question", "instruction", "context"]
    output_fields = [output_field] if output_field else []
    output_fields += ["output", "response", "answer", "answers", "completion", "summary"]
    return (
        text_value(first_field(record, prompt_fields)),
        text_value(first_field(record, output_fields)),
    )


def make_prompt(tokenizer, target_len: int) -> str:
    text = PROMPT_TEXT
    while len(tokenizer.encode(text, add_special_tokens=False)) < target_len:
        text += PROMPT_TEXT
    token_ids = tokenizer.encode(text, add_special_tokens=False)[:target_len]
    return tokenizer.decode(token_ids, skip_special_tokens=True)


def clamp_prompt(tokenizer, text: str, max_prompt_tokens: int) -> Tuple[str, int]:
    token_ids = tokenizer.encode(text, add_special_tokens=False)
    if max_prompt_tokens > 0 and len(token_ids) > max_prompt_tokens:
        token_ids = token_ids[:max_prompt_tokens]
        text = tokenizer.decode(token_ids, skip_special_tokens=True)
    return text, len(token_ids)


def token_count(tokenizer, text: Optional[str]) -> int:
    if not text:
        return 0
    return len(tokenizer.encode(text, add_special_tokens=False))


def choose_records(records: List[Dict[str, Any]], num_requests: int, sample_mode: str, seed: int):
    if sample_mode == "first":
        return list(enumerate(records[:num_requests]))
    rng = random.Random(seed)
    indexed = list(enumerate(records))
    if num_requests >= len(indexed):
        rng.shuffle(indexed)
        return indexed
    return rng.sample(indexed, num_requests)


def bucket(value: int, boundaries: List[int]) -> str:
    low = 0
    for high in boundaries:
        if value <= high:
            return f"({low},{high}]"
        low = high
    return f">{boundaries[-1]}"


def build_dataset(args) -> Tuple[Dataset, Dict[str, Any]]:
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer, use_fast=True)
    input_path = Path(args.input)
    records = read_records(input_path)
    rng = random.Random(args.seed)
    requests: List[TestRequest] = []
    metadata_rows = []
    dropped = Counter()

    for source_index, record in choose_records(records, len(records), args.sample_mode, args.seed):
        prompt_cap = args.max_prompt_tokens
        if args.target_prompt_min > 0 and args.target_prompt_max > 0:
            prompt_cap = rng.randint(args.target_prompt_min, args.target_prompt_max)
        prompt_len = parse_int(nested_get(record, args.prompt_len_field)) if args.prompt_len_field else None
        output_len = parse_int(nested_get(record, args.output_len_field)) if args.output_len_field else None
        prompt_text = None
        output_text = None

        if args.source == "sharegpt":
            prompt_text, output_text = extract_sharegpt(record)
        elif args.source == "longbench":
            prompt_text, output_text = extract_longbench(record)
        elif args.source == "lengths":
            pass
        else:
            prompt_text, output_text = extract_generic(
                record,
                args.prompt_field,
                args.output_field,
            )

        if prompt_len is None and prompt_text:
            prompt_text, prompt_len = clamp_prompt(tokenizer, prompt_text, prompt_cap)
        if output_len is None:
            output_len = token_count(tokenizer, output_text)
        if output_len is None or output_len <= 0:
            output_len = args.default_output_len
        if prompt_len is None or prompt_len <= 0:
            dropped["missing_prompt"] += 1
            continue

        if prompt_cap > 0 and prompt_len > prompt_cap:
            prompt_len = prompt_cap
            if prompt_text:
                prompt_text, _ = clamp_prompt(tokenizer, prompt_text, prompt_cap)
        if args.max_output_tokens > 0 and output_len > args.max_output_tokens:
            output_len = args.max_output_tokens
        if args.max_total_tokens > 0 and prompt_len + output_len > args.max_total_tokens:
            output_len = args.max_total_tokens - prompt_len
        if prompt_len < args.min_prompt_tokens:
            dropped["short_prompt"] += 1
            continue
        if output_len < args.min_output_tokens:
            dropped["short_output"] += 1
            continue

        if args.length_only_prompts or not prompt_text:
            prompt_text = make_prompt(tokenizer, prompt_len)
            prompt_len = len(tokenizer.encode(prompt_text, add_special_tokens=False))

        requests.append(TestRequest(prompt_text, prompt_len, output_len))
        metadata_rows.append({
            "source_index": source_index,
            "phase": args.source,
            "phase_index": 0,
            "phase_request_index": len(metadata_rows),
            "request_rate": None,
            "prompt_len": prompt_len,
            "output_len": output_len,
            "target_prompt_cap": prompt_cap,
            "prompt_bucket": bucket(prompt_len, [64, 128, 256, 512, 1024, 2048, 4096]),
            "output_bucket": bucket(output_len, [16, 64, 128, 256, 512, 1024]),
        })
        if len(requests) >= args.num_requests:
            break

    if len(requests) < args.num_requests:
        raise ValueError(
            f"Only built {len(requests)} requests from {input_path}; "
            f"requested {args.num_requests}. Dropped={dict(dropped)}"
        )

    prompt_counts = Counter(row["prompt_bucket"] for row in metadata_rows)
    output_counts = Counter(row["output_bucket"] for row in metadata_rows)
    metadata = {
        "name": args.name,
        "source": args.source,
        "input": str(input_path),
        "tokenizer": args.tokenizer,
        "sample_mode": args.sample_mode,
        "seed": args.seed,
        "num_requests": len(requests),
        "length_only_prompts": args.length_only_prompts,
        "filters": {
            "min_prompt_tokens": args.min_prompt_tokens,
            "max_prompt_tokens": args.max_prompt_tokens,
            "target_prompt_min": args.target_prompt_min,
            "target_prompt_max": args.target_prompt_max,
            "min_output_tokens": args.min_output_tokens,
            "max_output_tokens": args.max_output_tokens,
            "max_total_tokens": args.max_total_tokens,
        },
        "dropped": dict(dropped),
        "prompt_buckets": dict(sorted(prompt_counts.items())),
        "output_buckets": dict(sorted(output_counts.items())),
        "phases": [{
            "name": args.source,
            "phase_index": 0,
            "count": len(requests),
            "base_rate": None,
        }],
        "requests": metadata_rows,
    }
    return Dataset(args.name, requests), metadata


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--tokenizer", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--metadata-output", required=True)
    parser.add_argument(
        "--source",
        choices=["generic", "sharegpt", "longbench", "lengths"],
        default="generic",
    )
    parser.add_argument("--num-requests", type=int, default=256)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--sample-mode", choices=["first", "random"], default="random")
    parser.add_argument("--prompt-field")
    parser.add_argument("--output-field")
    parser.add_argument("--prompt-len-field", default="prompt_len")
    parser.add_argument("--output-len-field", default="output_len")
    parser.add_argument("--min-prompt-tokens", type=int, default=1)
    parser.add_argument("--max-prompt-tokens", type=int, default=4096)
    parser.add_argument("--target-prompt-min", type=int, default=0)
    parser.add_argument("--target-prompt-max", type=int, default=0)
    parser.add_argument("--min-output-tokens", type=int, default=1)
    parser.add_argument("--max-output-tokens", type=int, default=1024)
    parser.add_argument("--max-total-tokens", type=int, default=0)
    parser.add_argument("--default-output-len", type=int, default=128)
    parser.add_argument("--length-only-prompts", action="store_true")
    parser.add_argument("--name", default="phaseserve-trace")
    args = parser.parse_args()

    dataset, metadata = build_dataset(args)
    output_path = Path(args.output)
    metadata_path = Path(args.metadata_output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    dataset.dump(str(output_path))
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Wrote {len(dataset.reqs)} requests to {output_path}")
    print(f"Wrote request metadata to {metadata_path}")
    print(f"Prompt buckets: {metadata['prompt_buckets']}")
    print(f"Output buckets: {metadata['output_buckets']}")


if __name__ == "__main__":
    main()
