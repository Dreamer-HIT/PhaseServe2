# BPS Bounded-Progress Instrumentation

更新时间：2026-05-27

## 目的

BPS 的论文 claim 不是“短 prompt 更快”这么简单，而是：

> 在 prompt-skew workload 中，BPS 可以通过 cost-compatible batching 改善 prefill-side TTFT，同时用 protected-oldest 规则约束长 prompt 的 bounded waiting。

因此只报告全局 TTFT p90/p99 不够。我们必须能回答三个问题：

1. BPS 是否真的触发了 protected-oldest 路径。
2. 被保护请求触发后是否在下一轮被 dispatch。
3. 长 prompt 的 context queue wait 是否被控制住，而不是被短 prompt 收益掩盖。

## 本次实现

### 1. 调度器指标

`distserve/context_stage_scheduler.py` 现在在每次 context dispatch 中记录：

- `protected_triggered`：protected-oldest 是否触发。
- `protected_due_age`：是否由 `tau_prefill` 超时触发。
- `protected_due_budget`：是否由 PBC 的 `allow_protected_oldest` 触发。
- `protected_selected`：触发后 protected request 是否被选中。
- `protected_forced_single`：是否因为没有可行 bucket batch 而单独 dispatch protected request。
- `protected_blocked`：protected request 在忽略 pressure budget 后仍物理不可行。
- `protected_wait_s`：protected request 的等待时间。
- `protected_prompt_len` / `protected_bucket`：被保护请求的 prompt 特征。
- `waiting_waits`：整个 context waiting queue 的最大等待和长 prompt 最大等待。
- `candidate_waits`：bounded candidate window 内的最大等待和长 prompt 最大等待。
- `selected_waits`：实际 dispatch batch 内的最大等待和长 prompt 数量。

默认 long prompt 阈值为 `1024` tokens，可通过：

```bash
export PHASESERVE_PREFILL_LONG_PROMPT_TOKENS=1024
```

调整。

### 2. Bounded-progress 修正

此前当 protected-oldest 已经触发、但 protected request 无法组成 budget-feasible batch 且单独 dispatch 也物理不可行时，调度器仍可能继续选择其它不包含 protected request 的候选 batch。

这会让 protected-oldest invariant 在极端 KV/block 压力下失真。

现在的行为是：

- 如果 protected request 可以放入某个候选 batch，只在这些 batch 中选择。
- 如果没有候选 batch，但 protected request 单独 dispatch 可行，则单独 dispatch。
- 如果 protected request 物理不可行，则本轮不 dispatch 其它请求，并记录 `protected_blocked=True`。

这样可以区分两类情况：

1. **策略绕过**：应由 BPS 避免。
2. **资源不可行**：应由 PBC/容量或 workload 配置解释。

### 3. 汇总脚本

`benchmarks/phase_native_benchmark.py` 汇总 context metrics：

- `protected_triggered`
- `protected_selected`
- `protected_dispatch_ratio`
- `protected_feasible_dispatch_ratio`
- `protected_feasible_triggers`
- `protected_forced_single`
- `protected_blocked`
- `protected_wait_s`
- `waiting_max_wait_s`
- `waiting_long_prompt_max_wait_s`
- `candidate_long_prompt_max_wait_s`
- `selected_long_prompt_count`

`benchmarks/phase_collect_summaries.py` 和 `benchmarks/phase_analyze_sweep.py` 进一步把这些字段写入 CSV/Markdown：

- `phase_context_protected_dispatch_ratio`
- `phase_context_protected_feasible_dispatch_ratio`
- `phase_context_protected_blocked`
- `phase_context_protected_wait_p99`
- `phase_context_long_prompt_max_wait`

bucket-level analysis 也新增：

- `ttft_max`
- `context_queue_max`

用于直接观察最长 prompt bucket 的最坏等待情况。

## 论文中如何使用

BPS 主表不需要展示所有内部变体。更合适的呈现方式是：

1. Prompt-skew workload：比较 `fcfs` 和 `bps`。
2. 主指标：TTFT p90/p99、SLO goodput、output tok/s。
3. 公平性/约束指标：long-prompt context queue max、long-prompt TTFT p99、protected dispatch ratio。
4. Appendix 或小表：只保留必要的 BPS sensitivity，不把 `bucket_only/no_oldest_bonus/age_bonus` 全部放进主文。

如果 BPS 改善短/中 prompt TTFT，但 long-prompt max queue wait 明显失控，则论文 claim 必须收窄，不能写成稳定降低所有 prompt bucket tail。

## 下一步验证

建议先跑一个小 smoke：

```bash
SWEEP_ROOT=/root/data/phase_scheduler_results/bps_progress_smoke_$(date +%Y%m%d_%H%M%S) \
SEEDS=0 \
RATES=0 \
NUM_PROMPTS=12 \
DATASET_SIZE=12 \
POLICIES="fcfs bps" \
./scripts/run_phase_prefill_skew_sweep.sh
```

然后跑正式 2-seed 或 5-seed：

```bash
SWEEP_ROOT=/root/data/phase_scheduler_results/bps_progress_prefill_skew_$(date +%Y%m%d_%H%M%S) \
SEEDS="0 1" \
RATES="0 4 6 8 10" \
NUM_PROMPTS=96 \
DATASET_SIZE=96 \
POLICIES="fcfs bps" \
./scripts/run_phase_prefill_skew_sweep.sh
```

验收标准：

1. `phase_context_protected_feasible_dispatch_ratio` 接近 1，且 `protected_blocked` 可解释。
2. 最长 prompt bucket 的 `context_queue_max` 和 TTFT p99 没有随 BPS 明显恶化。
3. BPS 的 TTFT 收益仍主要出现在 prompt-skew 的 dominant buckets，而不是通过饿死长 prompt 换来。
