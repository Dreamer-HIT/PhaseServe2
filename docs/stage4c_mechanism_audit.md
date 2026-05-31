# Stage 4C: Mechanism Audit

## 本阶段目标

本阶段解释 OPT-13B mixed-regime 端到端结果背后的机制链路：

```text
pressure signature -> PBC budget/regime -> BPS/KAS action -> TTFT/TPOT/SLO outcome
```

本阶段不修改调度器，不新增性能 claim，只审计已经完成的 mixed-regime runs。

## 产物

新增脚本：

| 文件 | 用途 |
|---|---|
| `remote_distserve/benchmarks/phase_mechanism_audit.py` | 合并 `fcfs`/`phase` summary 与 `phase_metrics`，输出端到端和机制指标对照表 |

远端审计输出：

| 文件 | 路径 |
|---|---|
| Markdown | `/root/data/phase_scheduler_results/stage4_mixed_regime_mechanism_audit_opt13b.md` |
| CSV | `/root/data/phase_scheduler_results/stage4_mixed_regime_mechanism_audit_opt13b.csv` |

输入 runs：

| seed | rate | root |
|---:|---:|---|
| 0 | 2 | `/root/data/phase_scheduler_results/stage4_mixed_regime_fixedrate_opt13b_20260528_113939/seed_0/rate_2` |
| 1 | 2 | `/root/data/phase_scheduler_results/stage4_mixed_regime_seed1_opt13b_20260528_115710/seed_1/rate_2` |
| 0 | 3 | `/root/data/phase_scheduler_results/stage4_mixed_regime_rate3_opt13b_20260528_120758/seed_0/rate_3` |
| 1 | 3 | `/root/data/phase_scheduler_results/stage4_mixed_regime_rate3_opt13b_20260528_120758/seed_1/rate_3` |
| 0 | 4 | `/root/data/phase_scheduler_results/stage4_mixed_regime_fixedrate_opt13b_20260528_113939/seed_0/rate_4` |
| 1 | 4 | `/root/data/phase_scheduler_results/stage4_mixed_regime_seed1_opt13b_20260528_115710/seed_1/rate_4` |
| 0 | 6 | `/root/data/phase_scheduler_results/stage4_mixed_regime_fixedrate_opt13b_20260528_113939/seed_0/rate_6` |

## 端到端指标

正数表示 Phase 相比 DistServe FCFS latency 更低。

| seed | rate | TTFT p50 | TTFT p90 | TTFT p95 | TTFT p99 | TPOT p50 | TPOT p90 | TPOT p95 | TPOT p99 | SLO delta | throughput |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 2 | +3.6% | +22.9% | +20.6% | +42.6% | +2.6% | +21.0% | +13.7% | +30.9% | +1.56 pp | +5.1% |
| 1 | 2 | +55.7% | +22.5% | +29.2% | +45.6% | +24.5% | +18.4% | +6.0% | -26.8% | +7.81 pp | +4.8% |
| 0 | 3 | -9.5% | -0.5% | +1.1% | +19.2% | -4.7% | +18.1% | +17.0% | +16.8% | +4.69 pp | +2.8% |
| 1 | 3 | +10.7% | +5.0% | +8.0% | +3.1% | +8.6% | +0.5% | -0.6% | -55.7% | +7.81 pp | -7.7% |
| 0 | 4 | +19.5% | +45.2% | +0.6% | +18.8% | -3.4% | +6.3% | +1.8% | +7.9% | +9.38 pp | -6.4% |
| 1 | 4 | +6.2% | -14.2% | -11.9% | +7.5% | -17.5% | -2.5% | +9.0% | -49.8% | +6.25 pp | -8.5% |
| 0 | 6 | +1.3% | +12.1% | -7.5% | -20.2% | +1.9% | +13.4% | -11.2% | +7.4% | -7.81 pp | +0.2% |

跨 seed 平均：

| rate | n | TTFT p50 | TTFT p90 | TTFT p95 | TTFT p99 | TPOT p50 | TPOT p90 | TPOT p95 | TPOT p99 | SLO delta | throughput |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | 2 | +29.6% | +22.7% | +24.9% | +44.1% | +13.5% | +19.7% | +9.8% | +2.0% | +4.69 pp | +5.0% |
| 3 | 2 | +0.6% | +2.2% | +4.6% | +11.1% | +2.0% | +9.3% | +8.2% | -19.4% | +6.25 pp | -2.4% |
| 4 | 2 | +12.8% | +15.5% | -5.7% | +13.1% | -10.5% | +1.9% | +5.4% | -21.0% | +7.81 pp | -7.4% |
| 6 | 1 | +1.3% | +12.1% | -7.5% | -20.2% | +1.9% | +13.4% | -11.2% | +7.4% | -7.81 pp | +0.2% |

## 机制指标

| seed | rate | context FTL | decode DH | prefill budget ratio | decode intensity | effective KAS | decode pressure | bridge pressure | KV pressure | hard pressure | max skips p95 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 2 | 98.7% | 69.1% | 0.999 | 0.708 | 0.940 | 0.635 | 0.573 | 0.484 | 0.000 | 569.2 |
| 1 | 2 | 99.4% | 77.5% | 0.999 | 0.794 | 0.939 | 0.708 | 0.788 | 0.519 | 0.000 | 294.6 |
| 0 | 3 | 99.4% | 68.5% | 0.999 | 0.705 | 0.946 | 0.643 | 0.625 | 0.487 | 0.000 | 535.2 |
| 1 | 3 | 99.8% | 64.9% | 0.999 | 0.665 | 0.946 | 0.543 | 0.658 | 0.433 | 0.000 | 229.7 |
| 0 | 4 | 99.7% | 70.7% | 0.999 | 0.717 | 0.952 | 0.605 | 0.681 | 0.439 | 0.000 | 559.1 |
| 1 | 4 | 99.9% | 66.3% | 0.999 | 0.675 | 0.948 | 0.565 | 0.667 | 0.431 | 0.000 | 186.8 |
| 0 | 6 | 99.9% | 80.4% | 0.999 | 0.818 | 0.948 | 0.652 | 0.706 | 0.485 | 0.000 | 358.8 |

跨 seed 平均：

| rate | context FTL | decode DH | prefill budget ratio | decode intensity | effective KAS | decode pressure | bridge pressure | KV pressure | SLO delta |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | 99.1% | 73.3% | 0.999 | 0.751 | 0.939 | 0.672 | 0.681 | 0.502 | +4.69 pp |
| 3 | 99.6% | 66.7% | 0.999 | 0.685 | 0.946 | 0.593 | 0.641 | 0.460 | +6.25 pp |
| 4 | 99.8% | 68.5% | 0.999 | 0.696 | 0.950 | 0.585 | 0.674 | 0.435 | +7.81 pp |
| 6 | 99.9% | 80.4% | 0.999 | 0.818 | 0.948 | 0.652 | 0.706 | 0.485 | -7.81 pp |

## 机制解释

### TTFT 为什么改善

context 侧几乎全程处于 `FIRST_TOKEN_LIMITED` regime，rate `2/3/4/6` 的 context FTL share 为 `98.7%-99.9%`。这说明 PBC 在 mixed-regime workload 中确实识别到了 first-token / bridge pressure。

同时，context prefill budget ratio 始终约为 `0.999`。这点很重要：PBC 没有像早期版本那样把 prefill budget 过度压低，而是在 first-token-limited regime 中保留 BPS 的 prefill shaping 自由度。因此 rate `2` 下 TTFT p50/p90/p95/p99 都稳定改善。

### TPOT 为什么改善

decode 侧有大量 `DECODE_HEAVY` regime。rate `2` 两个 seed 的 decode DH share 平均为 `73.3%`，decode pressure 平均为 `0.672`。PBC 给出的 decode intensity 平均为 `0.751`，而 selected effective KAS intensity 平均为 `0.939`。

这说明 KAS 并不是全程关闭。短输出和 first-token-sensitive 场景下 KAS intensity 会受控，但长输出 eligible 请求仍经常获得 full KAS 排序强度。这解释了 rate `2` 下 TPOT p90/p95 的稳定改善。

### 为什么 TPOT p99 不稳

bucket 诊断显示，TPOT p99 tradeoff 主要来自部分中长 output buckets，而不是所有请求整体变差。

rate `2`：

| seed | bucket | TPOT p90 ratio | TPOT p95 ratio | TPOT p99 ratio |
|---:|---|---:|---:|---:|
| 0 | `(16,64]` | 0.780 | 0.574 | 0.790 |
| 0 | `(128,256]` | 0.896 | 0.975 | 1.046 |
| 0 | `(256,512]` | 0.787 | 0.930 | 1.044 |
| 0 | `>512` | 1.061 | 1.038 | 1.015 |
| 1 | `(16,64]` | 0.960 | 1.031 | 1.387 |
| 1 | `(128,256]` | 0.898 | 1.212 | 1.590 |
| 1 | `(256,512]` | 1.385 | 1.370 | 1.357 |
| 1 | `>512` | 1.158 | 1.135 | 1.113 |

因此，TPOT p90/p95 可以作为主图指标；TPOT p99 应作为 tradeoff 指标报告，不应写成稳定改善 claim。

### rate 3/4 为什么进入 tradeoff

rate `3/4` 的 context 侧仍然是 first-token-limited，prefill budget ratio 也保持约 `0.999`，但 throughput 和 TPOT p99 开始波动。这说明问题不在 prefill budget collapse，也不是 hard KV/swap pressure：hard pressure 均值为 `0.000`。

更可能的原因是 decode active-set shaping 在高压力下把收益集中到 p90/p95 和 SLO goodput，但会让少量中长 output 请求承担更高 tail cost。机制指标中的 `max_consecutive_skips_p95` 很高，也支持这个解释。

## 结论

当前 mixed-regime 机制链路是成立的：

1. PBC 识别出 context 侧 first-token-limited pressure。
2. PBC 保持 prefill budget ratio 约 `0.999`，避免破坏 BPS 的 TTFT owner 作用。
3. decode 侧大比例进入 decode-heavy，KAS 对 eligible 请求保持高 effective intensity。
4. 端到端表现为 rate `2` 下 TTFT p50/p90/p95/p99、TPOT p50/p90/p95、SLO 和吞吐同时改善。

当前边界也很明确：

1. TPOT p99 不稳定，主图不应选择它作为核心 claim。
2. rate `3/4` 已进入 tradeoff 区，适合用于解释压力边界和 SLO tradeoff。
3. 下一步消融必须比较 `bps`、`kas`、`bps_kas` 和 `phase`，证明 rate `2` 的收益不是单个局部策略偶然造成的。

## 后续状态

mixed-regime ablation 已完成，详见 `docs/stage4c_mixed_regime_ablation.md`。

本阶段建议的消融矩阵已经按下表执行：

| policy | 目的 |
|---|---|
| `fcfs` | DistServe baseline |
| `bps` | 验证 TTFT owner |
| `kas` | 验证 TPOT owner |
| `bps_kas` | 验证无 PBC 的局部组合 |
| `phase` | 验证 PBC+BPS+KAS full method |

消融结果显示，`phase` 相比 `bps_kas` 在 rate `2/3` 均进一步改善 SLO、goodput、TTFT tail 和 TPOT p90，支持 PBC 的动态仲裁价值。下一步进入 LLaMA2-13B mixed-regime 复现。
