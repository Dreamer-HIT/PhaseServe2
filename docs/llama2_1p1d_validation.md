# LLaMA2-7B 1P1D 初步验证记录

日期：2026-05-26

目标：在 DistServe 上用 `1p1d + LLaMA2-7B` 初步验证 `PS-Prefill` 与 `PS-Decode` 的最小可运行实现。

## 实现状态

已在远端 `/root/data/DistServe` 中实现可开关 scheduler：

- `ContextStageCostCompatibleScheduler`
- `DecodingStageKVAwareLASScheduler`

新增策略名：

- context: `cost-compatible` / `cost-compatible-prefill` / `phase`
- decoding: `kv-aware-las` / `kv-aware-las-decode` / `phase`

启动时使用：

```text
--context-sched-policy phase
--decoding-sched-policy phase
```

权重转换缓存固定在数据盘：

```text
DISTSERVE_CACHE=/root/data/distserve-cache
```

否则 DistServe 会回退到系统盘 `~/.cache/distserve` 并重新转换权重。

## Benchmark 设计

参考 DistServe 自带 `evaluation/2-benchmark-serving/2-benchmark-serving.py`：

- 使用 `Dataset/TestRequest` marshal 数据格式。
- 使用 `aiohttp` 异步发送请求。
- 支持 uniform arrival process。
- 保存 `.exp` 结果文件。
- 统计 `latency`、`ftl`、`tpot`。

由于 LLaMA2-7B 在较长 prompt 并发时触发 SwiftTransformer worker 崩溃，本轮先使用 tiny controlled workload：

```text
prompt_len = 33 tokens
output_len in {8, 16, 24, 32}
```

结果路径：

```text
/root/data/phase_scheduler_results/native_fcfs_1p1d_llama2_tiny/
/root/data/phase_scheduler_results/native_phase_1p1d_llama2_tiny/
/root/data/phase_scheduler_results/native_compare_tiny_summary_all.json
```

## 初步结果

### 12 requests, 2 req/s

| policy | latency p95 | FTL p95 | TPOT p95 |
|---|---:|---:|---:|
| FCFS | 0.4344s | 0.0371s | 0.0162s |
| Phase | 0.4410s | 0.0380s | 0.0151s |

### 24 requests, 8 req/s

| policy | latency p95 | FTL p95 | TPOT p95 |
|---|---:|---:|---:|
| FCFS | 0.4565s | 0.0388s | 0.0157s |
| Phase | 0.4533s | 0.0207s | 0.0153s |

At 24 requests / 8 req/s, Phase slightly improves tail TPOT and FTL in this tiny workload. This is only a smoke-test signal, not a paper-quality result.

## Observed Stability Issue

LLaMA2-7B on this DistServe/SwiftTransformer path crashed under longer prompts:

- prompt around 838 tokens crashed decoding worker;
- prompt around 214 tokens crashed in FCFS baseline during repeated/benchmark requests.

Representative error:

```text
DECODING worker returned out-of-vocab token id 137438954496
CUDA illegal memory access
RayActorError: ParaWorker died unexpectedly
```

Further slicing showed:

- `max_tokens=1` and `max_tokens=2` on a 214-token prompt can succeed.
- Repeated benchmark requests can make the decoding worker return invalid token ids such as `137438954496` and `140174847640576`.
- Once the invalid token id is appended to request state, the next decode iteration feeds it back to SwiftTransformer and can crash CUDA.

This happens under FCFS baseline as well, so it is not caused by the new scheduler. A defensive engine-side guard was added in `distserve/single_stage_engine.py`: worker-returned token ids are checked against tokenizer vocab size before decoding or being appended to request state; invalid ids are replaced by EOS/0 fallback and logged.

With this guard:

| workload | policy | status |
|---|---|---|
| small, 4 requests, 0.2 req/s | FCFS | pass |
| small, 12 requests, 2 req/s | FCFS | pass |
| small, 12 requests, 2 req/s | Phase | pass |

Small workload result paths:

```text
/root/data/phase_scheduler_results/debug_sanitize_serial/fcfs-small-4-0.2.exp
/root/data/phase_scheduler_results/debug_sanitize_overlap/fcfs-small-12-2.0.exp
/root/data/phase_scheduler_results/debug_phase_sanitize_overlap/phase-small-12-2.0.exp
```

Small workload directional numbers, 12 requests at 2 req/s:

| policy | latency p95 | FTL p95 | TPOT p95 |
|---|---:|---:|---:|
| FCFS | 0.5900s | 0.0324s | 0.0188s |
| Phase | 0.4540s | 0.0495s | 0.0170s |

These numbers are smoke-test evidence only. The guard keeps the service alive, but the underlying SwiftTransformer/LLaMA2 invalid-token behavior still needs root-cause analysis before using long LLaMA2 generations for paper-grade quality claims. For methodology validation, this means:

1. The tiny workload can validate that the scheduler implementation path runs.
2. The small workload now validates that FCFS and Phase can survive repeated 1P1D LLaMA2 requests.
3. It is not sufficient to validate PS-Prefill deeply, because the current guard may alter generated token contents when SwiftTransformer emits invalid ids.
4. Before paper-grade experiments, either the LLaMA2/SwiftTransformer invalid-token issue must be fixed at root, or evaluation should move to a model/backend configuration that supports stable heterogeneous prompt concurrency.

## Current Interpretation

This run validates:

- `1p1d + LLaMA2-7B` can start with the new scheduler policies.
- The DistServe-native benchmark/result path works.
- `KVAwareLAS` has very low reported scheduling overhead in logs.
- Tiny workload does not show regression.

This run does not yet validate:

- PS-Prefill under skewed prompt lengths.
- KV-aware admission under real memory pressure.
- Fairness under long-output contention.
- Any publishable speedup claim.
