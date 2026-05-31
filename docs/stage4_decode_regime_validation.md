# Stage 4 Decode-Heavy Regime Validation

更新时间：2026-05-27

## 本阶段目标

验证 `regime-aware PBC + intensity-controlled KAS` 代码对齐后，full `phase` 在 OPT-13B decode-heavy workload 下是否仍保留 KAS 的 TPOT tail 优势，并确认新指标 `regime`、`decode_utility_intensity` 能被记录和汇总。

## 读取或修改的文件

本阶段运行实验和读取结果，不修改调度代码。

相关代码和脚本：

- `distserve/phase_scheduler.py`
- `distserve/decoding_stage_scheduler.py`
- `distserve/context_stage_scheduler.py`
- `benchmarks/phase_native_benchmark.py`
- `benchmarks/phase_collect_summaries.py`
- `benchmarks/phase_analyze_sweep.py`
- `scripts/run_phase_decode_heavy_sweep.sh`

## 实验配置

结果目录：

```text
/root/data/phase_scheduler_results/stage4_decode_regime_opt13b_s0_r2_gpu085_20260527_190952
```

配置：

- model：`/root/data/models/opt-13b`
- serving：1P1D，2 x A800 40GB
- GPU memory utilization：`0.85`
- workload：decode-heavy synthetic
- prompt mix：`64:0.60,256:0.25,512:0.15`
- output mix：`128:0.25,256:0.30,512:0.30,1024:0.15`
- seed：`0`
- total request rate：`2 req/s`
- requests：`48`
- policies：`fcfs`、`kas`、`phase`、`bps_kas`
- SLO：TTFT `10s`，TPOT `1s`

初次尝试使用默认 `GPU_MEMORY_UTILIZATION=0.38`，OPT-13B profile 得到 `num_gpu_blocks=0` 并触发 CUDA IPC handle error；随后改为 `0.85` 后实验正常完成。

## 具体产物

四个 policy 均完成，`completed=48/48`。核心结果如下：

| policy | TTFT p50 | TTFT p90 | TTFT p99 | TPOT p50 | TPOT p90 | TPOT p95 | TPOT p99 | TPOT p99 ratio vs FCFS | completed req/s | output tok/s | SLO |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| fcfs | 0.0584 | 0.0925 | 0.1025 | 0.0688 | 0.1806 | 0.2991 | 0.3251 | 1.000 | 0.504 | 248.8 | 1.000 |
| kas | 0.0578 | 0.0918 | 0.1015 | 0.0646 | 0.1828 | 0.2872 | 0.3103 | 0.955 | 0.519 | 255.9 | 1.000 |
| phase | 0.0574 | 0.0919 | 0.1026 | 0.0646 | 0.1835 | 0.2886 | 0.3102 | 0.954 | 0.518 | 255.4 | 1.000 |
| bps_kas | 0.0567 | 0.0921 | 0.1027 | 0.0644 | 0.1844 | 0.2865 | 0.3089 | 0.950 | 0.517 | 255.0 | 1.000 |

机制指标：

| policy | mean KAS intensity | decode regimes | context regimes | mean context prefill budget ratio |
|---|---:|---|---|---:|
| kas | 1.000 | `STATIC:3421` | n/a | n/a |
| phase | 0.310 | `DECODE_HEAVY:910, FIRST_TOKEN_LIMITED:1406, MIXED_SLO:1111` | `DECODE_HEAVY:20, FIRST_TOKEN_LIMITED:17, MIXED_SLO:11` | 0.934 |
| bps_kas | 1.000 | `STATIC:3437` | `STATIC:48` | 1.000 |

## 当前结论

这次最小验证支持两个有限结论：

1. 新代码的 `phase` 没有破坏 KAS 的 TPOT p99 收益。`phase` 的 TPOT p99 ratio 为 `0.954`，和 `kas` 的 `0.955` 基本一致。
2. `decode_utility_intensity` 与 `regime` 指标已经进入 summary。`phase` 的 decode 侧同时出现 `DECODE_HEAVY`、`FIRST_TOKEN_LIMITED` 和 `MIXED_SLO`，平均 KAS intensity 为 `0.310`，说明 PBC 仲裁确实在运行。

但这次不能作为最终论文主结果：

1. rate=2 下所有 policy 的 SLO attainment 都是 `1.0`，SLO 指标没有区分度。
2. TPOT p90 略高于 FCFS；收益主要出现在 p95/p99。
3. 只有 seed0，缺少跨 seed 稳定性。
4. workload 压力还不够强，尚未验证高负载下 regime-aware PBC 是否优于 static `bps_kas`。

## 验收标准

本轮验收：

- `fcfs/kas/phase/bps_kas` 均完成：通过。
- summary/analysis 生成：通过。
- `phase` 记录 `regime` 和 `decode_utility_intensity`：通过。
- `phase` 相比 FCFS 保留 TPOT p99 优势：通过。

## 风险和阻塞点

1. SLO 设置过松，不适合直接画 SLO attainment 主图。
2. rate=2 对 OPT-13B decode-heavy 仍偏轻，不能判断 PBC 在 decode pressure 上的上限收益。
3. `phase` 的平均 KAS intensity 只有 `0.310`，但 p99 TPOT 仍保留；需要更高 rate 验证是否会在 p90/p95 上出现损失。
4. 下一步应跑 seed1，以及 rate3/rate4 小矩阵，寻找 SLO 和 TPOT tail 都有区分度的展示区间。

## 新增：rate3/rate4 两 seed 小矩阵

结果目录：

```text
/root/data/phase_scheduler_results/stage4_decode_regime_opt13b_s01_r34_gpu085_20260527_195236
```

配置沿用上面的 OPT-13B decode-heavy workload，新增：

- seeds：`0,1`
- total request rates：`3,4 req/s`
- 1P1D 使用 2 张 GPU；若论文图横轴使用 Per-GPU Rates，则对应 `1.5,2.0 req/s/GPU`
- 每个 seed/rate/policy：`48` 个请求
- policies：`fcfs`、`kas`、`phase`、`bps_kas`

本轮 16 个 runs 全部完成，并生成：

- `sweep_summary.csv`
- `sweep_summary.md`
- `sweep_analysis.md`
- `sweep_analysis.paired.csv`
- `slo_grid.csv`

### 相对 FCFS 的平均比例

下表按 seed 配对后再平均。latency ratio 小于 `1.0` 表示更好，throughput ratio 大于 `1.0` 表示更好。

| total rate | policy | TTFT p50 | TTFT p90 | TTFT p95 | TTFT p99 | TPOT p50 | TPOT p90 | TPOT p95 | TPOT p99 | completed req/s | output tok/s |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 3 | kas | 0.9759 | 1.0098 | 0.9842 | 0.9622 | 0.9029 | 0.9021 | 0.9529 | 0.9215 | 1.0517 | 1.0517 |
| 3 | phase | 0.9779 | 1.0015 | 1.0229 | 1.0333 | 0.9049 | 0.9036 | 0.9541 | 0.9233 | 1.0503 | 1.0503 |
| 3 | bps_kas | 1.0232 | 1.0203 | 1.0179 | 1.0484 | 0.9080 | 0.9124 | 0.9226 | 0.9083 | 1.0223 | 1.0223 |
| 4 | kas | 0.9954 | 0.9612 | 1.0083 | 1.0294 | 0.9130 | 0.9046 | 0.9606 | 0.9284 | 1.0506 | 1.0506 |
| 4 | phase | 1.0275 | 0.9743 | 0.9701 | 1.1241 | 0.9094 | 0.9189 | 0.9251 | 0.8987 | 1.0306 | 1.0306 |
| 4 | bps_kas | 1.0013 | 0.9724 | 0.9848 | 1.0757 | 0.9108 | 0.9059 | 0.9631 | 0.9279 | 1.0502 | 1.0502 |

跨 rate 和 seed 的总体平均：

| policy | TTFT p50 | TTFT p90 | TTFT p95 | TTFT p99 | TPOT p50 | TPOT p90 | TPOT p95 | TPOT p99 | completed req/s | output tok/s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| kas | 0.9857 | 0.9855 | 0.9962 | 0.9958 | 0.9079 | 0.9034 | 0.9567 | 0.9249 | 1.0511 | 1.0511 |
| phase | 1.0027 | 0.9879 | 0.9965 | 1.0787 | 0.9072 | 0.9112 | 0.9396 | 0.9110 | 1.0404 | 1.0404 |
| bps_kas | 1.0123 | 0.9964 | 1.0014 | 1.0620 | 0.9094 | 0.9091 | 0.9429 | 0.9181 | 1.0362 | 1.0362 |

### 绝对均值

| total rate | policy | TTFT p50 | TTFT p90 | TTFT p95 | TTFT p99 | TPOT p50 | TPOT p90 | TPOT p95 | TPOT p99 | completed req/s | output tok/s |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 3 | fcfs | 0.05322 | 0.09166 | 0.09574 | 0.10547 | 0.07438 | 0.19826 | 0.29268 | 0.33308 | 0.57315 | 242.69 |
| 3 | kas | 0.05186 | 0.09256 | 0.09421 | 0.10143 | 0.06721 | 0.18014 | 0.27968 | 0.30840 | 0.60410 | 255.08 |
| 3 | phase | 0.05207 | 0.09180 | 0.09796 | 0.10889 | 0.06735 | 0.18042 | 0.28003 | 0.30898 | 0.60323 | 254.75 |
| 3 | bps_kas | 0.05440 | 0.09352 | 0.09749 | 0.11057 | 0.06755 | 0.18236 | 0.26850 | 0.30161 | 0.58771 | 247.90 |
| 4 | fcfs | 0.05197 | 0.09729 | 0.10193 | 0.10715 | 0.07877 | 0.21332 | 0.31416 | 0.36068 | 0.57458 | 243.30 |
| 4 | kas | 0.05175 | 0.09319 | 0.10271 | 0.11001 | 0.07199 | 0.19425 | 0.30311 | 0.33613 | 0.60502 | 255.46 |
| 4 | phase | 0.05346 | 0.09446 | 0.09817 | 0.11996 | 0.07169 | 0.19743 | 0.28974 | 0.32389 | 0.59469 | 250.46 |
| 4 | bps_kas | 0.05207 | 0.09428 | 0.09990 | 0.11526 | 0.07183 | 0.19452 | 0.30389 | 0.33606 | 0.60478 | 255.35 |

### 机制指标

`phase` 的 PBC 确实在做 regime arbitration，而不是退化为固定 KAS：

| policy | total rate | component | records | mean decode utility intensity | regimes |
|---|---:|---|---:|---:|---|
| phase | 3 | context | 95 | 0.595 | `DECODE_HEAVY:44, FIRST_TOKEN_LIMITED:28, MIXED_SLO:23` |
| phase | 3 | decode | 6139 | 0.359 | `DECODE_HEAVY:1824, FIRST_TOKEN_LIMITED:2275, MIXED_SLO:1944` |
| phase | 4 | context | 95 | 0.657 | `DECODE_HEAVY:54, FIRST_TOKEN_LIMITED:19, MIXED_SLO:22` |
| phase | 4 | decode | 6272 | 0.382 | `DECODE_HEAVY:2025, FIRST_TOKEN_LIMITED:2007, MIXED_SLO:2144` |

### 更新后的结论

本轮结果比 rate2 更有说明力：

1. `phase` 在 decode-heavy workload 下稳定改善 TPOT：跨 seed/rate 平均 TPOT p50/p90/p95/p99 分别约下降 `9.3%/8.9%/6.0%/8.9%`。
2. `phase` 的吞吐量也有收益：completed req/s 与 output tok/s 平均提升约 `4.0%`。
3. TTFT 不是本 workload 的主收益指标：`phase` 的 TTFT p90/p95 基本持平或小幅改善，但 TTFT p99 平均变差约 `7.9%`。因此论文中不能声称 decode-heavy regime 下 TTFT tail 全面提升。
4. `kas` 是当前 decode-heavy 下最稳的单组件 baseline：TPOT 与吞吐改善稳定，TTFT 几乎不变。`phase` 的价值需要通过 regime-aware 切换、prompt-skew workload、以及 SLO goodput 进一步证明，而不能只靠 decode-heavy 的 TPOT 图。
5. `bps_kas` 在部分 TPOT tail 上接近或优于 `phase`，但没有 regime arbitration。后续实验需要展示 `phase` 在不同 workload/regime 间自动选择预算，而不是只在单一 decode-heavy workload 上和静态组合比拼。
