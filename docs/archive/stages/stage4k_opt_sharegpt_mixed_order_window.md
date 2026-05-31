# Stage 4K: OPT-13B + ShareGPT Mixed-Order Window

## 目标

本阶段目标是在 `OPT-13B + ShareGPT` 上验证 full PhaseServe 是否能在同一端到端 workload 中同时改善 TTFT 和 TPOT 的多个分位指标。此前 first-order ShareGPT trace 呈现出分离现象：低 rate 下 TPOT 改善明显但 TTFT 压力不足，高一点 rate 下 TTFT 改善明显但 TPOT p90/p99 不稳定。

## 代码和 workload 变更

### KAS completion-aware 默认策略

文件：

- `remote_distserve/distserve/decoding_stage_scheduler.py`

变更：

- `PHASESERVE_KAS_BRIDGE_COMPLETION_PRESSURE` 默认值从 `0.65` 调整为 `0.0`。
- `PHASESERVE_KAS_BRIDGE_COMPLETION_REMAINING` 默认值从 `96` 调整为 `0`。
- 新增 `PHASESERVE_KAS_BRIDGE_COMPLETION_FIRST_DECODE_FRAC` 和 `PHASESERVE_KAS_BRIDGE_COMPLETION_FIRST_DECODE_MIN`，用于后续控制 mixed-pressure 下 first-decode quota；当前默认 `1.0/1`，不改变默认排序。

含义：KAS 在非 hard-pressure 下默认使用 completion-aware remaining-order，而不是只在 bridge pressure 很高时触发。实验中 `remaining=0` 表示不设置二元 near-completion 阈值，直接按 remaining output 长度排序。

### ShareGPT mixed-order trace

新增脚本：

- `remote_distserve/benchmarks/phase_make_sharegpt_mixed_order.py`

构造原则：

- 输入仍然是 ShareGPT processed marshal。
- 保持 first `N=128` 请求集合不变。
- 只改变发送顺序：交错 long-prompt、long-output、short-prompt/long-output 请求。

远端生成的 trace：

- `/root/data/datasets/distserve_eval/processed/opt13b_sharegpt_first128_mixedorder.ds`
- `/root/data/datasets/distserve_eval/processed/opt13b_sharegpt_first128_mixedorder.metadata.json`

长度分布与 original first-128 一致：

| Field | Min | P50 | P90 | Max |
|---|---:|---:|---:|---:|
| prompt chars | 13 | 2196 | 5554 | 8211 |
| output tokens | 6 | 529 | 1423 | 1969 |

## 运行设置

- Model: `/root/data/models/opt-13b`
- Dataset: `opt13b_sharegpt_first128_mixedorder.ds`
- 1P1D, 2 GPUs
- `NUM_PROMPTS=128`
- `PROCESS_NAME=poisson`
- `MAX_TOTAL_TOKENS=2048`
- Policies: `fcfs`, `phase`
- Seeds: `0`, `1`
- Global rates: `1.9`, `2.0`, `2.1`
- Per-GPU rates: `0.95`, `1.0`, `1.05`

## 结果

### Global Rate 1.9

Result roots:

- seed0: `/root/data/phase_scheduler_results/opt13b_sharegpt_first128mixed_tuneC_r19_seed0_20260530_144605`
- seed1: `/root/data/phase_scheduler_results/opt13b_sharegpt_first128mixed_tuneC_r19_seed1_20260530_145157`

两 seed 平均，Phase 相比 DistServe/FCFS 的 latency reduction：

| Metric | P50 | P90 | P95 | P99 |
|---|---:|---:|---:|---:|
| TTFT | 9.6% | 53.5% | 67.5% | 67.7% |
| TPOT | 11.7% | 27.7% | 27.9% | 25.4% |

### Global Rate 2.0

Result roots:

- seed0: `/root/data/phase_scheduler_results/opt13b_sharegpt_first128mixed_tuneC_r2_seed0_20260530_141608`
- seed1: `/root/data/phase_scheduler_results/opt13b_sharegpt_first128mixed_tuneC_r2_seed1_20260530_145738`

两 seed 平均，Phase 相比 DistServe/FCFS 的 latency reduction：

| Metric | P50 | P90 | P95 | P99 |
|---|---:|---:|---:|---:|
| TTFT | 15.7% | 79.7% | 74.8% | 46.8% |
| TPOT | 9.8% | 26.1% | 22.4% | 20.2% |

### Global Rate 2.1

Result root:

- `/root/data/phase_scheduler_results/opt13b_sharegpt_first128mixed_tuneC_r21_seed01_20260530_150334`

两 seed 平均，Phase 相比 DistServe/FCFS 的 latency reduction：

| Metric | P50 | P90 | P95 | P99 |
|---|---:|---:|---:|---:|
| TTFT | 33.9% | 58.5% | 59.0% | 51.8% |
| TPOT | 8.6% | 19.3% | 21.7% | 18.4% |

## 结论

当前最干净窗口是 global rate `1.9-2.0`，对应 per-GPU rate `0.95-1.0`。在该窗口内，TTFT 和 TPOT 都可以各自选择至少两个常用 tail 指标并超过 20% 改善：

- TTFT: p90/p95/p99
- TPOT: p90/p95/p99

global rate `2.1` 仍显著改善 TTFT，但 TPOT 只剩 p95 超过 20%，因此更适合作为右侧压力边界，不应纳入主 positive window。

## Strict 2-Wide Window Check

为了检查“Per-GPU rate 区间长度为 2，粒度为 0.5”的更严格目标，额外启动了如下矩阵：

- Result root: `/root/data/phase_scheduler_results/opt13b_sharegpt_first128mixed_strict2wide_pgpu05to25_seed01_20260530_161352`
- Per-GPU rates: `0.5/1.0/1.5/2.0/2.5`
- Global rates: `1/2/3/4/5`
- Dataset: `opt13b_sharegpt_first128_mixedorder.ds`
- Policies: `fcfs`, `phase`

seed0 五个点已经足以否定该严格区间目标，因此停止剩余 seed1 以节省实验时间。seed0 latency reduction 如下：

| Per-GPU Rate | TTFT p50 | TTFT p90 | TTFT p95 | TTFT p99 | TPOT p50 | TPOT p90 | TPOT p95 | TPOT p99 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.5 | -0.2% | -2.1% | -1.6% | -6.2% | -4.1% | 26.0% | 53.1% | 3.8% |
| 1.0 | 25.1% | 86.8% | 86.7% | 49.5% | 6.5% | 15.9% | 18.7% | 17.0% |
| 1.5 | 43.3% | 12.7% | 15.3% | 18.2% | 1.0% | 21.3% | 1.6% | 12.6% |
| 2.0 | 50.4% | 1.8% | 6.9% | 6.0% | 0.0% | 15.0% | 5.4% | 14.6% |
| 2.5 | 35.8% | 5.0% | 5.5% | 4.0% | 6.1% | 4.3% | 3.1% | 9.7% |

严格目标未达成。主要原因不是单个阈值调参不足，而是不同 rate 的 bottleneck 不同：

- Per-GPU `0.5`: decode tail 有收益，但 TTFT 基线压力太轻。
- Per-GPU `1.0`: TTFT 很强，但 TPOT 第二个 tail 指标未稳定超过 20%。
- Per-GPU `1.5+`: 系统进入更强排队/过载区域，TTFT tail 或 TPOT tail 不能同时保持两个指标超过 20%。

因此，当前可支撑的主张应是“在 mixed-pressure operating window 中同时改善 TTFT 和 TPOT tail”，而不是“在长度为 2 的连续 per-GPU rate 区间内每个 0.5 粒度点都同时超过 20%”。若坚持 strict 2-wide 目标，需要重新设计 workload 或方法，而不能只沿用当前 first128 mixed-order trace 与 KAS defaults。

## 风险和后续验证

1. 该 workload 是 ShareGPT-derived mixed-order trace，不是原始 first-order trace。论文中必须明确说明：请求集合来自 ShareGPT first-128，实验改变的是 arrival order，用于构造 prefill/decode mixed pressure。
2. 当前窗口是 1P1D + OPT-13B 上的结果；后续需要在 LLaMA2-13B 上复验同一构造。
3. `PHASESERVE_KAS_BRIDGE_COMPLETION_PRESSURE=0.0` 和 `REMAINING=0` 已固化为默认值，但还需要补消融：old bridge-triggered drain vs always completion-aware drain。
4. 主图建议展示 TTFT p90/p95 和 TPOT p90/p95，p99 可以作为补充表格，因为 p99 对 seed 更敏感。
