# Stage 4：W2 TTFT Calibration

更新时间：2026-05-27

## 结论先行

本轮 OPT-13B prompt-skew 校准已经找到 BPS 能降低 TTFT 的压力区间，并完成了一次 Stage 4 -> Stage 2 的 full `phase` 仲裁修复。

在 total rate `10/12`，也就是 1p1d 两张 GPU下 per-GPU 约 `5/6 req/s` 时，`bps` 相比 `fcfs` 的 TTFT p90 分别下降约 `20.6%/16.2%`。修复前完整 `phase` 在 rate `8/10/12` 的 TTFT tail 明显变差；加入 typed hard-pressure PBC 后，full `phase` 在 rate 10 的 TTFT p90 从 `1.351s` 降到 `0.915s`，优于 FCFS 的 `1.052s`，同时 TPOT p90 也从 FCFS 的 `0.121s` 降到 `0.112s`。rate 12 的 TTFT p90 从 `2.298s` 恢复到 `2.042s`，基本持平 FCFS 的 `2.053s`，但仍弱于 BPS 的 `1.682s`。

后续 KAS workload-aware gating 试验显示，简单地在 first-token/prefill pressure 高时弱化 KAS 重排，并不能稳定保住 BPS 的 TTFT 收益：rate 10 会退化，rate 12 只有很小收益且 TPOT 变差。因此当前保留的默认策略是 typed hard-pressure PBC + BPS + 原 KAS；KAS gating 代码保留为 opt-in 诊断开关，不作为论文主方法默认配置。

## 本阶段目标

本轮属于 Stage 4 的 W2 prompt-skew pilot，目标是回答一个窄问题：

在 OPT-13B、1p1d、长短 prompt 混合的 workload 下，是否存在 `bps` 或完整 `phase` 能降低 TTFT 的 per-GPU rate 区间。

本轮只用于定位压力区间和发现方法冲突，不作为论文最终数字。

## 需要读取或修改的文件

### 已读取文件

| 文件或路径 | 用途 |
|---|---|
| `/root/data/DistServe/scripts/run_phase_prefill_skew_sweep.sh` | W2 prompt-skew sweep 入口 |
| `/root/data/DistServe/scripts/run_phase_hetero_sweep.sh` | 统一 sweep、summary、analysis 和 SLO grid 生成 |
| `/root/data/phase_scheduler_results/w2_opt13b_ttft_highrate_20260527_153750/sweep_summary.md` | 本轮主要结果表 |
| `/root/data/phase_scheduler_results/w2_opt13b_ttft_highrate_20260527_153750/sweep_analysis.md` | grouped means、paired delta、机制指标 |
| `/root/data/phase_scheduler_results/w2_opt13b_ttft_highrate_20260527_153750/slo_grid.grouped.md` | tight/medium/loose SLO 重新计算 |

### 本阶段修改文件

| 文件 | 修改内容 |
|---|---|
| `docs/stage4_w2_ttft_calibration.md` | 新增本轮 W2 TTFT 校准记录 |
| `docs/current_progress.md` | 同步 Stage 4 当前状态和下一步风险 |
| `remote_distserve/distserve/phase_scheduler.py` | typed hard-pressure PBC 与 prefill progress floor |
| `remote_distserve/distserve/context_stage_scheduler.py` | decode hard pressure / KV hard pressure snapshot |
| `remote_distserve/distserve/decoding_stage_scheduler.py` | KAS first-decode-step gate 诊断实现，默认关闭 |
| `remote_distserve/benchmarks/phase_native_benchmark.py` | hard-pressure 与 KAS gate summary 指标 |
| `remote_distserve/benchmarks/phase_collect_summaries.py` | hard-pressure 与 KAS gate sweep 字段 |
| `remote_distserve/benchmarks/phase_analyze_sweep.py` | hard-pressure 与 KAS gate grouped diagnostics |

## 运行配置

| 项 | 值 |
|---|---|
| server | `js4.blockelite.cn:15330` |
| repo | `/root/data/DistServe` |
| model | `facebook/opt-13b` |
| model path | `/root/data/models/opt-13b` |
| structure | `1p1d` |
| GPUs | 2 x A800 40GB |
| seed | `0` |
| policies | `fcfs bps phase` |
| total request rates | `6 8 10 12 req/s` |
| per-GPU rates | `3 4 5 6 req/s` |
| num prompts | `64` |
| process | `poisson` |
| prompt mix | `64:0.45,512:0.25,1024:0.20,1536:0.10` |
| output mix | `32:0.60,64:0.30,128:0.10` |
| max total tokens | `1800` |
| GPU memory utilization | `0.85` |
| result root | `/root/data/phase_scheduler_results/w2_opt13b_ttft_highrate_20260527_153750` |

注：本轮开始前曾启动过一个低压 sweep `w2_opt13b_ttft_calib_20260527_153347`，其中 rate 2 已显示负载过轻，因此保留已有结果后停止，改为直接扫高压区间。

## 具体产物

远程已生成：

| 产物 | 路径 |
|---|---|
| per-policy summaries | `/root/data/phase_scheduler_results/w2_opt13b_ttft_highrate_20260527_153750/seed_0/rate_*/*/*.summary.json` |
| per-rate summaries | `/root/data/phase_scheduler_results/w2_opt13b_ttft_highrate_20260527_153750/seed_0/rate_*/summary.md` |
| sweep summary | `/root/data/phase_scheduler_results/w2_opt13b_ttft_highrate_20260527_153750/sweep_summary.md` |
| sweep analysis | `/root/data/phase_scheduler_results/w2_opt13b_ttft_highrate_20260527_153750/sweep_analysis.md` |
| bucket analysis | `/root/data/phase_scheduler_results/w2_opt13b_ttft_highrate_20260527_153750/sweep_analysis.bucket.md` |
| SLO grid | `/root/data/phase_scheduler_results/w2_opt13b_ttft_highrate_20260527_153750/slo_grid.grouped.md` |

本地文档产物：

| 产物 | 路径 |
|---|---|
| W2 TTFT calibration | `docs/stage4_w2_ttft_calibration.md` |

## 验收标准

| 验收项 | 状态 | 说明 |
|---|---|---|
| 12 个 run 全部完成 | 通过 | `fcfs/bps/phase` x `rate 6/8/10/12` 均 `completed=64`, `failed=0` |
| summary/analysis/SLO grid 生成 | 通过 | `sweep_summary.md`、`sweep_analysis.md`、`slo_grid.grouped.md` 均生成 |
| 进入 TTFT 压力区 | 通过 | `fcfs` 在 total rate 10/12 的 TTFT p90 为 `1.024s/1.969s` |
| 找到 BPS TTFT 下降区间 | 通过 | `bps` 在 per-GPU 5/6 req/s 的 TTFT p90 分别下降约 `20.6%/16.2%` |
| 验证完整 Phase 的 TTFT 优势 | 未通过 | `phase` 在 rate 8/10/12 的 TTFT p90/p99 均不稳定，rate 10/12 明显差于 `fcfs` |
| 可直接扩展到论文 final matrix | 未通过 | 当前只有 seed 0，且 full `phase` 需要先修仲裁逻辑 |

## OPT-13B W2 结果摘要

### TTFT

| total rate | per-GPU rate | policy | TTFT p50 | TTFT p90 | TTFT p99 | p90 vs FCFS | p99 vs FCFS |
|---:|---:|---|---:|---:|---:|---:|---:|
| 6 | 3 | fcfs | 0.130 | 0.272 | 0.427 | 0.0% | 0.0% |
| 6 | 3 | bps | 0.134 | 0.279 | 0.386 | +2.5% | -9.6% |
| 6 | 3 | phase | 0.136 | 0.282 | 0.386 | +3.6% | -9.5% |
| 8 | 4 | fcfs | 0.191 | 0.331 | 0.472 | 0.0% | 0.0% |
| 8 | 4 | bps | 0.191 | 0.356 | 0.440 | +7.5% | -6.6% |
| 8 | 4 | phase | 0.190 | 0.373 | 0.587 | +12.7% | +24.5% |
| 10 | 5 | fcfs | 0.217 | 1.024 | 1.722 | 0.0% | 0.0% |
| 10 | 5 | bps | 0.224 | 0.813 | 1.703 | -20.6% | -1.1% |
| 10 | 5 | phase | 0.230 | 1.351 | 1.915 | +32.0% | +11.2% |
| 12 | 6 | fcfs | 0.284 | 1.969 | 2.689 | 0.0% | 0.0% |
| 12 | 6 | bps | 0.261 | 1.649 | 2.668 | -16.2% | -0.8% |
| 12 | 6 | phase | 0.270 | 2.298 | 2.718 | +16.7% | +1.1% |

解释：

- rate 6/8：压力刚开始出现，BPS 主要削 p99，p90 还没有收益。
- rate 10/12：压力进入排队区，BPS 的 p90 收益稳定出现。
- full `phase` 在 rate 8/10/12 上没有保住 BPS 的 TTFT 收益，说明 PBC/KAS 对 prefill budget 的干预过强。

### TPOT 与吞吐

| total rate | per-GPU rate | policy | goodput req/s | per-GPU goodput | TPOT p90 | TPOT p99 | goodput vs FCFS |
|---:|---:|---|---:|---:|---:|---:|---:|
| 10 | 5 | fcfs | 4.864 | 2.432 | 0.120 | 0.137 | 1.000 |
| 10 | 5 | bps | 4.799 | 2.400 | 0.119 | 0.147 | 0.987 |
| 10 | 5 | phase | 4.619 | 2.310 | 0.119 | 0.136 | 0.950 |
| 12 | 6 | fcfs | 4.870 | 2.435 | 0.132 | 0.143 | 1.000 |
| 12 | 6 | bps | 4.714 | 2.357 | 0.135 | 0.147 | 0.968 |
| 12 | 6 | phase | 4.719 | 2.360 | 0.130 | 0.138 | 0.969 |

解释：

- `bps` 的 TTFT p90 收益伴随少量 goodput 下降，rate 10/12 分别约 `1.3%/3.2%`。
- `phase` 在 rate 10/12 的 TPOT p99 略好或持平，但以更差 TTFT 和更低 goodput 为代价。
- 当前完整 `phase` 更像偏向 decode/TPOT 的策略，而不是同时改善 TTFT/TPOT 的策略。

### SLO Grid

| SLO | total rate | policy | attainment | per-GPU goodput |
|---|---:|---|---:|---:|
| tight `1.0s/0.10s` | 10 | fcfs | 0.734 | 1.786 |
| tight `1.0s/0.10s` | 10 | bps | 0.750 | 1.800 |
| tight `1.0s/0.10s` | 10 | phase | 0.656 | 1.516 |
| medium `1.5s/0.20s` | 12 | fcfs | 0.797 | 1.940 |
| medium `1.5s/0.20s` | 12 | bps | 0.859 | 2.026 |
| medium `1.5s/0.20s` | 12 | phase | 0.750 | 1.770 |

解释：

- `bps` 在 rate 10 的 tight SLO 和 rate 12 的 medium SLO 上都有收益。
- `phase` 在这些 SLO 下均明显差于 `fcfs/bps`，不适合进入 final matrix 前直接扩 seed。

## 机制解释

本轮最关键的机制现象是：`phase` 的 PBC 在高 prefill pressure 下把 prefill budget 压得过低，但实验中没有看到真实 swap pressure 需要它这么做。

从 `sweep_analysis.md` 看：

- `bps` 的 `phase_context_prefill_budget_ratio_mean` 始终是 `1.0`，rate 10/12 下仍能保住 BPS 的调度自由度。
- `phase` 的 `phase_context_prefill_budget_ratio_mean` 在 rate 10/12 下降到约 `0.762/0.758`。
- `phase` 的 `phase_context_goodput_capacity_mean` 在 rate 10/12 只有约 `0.414/0.409`。
- `phase` 的 `phase_context_protected_blocked_mean` 在 rate 10/12 为 `400/504`，说明 protected progress 大量被 budget/feasibility 挡住。
- 同时 `phase_decode_swap_ins=0`、`phase_decode_evictions=0`、`phase_decode_infeasible_rounds=0`，说明 decode 侧并没有真实 swap/memory infeasibility 压力。

因此，当前问题不是 BPS 无效，而是 full `phase` 的 typed pressure arbitration 没有区分“真实 decode/KV 硬压力”和“普通 decode 负载压力”。在没有 swap/infeasible pressure 时，PBC 不应牺牲 prefill budget 到破坏 BPS progress 的程度。

## 风险和阻塞点

1. **只有 seed 0**：本轮是校准，不是最终实验。BPS 在 rate 10/12 的 TTFT p90 收益需要 seed 1/2 复核。
2. **完整 Phase 仍未完全追上 BPS**：typed hard-pressure PBC 已修复明显退化，但 rate 12 仍弱于 BPS，剩余冲突主要来自 KAS 与 prompt-skew workload 的交互。
3. **KAS gating 不是当前解法**：first-token workload gate 已实现并试跑，但结果不稳定，默认关闭。
4. **SLO 需要按 workload 调整**：默认 SLO 全是 `1.0`，需要继续使用 tight/medium/loose grid 报告。
5. **claim 需要收窄**：当前可以 claim typed hard-pressure PBC 修复了 full `phase` 对 BPS 的破坏，并在 rate 10 同时改善 TTFT p90 与 TPOT p90；不能 claim full `phase` 已在所有 prompt-skew high-rate 下稳定优于 BPS。

## 下一步建议

先暂停继续扩展实验，回到 Stage 2 做一次小范围实现修正，然后只重跑 rate 10/12。

建议修改方向：

1. **PBC 仲裁加 hard pressure typing**：只有当 decode 侧出现 swap-in、eviction、infeasible round 或显著 KV block shortage 时，才允许 decode pressure 强力收缩 prefill budget。
2. **Prefill progress floor**：当 `rho_prefill` 高、oldest/long-prompt wait 高时，full `phase` 的 prefill budget ratio 不应低于一个安全下界，例如 `0.90`，除非 decode 侧有 hard pressure。
3. **Protected-oldest feasibility 优先级**：protected request 触发后，应优先保证至少一个可行 prefill batch，而不是被 pressure budget 长时间挡住。
4. **重新验证**：修正后先跑 OPT-13B prompt-skew `rate=10 12`, `seed=0 1`, policies `fcfs bps phase`。只有当 `phase` 至少不破坏 BPS 的 TTFT p90，同时保留 TPOT/SLO 收益时，再扩展完整 W2/W3。

这一步属于 Stage 4 反推 Stage 2 的正常循环。当前最有价值的论文方向不是掩盖冲突，而是把 typed pressure arbitration 做实，让 PBC 真正成为跨阶段预算协调，而不是简单牺牲 prefill。

## Stage 4 -> Stage 2 修复记录

更新时间：2026-05-27

### 修改目标

修复 full `phase` 在 prompt-skew workload 下过度收缩 prefill budget 的问题，使完整策略在没有真实 KV/swap 硬压力时至少不破坏 BPS 的 TTFT 保护能力。

### 修改文件

| 文件 | 修改内容 |
|---|---|
| `remote_distserve/distserve/phase_scheduler.py` | `AdmissionBudget` 增加 `pressure_decode_hard/pressure_kv_hard`；context 侧 PBC 改为使用 typed hard pressure 计算 prefill budget 和 block margin；增加 `PHASESERVE_PBC_PREFILL_PROGRESS_FLOOR_FRAC`，默认 `0.90` |
| `remote_distserve/distserve/context_stage_scheduler.py` | 从 decode snapshot 中计算 `decode_hard/kv_hard`；默认只有 swap 或 GPU free block 低于 `PHASESERVE_PBC_HARD_FREE_BLOCK_FRAC=0.02` 时触发硬压力 |
| `remote_distserve/benchmarks/phase_native_benchmark.py` | summary 中增加 hard-pressure 指标 |
| `remote_distserve/benchmarks/phase_collect_summaries.py` | sweep summary 中增加 hard-pressure 指标 |
| `remote_distserve/benchmarks/phase_analyze_sweep.py` | grouped diagnostics 中增加 hard-pressure 指标 |

### 验证

本地与远端均已通过 `py_compile`。远端最小验证如下：

| 项 | 值 |
|---|---|
| result root | `/root/data/phase_scheduler_results/w2_opt13b_phasefix_rate10_12_20260527_160646` |
| model | OPT-13B |
| workload | prompt-skew |
| seed | `0` |
| rates | total `10/12`，per-GPU 约 `5/6 req/s` |
| policies | `fcfs bps phase` |

### 修复后结果

| total rate | policy | TTFT p50 | TTFT p90 | TTFT p99 | TPOT p90 | TPOT p99 | goodput req/s |
|---:|---|---:|---:|---:|---:|---:|---:|
| 10 | fcfs | 0.225 | 1.052 | 1.717 | 0.121 | 0.138 | 4.852 |
| 10 | bps | 0.223 | 0.811 | 1.678 | 0.118 | 0.147 | 4.807 |
| 10 | phase | 0.222 | 0.915 | 1.633 | 0.112 | 0.146 | 4.551 |
| 12 | fcfs | 0.295 | 2.053 | 2.771 | 0.133 | 0.145 | 4.834 |
| 12 | bps | 0.262 | 1.682 | 2.701 | 0.136 | 0.148 | 4.705 |
| 12 | phase | 0.265 | 2.042 | 2.713 | 0.134 | 0.147 | 4.756 |

相对修复前：

- rate 10 的 full `phase` TTFT p90 从 `1.351s` 降到 `0.915s`，由明显差于 FCFS 变为优于 FCFS。
- rate 12 的 full `phase` TTFT p90 从 `2.298s` 降到 `2.042s`，由明显差于 FCFS 变为基本持平 FCFS，但仍未追上 BPS。
- `phase_context_prefill_budget_ratio_mean` 从旧版 rate 10/12 的约 `0.762/0.758` 提升到 `0.904/0.902`。
- `phase_context_prefill_block_margin_mean` 从旧版约 `70/72` 降到 `0`。
- `phase_context_pressure_decode_hard_mean` 和 `phase_context_pressure_kv_hard_mean` 均为 `0`，说明本轮确实属于无硬 KV/swap 压力场景。

### 额外试验

尝试把 `PHASESERVE_PBC_PREFILL_PROGRESS_FLOOR_FRAC` 调成 `1.00` 与 `0.85`，并只重跑 `phase`：

| floor | result root | rate 10 TTFT p90 | rate 12 TTFT p90 | 结论 |
|---:|---|---:|---:|---|
| 1.00 | `/root/data/phase_scheduler_results/w2_opt13b_phasefix_floor100_phaseonly_20260527_161736` | 1.156 | 2.041 | rate 10 明显差于默认 `0.90` |
| 0.85 | `/root/data/phase_scheduler_results/w2_opt13b_phasefix_floor085_phaseonly_20260527_162759` | 1.162 | 2.102 | rate 10/12 均差于默认 `0.90` |

因此当前保留默认 `0.90`。这说明 full `phase` 需要一个轻度 prefill progress floor，过度放开或过度收缩都会损害 prompt-skew 下的 TTFT。

### BPS+KAS 对照

为了分解剩余损失，额外运行 `bps_kas`，即 BPS + KAS 但禁用动态 PBC：

| result root | rate 10 TTFT p90 | rate 12 TTFT p90 | 结论 |
|---|---:|---:|---|
| `/root/data/phase_scheduler_results/w2_opt13b_bpskas_compare_20260527_162327` | 1.160 | 2.084 | 明显差于 BPS，接近或差于修复后的 full `phase` |

这说明剩余 TTFT 损失主要来自 KAS 与 prompt-skew workload 的交互，而不是 typed PBC 修复后的动态预算本身。full `phase` 在 rate 10 反而优于 `bps_kas`，说明动态 PBC 的轻度 throttling 能缓解一部分 KAS 引入的 decode-side congestion。

### 当前结论

这次修复已经解决了 full `phase` 在 W2 中“明显破坏 TTFT”的问题，但还没有完全解决“追上 BPS”的问题。

## KAS workload-aware gating 试验

更新时间：2026-05-27

### 修改目标

验证一个更保守的 KAS 仲裁策略：当 decode 侧出现大量刚进入 decode 的 first-token 请求、且没有真实 KV/swap 硬压力时，临时降低 LAS/KV 重排强度，优先让新迁移请求完成首个 decode step，从而减少 prompt-skew 下的 TTFT tail。

### 修改文件

| 文件 | 修改内容 |
|---|---|
| `remote_distserve/distserve/decoding_stage_scheduler.py` | 增加 first-decode-step 标记、prefill/first-token gate 状态、gate 激活时的 FCFS-like ready 排序；默认关闭 `PHASESERVE_KAS_WORKLOAD_GATING` |
| `remote_distserve/benchmarks/phase_native_benchmark.py` | summary 中增加 KAS gate 指标 |
| `remote_distserve/benchmarks/phase_collect_summaries.py` | sweep summary 中增加 KAS gate 指标 |
| `remote_distserve/benchmarks/phase_analyze_sweep.py` | grouped diagnostics 中增加 KAS gate 指标 |

### 试验结果

| result root | 配置 | rate 10 TTFT p90 | rate 12 TTFT p90 | 结论 |
|---|---|---:|---:|---|
| `/root/data/phase_scheduler_results/w2_opt13b_kasgate_phaseonly_20260527_164102` | 初版，使用 `get_output_len() <= 0` 判断 first-token | 0.945 | 2.048 | gate 实际未触发，`first_token_ready=0`，判断条件不符合 DistServe 的迁移语义 |
| `/root/data/phase_scheduler_results/w2_opt13b_kasgate_step_phaseonly_20260527_164635` | 显式 `phaseserve_decode_steps`，threshold `0.25` | 1.116 | 2.013 | gate 触发过多，rate 10 明显退化，rate 12 只有小幅改善 |
| `/root/data/phase_scheduler_results/w2_opt13b_kasgate065_phaseonly_20260527_165121` | 显式 decode step，threshold `0.65` | 0.982 | 2.029 | rate 10 仍差于默认 typed-PBC phase 的 `0.915`，rate 12 仅小幅好于 `2.042` 且 TPOT p90 变差 |

0.65 阈值下的机制指标显示，gate 在 rate 10/12 分别平均激活 `7/9` 次，`phase_decode_prefill_gate_pressure_mean` 分别为 `0.553/0.689`，但 `phase_decode_prefill_gate_hard_mean=0`。这说明 workload gate 捕捉到的是普通 first-token/bridge pressure，而不是 KV/swap hard pressure；简单切换为 FCFS-like 排序会削弱 KAS 对 TPOT 的保护，却不能稳定换回 TTFT。

### 当前保留策略

KAS workload-aware gating 代码和指标保留，用于后续诊断，但默认关闭。当前默认 full `phase` 保留为：

1. typed hard-pressure PBC；
2. prefill progress floor `PHASESERVE_PBC_PREFILL_PROGRESS_FLOOR_FRAC=0.90`；
3. BPS；
4. 原 KAS hard feasibility 与 swap budget 逻辑；
5. `PHASESERVE_KAS_WORKLOAD_GATING=0`。

### 下一步

下一轮不再继续调 first-token gate 阈值，而应重新审视 KAS 的目标函数：prompt-skew 下的 decode scheduler 需要区分“刚迁移请求的 TTFT debt”和“长输出请求的 TPOT fairness”，而不是用一个 gate 全局切换排序。更合理的方向是把 first-decode-step debt 作为 KAS scoring 的连续项，并用 hard KV/swap pressure 决定其权重，而不是二值化地关闭 LAS/KV-aware ordering。

## 默认配置 seed 0/1 复核

更新时间：2026-05-27

### 修改目标

固定当前默认实现，不继续调 KAS gate 阈值，复核 OPT-13B W2 prompt-skew 在 seed `0/1`、total rate `10/12` 下的稳定性。

### 运行配置

| 项 | 值 |
|---|---|
| result root | `/root/data/phase_scheduler_results/w2_opt13b_seed01_default_20260527_170620` |
| model | OPT-13B |
| model path | `/root/data/models/opt-13b` |
| structure | `1p1d` |
| seeds | `0 1` |
| total rates | `10 12` |
| per-GPU rates | `5 6 req/s` |
| policies | `fcfs bps phase` |
| prompts | `64` |
| process | `poisson` |
| prompt mix | `64:0.45,512:0.25,1024:0.20,1536:0.10` |
| output mix | `32:0.60,64:0.30,128:0.10` |
| KAS gate | `PHASESERVE_KAS_WORKLOAD_GATING=0` |

### 产物

| 产物 | 路径 |
|---|---|
| per-run summaries | `/root/data/phase_scheduler_results/w2_opt13b_seed01_default_20260527_170620/seed_*/rate_*/*/*.summary.json` |
| sweep summary | `/root/data/phase_scheduler_results/w2_opt13b_seed01_default_20260527_170620/sweep_summary.md` |
| sweep analysis | `/root/data/phase_scheduler_results/w2_opt13b_seed01_default_20260527_170620/sweep_analysis.md` |
| bucket analysis | `/root/data/phase_scheduler_results/w2_opt13b_seed01_default_20260527_170620/sweep_analysis.bucket.md` |
| SLO grid | `/root/data/phase_scheduler_results/w2_opt13b_seed01_default_20260527_170620/slo_grid.grouped.md` |

### 验收标准

| 验收项 | 状态 | 说明 |
|---|---|---|
| 12 个 run 全部完成 | 通过 | `2 seeds x 2 rates x 3 policies` 均 `completed=64`, `failed=0` |
| summary/analysis/SLO grid 生成 | 通过 | `sweep_summary.md`、`sweep_analysis.md`、`slo_grid.grouped.md` 均生成 |
| BPS TTFT 复核 | 通过 | TTFT p90 在 rate 10/12 平均下降约 `15.3%/12.2%` |
| full Phase TTFT 复核 | 未通过 | rate 10 平均略差于 FCFS，rate 12 基本持平 |
| full Phase TPOT/SLO 信号 | 部分通过 | TPOT p90 在 rate 10/12 平均下降约 `12.4%/2.8%`；tight SLO 两个 rate 均提升约 `4.7pp` |

### 跨 seed 平均结果

| total rate | policy | goodput req/s | TTFT p50 | TTFT p90 | TTFT p99 | TPOT p50 | TPOT p90 | TPOT p99 |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 10 | fcfs | 5.069 | 0.266 | 0.867 | 1.349 | 0.067 | 0.119 | 0.133 |
| 10 | bps | 5.139 | 0.223 | 0.735 | 1.253 | 0.067 | 0.112 | 0.134 |
| 10 | phase | 4.937 | 0.230 | 0.893 | 1.418 | 0.069 | 0.104 | 0.131 |
| 12 | fcfs | 5.085 | 0.382 | 1.543 | 2.231 | 0.072 | 0.125 | 0.137 |
| 12 | bps | 5.020 | 0.291 | 1.354 | 2.185 | 0.070 | 0.131 | 0.141 |
| 12 | phase | 5.098 | 0.322 | 1.540 | 2.191 | 0.075 | 0.122 | 0.140 |

相对 FCFS 的 paired delta：

| total rate | policy | TTFT p90 delta | TTFT p99 delta | TPOT p90 delta | TPOT p99 delta | goodput ratio |
|---:|---|---:|---:|---:|---:|---:|
| 10 | bps | -0.133 | -0.097 | -0.006 | +0.001 | 1.013 |
| 10 | phase | +0.025 | +0.068 | -0.015 | -0.002 | 0.972 |
| 12 | bps | -0.188 | -0.046 | +0.006 | +0.004 | 0.987 |
| 12 | phase | -0.003 | -0.040 | -0.004 | +0.003 | 1.002 |

### SLO 结果

| SLO | total rate | fcfs | bps | phase |
|---|---:|---:|---:|---:|
| tight `1.0s/0.10s` | 10 | 0.789 | 0.797 | 0.836 |
| tight `1.0s/0.10s` | 12 | 0.617 | 0.602 | 0.664 |
| medium `1.5s/0.20s` | 10 | 0.984 | 0.984 | 0.977 |
| medium `1.5s/0.20s` | 12 | 0.867 | 0.906 | 0.883 |
| loose `2.0s/0.30s` | 10 | 1.000 | 1.000 | 1.000 |
| loose `2.0s/0.30s` | 12 | 0.945 | 0.961 | 0.938 |

### 机制解释

这轮 seed 复核把当前方法边界暴露得更清楚：

1. **BPS 的 TTFT 结论较稳**：rate 10/12 的 TTFT p90 均下降，且 seed0/seed1 都没有明显反向。
2. **full Phase 的 TTFT 仍不稳**：rate 10 的 seed0 中，full `phase` 的 TTFT p90 为 `1.125s`，高于 FCFS 的 `1.080s`；seed1 中基本持平。rate 12 平均基本持平 FCFS。
3. **full Phase 的 TPOT 与 tight SLO 有信号**：full `phase` 在 rate 10/12 的 TPOT p90 平均低于 FCFS，tight SLO 两个 rate 都高约 `4.7pp`。
4. **问题不再是 PBC hard pressure 误触发**：`phase_context_pressure_decode_hard_mean=0`、`phase_context_pressure_kv_hard_mean=0`，prefill budget ratio 保持约 `0.903-0.905`。
5. **剩余冲突在 KAS 排序**：bucket breakdown 显示 full `phase` 对短 prompt bucket 明显友好，但对 `256-512`、`512-1024`、`1024-2048` prompt bucket 的 TTFT p90 经常产生 tail transfer；同时 decode queue p90 接近 0，说明 KAS 把 decode 排队压得很低，但代价部分转移到 context/prefill wait。

### 当前结论

论文 claim 需要继续收窄：

- 可以保留：`BPS` 是 prompt-skew 下稳定降低 TTFT tail 的组件。
- 可以保留：typed PBC 使 full `phase` 不再因为错误 hard pressure 过度收缩 prefill budget。
- 可以谨慎保留：full `phase` 在当前 W2 中更像 TPOT/tight-SLO 优化，而不是稳定 TTFT 优化。
- 不能保留：full `phase` 在 prompt-skew 下稳定同时优于 FCFS/BPS 的 TTFT 和 TPOT。

下一步应回到 Stage 2 重新设计 KAS scoring，而不是继续扩 LLaMA2-13B final matrix。方向是把 first-decode-step TTFT debt 和 attained-service/KV fairness 合成连续打分，让 KAS 在 prompt-skew 中少制造 TTFT tail transfer，同时保留 decode-heavy 下的 TPOT tail 优势。

## Stage 4 -> Stage 2：KAS adaptive intensity

更新时间：2026-05-27

### 修改目标

修复 full `phase` 在 prompt-skew 下的 KAS/BPS 冲突：当 bridge/first-token pressure 主导、但 decode 侧没有 hard KV/swap pressure 时，KAS 不应持续用完整 LAS/KV-aware 排序重排 decode active set；当 decode/swap pressure 真正成为瓶颈时，再恢复完整 KAS 强度。

### 修改文件

| 文件 | 修改内容 |
|---|---|
| `remote_distserve/distserve/decoding_stage_scheduler.py` | 增加 `PHASESERVE_KAS_ADAPTIVE_INTENSITY`，用连续 `kas_intensity` 缩放 attained-service score 和 resident preference；`PHASESERVE_KAS_HANDOFF_DEBT` 保留为默认关闭的诊断开关 |
| `remote_distserve/benchmarks/phase_native_benchmark.py` | summary 中增加 `kas_intensity` 与 handoff-debt 指标 |
| `remote_distserve/benchmarks/phase_collect_summaries.py` | sweep summary 中增加 adaptive KAS 字段 |
| `remote_distserve/benchmarks/phase_analyze_sweep.py` | grouped diagnostics 中增加 adaptive KAS 字段 |

当前默认参数：

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `PHASESERVE_KAS_ADAPTIVE_INTENSITY` | `1` for `phase` | full `phase` 默认启用 |
| `PHASESERVE_KAS_INTENSITY_LOW` | `0.45` | decode/swap soft pressure 低于该值时弱化 LAS |
| `PHASESERVE_KAS_INTENSITY_HIGH` | `0.75` | decode/swap soft pressure 达到该值时恢复 LAS |
| `PHASESERVE_KAS_INTENSITY_BRIDGE_DISCOUNT` | `0.25` | bridge/first-token pressure 对 KAS intensity 的折扣 |
| `PHASESERVE_KAS_HANDOFF_DEBT` | `0` | first-decode-step debt 仅作为 opt-in 诊断 |

### 验证结果

| result root | 配置 | seed/rate | TTFT p90 | TPOT p90 | 结论 |
|---|---|---|---:|---:|---|
| `/root/data/phase_scheduler_results/w2_opt13b_handoff_phase_20260527_173247` | handoff debt only, weight `1.0` | seed0/rate10 | 1.166 | 0.111 | rate10 变差，不作为默认 |
| `/root/data/phase_scheduler_results/w2_opt13b_adaptive_phase_20260527_174244` | adaptive intensity, bridge discount `0.50` | seed0/rate10 | 0.949 | 0.113 | rate10 明显改善 |
| `/root/data/phase_scheduler_results/w2_opt13b_adaptive_phase_20260527_174244` | adaptive intensity, bridge discount `0.50` | seed0/rate12 | 2.370 | 0.139 | rate12 明显变差，折扣过强 |
| `/root/data/phase_scheduler_results/w2_opt13b_adaptive025_phase_20260527_175045` | adaptive intensity, bridge discount `0.25` | seed0/rate10 | 1.016 | 0.120 | 比旧 phase 改善 TTFT，但弱于 `0.50` |
| `/root/data/phase_scheduler_results/w2_opt13b_adaptive025_phase_20260527_175045` | adaptive intensity, bridge discount `0.25` | seed0/rate12 | 1.989 | 0.135 | 基本恢复旧 phase 的 rate12 TTFT |
| `/root/data/phase_scheduler_results/w2_opt13b_adaptive025_s1_20260527_175517` | adaptive intensity, bridge discount `0.25` | seed1/rate10 | 0.662 | 0.102 | 基本持平旧 phase TTFT，TPOT 仍优于 FCFS |
| `/root/data/phase_scheduler_results/w2_opt13b_adaptive025_s1_20260527_175517` | adaptive intensity, bridge discount `0.25` | seed1/rate12 | 1.186 | 0.114 | TTFT 略差于旧 phase，TPOT 仍优于 FCFS |

与上一轮默认 full `phase` 相比，`bridge_discount=0.25` 的跨 seed 近似结果为：

| total rate | old phase TTFT p90 | adaptive025 TTFT p90 | old phase TPOT p90 | adaptive025 TPOT p90 | 结论 |
|---:|---:|---:|---:|---:|---|
| 10 | 0.893 | 0.839 | 0.104 | 0.111 | TTFT 改善，TPOT 有小幅回退 |
| 12 | 1.540 | 1.587 | 0.122 | 0.124 | TTFT 小幅回退，TPOT 基本持平 |

### 当前结论

adaptive KAS intensity 比 first-token gate 和 handoff-debt 更符合当前机制：它不是让某类请求硬插队，而是让 PBC pressure 改变 KAS local utility 的强度。它能缓解 rate 10 的 full `phase` TTFT 退化，但 rate 12 仍存在轻微 tradeoff，因此还不能把 full `phase` claim 为 prompt-skew 下稳定 TTFT 优化。

下一步应把该版本带回 decode-heavy workload，确认 adaptive intensity 不破坏 KAS 原本的 TPOT tail 优势；如果 decode-heavy TPOT 仍成立，再把 OPT-13B W2 作为“BPS 主导 TTFT、PhaseServe 在 tight SLO/TPOT 上折中”的结果呈现。
