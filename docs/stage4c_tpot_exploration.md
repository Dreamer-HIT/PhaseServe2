# Stage 4C: TPOT-Focused Mixed-Regime Exploration

## 本阶段目标

本阶段复盘 Stage 4C 后，针对一个现象做小规模验证：当前 mixed-regime 结果中 TTFT 改善强于 TPOT 改善。我们需要判断 TPOT 收益是否会在更合适的 operating point 或更 decode-heavy 的 mixed workload 中增强。

本阶段不修改调度器算法，只调整 workload profile 和 rate。

## 需要读取或修改的文件

| 类型 | 文件 |
|---|---|
| workload generator | `remote_distserve/benchmarks/phase_make_regime_shift_dataset.py` |
| mixed-regime sweep | `remote_distserve/scripts/run_phase_mixed_regime_sweep.sh` |
| summary collector | `remote_distserve/benchmarks/phase_collect_summaries.py` |
| sweep analyzer | `remote_distserve/benchmarks/phase_analyze_sweep.py` |
| 本文档 | `docs/stage4c_tpot_exploration.md` |

## 实验假设

TPOT 改善不一定随 request rate 单调增强。更高 rate 会提高 decode pressure，但过高 rate 会进入 overload，使少量 long-output 请求承担 tail cost。因此更合理的验证方式是：

1. 在已有 `cross_skew_v1` 上补 rate `2.5/3.5`，检查 `2 -> 4` 之间是否存在更好的 TPOT p90/p95 窗口。
2. 新增一个 decode-heavier mixed profile，在不完全丢掉 prefill pressure 的前提下，提高 short-prompt/long-output 的比例。

## 新 workload profile

新增 `cross_decode_v1`：

```text
64x1024:0.28, 256x512:0.22,
512x512:0.15,
1536x32:0.15, 1024x64:0.10,
64x32:0.10
```

该 profile 保留 long-prompt/short-output 请求用于制造 first-token pressure，但把 long-output 请求比例提高到约 `65%`，用于放大 decode/KAS 作用。

## 小实验矩阵

### A. Rate 细扫补点

| 项目 | 设置 |
|---|---|
| model | OPT-13B |
| structure | 1P1D |
| workload | `cross_skew_v1` |
| policies | `fcfs`, `phase` |
| rates | `2.5`, `3.5` |
| seeds | `0`, `1` |
| requests | `64` |

目的：补齐已有 rate `2/3/4` 之间的空档，判断 TPOT p90/p95 的最优区间是否在 `2.5/3.5`。

### B. Decode-heavier mixed workload

| 项目 | 设置 |
|---|---|
| model | OPT-13B |
| structure | 1P1D |
| workload | `cross_decode_v1` |
| policies | `fcfs`, `bps_kas`, `phase` |
| rates | `2`, `2.5`, `3` |
| seeds | `0`, `1` |
| requests | `64` |

目的：判断提高 decode-heavy 占比后，full `phase` 的 TPOT p90/p95 是否比 `cross_skew_v1` 更强，同时检查 PBC 是否仍优于静态 `bps_kas`。

## 验收标准

| 问题 | 验收方式 |
|---|---|
| 更高 rate 是否增强 TPOT | `cross_skew_v1` rate `2.5/3.5` 的 TPOT p90/p95 相比 FCFS 的改善是否高于 rate `2/3` |
| decode-heavy mixed 是否增强 TPOT | `cross_decode_v1` 的 TPOT p90/p95 改善是否明显高于 `cross_skew_v1` |
| 是否进入 overload | 检查 SLO、goodput、TPOT p99 和 completed throughput 是否明显恶化 |
| PBC 是否仍有价值 | `phase` 相比 `bps_kas` 是否改善 SLO/goodput/TPOT p90，且不明显牺牲 TTFT tail |

## 风险和阻塞点

1. decode-heavy profile 可能提升 TPOT，但削弱 TTFT 主窗口，因此不能直接替代 `cross_skew_v1`。
2. rate `3.5/4` 可能进入 overload，TPOT p99 会波动。
3. 若 TPOT 改善仍不强，下一步应回到 Stage 2 优化 KAS 的 long-output fairness，而不是继续拉高 rate。

## 具体产物

远端结果目录：

```text
/root/data/phase_scheduler_results/stage4c_tpot_rate_finesweep_opt13b_20260528_155734
/root/data/phase_scheduler_results/stage4c_tpot_cross_decode_opt13b_20260528_155734
```

自动生成文件：

| 文件 | 说明 |
|---|---|
| `sweep_summary.csv` / `sweep_summary.md` | 每个 run 的端到端 summary |
| `sweep_analysis.md` | grouped means、paired delta 和机制字段聚合 |
| `sweep_analysis.paired_summary.csv` | policy 相对 FCFS 的 paired delta/ratio |
| `slo_grid.grouped.md` | loose/medium/tight SLO grid |

完成情况：

| sweep | runs | 状态 |
|---|---:|---|
| `cross_skew_v1` rate fine | `8/8` | 完成 |
| `cross_decode_v1` | `18/18` | 完成 |

## 结果 A：`cross_skew_v1` rate 细扫

下表为两个 seed 的均值。

| rate | policy | SLO | done/s | good/s | TTFT p50 | TTFT p90 | TTFT p95 | TTFT p99 | TPOT p50 | TPOT p90 | TPOT p95 | TPOT p99 |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2.5 | fcfs | 0.8047 | 0.7533 | 0.6056 | 0.3065 | 12.4031 | 13.3578 | 18.0401 | 0.0733 | 0.5621 | 0.6442 | 0.9713 |
| 2.5 | phase | 0.8516 | 0.7920 | 0.6722 | 0.2869 | 10.5761 | 11.4204 | 12.2966 | 0.0653 | 0.4762 | 0.5670 | 0.9418 |
| 3.5 | fcfs | 0.7578 | 0.7604 | 0.5752 | 0.6670 | 16.4768 | 17.5561 | 22.2418 | 0.0745 | 0.5957 | 0.6811 | 0.9553 |
| 3.5 | phase | 0.8594 | 0.7294 | 0.6279 | 0.6194 | 14.6382 | 16.3752 | 21.4823 | 0.0712 | 0.6035 | 0.6449 | 1.0719 |

相比 FCFS，正数表示 Phase 更好。

| rate | SLO delta | completed | goodput | TTFT p50 | TTFT p90 | TTFT p95 | TTFT p99 | TPOT p50 | TPOT p90 | TPOT p95 | TPOT p99 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2.5 | +4.69 pp | +5.12% | +10.77% | +5.38% | +14.15% | +14.07% | +31.75% | +9.12% | +15.12% | +11.96% | -0.30% |
| 3.5 | +10.16 pp | -3.95% | +9.09% | +12.32% | +11.39% | +6.41% | +5.14% | +4.18% | -3.15% | +4.43% | -18.95% |

结论是：`cross_skew_v1` 的 TPOT 收益确实存在更合适的中间 operating point。rate `2.5` 比 rate `3.5` 更适合作为 TPOT 辅助窗口，因为它同时改善 TTFT p90/p95、TPOT p90/p95、SLO、completed throughput 和 goodput；rate `3.5` 虽然 SLO/goodput 仍提高，但 completed throughput 下降，TPOT p90 和 p99 变差，已经接近 overload/tradeoff 边界。

## 结果 B：`cross_decode_v1` decode-heavy mixed profile

下表为两个 seed 的均值。

| rate | policy | SLO | done/s | good/s | TTFT p50 | TTFT p90 | TTFT p95 | TTFT p99 | TPOT p50 | TPOT p90 | TPOT p95 | TPOT p99 |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | fcfs | 0.6953 | 0.6046 | 0.4218 | 0.1921 | 24.0259 | 31.4645 | 33.2507 | 0.0940 | 1.0432 | 1.3046 | 1.5996 |
| 2 | bps_kas | 0.7188 | 0.5975 | 0.4334 | 0.1352 | 24.8449 | 30.2809 | 35.2631 | 0.0865 | 1.0809 | 1.3281 | 1.5209 |
| 2 | phase | 0.7344 | 0.5953 | 0.4395 | 0.1361 | 22.6762 | 30.6585 | 34.8057 | 0.0867 | 0.9759 | 1.4261 | 1.6558 |
| 2.5 | fcfs | 0.6953 | 0.6038 | 0.4210 | 0.2515 | 28.5291 | 35.9776 | 37.9909 | 0.0979 | 1.1114 | 1.3867 | 1.6044 |
| 2.5 | bps_kas | 0.6562 | 0.6049 | 0.3970 | 0.1658 | 30.1773 | 35.6855 | 39.5699 | 0.0883 | 1.1434 | 1.3784 | 1.7772 |
| 2.5 | phase | 0.6875 | 0.6054 | 0.4171 | 0.1640 | 26.7808 | 34.8652 | 38.7011 | 0.0890 | 1.0301 | 1.4586 | 1.7608 |
| 3 | fcfs | 0.6641 | 0.6076 | 0.4039 | 0.4943 | 31.1888 | 38.5329 | 40.6226 | 0.0989 | 1.1331 | 1.4032 | 1.6041 |
| 3 | bps_kas | 0.6562 | 0.6031 | 0.3958 | 0.1940 | 32.4036 | 38.9691 | 44.5880 | 0.0906 | 1.1650 | 1.3894 | 1.5978 |
| 3 | phase | 0.6719 | 0.6089 | 0.4091 | 0.1942 | 28.8632 | 37.4965 | 41.5503 | 0.0912 | 1.0796 | 1.4867 | 1.7624 |

相比 FCFS，正数表示对应 policy 更好。

| rate | policy | SLO delta | completed | goodput | TTFT p50 | TTFT p90 | TTFT p95 | TTFT p99 | TPOT p50 | TPOT p90 | TPOT p95 | TPOT p99 |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | bps_kas | +2.34 pp | -1.22% | +1.96% | +29.56% | -11.40% | +2.82% | -6.09% | +7.95% | -2.71% | -3.85% | +3.75% |
| 2 | phase | +3.91 pp | -1.40% | +3.99% | +29.10% | -2.06% | +4.04% | -2.86% | +7.67% | +6.24% | -10.73% | -4.56% |
| 2.5 | bps_kas | -3.91 pp | -0.02% | -5.61% | +32.26% | -11.99% | -0.95% | -3.79% | +9.88% | -2.37% | -0.47% | -9.99% |
| 2.5 | phase | -0.78 pp | +0.17% | -0.93% | +32.94% | +1.46% | +4.38% | -0.03% | +9.15% | +7.42% | -5.40% | -9.55% |
| 3 | bps_kas | -0.78 pp | -0.90% | -2.07% | +60.49% | -9.69% | -2.99% | -8.53% | +8.34% | -2.68% | -1.22% | -0.27% |
| 3 | phase | +0.78 pp | +0.14% | +1.32% | +60.26% | +3.03% | +3.35% | -0.75% | +7.79% | +4.97% | -6.60% | -9.46% |

结论是：简单提高 decode-heavy 请求占比并不会让 TPOT 全分位单调变好。`cross_decode_v1` 中 full Phase 在 rate `2/2.5/3` 均改善 TPOT p50 和 p90，但 TPOT p95/p99 变差，说明长输出请求把 tail cost 推到了更高分位。该 profile 更适合作为 long-output stress 或 failure-boundary 分析，而不是端到端主图 workload。

## 验收结论

| 问题 | 结论 |
|---|---|
| 更高 rate 是否增强 TPOT | 部分成立。`cross_skew_v1` rate `2.5` 是更好的 TPOT p90/p95 窗口；rate `3.5` 已出现 TPOT p90/p99 和 completed throughput tradeoff |
| decode-heavy mixed 是否增强 TPOT | 不适合作为主结论。它增强了 TPOT p50/p90，但 p95/p99 变差，反映 long-output tail transfer |
| 是否进入 overload | `cross_decode_v1` seed1/rate `3` 的 FCFS TTFT p90 约 `39.68s`、TPOT p90 约 `1.33s`，属于明显边界压力 |
| PBC 是否仍有价值 | 在 `cross_decode_v1` 中，full Phase 相比静态 `bps_kas` 更稳定地改善 SLO/goodput/TTFT p90，但无法消除 TPOT p95/p99 tail |

## 本阶段结论

1. 端到端主 workload 仍应使用 `cross_skew_v1`，因为它同时包含 prefill pressure 与 decode pressure，且 full Phase 能在同一请求流中同时改善 TTFT、TPOT、SLO 和 goodput。
2. TPOT 辅助图可以优先考虑 `cross_skew_v1` 的 rate `2` 和 `2.5`。rate `2.5` 相比 FCFS 的 TPOT p90/p95 分别下降 `15.12%/11.96%`，同时 TTFT p90/p95 分别下降 `14.15%/14.07%`。
3. `cross_decode_v1` 不应作为主图 workload。它可以作为 stress/boundary 结果，用来说明在极端长输出混合下，PhaseServe 仍能改善 TPOT p50/p90 和 TTFT p50/p90，但 TPOT p95/p99 存在 tail transfer。
4. 若后续希望把 TPOT p95/p99 也做成强 claim，需要回到 Stage 2 优化 KAS 的 long-output fairness，而不是继续简单提高 rate 或增加 long-output 占比。

因此，本阶段没有推翻 Stage 4C mixed-regime 主结果；它把 TPOT 展示窗口从原先的 rate `2/3` 细化为：主窗口 `cross_skew_v1` rate `2`，TPOT 辅助窗口 `cross_skew_v1` rate `2.5`，stress/boundary 使用 `cross_decode_v1`。
