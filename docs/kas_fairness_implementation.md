# KAS Fairness Instrumentation

更新时间：2026-05-27

## 目的

本文档记录 KAS fairness 补强。此前 KAS 已经有 `consecutive_skips` 和 `starved` tie-breaker，但指标还不能回答一个关键 reviewer 问题：

> KAS 降低 TPOT tail，是不是只是把长输出请求饿住了？

本次改动让 decode scheduler 能区分两类未被选中的请求：

1. **Policy skipped**：请求本轮没有被选中，主要是因为排序、scan limit 或 batch slot 被更高优先级请求占用。
2. **Infeasible**：请求本轮被检查过，但因为 batch/token/GPU block/swap budget 等资源约束无法 admission。

这使论文中的 fairness bound 更可验证：

```text
consecutive_skips(r) <= skip_threshold + infeasible_rounds(r)
```

## 实现位置

- `distserve/decoding_stage_scheduler.py`
- `benchmarks/phase_native_benchmark.py`
- `benchmarks/phase_collect_summaries.py`
- `benchmarks/phase_analyze_sweep.py`

## Scheduler 改动

### 失败原因

`_check_add_to_las_batch()` 现在返回：

```text
(can_add, reason)
```

失败原因包括：

| reason | 含义 |
|---|---|
| `batch_size` | decode active batch 已满 |
| `token_budget` | 本轮 token budget 不足 |
| `gpu_append_blocks` | resident request 下一 token append block 不足 |
| `gpu_swap_blocks` | swapped request swap-in 后可用 GPU block 不足 |
| `swap_budget` | 本轮 swap-in budget 已用尽 |

### Skip 与 infeasible 分离

新增 per-request 状态：

- `consecutive_skips`
- `consecutive_infeasible`

规则：

1. 被选中的请求：两者都清零。
2. 被检查但资源不可行：增加 `consecutive_infeasible`，不增加 `consecutive_skips`。
3. 未被选中且不是资源不可行：增加 `consecutive_skips`，用于 starved tie-breaker。

这样可以避免把“当前资源确实不可行”的长输出请求错误计入策略 starvation。

## 新增 decode dispatch 指标

每轮 decode dispatch 现在记录：

| 指标 | 含义 |
|---|---|
| `considered` | 本轮被 scan 的 ready requests 数 |
| `policy_skipped` | 未被选中且不是资源不可行的请求数 |
| `infeasible_rounds` | 被检查但资源不可行的请求数 |
| `infeasible_batch_size` | 因 batch size 不可行的次数 |
| `infeasible_token_budget` | 因 token budget 不可行的次数 |
| `infeasible_gpu_append_blocks` | 因 append block 不足不可行的次数 |
| `infeasible_gpu_swap_blocks` | 因 swap-in 后 GPU block 不足不可行的次数 |
| `infeasible_swap_budget` | 因 swap budget 不足不可行的次数 |
| `starved_ready` | 本轮 ready requests 中已 starved 的数量 |
| `starved_selected` | 本轮被选中的 starved requests 数量 |
| `starved_admission_ratio` | `starved_selected / max(starved_ready, 1)` |
| `max_consecutive_infeasible` | 当前最大连续资源不可行轮数 |

这些指标会进入 summary 和 sweep analysis。

## Long-Output Slowdown Proxy

benchmark 侧新增两个 per-request/bucket 指标：

```text
e2e_per_output_token_s = latency_s / requested_output_len
decode_per_output_token_s = decode_exec_s / generated_tokens
```

它们不是严格的理论 slowdown，但能作为长输出 bucket 的可解释 proxy：

- `e2e_per_output_token_s` 反映端到端完成时间被输出长度归一化后的代价。
- `decode_per_output_token_s` 反映 decode execution 被生成 token 数归一化后的代价。

最终论文中仍应谨慎命名，避免把它们说成严格 slowdown。

## 验收标准

下一轮 long-output stress 应检查：

1. `>512` output bucket 的 TPOT/latency 是否没有失控。
2. `phase_decode_max_infeasible_max` 是否能解释长输出未被选中的资源原因。
3. `phase_decode_starved_admission_ratio_mean` 是否非零，证明 starved requests 会被重新 admission。
4. 如果 `policy_skipped` 高但 `starved_admission_ratio` 低，则说明 KAS 仍可能存在 starvation，需要继续改 tie-breaker。
