# Stage 4F：E2 主端到端实验进展

更新时间：2026-05-29

## 本阶段目标

本阶段对应 `docs/experiment_protocol.md` 中的 E2：在 E1 固定的真实 trace、rate、seed 上运行 PhaseServe full policy，并与 E1 的 DistServe/FCFS baseline 对比。

当前 E2 不重新搜索 workload 或 rate；rate 选择完全来自 `docs/stage4e_trace_baseline_calibration.md` 的 baseline pressure window。

## 实验口径

- 结构：1P1D，`num_gpus=2`
- 横轴口径：脚本 `RATES` 是全局 arrival rate；论文图若使用 `Per-GPU Rate`，应换算为 `RATES / 2`
- 对比方式：E1 已经完成 FCFS baseline，本阶段只补跑 `phase`
- 主要指标：SLO attainment、per-GPU goodput、TTFT p90/p99、TPOT p90/p95/p99
- 当前均为 seed `0`，正式主图仍需补 seed

## OPT-13B + ShareGPT

FCFS baseline：

`/root/data/phase_scheduler_results/e1_opt13b_sharegpt_fcfs_fine_20260529_152721`

PhaseServe full：

`/root/data/phase_scheduler_results/e2_opt13b_sharegpt_phase_20260529_165556`

配置：

- Model：`/root/data/models/opt-13b`
- Dataset：`/root/data/datasets/distserve_eval/processed/opt13b_sharegpt.ds`
- Num prompts：`128`
- Process：Poisson
- SLO：`TTFT <= 0.25s, TPOT <= 0.10s`
- Rates：`0.5 0.75 1.0 1.25 1.5`

| Script rate | Per-GPU rate | FCFS SLO | Phase SLO | ΔSLO | ΔTTFT p90 | ΔTTFT p99 | ΔTPOT p90 | ΔTPOT p95 | ΔTPOT p99 | Δper-GPU goodput |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.50 | 0.25 | 97.7% | 96.9% | -0.8 pp | +0.7% | +2.1% | +5.8% | +5.2% | +4.6% | -0.9% |
| 0.75 | 0.375 | 95.3% | 95.3% | +0.0 pp | +3.6% | +1.6% | +19.6% | +2.4% | -16.2% | -0.2% |
| 1.00 | 0.50 | 87.5% | 91.4% | +3.9 pp | +0.9% | +6.8% | -32.2% | -30.6% | -59.2% | +4.2% |
| 1.25 | 0.625 | 80.5% | 82.0% | +1.6 pp | -3.8% | +1.6% | +1.2% | -7.4% | -4.6% | +1.7% |
| 1.50 | 0.75 | 59.4% | 60.9% | +1.6 pp | +9.2% | +1068.9% | -4.8% | -1.6% | -0.0% | +2.1% |

初步结论：

- 最强信号在 script rate `1.00`：PhaseServe 将 SLO 从 `87.5%` 提升到 `91.4%`，TPOT p90/p95/p99 分别下降 `32.2%/30.6%/59.2%`，per-GPU goodput 提升 `4.2%`。
- script rate `1.25` 是温和收益区：SLO +`1.6 pp`，TTFT p90 下降 `3.8%`，TPOT p95/p99 小幅下降。
- script rate `1.50` 已是过载边界，虽然 SLO/goodput 略升，但 TTFT p99 明显变差，不适合作为主图 claim。
- 低压 `0.50/0.75` 主要是 sanity：PhaseServe 没有明显破坏稳定区，但也没有稳定主收益。

## LLaMA2-13B + LongBench-4K

FCFS baseline：

`/root/data/phase_scheduler_results/e1_llama13b_longbench_fcfs_20260529_155658`

PhaseServe full：

`/root/data/phase_scheduler_results/e2_llama13b_longbench_phase_20260529_171756`

配置：

- Model：`/root/data/models/modelscope-llama2-13b-hf`
- Dataset：`/root/data/datasets/distserve_eval/processed/llama13b_longbench_4k.ds`
- Num prompts：`96`
- Process：Poisson
- `MAX_TOTAL_TOKENS=4096`
- `CONTEXT_MAX_TOKENS_PER_BATCH=4096`
- SLO：`TTFT <= 5s, TPOT <= 0.12s`
- Rates：`0.2 0.25 0.35 0.5 0.75`

| Script rate | Per-GPU rate | FCFS SLO | Phase SLO | ΔSLO | ΔTTFT p90 | ΔTTFT p99 | ΔTPOT p90 | ΔTPOT p95 | ΔTPOT p99 | Δper-GPU goodput |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.20 | 0.10 | 97.9% | 97.9% | +0.0 pp | +0.2% | +28.9% | -0.9% | +1.9% | -54.8% | -0.1% |
| 0.25 | 0.125 | 97.9% | 100.0% | +2.1 pp | -0.5% | -0.9% | -1.6% | -4.9% | -83.7% | +2.1% |
| 0.35 | 0.175 | 95.8% | 100.0% | +4.2 pp | +1.0% | +0.1% | -8.1% | -42.7% | -98.0% | +4.3% |
| 0.50 | 0.25 | 86.5% | 93.8% | +7.3 pp | +42.9% | +23.5% | -78.7% | -82.2% | -95.5% | +8.8% |
| 0.75 | 0.375 | 46.9% | 88.5% | +41.7 pp | -80.5% | -82.4% | -80.6% | -62.4% | -84.8% | +90.3% |

初步结论：

- LongBench-4K 是当前最强 setting。PhaseServe 在 rate `0.35/0.50/0.75` 上分别将 SLO 提升 `4.2/7.3/41.7 pp`。
- TPOT tail 收益非常稳定：rate `0.35/0.50/0.75` 的 TPOT p99 分别下降 `98.0%/95.5%/84.8%`。
- rate `0.50` 的 TTFT p90/p99 变差，但仍显著低于 `5s` TTFT SLO；这个点应作为 “TPOT/KV tail 收敛，TTFT 有轻微 tradeoff” 来报告。
- rate `0.75` 上 TTFT 和 TPOT 都明显改善，是过载边界下 PhaseServe 控制 KV/swap pressure 的强证据。

## LLaMA2-13B + ShareGPT

FCFS baseline：

`/root/data/phase_scheduler_results/e1_llama13b_sharegpt_fcfs_20260529_163146`

PhaseServe full：

`/root/data/phase_scheduler_results/e2_llama13b_sharegpt_phase_20260529_175007`

配置：

- Model：`/root/data/models/modelscope-llama2-13b-hf`
- Dataset：`/root/data/datasets/distserve_eval/processed/llama13b_sharegpt.ds`
- Num prompts：`128`
- Process：Poisson
- SLO：`TTFT <= 0.25s, TPOT <= 0.10s`
- Rates：`0.5 0.75 1.0 1.25`

| Script rate | Per-GPU rate | FCFS SLO | Phase SLO | ΔSLO | ΔTTFT p90 | ΔTTFT p99 | ΔTPOT p90 | ΔTPOT p95 | ΔTPOT p99 | Δper-GPU goodput |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.50 | 0.25 | 96.1% | 96.1% | +0.0 pp | +2.5% | +0.8% | +6.1% | +2.6% | -11.0% | -0.1% |
| 0.75 | 0.375 | 93.0% | 95.3% | +2.3 pp | +1.1% | -2.0% | +15.2% | -28.1% | -45.8% | +2.3% |
| 1.00 | 0.50 | 83.6% | 86.7% | +3.1 pp | +4.4% | +0.2% | -55.0% | -37.9% | -66.7% | +3.5% |
| 1.25 | 0.625 | 72.7% | 75.8% | +3.1 pp | +4.7% | -0.3% | -9.4% | -13.7% | -7.7% | +2.4% |

初步结论：

- LLaMA2-13B + ShareGPT 复现了 OPT-13B + ShareGPT 的主趋势：主退化区 rate `1.00` 上 SLO 和 TPOT tail 同时改善。
- rate `1.00` 的 TPOT p90/p95/p99 分别下降 `55.0%/37.9%/66.7%`，SLO +`3.1 pp`，per-GPU goodput +`3.5%`。
- rate `1.25` 是温和收益区：SLO +`3.1 pp`，TPOT p90/p95/p99 均改善，但幅度小于 rate `1.00`。
- TTFT p90 有小幅退化，TTFT p99 基本持平或略好。该 setting 的主 claim 应聚焦 TPOT tail、SLO 和 goodput，而不是 TTFT。

## E2 当前总结

当前 seed0 下，三个真实 setting 都完成了 PhaseServe full vs DistServe/FCFS 对比。

主图候选窗口：

| Setting | 推荐主图 rate | 主要收益 |
|---|---|---|
| OPT-13B + ShareGPT | `1.00`，辅以 `1.25` | SLO +3.9pp，TPOT p90/p95/p99 明显下降 |
| LLaMA2-13B + LongBench-4K | `0.35/0.50/0.75` | SLO +4.2/+7.3/+41.7pp，TPOT p99 大幅下降 |
| LLaMA2-13B + ShareGPT | `1.00`，辅以 `1.25` | SLO +3.1pp，TPOT p90/p95/p99 明显下降 |

总体判断：

- PhaseServe 在真实 trace 上的最稳定收益是 TPOT tail、SLO attainment 和 per-GPU goodput。
- TTFT 不是所有 setting 都改善；LongBench rate `0.50` 的 TTFT p90/p99 有退化，但仍在 5s SLO 内。
- 论文主 claim 应写成 “pressure window 中改善 decode/KV tail 和 SLO，同时保持 TTFT SLO”，而不是 “所有 percentile 全面提升”。

## 下一步

1. 补 seed 1 或在主图候选窗口补重复实验，确认稳定性。
2. 做 E3 消融，优先选择 `OPT-13B + ShareGPT rate 1.0`、`LLaMA2-13B + LongBench rate 0.5`、`LLaMA2-13B + ShareGPT rate 1.0`。
3. 做 mechanism/bucket 诊断，解释 TPOT tail 收敛和 TTFT tradeoff。
