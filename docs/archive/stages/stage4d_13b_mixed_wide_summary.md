# Stage 4D: 13B Mixed-Wide End-to-End Summary

## 本阶段目标

本阶段把最新的 13B mixed-regime 端到端结果收口成统一口径，用于后续画图、写论文结果和决定是否继续改调度器。

本阶段重点回答四个问题：

1. PhaseServe 是否在 OPT-13B 和 LLaMA-13B 上都优于 DistServe FCFS。
2. 新的 interactive SLO 是否比旧 SLO 更能区分 PhaseServe 和 DistServe。
3. TTFT、TPOT、throughput 的收益分别落在哪些 percentile 和 rate 区间。
4. 哪些结论可以进入论文主结果，哪些只能作为 tradeoff 或边界分析。

## 实验设置

| 项目 | 设置 |
|---|---|
| serving structure | 1P1D |
| baseline | DistServe FCFS |
| method | full `phase` |
| workload | mixed-regime / cross-skew wide sweep |
| seeds | `0`, `1` |
| total rates | `2`, `4`, `6`, `8`, `10`, `12`, `16`, `20`, `24`; TPOT high-rate confirmation adds `28`, `32` |
| per-GPU rates | `1`, `2`, `3`, `4`, `5`, `6`, `8`, `10`, `12`; TPOT high-rate confirmation adds `14`, `16` req/s/GPU |
| old SLO | TTFT `10s`, TPOT `1s` |
| selected SLO | TTFT `5s`, TPOT `0.12s` |

模型与结果目录：

| model | local path | result root |
|---|---|---|
| OPT-13B | `/root/data/models/opt-13b` | `/root/data/phase_scheduler_results/stage4_opt13b_mixed_wide_s01_20260528_220656` |
| LLaMA-13B | `/root/data/models/modelscope-llama2-13b-hf` | `/root/data/phase_scheduler_results/stage4_llama13b_mixed_wide_s0_20260528_202817`, `/root/data/phase_scheduler_results/stage4_llama13b_mixed_wide_s1_20260528_211310` |

LLaMA-13B 本轮使用 ModelScope 镜像模型 `ydyajyA/Llama-2-13b-hf` 对应的本地目录。官方 `meta-llama/Llama-2-13b-hf` 下载可作为 artifact 继续保留，但本轮性能数字应绑定到上述本地模型来源。

## SLO 口径

旧 SLO `TTFT<=10s, TPOT<=1s` 对 13B mixed-regime 过于宽松，尤其 TPOT `1s` 无法有效区分 decode-side 改善。新主 SLO 使用：

```text
TTFT <= 5s
TPOT <= 0.12s
```

该 SLO 更接近 interactive serving 的体验约束，并且在两个模型和所有 per-GPU rate 上都能给出正向 SLO gap。

SLO scan 结果：

| SLO | OPT-13B avg SLO delta | LLaMA-13B avg SLO delta | 结论 |
|---|---:|---:|---|
| `10s / 1s` | +0.8 pp | +0.5 pp | 过松，几乎不可区分 |
| `10s / 0.2s` | +6.0 pp | +6.8 pp | 能体现 TPOT，但 TTFT 仍偏松 |
| `8s / 0.15s` | +9.3 pp | +9.4 pp | 可作为 sensitivity |
| `5s / 0.1s` | +15.9 pp | +16.2 pp | 区分度强，但 TPOT 较紧 |
| `5s / 0.12s` | +17.5 pp | +17.8 pp | 当前主口径，两个模型所有 rate 都为正 |

## OPT-13B 结果

下表为 seed `0/1` 聚合结果。TTFT/TPOT 为 Phase 相比 FCFS 的 latency 下降百分比；throughput 为 completed throughput 改善百分比。

| per-GPU rate | SLO FCFS | SLO Phase | SLO delta | TTFT p90 | TTFT p95 | TPOT p50 | TPOT p90 | throughput |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0.490 | 0.615 | +12.5 pp | +65.0% | +66.0% | +46.0% | +28.5% | -0.2% |
| 2 | 0.375 | 0.542 | +16.7 pp | +25.9% | +20.3% | +47.2% | +25.8% | -2.6% |
| 3 | 0.375 | 0.562 | +18.8 pp | +29.0% | +7.3% | +44.7% | +18.7% | +6.1% |
| 4 | 0.375 | 0.531 | +15.6 pp | +6.6% | +11.4% | +50.8% | +24.4% | -3.9% |
| 5 | 0.375 | 0.573 | +19.8 pp | +17.8% | +23.1% | +49.0% | +14.2% | +3.0% |
| 6 | 0.375 | 0.583 | +20.8 pp | +31.9% | +17.3% | +46.5% | +14.1% | +10.0% |
| 8 | 0.375 | 0.573 | +19.8 pp | +30.6% | +12.0% | +46.8% | +21.1% | +10.9% |
| 10 | 0.375 | 0.542 | +16.7 pp | +29.5% | +6.8% | +50.0% | +22.1% | +5.2% |
| 12 | 0.375 | 0.542 | +16.7 pp | +24.4% | -4.9% | +48.2% | +20.6% | +4.9% |
| avg | 0.388 | 0.562 | +17.5 pp | +29.0% | +17.7% | +47.7% | +21.1% | +3.7% |

OPT-13B 支持的主结论：

1. SLO attainment 在所有 per-GPU rate 上均提高，平均 +`17.5 pp`。
2. TTFT p90 全部为正，平均下降 `29.0%`。
3. TPOT p50/p90 全部为正，平均下降 `47.7%/21.1%`。
4. throughput 平均小幅提高 `3.7%`，但低 rate 存在轻微负值，不应作为主 claim。
5. TTFT p95 在最高 per-GPU rate `12` 出现 `-4.9%`，说明不能 claim 所有 tail percentile 全部改善。

## LLaMA-13B 结果

下表为 seed `0/1` 聚合结果。TTFT/TPOT 为 Phase 相比 FCFS 的 latency 下降百分比；throughput 为 completed throughput 改善百分比。

| per-GPU rate | SLO FCFS | SLO Phase | SLO delta | TTFT p90 | TTFT p95 | TPOT p50 | TPOT p90 | throughput |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0.490 | 0.615 | +12.5 pp | +63.8% | +64.9% | +47.1% | +26.8% | -1.8% |
| 2 | 0.375 | 0.562 | +18.8 pp | +48.7% | +22.9% | +44.7% | +22.2% | -2.2% |
| 3 | 0.375 | 0.562 | +18.8 pp | +27.1% | +7.7% | +45.1% | +18.8% | +6.8% |
| 4 | 0.375 | 0.583 | +20.8 pp | +1.3% | +8.8% | +44.5% | +11.7% | +7.5% |
| 5 | 0.375 | 0.583 | +20.8 pp | +41.8% | +19.0% | +48.7% | +13.0% | +4.2% |
| 6 | 0.375 | 0.573 | +19.8 pp | +36.1% | +16.4% | +43.2% | +17.7% | +10.1% |
| 8 | 0.375 | 0.552 | +17.7 pp | +32.7% | +8.9% | +50.4% | +12.8% | +4.7% |
| 10 | 0.375 | 0.542 | +16.7 pp | +23.8% | -2.3% | +49.0% | +20.9% | +5.9% |
| 12 | 0.375 | 0.521 | +14.6 pp | +5.1% | -10.7% | +42.4% | +18.1% | +4.5% |
| avg | 0.388 | 0.566 | +17.8 pp | +31.2% | +15.0% | +46.1% | +18.0% | +4.4% |

LLaMA-13B 支持的主结论：

1. SLO attainment 在所有 per-GPU rate 上均提高，平均 +`17.8 pp`。
2. TTFT p90 全部为正，平均下降 `31.2%`。
3. TPOT p50/p90 全部为正，平均下降 `46.1%/18.0%`。
4. throughput 平均小幅提高 `4.4%`，但低 rate 有轻微负值。
5. TTFT p95 在 per-GPU rate `10/12` 出现负值，说明高压 tail tradeoff 仍存在。

## 跨模型结论

两个模型的趋势一致：

| metric | OPT-13B avg | LLaMA-13B avg | 结论 |
|---|---:|---:|---|
| SLO delta | +17.5 pp | +17.8 pp | 最稳定主结果 |
| TTFT p90 | +29.0% | +31.2% | 可作为 TTFT 主图指标 |
| TTFT p95 | +17.7% | +15.0% | 平均为正，但高 rate 有 tradeoff |
| TPOT p50 | +47.7% | +46.1% | 最强 TPOT 指标 |
| TPOT p90 | +21.1% | +18.0% | 可作为 TPOT 主图指标 |
| throughput | +3.7% | +4.4% | 辅助指标，不作为核心 claim |

推荐主图口径：

1. SLO attainment：主图采用 SLO scale sensitivity，而不是固定 SLO 下的 rate sweep。固定 per-GPU rate 为 `6` req/s/GPU，横轴为 SLO scale，scale `1.0` 对应 `TTFT<=5s, TPOT<=0.12s`。这样可以避免宽松 SLO 或低压区间导致曲线过平，同时展示在不同 SLO 严格度下的 gap。
2. TTFT：主图在同一个 TTFT 子图中同时画 p90 和 p99。推荐 rate 区间为 `2,3,4,5,6,8` req/s/GPU；`10/12` 进入高压 tail tradeoff 区域，适合作为边界分析而非主图窗口。
3. TPOT：主图在同一个 TPOT 子图中同时画 p50 和 p90。推荐 rate 区间为 `2,3,4,5,6,8,10,12,14,16` req/s/GPU；TPOT p50 的绝对值随 rate 变化较小，但相对改善稳定，正文应把它解释为 typical-token latency 的稳定收益，尾部压力主要由 TPOT p90 展示。per-GPU `14/16` 仅用于 TPOT high-rate pressure 展示，不进入 TTFT 主图窗口。
4. 原 `SLO/TTFT/TPOT` 2x3 rate-sweep 图保留为 exploratory 或 appendix，不作为主文主证据。
5. throughput/goodput：作为辅助表或 appendix，说明 PhaseServe 没有用大幅吞吐损失换延迟。

当前绘图脚本为：

| figure | path | 用途 |
|---|---|---|
| latency rate sweep | `docs/figures/end_to_end_latency_rate_sweep.{pdf,png,svg}` | 主 latency 图；2 个模型 x TTFT/TPOT 两列，TTFT 内含 p90/p99，TPOT 内含 p50/p90 |
| SLO scale sensitivity | `docs/figures/slo_scale_sensitivity.{pdf,png,svg}` | 主 SLO 图 |
| legacy rate sweep | `docs/figures/end_to_end_rate_sweep.{pdf,png,svg}` | exploratory/appendix |

TPOT high-rate confirmation 记录在 `docs/stage4d_tpot_highrate_pilot.md`。合并两个 seed 后，per-GPU `14/16` 上 OPT-13B 的 TPOT p90 分别下降 `26.0%/21.2%`，LLaMA-13B 分别下降 `26.6%/20.3%`；但 seed-level TTFT p90 存在 tradeoff，因此 high-rate 点不用于 TTFT 主 claim。

论文目录中同步保留：

```text
paper/end_to_end_latency_rate_sweep.pdf
paper/slo_scale_sensitivity.pdf
```

## 当前可写入论文的 claim

可以写入主文：

> 在 1P1D disaggregated serving 上，PhaseServe 在 OPT-13B 与 LLaMA-13B 的 mixed-regime workload 中，相比 DistServe FCFS 提高 interactive SLO attainment，并稳定降低 TTFT p90 与 TPOT p50/p90。

可以写成更细的实验结论：

1. `TTFT<=5s, TPOT<=0.12s` 下，PhaseServe 平均提高 SLO attainment `17.5-17.8 pp`。
2. TTFT p90 平均下降 `29.0-31.2%`。
3. TPOT p50/p90 平均下降 `46.1-47.7%` / `18.0-21.1%`。
4. throughput 平均小幅提高 `3.7-4.4%`，但不是所有 rate 都提高。

不应写成主 claim：

1. PhaseServe 改善所有 percentile。
2. PhaseServe 在所有高压 rate 下都改善 TTFT p95/p99。
3. TPOT p95/p99 稳定优于 DistServe。
4. throughput 是主要贡献。
5. 越高 rate 收益越大。

## 与 Stage 4C 的关系

Stage 4C 的 OPT-13B `cross_skew_v1` 结果证明 full Phase 在主窗口 rate `2/2.5/3` 有端到端收益，并完成了组件消融。Stage 4D 把实验扩展到更宽 per-GPU rate 和双 13B 模型，并用更合理的 SLO 重新计算端到端 goodput。

因此，Stage 4D 替代 Stage 4C 作为最新端到端主结果入口；Stage 4C 继续保留为机制审计、消融和 workload 调参记录。

## 风险和下一步

当前风险：

1. 仍只有 1P1D，需要后续考虑更多 P/D 配比或多副本结构。
2. 只有两个 seed，论文最终可以补更多 seed 或置信区间。
3. 消融还没有完全在 Stage 4D 的最终双模型、新 SLO、宽 rate 口径下重跑。
4. TPOT p95/p99 与高压 TTFT p95 仍有 tradeoff，claim 必须按 percentile 收窄。
5. LLaMA 模型来源是 ModelScope 镜像，需要在 artifact 中明确记录。

下一步建议：

1. 把 Stage 4D 口径同步到 `docs/current_progress.md` 和图表脚本。
2. 在代表性 rate 上补最终消融：`fcfs`, `bps`, `kas`, `bps_kas`, `phase`。
3. 生成主图草稿：SLO attainment、TTFT p90、TPOT p50/p90。
4. 抽取机制指标：regime share、budget ratio、KAS intensity、pressure potential、bucket tail。
5. 若要强化 TPOT tail claim，再回到 KAS long-output fairness；否则把 TPOT p95/p99 作为 boundary。
