#!/usr/bin/env python3
import argparse
import asyncio
import json
import random
import sys
import time
from pathlib import Path
from typing import AsyncGenerator, List

import aiohttp
import numpy as np

sys.path.insert(0, "/root/data/DistServe/evaluation/2-benchmark-serving")
from structs import Dataset, TestRequest, RequestResult  # noqa: E402


async def get_request(
    input_requests: List[TestRequest],
    process_name: str,
    request_rate: float,
    cv: float,
) -> AsyncGenerator[TestRequest, None]:
    if request_rate not in [float("inf"), 0.0]:
        if process_name == "uniform":
            intervals = [1.0 / request_rate for _ in input_requests]
        elif process_name in ["gamma", "possion"]:
            if process_name == "possion":
                cv = 1.0
            shape = 1 / (cv * cv)
            scale = cv * cv / request_rate
            intervals = np.random.gamma(shape, scale, size=len(input_requests))
        else:
            raise ValueError(f"Unsupported process name: {process_name}")
    else:
        intervals = [0.0 for _ in input_requests]

    for idx, request in enumerate(input_requests):
        yield request
        if request_rate not in [float("inf"), 0.0]:
            await asyncio.sleep(float(intervals[idx]))


async def send_request(session, api_url: str, request: TestRequest):
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
    assert request.prompt_len + request.output_len < 2048
    start = time.perf_counter()
    async with session.post(api_url, json=payload) as response:
        body = await response.read()
    end = time.perf_counter()
    if response.status != 200:
        raise RuntimeError(f"HTTP {response.status}: {body[:200]!r}")
    output = json.loads(body.decode("utf-8"))
    if "error" in output:
        raise RuntimeError(output["error"])
    return RequestResult(
        request.prompt_len,
        request.output_len,
        start,
        end,
        token_timestamps=output["timestamps"],
        lifetime_events=output.get("lifetime_events", None),
    )


async def benchmark(args):
    dataset = Dataset.load(args.dataset)
    random.seed(args.seed)
    np.random.seed(args.seed)
    requests = random.sample(dataset.reqs, args.num_prompts)
    api_url = f"http://{args.host}:{args.port}/generate"
    timeout = aiohttp.ClientTimeout(total=args.timeout_s)
    connector = aiohttp.TCPConnector(limit=args.max_connections)
    tasks = []
    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        async for request in get_request(
            requests, args.process_name, args.request_rate, args.request_cv
        ):
            tasks.append(asyncio.create_task(send_request(session, api_url, request)))
        return await asyncio.gather(*tasks)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--num-prompts", type=int, default=16)
    parser.add_argument("--request-rate", type=float, default=2.0)
    parser.add_argument("--request-cv", type=float, default=1.0)
    parser.add_argument("--process-name", choices=["uniform", "gamma", "possion"], default="uniform")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-connections", type=int, default=16)
    parser.add_argument("--timeout-s", type=float, default=3600)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    start = time.time()
    results = asyncio.run(benchmark(args))
    end = time.time()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as f:
        json.dump(results, f, default=vars)
    print(f"Total time: {end - start:.2f} s")
    print(f"Throughput: {len(results) / (end - start):.2f} requests/s")
    print(f"Output: {output_path}")


if __name__ == "__main__":
    main()
