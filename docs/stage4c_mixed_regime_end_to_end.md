# Stage 4C: Mixed-Regime End-to-End Validation

## 本阶段目标

本阶段验证 full `phase` 在单一 mixed-regime workload 下，是否能相对 DistServe FCFS 同时改善端到端 TTFT tail、TPOT tail 和 SLO attainment。

这个 workload 将 prompt-skew 与 decode-heavy 合并为一个相关分布，而不是分成两个独立 workload。目标是模拟真实在线流量中的两类压力同时存在：

1. long-prompt / short-output 请求制造 prefill 和 first-token pressure。
2. short-prompt / long-output 请求制造 decode 和 TPOT pressure。
3. medium 请求和 short-short 请求作为背景流量，避免 workload 退化成单一极端案例。

## 读取和修改的文件

| 类型 | 文件 |
|---|---|
| workload generator | `remote_distserve/benchmarks/phase_make_regime_shift_dataset.py` |
| sweep script | `remote_distserve/scripts/run_phase_mixed_regime_sweep.sh` |
| 1p1d runner | `remote_distserve/scripts/run_phase_hetero_1p1d.sh` |
| benchmark summary | `remote_distserve/benchmarks/phase_native_benchmark.py` |

本阶段新增 `cross_skew_v1` profile：

```text
1536x32:0.18, 1024x64:0.17,
64x1024:0.18, 256x512:0.17,
512x256:0.15, 64x32:0.15
```

每个 pair 表示 `prompt_len x output_len`。该 profile 的 base rate 为 `1.0`，实际 total request rate 由 `PHASE_RATE_SCALE` 放大。

## 修复记录

### PHASE_RATE_SCALE 未传递

旧脚本只有在 `PHASE_RATE_SCHEDULE` 非空时才向 benchmark 传递 `--phase-rate-scale`。mixed-regime workload 使用 metadata 中的 `base_rate=1.0`，不使用显式 schedule，因此旧 pilot 的 rate2/rate4/rate6 实际都按 `1.0 req/s` 提交。

本阶段修复为：无论是否存在显式 phase schedule，都传递 `--phase-rate-scale`。修复后旧 pilot 的低压结果不再作为结论使用。

### 13B 默认 GPU memory utilization

OPT-13B 在 1p1d 启动时，`GPU_MEMORY_UTILIZATION=0.38` 会导致可用 GPU KV blocks 为 `0`，服务启动失败。本阶段将默认值调整为 `0.85`，本轮 OPT-13B 实验均使用该设置。

## 实验设置

| 项目 | 设置 |
|---|---|
| model | OPT-13B |
| model path | `/root/data/models/opt-13b` |
| structure | 1P1D |
| policies | `fcfs`, `phase` |
| workload profile | `cross_skew_v1` |
| requests per run | `64` |
| process | `poisson` |
| SLO | TTFT `10s`, TPOT `1s` |
| seeds | `0`, `1` |
| total rate scales | `2`, `3`, `4`, plus seed0 `6` as overload boundary |

结果目录：

| 内容 | 路径 |
|---|---|
| seed0 rate2/4/6 | `/root/data/phase_scheduler_results/stage4_mixed_regime_fixedrate_opt13b_20260528_113939` |
| seed1 rate2/4 | `/root/data/phase_scheduler_results/stage4_mixed_regime_seed1_opt13b_20260528_115710` |
| seed0/1 rate3 | `/root/data/phase_scheduler_results/stage4_mixed_regime_rate3_opt13b_20260528_120758` |

## 结果汇总

表中 ratio 为 `phase / fcfs`。小于 `1.0` 表示 Phase 更低。

| seed | rate | SLO FCFS->Phase | throughput FCFS->Phase | TTFT p90 | TTFT p95 | TPOT p90 | TPOT p95 | TPOT p99 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 2 | 0.9688->0.9844 | 0.734->0.771 (1.051) | 0.771 | 0.794 | 0.790 | 0.863 | 0.691 |
| 1 | 2 | 0.9062->0.9844 | 0.773->0.810 (1.048) | 0.775 | 0.708 | 0.816 | 0.940 | 1.268 |
| 0 | 3 | 0.8281->0.8750 | 0.749->0.770 (1.028) | 1.005 | 0.989 | 0.819 | 0.830 | 0.832 |
| 1 | 3 | 0.7188->0.7969 | 0.775->0.716 (0.923) | 0.950 | 0.920 | 0.995 | 1.006 | 1.557 |
| 0 | 4 | 0.8125->0.9062 | 0.748->0.700 (0.936) | 0.548 | 0.994 | 0.937 | 0.982 | 0.921 |
| 1 | 4 | 0.6875->0.7500 | 0.777->0.711 (0.915) | 1.142 | 1.119 | 1.025 | 0.910 | 1.498 |
| 0 | 6 | 0.8125->0.7344 | 0.749->0.751 (1.002) | 0.879 | 1.075 | 0.866 | 1.112 | 0.926 |

跨 seed 平均：

| rate | n | SLO delta | throughput ratio | TTFT p90 | TTFT p95 | TTFT p99 | TPOT p90 | TPOT p95 | TPOT p99 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | 2 | +4.69 pp | 1.050 | 0.773 | 0.751 | 0.559 | 0.803 | 0.902 | 0.980 |
| 3 | 2 | +6.25 pp | 0.976 | 0.978 | 0.954 | 0.889 | 0.907 | 0.918 | 1.194 |
| 4 | 2 | +7.81 pp | 0.926 | 0.845 | 1.057 | 0.869 | 0.981 | 0.946 | 1.210 |
| 6 | 1 | -7.81 pp | 1.002 | 0.879 | 1.075 | 1.202 | 0.866 | 1.112 | 0.926 |

## 结论

### 主窗口：rate 2

rate `2` 是当前最干净的 full Phase end-to-end 结果。两个 seed 均完成 `64/64` 请求，Phase 相比 FCFS：

1. TTFT p90 平均下降约 `22.7%`。
2. TTFT p95 平均下降约 `24.9%`。
3. TPOT p90 平均下降约 `19.7%`。
4. TPOT p95 平均下降约 `9.8%`。
5. SLO attainment 平均提升 `4.69 pp`。
6. completed request throughput 平均提升约 `5.0%`。

TPOT p99 在 seed1 变差，因此当前主图不应把 TPOT p99 作为唯一代表指标。更稳妥的展示是 TTFT p90/p95 与 TPOT p90/p95。

### 辅助窗口：rate 3

rate `3` 的 SLO attainment 两个 seed 均提升，TTFT p95/p99 平均改善，TPOT p90/p95 平均改善。但 seed1 的 TPOT p99 明显变差，throughput 也下降。

因此 rate `3` 可以作为 mixed-regime 的辅助点，展示 Phase 在更高压力下仍能提升 SLO 和多数 tail 指标，但需要同步报告 throughput 和 TPOT p99 tradeoff。

### 边界窗口：rate 4 和 rate 6

rate `4` 已进入明显 tradeoff 区。seed0 的 TTFT p90 和 SLO 很强，但 seed1 的 TTFT p90/p95 和 TPOT p99 变差。rate `6` 只跑了 seed0，SLO 下降且 TTFT p95/p99 变差。

这些点适合作为 overload/boundary analysis，而不是主 claim。

## 当前验收状态

| 验收项 | 状态 |
|---|---|
| mixed-regime workload 合并 prompt-skew 和 decode-heavy | 通过 |
| 修复 rate scale，使横轴 rate 真实生效 | 通过 |
| OPT-13B 1P1D full Phase 对比 FCFS 完成两个 seed | 通过 |
| 找到 TTFT 和 TPOT 同时改善的主窗口 | 通过，rate `2` |
| 找到连续 rate 上所有指标稳定改善 | 未通过，rate `3/4` 存在 p99 和吞吐 tradeoff |
| 可直接扩到 LLaMA-13B | 可以，但应先复用 rate `2/3`，不要从 rate `4/6` 开始 |

## 下一步

1. mechanism summary 已完成，详见 `docs/stage4c_mechanism_audit.md`。
2. 组件消融已完成，详见 `docs/stage4c_mixed_regime_ablation.md`。
3. 用同一 `cross_skew_v1` workload 在 LLaMA2-13B 上跑 rate `2/3`、seed `0/1`。
4. 端到端主图优先使用 TTFT p90/p95、TPOT p90/p95 和 SLO attainment；TPOT p99 与 throughput 作为 tradeoff 图或表格。
5. rate `4/6` 保留为 overload boundary，不写成稳定收益区间。

## 机制审计补充

机制审计已完成，详见 `docs/stage4c_mechanism_audit.md`。

核心结论：

1. context 侧几乎全程识别为 `FIRST_TOKEN_LIMITED`，rate `2/3/4/6` 的占比为 `98.7%-99.9%`。
2. context prefill budget ratio 始终约为 `0.999`，说明 PBC 没有过度压低 prefill budget，BPS 的 TTFT owner 作用被保留。
3. decode 侧存在大量 `DECODE_HEAVY` regime；rate `2` 两个 seed 的 decode DH share 平均为 `73.3%`。
4. rate `2` 的 selected effective KAS intensity 平均约 `0.939`，说明长输出 eligible 请求仍使用较强 KAS 排序。
5. TPOT p99 不稳定主要集中在部分中长 output buckets，因此 TPOT p99 应作为 tradeoff 指标，而不是主图核心 claim。
