# Stage 4C: Mixed-Regime Component Ablation

## 本阶段目标

本阶段验证 OPT-13B mixed-regime 端到端收益是否来自 PhaseServe 的完整闭环，而不是单个局部启发式偶然造成的。

核心问题是：

1. `bps` 是否主要承担 TTFT owner 的作用。
2. `kas` 是否主要承担 TPOT owner 的作用。
3. 静态组合 `bps_kas` 是否足够，还是需要 PBC 的动态 pressure-to-budget 仲裁。
4. full `phase` 是否能在同一 mixed-regime workload 中同时改善 TTFT、TPOT、SLO 和吞吐。

本阶段不修改调度器代码，只运行正式消融并记录结果。

## 需要读取或修改的文件

| 类型 | 文件 |
|---|---|
| workload generator | `remote_distserve/benchmarks/phase_make_regime_shift_dataset.py` |
| mixed-regime sweep | `remote_distserve/scripts/run_phase_mixed_regime_sweep.sh` |
| 1P1D runner | `remote_distserve/scripts/run_phase_hetero_1p1d.sh` |
| summary collector | `remote_distserve/benchmarks/phase_collect_summaries.py` |
| sweep analyzer | `remote_distserve/benchmarks/phase_analyze_sweep.py` |
| 本文档 | `docs/stage4c_mixed_regime_ablation.md` |

## 具体产物

远端结果目录：

```text
/root/data/phase_scheduler_results/stage4c_mixed_regime_ablation_opt13b_20260528_145013
```

自动生成文件：

| 文件 | 说明 |
|---|---|
| `sweep_summary.csv` / `sweep_summary.md` | 20 个 run 的端到端 summary |
| `sweep_analysis.md` | grouped means、paired delta 和机制字段聚合 |
| `sweep_analysis.paired_summary.csv` | policy 相对 FCFS 的 paired delta/ratio |
| `sweep_analysis.bucket.md` | prompt/output bucket 维度诊断 |
| `slo_grid.grouped.md` | loose/medium/tight 三组 SLO grid |

## 实验设置

| 项目 | 设置 |
|---|---|
| model | OPT-13B |
| model path | `/root/data/models/opt-13b` |
| structure | 1P1D |
| workload | `cross_skew_v1` mixed-regime |
| requests per run | `64` |
| process | `poisson` |
| policies | `fcfs`, `bps`, `kas`, `bps_kas`, `phase` |
| rates | `2`, `3` |
| seeds | `0`, `1` |
| SLO | TTFT `10s`, TPOT `1s` |
| total runs | `20/20` completed |

`cross_skew_v1` 同时包含 long-prompt/short-output、short-prompt/long-output、medium 和 short-short 请求。它用于验证 prefill pressure 与 decode pressure 同时存在时的动态仲裁能力。

## 聚合结果

下表为两个 seed 的均值。

| rate | policy | SLO | completed req/s | goodput req/s | TTFT p50 | TTFT p90 | TTFT p95 | TTFT p99 | TPOT p50 | TPOT p90 | TPOT p95 | TPOT p99 |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | fcfs | 0.9453 | 0.7555 | 0.7138 | 0.2551 | 8.0966 | 8.9645 | 13.5365 | 0.0695 | 0.5162 | 0.5976 | 0.9205 |
| 2 | bps | 0.9297 | 0.7839 | 0.7280 | 0.2480 | 7.9627 | 8.8219 | 12.1510 | 0.0710 | 0.5386 | 0.6229 | 1.0126 |
| 2 | kas | 0.9453 | 0.7498 | 0.7084 | 0.2201 | 8.5194 | 11.1348 | 11.6516 | 0.0585 | 0.4686 | 0.5015 | 0.8785 |
| 2 | bps_kas | 0.9766 | 0.7686 | 0.7504 | 0.2328 | 7.5559 | 8.9726 | 11.4119 | 0.0595 | 0.4613 | 0.5354 | 0.9617 |
| 2 | phase | 0.9844 | 0.7870 | 0.7747 | 0.1353 | 6.5235 | 6.8949 | 7.5797 | 0.0594 | 0.4214 | 0.5317 | 0.8975 |
| 3 | fcfs | 0.7734 | 0.7640 | 0.5901 | 0.4808 | 14.8818 | 15.9121 | 20.5476 | 0.0732 | 0.5816 | 0.6618 | 0.9470 |
| 3 | bps | 0.8125 | 0.7928 | 0.6431 | 0.4476 | 12.8248 | 16.6640 | 19.3699 | 0.0746 | 0.6806 | 0.7445 | 1.0883 |
| 3 | kas | 0.7734 | 0.7593 | 0.5867 | 0.4178 | 15.2608 | 18.0117 | 18.7220 | 0.0657 | 0.5330 | 0.5928 | 0.9298 |
| 3 | bps_kas | 0.7734 | 0.7779 | 0.6011 | 0.4279 | 14.8901 | 15.3419 | 18.4128 | 0.0694 | 0.5232 | 0.5891 | 1.0209 |
| 3 | phase | 0.8047 | 0.7976 | 0.6405 | 0.4096 | 13.3744 | 13.9643 | 15.1142 | 0.0688 | 0.5034 | 0.5923 | 0.9339 |

## 相比 FCFS 的收益

正数表示 PhaseServe policy 更好：latency 为下降百分比，throughput/goodput 为提升百分比，SLO 为百分点。

| rate | policy | SLO delta | completed req/s | goodput | TTFT p50 | TTFT p90 | TTFT p95 | TTFT p99 | TPOT p50 | TPOT p90 | TPOT p95 | TPOT p99 |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | bps | -1.56 pp | +3.75% | +2.00% | +2.78% | +1.65% | +1.59% | +10.24% | -2.09% | -4.32% | -4.24% | -10.01% |
| 2 | kas | +0.00 pp | -0.76% | -0.75% | +13.71% | -5.22% | -24.21% | +13.92% | +15.79% | +9.23% | +16.08% | +4.56% |
| 2 | bps_kas | +3.12 pp | +1.73% | +5.13% | +8.72% | +6.68% | -0.09% | +15.70% | +14.35% | +10.64% | +10.40% | -4.47% |
| 2 | phase | +3.91 pp | +4.17% | +8.54% | +46.96% | +19.43% | +23.09% | +44.01% | +14.52% | +18.37% | +11.03% | +2.50% |
| 3 | bps | +3.91 pp | +3.78% | +8.99% | +6.90% | +13.82% | -4.73% | +5.73% | -1.95% | -17.03% | -12.51% | -14.92% |
| 3 | kas | +0.00 pp | -0.61% | -0.57% | +13.09% | -2.55% | -13.19% | +8.88% | +10.20% | +8.35% | +10.41% | +1.81% |
| 3 | bps_kas | +0.00 pp | +1.82% | +1.86% | +10.99% | -0.06% | +3.58% | +10.39% | +5.17% | +10.05% | +10.97% | -7.81% |
| 3 | phase | +3.12 pp | +4.40% | +8.55% | +14.80% | +10.13% | +12.24% | +26.44% | +6.08% | +13.45% | +10.49% | +1.38% |

## full Phase 相比静态 BPS+KAS

这组对比用于判断 PBC 是否只是把 BPS 和 KAS 拼起来，还是提供了额外的动态仲裁价值。

| rate | SLO delta | completed req/s | goodput | TTFT p50 | TTFT p90 | TTFT p95 | TTFT p99 | TPOT p50 | TPOT p90 | TPOT p95 | TPOT p99 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | +0.78 pp | +2.40% | +3.25% | +41.89% | +13.66% | +23.16% | +33.58% | +0.20% | +8.65% | +0.70% | +6.68% |
| 3 | +3.12 pp | +2.54% | +6.56% | +4.28% | +10.18% | +8.98% | +17.91% | +0.96% | +3.78% | -0.54% | +8.53% |

结论是：静态 BPS+KAS 已经能提供部分 TPOT 和 SLO 好处，但 full Phase 在两个 rate 上都进一步降低 TTFT tail、提高 goodput，并改善 SLO。rate `3` 下 TPOT p95 相比静态组合略差 `0.54%`，但相比 FCFS 仍改善 `10.49%`。

## 组件结论

### BPS

BPS 是 prefill/first-token 侧的局部优化器。它在 rate `3` 明显改善 TTFT p90、SLO 和 goodput，但同时显著恶化 TPOT p90/p95/p99。rate `2` 下 BPS 的 TTFT 改善较弱，TPOT tail 仍变差。

这说明 BPS 单独使用时会把部分压力转移到 decode 侧，因此不能作为完整方法。

### KAS

KAS 是 decode/TPOT 侧的局部优化器。它在 rate `2/3` 都改善 TPOT p50/p90/p95/p99，并且对 TTFT p99 也有帮助。但 KAS 单独使用会恶化 TTFT p90/p95，特别是 rate `2` 的 TTFT p95 下降为 `-24.21%`。

这说明 KAS 能处理 decode tail，但缺少 first-token owner 保护。

### BPS+KAS

静态组合能恢复一部分平衡：rate `2` 的 SLO、goodput、TPOT p90/p95 明显优于 FCFS，rate `3` 也改善 TPOT p90/p95。但静态组合没有 pressure-aware budget 仲裁，rate `2` 的 TTFT p95 基本不变，rate `3` 的 TTFT p90 也没有改善，TPOT p99 仍不稳定。

这说明单纯把两个局部策略打开还不足以形成完整 mixed-regime 控制。

### full Phase

full Phase 在 rate `2/3` 均同时改善 SLO、completed throughput、goodput、TTFT p50/p90/p95/p99 和 TPOT p50/p90/p95/p99。

最干净的主窗口仍是 rate `2`：

1. TTFT p50/p90/p95/p99 分别下降 `46.96%/19.43%/23.09%/44.01%`。
2. TPOT p50/p90/p95/p99 分别下降 `14.52%/18.37%/11.03%/2.50%`。
3. SLO attainment 提升 `3.91 pp`。
4. completed throughput 提升 `4.17%`，goodput 提升 `8.54%`。

rate `3` 作为更高压力辅助窗口：

1. TTFT p50/p90/p95/p99 分别下降 `14.80%/10.13%/12.24%/26.44%`。
2. TPOT p50/p90/p95/p99 分别下降 `6.08%/13.45%/10.49%/1.38%`。
3. SLO attainment 提升 `3.12 pp`。
4. completed throughput 提升 `4.40%`，goodput 提升 `8.55%`。

## SLO grid 补充

默认 SLO 为 TTFT `10s`、TPOT `1s`，偏宽松。额外 SLO grid 说明，在更严格的 loose/medium/tight SLO 下，full Phase 仍然保持最高或接近最高的 SLO attainment 与 goodput。

| SLO label | TTFT | TPOT | rate | FCFS SLO | BPS+KAS SLO | Phase SLO | FCFS goodput | Phase goodput |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| loose | 2.0s | 0.3s | 2 | 0.6250 | 0.6484 | 0.6953 | 0.4704 | 0.5459 |
| loose | 2.0s | 0.3s | 3 | 0.5078 | 0.5625 | 0.5781 | 0.3867 | 0.4594 |
| medium | 1.5s | 0.2s | 2 | 0.5703 | 0.5703 | 0.6250 | 0.4286 | 0.4897 |
| medium | 1.5s | 0.2s | 3 | 0.4375 | 0.5313 | 0.5547 | 0.3333 | 0.4405 |
| tight | 1.0s | 0.1s | 2 | 0.4844 | 0.5313 | 0.5781 | 0.3641 | 0.4524 |
| tight | 1.0s | 0.1s | 3 | 0.3984 | 0.4766 | 0.5000 | 0.3036 | 0.3971 |

这支持后续把主图的 SLO 设置从单一宽松阈值扩展为 SLO sensitivity，而不是只报告 `10s/1s`。

## 验收标准

| 验收项 | 结果 |
|---|---|
| 5 个 policy 全部跑完 | 通过，`20/20` runs completed |
| 每个 run 完成所有请求 | 通过，全部 `64/64` completed |
| full Phase 相比 FCFS 在 rate `2` 同时改善 TTFT 与 TPOT | 通过 |
| full Phase 相比 FCFS 在 rate `3` 保持多数指标改善 | 通过 |
| full Phase 相比静态 `bps_kas` 有额外收益 | 通过，两个 rate 均改善 SLO、goodput、TTFT tail 和 TPOT p90 |
| BPS/KAS 组件职责能被实验区分 | 通过 |
| 可直接写成最终论文结果 | 未通过，需要 LLaMA2-13B 复现和更大 seed 数 |

## 风险和阻塞点

1. 当前仅为 OPT-13B，仍需 LLaMA2-13B 复现。
2. 当前每个 rate 只有两个 seed。趋势清楚，但最终论文需要增加 seed 或置信区间。
3. `10s/1s` 默认 SLO 偏宽松，建议主文同时使用 SLO grid 或更紧 SLO。
4. TPOT p99 不适合作为唯一主图指标；更稳妥的是使用 TPOT p90/p95，并把 p99 作为 tradeoff/sensitivity。
5. rate `3` 虽然 full Phase 整体表现好，但 TPOT p95 相比静态 `bps_kas` 略差，论文表述应强调 full Phase 的端到端 balance，而不是所有子指标都优于所有 ablation。

## 本阶段结论

本阶段给出目前最完整的 mixed-regime ablation 证据：

1. BPS 单独优化 TTFT 倾向，但会造成 decode-side TPOT tradeoff。
2. KAS 单独优化 TPOT 倾向，但会牺牲部分 TTFT tail。
3. 静态 BPS+KAS 能改善部分指标，但不能稳定获得 TTFT/TPOT/SLO/goodput 的联合收益。
4. full Phase 通过 PBC 的动态仲裁，在 rate `2/3` 同时改善 TTFT tail、TPOT tail、SLO attainment 和 goodput。

因此，当前 ablation 支持把 PhaseServe 的核心 claim 收窄为：

> 在 prefill pressure 与 decode pressure 同时存在的 mixed-regime serving workload 中，PhaseServe 通过 pressure-to-budget 仲裁把 BPS 和 KAS 约束在同一个动态预算闭环内，从而比 DistServe FCFS 和静态 BPS+KAS 取得更好的端到端 balance。

下一步不应继续盲目调 OPT-13B rate，而应进入 LLaMA2-13B mixed-regime 复现，并同时准备最终图表脚本。
