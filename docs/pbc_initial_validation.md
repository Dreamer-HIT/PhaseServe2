# PBC Initial Validation Notes

状态：第一轮实现后 smoke / stress 验证记录，不作为论文最终实验结果。

## 目的

本轮验证的目标不是证明 PhaseServe 已经优于所有 baseline，而是确认方法论文档中冻结的最小闭环是否可执行：

```text
PBC pressure/budget metrics
  -> BPS/KAS budgeted scheduling
  -> TTFT/TPOT/goodput summary
  -> phase metrics JSONL
```

## 代码状态

远程提交：

```text
314e2b8 Implement pressure-budget scheduler metrics
```

主要实现：

1. `distserve/phase_scheduler.py`：新增 `PressureBudgetController`、`AdmissionBudget` 和 phase metrics JSONL 写出。
2. `distserve/context_stage_scheduler.py`：BPS 消费 PBC 的 prefill token budget 和 block margin。
3. `distserve/decoding_stage_scheduler.py`：KAS 消费 PBC 的 decode scan limit 和 swap-in budget，并记录 resident admission、swap bytes、stall、max skips。
4. `benchmarks/phase_native_benchmark.py`：新增 `--phase-metrics`，把 phase metrics 汇总进 summary。

## Smoke Matrix

路径：

```text
/root/data/phase_scheduler_results/pbc_tiny_matrix_20260526_165508
```

配置：

- 1P1D LLaMA2-7B。
- `phase` vs `fcfs`。
- `synthetic_phase_sched.marshal` prompt-skew。
- `synthetic_phase_sched_tiny.marshal` decode-pressure smoke。

结论：

- 所有请求成功。
- phase metrics 成功写出并进入 `.summary.json`。
- 该矩阵压力较轻，PBC 基本保持 `OPEN`，只能证明指标链路可用，不能证明 pressure chain。

## Stress Matrix

路径：

```text
/root/data/phase_scheduler_results/pbc_stress_matrix_20260526_165810
```

配置：

- 1P1D LLaMA2-7B。
- burst arrival。
- context batch size = 8。
- decode batch size = 4。
- `PHASESERVE_PBC_RHO_LOW=0.20`。
- `PHASESERVE_PBC_RHO_HIGH=0.40`。
- `PHASESERVE_PBC_DECODE_QUEUE_TARGET=4`。
- `PHASESERVE_PBC_BRIDGE_TARGET=2`。

### Prompt-Skew Workload

Dataset:

```text
/root/data/phase_scheduler_results/pbc_prompt_skew_burst.marshal
```

Result:

| Policy | completed | goodput req/s | TTFT p95 | TTFT p99 | TPOT p95 | TPOT p99 |
|---|---:|---:|---:|---:|---:|---:|
| phase | 32 | 9.081 | 1.097 | 1.203 | 0.099 | 0.100 |
| fcfs | 32 | 9.686 | 1.159 | 1.159 | 0.087 | 0.091 |

Interpretation:

- Phase improves TTFT p95 by about 5.3%.
- Phase hurts goodput by about 6.2% and TPOT tail by about 9-14%.
- This is a tradeoff case, not a clean win.
- It supports the methodology requirement that not every workload metric must improve.

### Decode-Pressure Workload

Dataset:

```text
/root/data/phase_scheduler_results/pbc_decode_pressure_burst.marshal
```

Result:

| Policy | completed | goodput req/s | TTFT p95 | TTFT p99 | TPOT p95 | TPOT p99 |
|---|---:|---:|---:|---:|---:|---:|
| phase | 32 | 4.299 | 0.165 | 0.165 | 0.106 | 0.107 |
| fcfs | 32 | 4.085 | 0.165 | 0.166 | 0.285 | 0.351 |

Interpretation:

- Phase improves goodput by about 5.2%.
- Phase reduces TPOT p95 by about 62.8%.
- Phase reduces TPOT p99 by about 69.4%.
- TTFT is effectively unchanged.
- This is the first positive signal for the decode-pressure claim.

## Phase Metrics Observations

For stress runs:

- Phase prompt-skew:
  - context dispatches: 14
  - context modes: `BACKPRESSURE=13`, `OPEN=1`
  - decode dispatches: 191
  - decode modes: `BACKPRESSURE=172`, `OPEN=19`

- Phase decode-pressure:
  - context dispatches: 4
  - context modes: `BACKPRESSURE=3`, `OPEN=1`
  - decode dispatches: 528
  - decode modes: `BACKPRESSURE=479`, `OPEN=49`

Current limitation:

- swap pressure did not appear in these runs (`swap_ins=0`, resident admission ratio = 1.0).
- Therefore the current stress matrix validates decode queue / active-set behavior, but not the full KV/swap claim.

## Next Experimental Step

The next experiment should target memory pressure explicitly:

1. Reduce effective GPU KV capacity or increase sequence lengths/concurrency.
2. Force swapped requests to appear.
3. Compare `phase` against `kv-unaware-las` or FCFS.
4. Require nonzero `swap_ins`, `swap_in_bytes`, or `iteration_stall_s`; otherwise the KV-constrained claim remains unvalidated.

## Current Judgment

The implementation now supports the core metrics needed by the methodology:

- PBC mode and pressure.
- prefill budget and block margin.
- decode scan limit.
- swap budget.
- resident admission ratio.
- max consecutive skips.
- scheduler overhead.

The first stress matrix shows a promising decode-pressure result, but final paper experiments still need:

1. Multiple seeds.
2. Larger request counts.
3. OPT or another more stable model for main experiments.
4. Explicit memory-pressure workload.
5. Fair baselines for BPS-only, KAS-only, PBC+BPS, PBC+KAS, and full PhaseServe.
