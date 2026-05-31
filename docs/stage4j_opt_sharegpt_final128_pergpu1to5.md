# Stage 4J OPT-13B ShareGPT Final-Code 128-Request Per-GPU 1-5 Sweep

## 目标

本阶段复查最终默认代码是否保留 Stage 4H Phase512 在 OPT-13B + ShareGPT 的 per-GPU `1-5` 区间上的收益。

Phase512 的旧结果使用 64 requests。本阶段改为 128 requests，并使用当前最终默认机制：

- PBC first/decode conflict owner，默认 first-token path 优先；
- KAS bridge completion drain；
- long-output full-KAS threshold `512`；
- HOL bypass 和 short-output fastlane 默认关闭。

## 配置

| 项 | 设置 |
|---|---|
| 远端结果目录 | `/root/data/phase_scheduler_results/opt13b_sharegpt_final128_pergpu1to5_20260530_111232` |
| Model | OPT-13B, `/root/data/models/opt-13b` |
| Dataset | ShareGPT trace, `/root/data/datasets/distserve_eval/processed/opt13b_sharegpt.ds` |
| Request count | first 128 requests |
| Structure | 1P1D, 2 GPUs |
| Global rates | `2/4/6/8/10` |
| Per-GPU rates | `1/2/3/4/5` |
| Seeds | `0/1` |
| Policies | `fcfs`, `phase` |
| Arrival | Poisson |
| SLO | TTFT `0.25s`, TPOT `0.10s` |
| Max total tokens | `2048` |

## 两 seed 平均改善

正数表示 Phase 优于 FCFS；延迟项为下降比例，SLO 为百分点，Goodput 为 req/s。

| Per-GPU Rate | SLO delta | Goodput delta | TTFT p50 | TTFT p90 | TTFT p95 | TTFT p99 | TPOT p50 | TPOT p90 | TPOT p95 | TPOT p99 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | +8.2 pp | +0.075 | +36.3% | +34.6% | +30.8% | +26.5% | +7.1% | +14.5% | +29.7% | +3.6% |
| 2 | +1.6 pp | +0.005 | +33.5% | +9.5% | +3.1% | +3.1% | +8.4% | -1.3% | +19.9% | +10.7% |
| 3 | +0.0 pp | -0.013 | +30.4% | +6.3% | +6.5% | +2.1% | +3.9% | +1.1% | +16.6% | +8.4% |
| 4 | +0.8 pp | -0.004 | +17.3% | +4.8% | +0.8% | +2.2% | -0.4% | +4.6% | +10.6% | +0.2% |
| 5 | +1.6 pp | +0.009 | +24.8% | -2.8% | +0.3% | +0.5% | +2.2% | -4.6% | +2.4% | +11.8% |

## 两 seed 平均原始值

延迟单位为秒。

| Per-GPU Rate | Policy | SLO | Goodput | TTFT p50 | TTFT p90 | TTFT p95 | TTFT p99 | TPOT p50 | TPOT p90 | TPOT p95 | TPOT p99 |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | `fcfs` | 0.406 | 0.553 | 0.252 | 7.491 | 8.879 | 10.128 | 0.082 | 0.950 | 1.441 | 4.073 |
| 1 | `phase` | 0.488 | 0.627 | 0.157 | 5.323 | 6.559 | 7.704 | 0.076 | 0.812 | 1.015 | 3.927 |
| 2 | `fcfs` | 0.203 | 0.281 | 15.515 | 33.698 | 35.752 | 36.819 | 0.098 | 1.042 | 1.821 | 4.055 |
| 2 | `phase` | 0.219 | 0.285 | 10.325 | 30.491 | 34.657 | 35.684 | 0.090 | 1.056 | 1.457 | 3.619 |
| 3 | `fcfs` | 0.160 | 0.222 | 21.045 | 41.976 | 45.489 | 46.740 | 0.099 | 1.058 | 1.826 | 4.116 |
| 3 | `phase` | 0.160 | 0.210 | 14.643 | 39.313 | 42.536 | 45.750 | 0.096 | 1.047 | 1.523 | 3.770 |
| 4 | `fcfs` | 0.137 | 0.190 | 23.486 | 46.553 | 50.287 | 51.602 | 0.100 | 1.050 | 1.827 | 4.093 |
| 4 | `phase` | 0.145 | 0.186 | 19.407 | 44.307 | 49.889 | 50.453 | 0.101 | 1.002 | 1.633 | 4.087 |
| 5 | `fcfs` | 0.113 | 0.157 | 25.008 | 49.397 | 53.323 | 54.750 | 0.101 | 1.054 | 1.835 | 4.111 |
| 5 | `phase` | 0.129 | 0.166 | 18.805 | 50.742 | 53.166 | 54.483 | 0.099 | 1.103 | 1.792 | 3.625 |

## 观察

1. Per-GPU `1` 是当前最干净的 128-request 正向点。Phase 同时提升 SLO、goodput、TTFT p50/p90/p95/p99 和 TPOT p50/p90/p95/p99。
2. Per-GPU `2` 之后 FCFS 已经明显过载，SLO 从 `0.203` 继续下降到 `0.113`。这些点不能按 Stage 4H 的 64-request 口径解释为常规主图区间。
3. Per-GPU `2-4` 上，Phase 仍稳定改善 TTFT p50/p90/p95/p99，并改善 TPOT p95/p99；但 TPOT p90 和 goodput 不总是提升。
4. Per-GPU `5` 是过载边界。Phase 改善 SLO、goodput、TTFT p50、TPOT p95/p99，但 TTFT p90 和 TPOT p90 变差。
5. 最终代码相对 Phase512 的价值不是在 64-request 表上继续刷更大数值，而是在更长 128-request trace 中修复 bridge/unaccepted pressure transfer，使 per-GPU `1` 和部分高压 tail 指标仍保持正向。

## 对图表的影响

OPT-13B + ShareGPT 的最终主端到端图不应直接展示 per-GPU `1-5` 全区间作为同一种正向 claim。更合理的展示方式是：

1. 主综合图使用 per-GPU `0.75-1.5` 的细粒度区间，重点覆盖当前 per-GPU `1` 的正向窗口。
2. per-GPU `2-4` 可以作为 high-pressure extension 或 appendix，展示 TTFT tail 和 TPOT p95/p99 的压力边界收益。
3. per-GPU `5` 应作为 overload/failure-boundary 点，不能用于 “TTFT 和 TPOT 全部分位同时改善” 的主 claim。
4. 若需要保留 rate `1-5` 图，图注必须明确这是 128-request 压力扫描，其中 `2-5` 已经进入 overload 区。

## 验收

本阶段完成：

- `20/20` runs 全部完成；
- 远端无残留 screen、benchmark 或 server 进程；
- 生成 `sweep_summary.csv/md`、`sweep_analysis.*` 和 `slo_grid.*`；
- 得到最终代码在 128-request per-GPU `1-5` 上的两 seed 平均结果。

结论是：最终代码在 OPT-13B + ShareGPT 128-request 下已经有稳定正向窗口，但主图 rate 区间需要比 Stage 4H 更窄。下一步应围绕 per-GPU `0.75/1.0/1.25/1.5` 做细扫，而不是继续把 `1-5` 全部当作同质主图区间。
