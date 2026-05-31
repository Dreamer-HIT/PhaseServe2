# Stage 4H OPT-13B ShareGPT Phase512 Repair

## 本阶段目标

先把 OPT-13B + ShareGPT 上的 full PhaseServe 做到同时改善 TTFT 和 TPOT，而不是只改善 TPOT、牺牲 TTFT tail。

本阶段聚焦 1P1D、OPT-13B、ShareGPT、64 requests、`MAX_TOTAL_TOKENS=1600` 的小矩阵。它是代码修复和机制确认，不是最终论文全量实验。

## 读取和修改的文件

读取：

- `remote_distserve/distserve/phase_scheduler.py`
- `remote_distserve/distserve/context_stage_scheduler.py`
- `remote_distserve/distserve/decoding_stage_scheduler.py`
- 远端 raw traces: `/root/data/phase_scheduler_results/e2b_opt13b_sharegpt_broad_20260529_185758`

修改：

- `remote_distserve/distserve/decoding_stage_scheduler.py`

## 诊断结论

OPT-13B + ShareGPT 原始 broad sweep 中，full PhaseServe 的问题不是 TPOT 无效，而是 KAS 对中长输出过早使用 full attained-service priority，导致部分 decode 执行时间和 bridge/unaccepted pressure 被拉长，最终反向堵塞 context 侧，使 TTFT p95/p99 变差。

组件探针在 global rate `4`，即 per-GPU `2` 上显示：

| Policy | TTFT p95 | TTFT p99 | TPOT p90 | TPOT p95 | TPOT p99 | SLO Submitted | Goodput |
|---|---:|---:|---:|---:|---:|---:|---:|
| `fcfs` | 1.277 | 1.870 | 0.373 | 0.571 | 3.150 | 56.2% | 0.72 |
| `bps` | 1.130 | 1.787 | 0.367 | 0.589 | 3.085 | 56.2% | 0.73 |
| `kas` | 1.345 | 2.399 | 0.347 | 0.542 | 2.820 | 56.2% | 0.71 |
| `bps_kas` | 1.338 | 2.260 | 0.342 | 0.535 | 2.824 | 56.2% | 0.71 |
| old `phase` | 2.283 | 3.158 | 0.385 | 0.523 | 2.739 | 57.8% | 0.74 |

解释：

1. `bps` 单独更接近 TTFT owner。
2. `kas` / `bps_kas` 改善 TPOT，但会伤 TTFT tail。
3. old `phase` 的 PBC 提高了 SLO/goodput，但没有正确限制 KAS 在 mixed ShareGPT 下的接管边界。

## 代码修复

将 full PhaseServe 的 `PHASESERVE_KAS_LONG_OUTPUT_FULL_THRESHOLD` 默认值从 `192` 调整为 `512`。

这个修复的语义是：输出长度在 `96-512` 的中间区间不再无条件使用 full KAS，而是服从 PBC 的 `decode_utility_intensity`；只有更长输出才强制 full KAS。这样能减少中长输出在 mixed workload 中被过早当成 decode-heavy tail 处理，从而保留 TPOT 收益，同时避免 TTFT tail 被 bridge/context 反压放大。

同时保留两个可选诊断开关，但默认关闭：

- `PHASESERVE_KAS_LONG_OUTPUT_FULL_REQUIRES_DECODE_PRESSURE`
- `PHASESERVE_KAS_BRIDGE_FCFS_FALLBACK_PRESSURE`

验证中发现 bridge-pressure FCFS fallback 过于激进，会同时伤害 TTFT 和 TPOT，因此没有作为默认策略。

## Seed0 多 rate 验证

结果目录：

```text
/root/data/phase_scheduler_results/opt13b_sharegpt_phase512_rates2to10_20260529_212802
```

对比基线：

```text
/root/data/phase_scheduler_results/e2b_opt13b_sharegpt_broad_20260529_185758
```

表中为 Phase512 相对 FCFS 的变化，延迟正数表示下降。

| Per-GPU Rate | SLO | TTFT p50 | TTFT p90 | TTFT p95 | TTFT p99 | TPOT p50 | TPOT p90 | TPOT p95 | TPOT p99 | Goodput |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | +4.7 pp | -0.8% | +0.8% | +0.7% | +6.2% | +1.9% | +47.5% | +47.9% | +58.3% | +9.7% |
| 2 | +3.1 pp | +4.1% | +20.2% | +75.3% | +33.4% | +18.0% | +28.4% | +6.2% | +13.5% | +8.7% |
| 3 | +1.6 pp | -1.3% | +35.7% | +37.1% | +21.2% | +19.1% | +18.8% | -6.8% | +5.3% | +6.4% |
| 4 | +1.6 pp | +4.0% | +21.5% | +24.2% | +20.4% | +10.4% | +10.4% | -0.8% | +10.4% | +10.4% |
| 5 | +0.0 pp | +9.2% | +7.2% | +17.6% | +14.9% | +11.0% | +4.9% | +5.5% | +10.8% | +2.4% |

## Seed1 确认矩阵

结果目录：

```text
/root/data/phase_scheduler_results/opt13b_sharegpt_phase512_seed1_confirm_20260529_213905
```

Seed1 跑 `fcfs` 与 `phase`，rates 为 global `2/4/6`，即 per-GPU `1/2/3`。

后续补充了 seed1 的 high-rate 确认矩阵：

```text
/root/data/phase_scheduler_results/opt13b_sharegpt_phase512_seed1_rate8to10_20260529_215725
```

该矩阵跑 `fcfs` 与 `phase`，rates 为 global `8/10`，即 per-GPU `4/5`。

两 seed 平均结果如下：

| Per-GPU Rate | SLO | TTFT p50 | TTFT p90 | TTFT p95 | TTFT p99 | TPOT p50 | TPOT p90 | TPOT p95 | TPOT p99 | Goodput |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | +4.7 pp | -0.1% | +4.1% | +7.5% | +6.4% | +0.0% | +37.9% | +35.0% | +44.3% | +9.6% |
| 2 | +3.9 pp | +4.3% | +27.3% | +68.3% | +45.0% | +16.7% | +19.3% | +6.8% | +13.4% | +11.1% |
| 3 | +2.3 pp | +0.3% | +31.2% | +31.9% | +22.3% | +17.2% | +10.8% | -1.2% | +5.5% | +9.3% |
| 4 | +2.3 pp | +11.3% | +19.9% | +22.2% | +19.1% | +11.3% | +5.5% | +3.9% | +8.2% | +12.3% |
| 5 | +3.1 pp | +9.1% | +11.3% | +20.5% | +16.8% | +8.4% | +5.6% | +4.7% | +13.1% | +18.4% |

## 验收判断

本阶段验收通过。

Phase512 在 OPT-13B + ShareGPT 上已经从“TPOT 收益但 TTFT tail 不稳定”变为“TTFT p90/p95/p99 与 TPOT p90/p99 同时改善”的形态。当前最好主图候选区间是 per-GPU `1-5`，其中 per-GPU `2` 的 TTFT tail 改善最强，两 seed 平均 SLO +`3.9 pp`，TTFT p90/p95/p99 下降 `27.3%/68.3%/45.0%`，TPOT p90/p95/p99 下降 `19.3%/6.8%/13.4%`，goodput +`11.1%`。per-GPU `4/5` 属于更高压力区，SLO 基线更低，但两 seed 平均仍同时改善 TTFT、TPOT 和 goodput，可作为 high-pressure extension。

## 风险和后续

1. 当前仍是 64 requests 小矩阵，正式实验需要扩到 128 requests。
2. Per-GPU `4/5` 已有 seed1 确认，适合作为 high-pressure extension；但正式图仍需 128 requests 复核。
3. TPOT p95 在 per-GPU `3` 的两 seed 平均仍有轻微波动，因此 TPOT 主图优先展示 p50/p90 或 p90/p99，不建议只押 p95。
4. 需要把 LLaMA2-13B + ShareGPT 也切到同一默认代码后复查，确认 512 threshold 不只对 OPT 有效。
5. 后续消融应在 per-GPU `2` 上补 `fcfs/bps/kas/bps_kas/phase512`，证明新 gate 不是单纯削弱 KAS，而是更准确的 output-tail eligibility。
