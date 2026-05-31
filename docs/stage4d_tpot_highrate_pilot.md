# Stage 4D TPOT High-Rate Pilot

## 本阶段目标

本 pilot 用于判断：在 Stage 4D mixed-wide workload 上继续提高 request rate，是否能让 TPOT 曲线呈现更明显的 decode-side pressure，从而改善端到端 TPOT 图的展示效果。

## 实验设置

| 项目 | 设置 |
|---|---|
| model | OPT-13B |
| serving structure | 1P1D |
| workload | `cross_skew_v1` mixed-regime |
| seed | `0` |
| policies | `fcfs`, `phase` |
| total rates | `28`, `32`, `36`, `40` req/s |
| per-GPU rates | `14`, `16`, `18`, `20` req/s/GPU |
| num prompts | `48` |
| SLO | `TTFT<=5s`, `TPOT<=0.12s` |
| result root | `/root/data/phase_scheduler_results/stage4d_opt13b_tpot_highrate_pilot_20260529_115851` |

本地汇总文件：

| file | purpose |
|---|---|
| `docs/figures/data/opt13b_tpot_highrate_pilot_summary.csv` | per-run summary |
| `docs/figures/data/opt13b_tpot_highrate_pilot_grouped.csv` | grouped analysis |
| `docs/figures/data/opt13b_tpot_highrate_pilot_analysis.md` | remote analysis markdown |

## Pilot 结果

下表为 PhaseServe 相比 DistServe FCFS 的改善。正数表示 latency 降低、SLO/throughput 提高。

| per-GPU rate | TTFT p90 | TPOT p50 | TPOT p90 | TPOT p95 | TPOT p99 | SLO delta | completed throughput |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 14 | +71.0% | +43.4% | +23.1% | -3.2% | +3.8% | +6.2 pp | +2.8% |
| 16 | +72.0% | +43.5% | +25.5% | -4.3% | +3.4% | +6.2 pp | +2.4% |
| 18 | +2.1% | +47.7% | +27.7% | +27.5% | +6.8% | +6.2 pp | -1.8% |
| 20 | +70.7% | +43.2% | +22.7% | -3.9% | +3.5% | +6.2 pp | +2.4% |

TPOT 原始值如下：

| per-GPU rate | FCFS p90 | Phase p90 | FCFS p95 | Phase p95 | FCFS p99 | Phase p99 |
|---:|---:|---:|---:|---:|---:|---:|
| 14 | 0.937 | 0.720 | 1.190 | 1.228 | 1.341 | 1.290 |
| 16 | 0.936 | 0.697 | 1.184 | 1.235 | 1.335 | 1.290 |
| 18 | 0.934 | 0.675 | 1.187 | 0.861 | 1.338 | 1.247 |
| 20 | 0.932 | 0.720 | 1.180 | 1.227 | 1.332 | 1.286 |

## 结论

1. high-rate 确实让 TPOT p90 展示更清楚。per-GPU `14/16/18/20` 下，TPOT p90 分别下降 `23.1%/25.5%/27.7%/22.7%`，明显强于低 rate 视觉上的平缓形态。
2. TPOT p50 仍然稳定改善，但绝对值随 rate 变化不大。这说明 p50 更适合表达 typical-token latency 的稳定收益，而不是表达压力随 rate 增长。
3. TPOT p95/p99 不能作为主图核心。p95 在 per-GPU `18` 很好，但在 `14/16/20` 略差；p99 虽然全部为正，但幅度较小。
4. high-rate 不是越高越好。FCFS 在 per-GPU `14` 之后 TPOT p90 基本进入平台期，说明 offered load 已超过系统有效服务能力；继续增大 rate 更多是在改变排队形态，而不是线性增加可解释压力。
5. per-GPU `14/16` 可作为 TPOT high-rate 展示窗口；per-GPU `18` 可作为 decode-pressure stress point，但 TTFT p90 只小幅改善，适合作为边界分析。

## 确认矩阵

为避免只依赖 OPT seed0 的 pilot，本阶段继续补充：

| model | seeds | per-GPU rates | result root |
|---|---|---|---|
| OPT-13B | `1` | `14`, `16` | `/root/data/phase_scheduler_results/stage4d_tpot_highrate_confirm_20260529_135452/opt13b_seed1` |
| LLaMA-13B | `0`, `1` | `14`, `16` | `/root/data/phase_scheduler_results/stage4d_tpot_highrate_confirm_20260529_135452/llama13b_seed01` |

本地新增汇总文件：

| file | purpose |
|---|---|
| `docs/figures/data/opt13b_tpot_highrate_confirm_seed1_summary.csv` | OPT-13B seed1 high-rate summary |
| `docs/figures/data/llama13b_tpot_highrate_confirm_summary.csv` | LLaMA-13B seed0/1 high-rate summary |

合并 pilot 与确认矩阵后，两个模型在 per-GPU `14/16` 上的均值如下。正数表示 latency 降低、SLO/throughput 提高。

### OPT-13B

| per-GPU rate | TTFT p90 | TPOT p50 | TPOT p90 | TPOT p95 | TPOT p99 | SLO delta | throughput |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 14 | +33.1% | +41.9% | +26.0% | +9.0% | +8.5% | +9.4 pp | +5.2% |
| 16 | +33.4% | +42.5% | +21.2% | +2.9% | +8.4% | +14.6 pp | +5.2% |

### LLaMA-13B

| per-GPU rate | TTFT p90 | TPOT p50 | TPOT p90 | TPOT p95 | TPOT p99 | SLO delta | throughput |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 14 | +33.4% | +42.4% | +26.6% | +8.9% | +8.3% | +9.4 pp | +5.2% |
| 16 | +32.7% | +42.9% | +20.3% | +3.5% | +8.2% | +14.6 pp | +5.4% |

Seed-level 结果显示，TPOT p50/p90 在两个模型、两个 seed、两个 high-rate 点上全部为正；但 TTFT p90 在 seed1 上显著退化。

| model | seed | per-GPU rate | TTFT p90 | TPOT p50 | TPOT p90 | TPOT p95 |
|---|---:|---:|---:|---:|---:|---:|
| OPT-13B | 0 | 14 | +71.0% | +43.4% | +23.1% | -3.2% |
| OPT-13B | 0 | 16 | +72.0% | +43.5% | +25.5% | -4.3% |
| OPT-13B | 1 | 14 | -56.8% | +40.5% | +30.1% | +27.8% |
| OPT-13B | 1 | 16 | -57.9% | +41.6% | +15.3% | +13.8% |
| LLaMA-13B | 0 | 14 | +72.1% | +43.5% | +24.0% | -3.7% |
| LLaMA-13B | 0 | 16 | +72.0% | +43.8% | +24.3% | -3.4% |
| LLaMA-13B | 1 | 14 | -59.5% | +41.5% | +30.3% | +28.1% |
| LLaMA-13B | 1 | 16 | -61.9% | +42.2% | +14.8% | +14.0% |

确认矩阵结论：

1. per-GPU `14/16` 可以纳入 TPOT 主图，用于增强 high-rate decode pressure 下的 TPOT p90 展示。
2. high-rate 不适合作为 TTFT 主图窗口。seed1 的 TTFT p90 明显退化，说明 high-rate 区间已经触及 PBC 对 decode pressure 的优先保护边界。
3. TPOT p95/p99 在聚合均值上转正，但 seed-level 仍有波动，因此论文主 claim 仍应绑定到 TPOT p50/p90。
4. high-rate 的作用是补强 TPOT pressure 展示，不替代 Stage 4D 原有 mixed-wide 端到端主窗口。

## 对主图的影响

当前建议：

1. 主 SLO 图继续使用 SLO scale sensitivity。
2. 主 latency 图仍保持 TTFT/TPOT 两列，不拆开指标。
3. TTFT 图使用 per-GPU `2,3,4,5,6,8`。
4. TPOT 图扩展到 per-GPU `2,3,4,5,6,8,10,12,14,16`，用 high-rate 结果增强 p90 的视觉区分度。
5. 图注和正文需要说明：TTFT 与 TPOT 使用不同 operating ranges；high-rate 点用于 decode-side TPOT pressure，不用于 TTFT 主 claim。
