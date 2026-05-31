# Stage 4I OPT-13B ShareGPT TPOT Diagnostic and KAS Bridge Repair

## 本阶段目标

本阶段继续围绕 OPT-13B + ShareGPT 验证 full PhaseServe 是否能在真实 trace 上同时改善 TTFT 和 TPOT。

Stage 4H 的 64-request 结果已经显示 Phase512 在 per-GPU `1-5` 上具备较好的综合收益。本阶段把请求数扩到 128，并重点检查两个问题：

1. TPOT 的提升是否只是小样本现象。
2. 高 pressure 下 TPOT/TTFT tradeoff 来自 workload 本身，还是来自 KAS/BPS/PBC 代码之间的 gap。

本阶段仍属于 Stage 4 的代码诊断和机制修复，不是最终论文实验矩阵。

## 读取和修改的文件

读取：

- `remote_distserve/distserve/decoding_stage_scheduler.py`
- `remote_distserve/distserve/context_stage_scheduler.py`
- `remote_distserve/benchmarks/phase_native_benchmark.py`
- `docs/stage4h_opt_sharegpt_phase512_repair.md`
- `docs/current_progress.md`

修改：

- `remote_distserve/distserve/phase_scheduler.py`
- `remote_distserve/distserve/decoding_stage_scheduler.py`
- `remote_distserve/distserve/context_stage_scheduler.py`
- `docs/stage4i_tpot_diagnostic_and_kas_bridge_repair.md`
- `docs/current_progress.md`

## 实验设置

| 项目 | 设置 |
|---|---|
| Model | OPT-13B |
| Dataset | ShareGPT trace, first 128 requests |
| Structure | 1P1D |
| Policies | `fcfs`, old `phase`, patched `phase` |
| Arrival | poisson |
| Global rates | `1`, `1.5`, `2` for full diagnostic; bridge patch spot check at `1.5` |
| Per-GPU rates | `0.5`, `0.75`, `1.0` |
| Max total tokens | `2048` |
| SLO used for diagnostic | TTFT `0.25s`, TPOT `0.10s` |

128-request ShareGPT trace 的长度分布如下：

| Metric | Prompt | Output | Total |
|---|---:|---:|---:|
| mean | 599.4 | 189.2 | 788.6 |
| p50 | 531.5 | 147.0 | 715.0 |
| p90 | 1429.9 | 456.0 | 1557.2 |
| p95 | 1579.9 | 504.8 | 1740.7 |
| p99 | 1720.7 | 772.9 | 1959.8 |
| max | 1969 | 821 | 1978 |

该 trace 同时包含长 prompt 和中长 output，因此适合作为 bridge/context 反压诊断；它不是纯 decode-heavy workload。

## 128-Request 诊断结果

下表中 old `phase` 是 Stage 4H 后的 Phase512 版本，`starved_phase` 是加入 starved-primary 排序后的版本。延迟单位为秒。

| Global Rate | Policy | SLO | TTFT p90 | TTFT p99 | TPOT p50 | TPOT p90 | TPOT p95 | TPOT p99 | Context Queue p99 | Decode Queue p99 | Goodput |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1.0 | `fcfs` | 0.891 | 0.198 | 0.266 | 0.027 | 0.071 | 0.168 | 0.758 | 0.103 | 3.161 | 0.855 |
| 1.0 | old `phase` | 0.930 | 0.199 | 0.255 | 0.029 | 0.054 | 0.083 | 0.305 | 0.105 | 0.007 | 0.891 |
| 1.0 | `starved_phase` | 0.938 | 0.201 | 0.263 | 0.029 | 0.057 | 0.086 | 0.316 | 0.104 | 0.006 | 0.898 |
| 1.5 | `fcfs` | 0.617 | 0.211 | 0.312 | 0.059 | 0.689 | 0.808 | 3.029 | 0.203 | 5.990 | 0.789 |
| 1.5 | old `phase` | 0.609 | 0.233 | 3.572 | 0.059 | 0.671 | 0.808 | 3.132 | 3.519 | 0.011 | 0.767 |
| 1.5 | `starved_phase` | 0.625 | 0.248 | 3.798 | 0.055 | 0.621 | 0.831 | 2.592 | 3.638 | 0.008 | 0.775 |
| 2.0 | `fcfs` | 0.430 | 10.212 | 12.089 | 0.079 | 0.944 | 1.404 | 4.067 | 11.905 | 6.629 | 0.576 |
| 2.0 | old `phase` | 0.484 | 13.549 | 14.833 | 0.081 | 0.889 | 1.371 | 4.022 | 14.622 | 0.011 | 0.631 |
| 2.0 | `starved_phase` | 0.477 | 13.601 | 15.117 | 0.082 | 0.956 | 1.384 | 3.897 | 14.908 | 0.013 | 0.607 |

相对 FCFS 的改善如下，正数表示延迟下降或 goodput 提升：

| Global Rate | Policy | SLO Delta | TTFT p90 | TTFT p99 | TPOT p90 | TPOT p95 | TPOT p99 | Goodput |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 1.0 | old `phase` | +3.9 pp | -0.4% | +3.8% | +23.8% | +50.3% | +59.8% | +4.2% |
| 1.0 | `starved_phase` | +4.7 pp | -1.6% | +0.9% | +20.0% | +48.6% | +58.3% | +5.0% |
| 1.5 | old `phase` | -0.8 pp | -10.7% | -1046.0% | +2.6% | -0.0% | -3.4% | -2.8% |
| 1.5 | `starved_phase` | +0.8 pp | -17.7% | -1118.4% | +9.9% | -3.0% | +14.4% | -1.8% |
| 2.0 | old `phase` | +5.5 pp | -32.7% | -22.7% | +5.9% | +2.3% | +1.1% | +9.5% |
| 2.0 | `starved_phase` | +4.7 pp | -33.2% | -25.1% | -1.2% | +1.4% | +4.2% | +5.5% |

结论：

1. Global rate `1.0` 是干净 TPOT 改善窗口：Phase 显著降低 TPOT p90/p95/p99，并提高 SLO/goodput，TTFT 基本持平。
2. Global rate `1.5` 暴露出 bridge/context 反压：decode queue p99 几乎被 Phase 清空，但 context queue p99 从 FCFS 的 `0.203s` 放大到 `3.5s+`，TTFT tail 被转移到 first-token 侧。
3. Global rate `2.0` 进入更强过载区，Phase 仍能提高 SLO/goodput 和部分 TPOT tail，但 TTFT tail 更差，不适合作为正向主 claim。

## 机制诊断

Rate `1.5` 的 mechanism metrics 显示，问题不在 decode queue 无法被 KAS 管住，而在 bridge/unaccepted pressure 没有被足够快释放：

| Metric | old `phase` | `starved_phase` |
|---|---:|---:|
| decode dispatch rows | 1449 | 1582 |
| protected blocked rows | 1192 | 1285 |
| selected rows | 126 | 126 |
| unaccepted mean | 17.511 | 17.655 |
| unaccepted p50 | 18 | 18 |
| unaccepted p90/p99 | 21 / 21 | 21 / 21 |
| protected wait mean | 1.725s | 1.798s |
| protected wait p99 | 3.800s | 3.918s |

被反复 blocked 的 protected requests 主要集中在 bucket 2 的中长 prompt：

| Prompt Length | old `phase` blocked | `starved_phase` blocked |
|---:|---:|---:|
| 650 | 978 | 947 |
| 476 | 129 | 249 |
| 369 | 85 | 89 |

这说明当前 KAS 的 TPOT 保护已经能把 decode ready queue 管得很短，但如果 bridge 不能及时接收 context 完成的请求，BPS 的 oldest/protected first-token 目标仍会被物理容量卡住。

## 代码修复

### 1. Starved Primary Decode Ordering

原实现中的 `starved` 只是 attained-service 后面的 tie-break。对于长输出请求，如果 attained level 较高，即使已经连续被跳过，也可能仍排在年轻、低 attained level 的请求后面。

修复后新增：

- `PHASESERVE_DECODE_STARVED_PRIMARY`
- 默认值：在 `phase` 和非 pure LAS 策略中开启

排序语义从：

```text
attained level -> starved tie-break -> resident -> ready time
```

变为：

```text
starved primary -> attained level -> starved tie-break -> resident -> ready time
```

它对应 KAS 的 bounded-progress 语义：LAS/KV-aware priority 可以重排，但连续被跳过的请求必须先获得进展机会。

### 2. Bridge-Dominant Decode-Heavy Eviction

原 `maybe_evict_for_bridge` 只在 `FIRST_TOKEN_LIMITED` 或 `MIXED_SLO` regime 中允许为 bridge 接收腾出 GPU blocks。在真实 ShareGPT rate `1.5` 下，PBC 可能仍判断 decode 侧很重，但实际瓶颈已经转移到 bridge/unaccepted queue，导致 context 完成的请求无法迁入 decode。

修复后新增：

- `PHASESERVE_KAS_BRIDGE_EVICTION_ALLOW_DECODE_HEAVY`
- 默认值：`phase` 中开启

当满足以下条件时，即使当前 regime 不是 `FIRST_TOKEN_LIMITED/MIXED_SLO`，也允许为 bridge 接收 evict resident decode requests：

```text
bridge pressure >= decode pressure
and decode hard pressure < hard-pressure threshold
and migrating request requires more prompt blocks than currently free blocks
```

这把 PBC 的仲裁从“只看当前 nominal regime”推进到“看 pressure dominance 和 hard feasibility”。

## Bridge Eviction Spot Check

在 global rate `1.5` 上测试 bridge eviction 后，结果如下。

| Variant | SLO | TTFT p50 | TTFT p90 | TTFT p95 | TTFT p99 | TPOT p50 | TPOT p90 | TPOT p95 | TPOT p99 | Goodput |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| old `phase` | 0.609 | - | 0.233 | 0.391 | 3.572 | 0.059 | 0.671 | 0.808 | 3.132 | 0.767 |
| bridge eviction `0.50` | 0.625 | 0.094 | 0.238 | 1.613 | 3.490 | 0.051 | 0.606 | 0.824 | 2.633 | 0.770 |
| bridge eviction `0.25` | 0.617 | 0.093 | 0.256 | 0.717 | 3.835 | 0.051 | 0.622 | 0.821 | 2.546 | - |

Bridge eviction 默认阈值 `0.50` 能改善 TPOT p90/p99 和 SLO，但 TTFT p95 仍变差，说明单靠 decode 侧 reactive eviction 还不够。阈值调到 `0.25` 没有形成整体优势，因此不采用更激进默认值。

## Output-Backlog and Bridge-Waiting Attempts

根据上面的诊断，本阶段继续尝试了两个更直接的修复：

1. 在 decode pressure 中加入 remaining output-token backlog。
2. 在 bridge pressure 较高、decode hard pressure 较低时，临时放宽 decode waiting queue 的 block 接收上限。

这两个机制都已经保留在代码中，但默认关闭或退回原阈值，因为 spot check 显示它们还不是可靠默认策略。

### Attempt A：Output-token pressure + bridge reserve

结果目录：

```text
/root/data/phase_scheduler_results/opt13b_sharegpt_bridge_reserve128_r15_20260529_232938
```

结果：

| Variant | SLO | TTFT p50 | TTFT p90 | TTFT p95 | TTFT p99 | TPOT p50 | TPOT p90 | TPOT p95 | TPOT p99 | Goodput |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bridge reserve + output pressure | 0.609 | 0.093 | 0.255 | 1.571 | 2.491 | 0.060 | 0.689 | 0.821 | 2.883 | 0.75 |

机制指标显示：

| Metric | Value |
|---|---:|
| decode unaccepted mean / p90 / p99 | 7.19 / 19 / 24 |
| bridge reserve blocks mean / p90 / p99 | 14.89 / 49 / 77 |
| bridge reserve evictions p99 | 0 |
| output-token pressure mean / p90 | 0.666 / 1.0 |
| context protected wait mean / p99 | 2.079s / 4.913s |

结论：reserve 只限制新 decode 占用，但没有主动释放 resident KV；output-token pressure 过强时会进一步偏向 decode，不能解决 bridge 积压。

### Attempt B：Aggressive bridge waiting relaxation

结果目录：

```text
/root/data/phase_scheduler_results/opt13b_sharegpt_bridge_accept128_r15_20260529_233548
```

该实验把 bridge waiting block 上限放宽到 GPU blocks 的 `20%`。前半段 unaccepted 明显下降，但后半段 GPU blocks 达到 `97%`，decode `processing=0`、waiting/unaccepted 堆积，出现近似死锁。本轮被手动中止，不作为有效性能结果。

结论：不能无约束地放宽 bridge waiting；这会把 first-token pressure 转换成 decode-side KV 占用死锁。

### Attempt C：Conservative bridge waiting relaxation

结果目录：

```text
/root/data/phase_scheduler_results/opt13b_sharegpt_bridge_accept10p128_r15_20260529_234017
/root/data/phase_scheduler_results/opt13b_sharegpt_bridge_accept10p_no_tok128_r15_20260529_234341
```

将 bridge waiting block 上限收窄到 `10%`，并增加 waiting request 数上限后，系统可以完成运行。

| Variant | SLO | TTFT p50 | TTFT p90 | TTFT p95 | TTFT p99 | TPOT p50 | TPOT p90 | TPOT p95 | TPOT p99 | Goodput |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 10% waiting + output pressure weight 0.5 | 0.648 | 0.093 | 0.266 | 1.292 | 3.087 | 0.050 | 0.634 | 0.921 | 2.656 | 0.79 |
| 10% waiting + output pressure off | 0.609 | 0.093 | 0.286 | 1.125 | 3.090 | 0.052 | 0.622 | 0.909 | 2.689 | 0.75 |

结论：10% waiting relaxation 能改善部分 SLO/goodput 或 TPOT p90/p99，但 TTFT tail 仍明显弱于 FCFS，TPOT p95 也会变差。因此它不应作为 full Phase 默认策略。

代码最终状态：

- `PHASESERVE_DECODE_STARVED_PRIMARY`：默认开启。
- `PHASESERVE_KAS_BRIDGE_EVICTION_ALLOW_DECODE_HEAVY`：默认开启。
- `PHASESERVE_PBC_DECODE_TOKEN_WEIGHT`：Phase 默认 `0.0`，保留为实验开关。
- `PHASESERVE_KAS_BRIDGE_RESERVE`：默认关闭，保留为实验开关。
- `PHASESERVE_KAS_BRIDGE_WAITING_BLOCK_PROP`：默认保持 DistServe 原始 waiting block 比例，不默认放宽。

## Conflict-First PBC and Bridge Completion Drain

继续诊断 rate `1.5` 后，发现 `context` 侧大量空 dispatch 的直接原因是 bridge/unaccepted backlog 长时间占住 context blocks：

| Variant | Context dispatches | Protected blocked | Protected selected | Context selected p50/p90 | Context unaccepted p50/p90 | Context max wait p90 |
|---|---:|---:|---:|---:|---:|---:|
| old `phase` | 1449 | 1192 | 125 | 0 / 0 | 18 / 21 | 3.459s |
| short-priority BPS | 1579 | 1295 | 125 | 0 / 0 | 18 / 21 | 3.617s |

这个结果说明 BPS 的 protected oldest 逻辑本身不是主因；当 bridge queue 没有 decode capacity 时，protected request 物理上无法进入 first-token 路径。因此，本阶段最终采用两个默认机制。

### 1. PBC conflict-first regime arbitration

原 PBC 在 first-token/bridge pressure 和 decode pressure 同时较高时会优先落入 `DECODE_HEAVY`，导致 TTFT debt 和 relaxed bridge acceptance 被过早关闭。

新增：

- `PHASESERVE_PBC_FIRST_DECODE_CONFLICT_POLICY`
- 默认值：`first`

当 `first_token_pressure >= rho_high` 且 `decode_tail_pressure >= rho_high`，同时 hard pressure 未触发时，PBC 默认把该冲突交给 first-token owner 处理，而不是直接判为 decode-heavy。保留可选值：

| Value | Regime |
|---|---|
| `first` / `first_token` | `FIRST_TOKEN_LIMITED` |
| `mixed` | `MIXED_SLO` |
| `decode` / `decode_heavy` | `DECODE_HEAVY` |

### 2. KAS bridge completion drain

仅把冲突判给 first-token owner 仍不够；如果 decode 侧已有大量 resident KV，bridge 接收仍可能缺少 GPU blocks。因此 KAS 增加 bridge 高压下的 completion-drain 分支：

- `PHASESERVE_KAS_BRIDGE_COMPLETION_DRAIN`
- 默认值：`phase` 中开启
- `PHASESERVE_KAS_BRIDGE_COMPLETION_PRESSURE=0.65`
- `PHASESERVE_KAS_BRIDGE_COMPLETION_REMAINING=96`

当 bridge/first-token pressure 达到阈值且 hard pressure 未触发时，decode 排序临时转为：

```text
starved primary
-> first decode step
-> resident request
-> short remaining output
-> smaller remaining output
-> larger allocated KV blocks
-> ready time
```

该规则的目标不是放弃 KAS，而是在 bridge pressure 主导时先完成少量快结束请求、释放 KV blocks，让 context-finished requests 能迁入 decode 并产生 first token。

### 3. Failed branches kept off by default

以下分支在 spot check 中没有形成可靠收益，因此保留为实验开关，不进入默认 full Phase：

| Mechanism | Default | Reason |
|---|---:|---|
| `PHASESERVE_KAS_BRIDGE_HOL_BYPASS` | off | short-prompt bypass 会让中长 prompt 的 TTFT tail 升到秒级 |
| `PHASESERVE_KAS_BRIDGE_SHORT_OUTPUT_FASTLANE` | off | short-output bridge scan 会造成 starvation，TTFT p90/p99 明显恶化 |
| `PHASESERVE_KAS_BRIDGE_RESERVE` | off | reserve 不会主动 eviction，无法稳定释放 bridge capacity |
| `PHASESERVE_KAS_BRIDGE_WAITING_BLOCK_PROP` 放宽 | off | 10%-20% 放宽会带来 TPOT p95 或近似死锁风险 |

## Final OPT-13B + ShareGPT 128-Request Spot Results

采用最终默认方向后，用 `PHASESERVE_PBC_FIRST_DECODE_CONFLICT_POLICY=first` 和 bridge completion drain 在 ShareGPT first 128 requests 上复测。下表的 Phase 结果来自最新代码；FCFS 来自同一 trace、同 seed 的既有 baseline。延迟单位为秒。

| Global Rate | Policy | TTFT p50 | TTFT p90 | TTFT p95 | TTFT p99 | TPOT p50 | TPOT p90 | TPOT p95 | TPOT p99 | SLO | Goodput |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1.25 | `fcfs` | 0.091 | 0.207 | 0.222 | 0.263 | 0.030 | 0.310 | 0.430 | 1.940 | 0.805 | 0.94 |
| 1.25 | final `phase` | 0.077 | 0.203 | 0.228 | 0.278 | 0.033 | 0.196 | 0.314 | 0.743 | 0.859 | 1.00 |
| 1.35 | `fcfs` | 0.077 | 0.207 | 0.232 | 0.259 | 0.042 | 0.423 | 0.571 | 2.506 | 0.750 | 0.94 |
| 1.35 | final `phase` | 0.088 | 0.210 | 0.222 | 0.255 | 0.040 | 0.254 | 0.406 | 1.315 | 0.813 | 0.95 |
| 1.40 paired | `fcfs` | 0.085 | 0.208 | 0.238 | 0.282 | 0.049 | 0.515 | 0.644 | 2.467 | 0.711 | 0.90 |
| 1.40 paired | final `phase` | 0.078 | 0.201 | 0.243 | 0.266 | 0.044 | 0.349 | 0.458 | 1.191 | 0.758 | 0.91 |
| 1.50 | `fcfs` | 0.088 | 0.211 | 0.259 | 0.309 | 0.060 | 0.721 | 0.840 | 3.146 | 0.594 | 0.753 |
| 1.50 | final `phase` | 0.083 | 0.202 | 0.243 | 0.277 | 0.049 | 0.473 | 0.683 | 1.626 | 0.711 | 0.858 |

相对 FCFS 的改善如下，正数表示延迟下降、SLO/goodput 提升：

| Global Rate | TTFT p50 | TTFT p90 | TTFT p95 | TTFT p99 | TPOT p50 | TPOT p90 | TPOT p95 | TPOT p99 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1.25 | +15.8% | +1.8% | -2.3% | -5.7% | -8.2% | +36.8% | +27.1% | +61.7% |
| 1.35 | -14.8% | -1.1% | +4.6% | +1.5% | +4.3% | +39.9% | +28.9% | +47.5% |
| 1.40 paired | +7.9% | +3.5% | -2.3% | +5.7% | +11.1% | +32.1% | +28.9% | +51.7% |
| 1.50 | +5.3% | +4.4% | +6.2% | +10.3% | +19.6% | +34.3% | +18.8% | +48.3% |

当前最适合主端到端图的 spot 是 global rate `1.50`：TTFT p50/p90/p95/p99 与 TPOT p50/p90/p95/p99 同时改善，SLO 从 `59.4%` 提升到 `71.1%`，goodput 从 `0.753` 提升到 `0.858` req/s。global rate `1.25` 可作为 TPOT tail + TTFT p50/p90 辅助点；global rate `1.35/1.40` 可作为 TPOT tail + TTFT tail 辅助点。

### Seed1 Confirmation at Global Rate 1.50

随后补跑 `BENCHMARK_SEED=1`、global rate `1.50`、`fcfs/phase` paired run：

```text
/root/data/phase_scheduler_results/opt13b_sharegpt_conflict_first128_r15_seed1_20260530_1015
```

| Seed | Policy | TTFT p50 | TTFT p90 | TTFT p95 | TTFT p99 | TPOT p50 | TPOT p90 | TPOT p95 | TPOT p99 | SLO | Goodput |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | `fcfs` | 0.092 | 0.215 | 0.231 | 0.282 | 0.041 | 0.324 | 0.582 | 1.524 | 0.742 | 1.01 |
| 1 | final `phase` | 0.086 | 0.212 | 0.231 | 0.262 | 0.040 | 0.249 | 0.360 | 1.113 | 0.758 | 1.01 |

相对 FCFS，seed1 的 final `phase` 改善 TTFT p50/p90/p95/p99 `7.0%/1.2%/0.1%/7.3%`，改善 TPOT p50/p90/p95/p99 `3.9%/23.1%/38.2%/27.0%`，SLO +`1.56 pp`。这说明 rate `1.50` 不再只是单 seed 偶然点。

## 验收判断

本阶段完成“诊断 + 默认策略修复 + 128-request spot validation + seed1 confirmation”。它还不是最终论文矩阵，但已经把 OPT-13B + ShareGPT 上 full Phase 的主要实现风险从“TTFT tail 会秒级恶化”收敛到“可进入正式图表候选，需要继续扩 seed/rate 和机制审计”。

通过项：

1. 128-request trace 验证了 Phase 在低到中等 pressure 下确实能明显降低 TPOT tail。
2. 找到导致 rate `1.5` TTFT tail 退化的主要机制：decode queue 被清空，但 bridge/unaccepted queue 积压，BPS 保护对象无法进入 decode。
3. 修复了 KAS bounded-progress 中 `starved` 只做 tie-break 的实现 gap。
4. 修复了 PBC nominal regime 与 bridge-dominant pressure 不一致时 bridge eviction 不触发的实现 gap。
5. 验证了 output-token pressure、bridge reserve、bridge waiting relaxation 不能直接作为默认策略。
6. 新增 PBC conflict-first arbitration，使 first-token/bridge 与 decode 同时高压时由 first-token owner 优先处理。
7. 新增 KAS bridge completion drain，使 decode 在 bridge 高压时优先完成快结束 resident 请求并释放 KV blocks。
8. 在 global rate `1.5` 上，seed0 final `phase` 同时改善 TTFT p50/p90/p95/p99、TPOT p50/p90/p95/p99、SLO 和 goodput；seed1 进一步确认 TTFT p50/p90/p95/p99 和 TPOT p50/p90/p95/p99 全部不差于 FCFS。
9. 本地和远端 `py_compile` 已通过。

未通过项：

1. 目前只对 global rate `1.50` 做了 seed1 复验；`1.25/1.35/1.40` 仍是 seed0 或单 paired spot。
2. Global rate `1.25/1.35/1.40/1.50` 的正向 percentile 不完全相同，论文图需要明确选定指标和 rate 区间，不能声称所有 percentile 全面改善。
3. Bridge completion drain 是 reactive KV release，后续仍可探索 context-side bridge capacity prediction，但当前不作为本阶段阻塞项。
4. 当前 `pressure_decode` 仍偏请求数和 queue 状态，没有显式建模 bucket-aware 剩余 output-token backlog。

## 下一步

下一步不再继续盲目改 bridge waiting 参数。当前代码已经拿到可用 spot，优先做最小复验和机制确认：

1. 继续补 seed1/seed2：优先 global rate `1.40/1.50`，确认主图候选窗口。
2. 做 mechanism audit：比较修复前后 `protected_blocked`、context selected batch size、decode bridge pressure、bridge completion drain active ratio 和 selected remaining-output 分布。
3. 如果多 seed 仍稳定，再把 `1.40/1.50` 纳入端到端主图候选；如果只保留 TPOT 优势，则收窄 TTFT claim 到 rate `1.50` 或指定 percentile。
4. 后续可选增强是 bucket-aware output backlog pressure，但它不再阻塞当前 spot validation。

## 当前论文 claim 影响

本阶段不会削弱方法论，反而把方法论中的 hard feasibility 和 cross-stage pressure propagation 映射得更清楚：

1. PBC 不能只输出 nominal regime，还必须支持 pressure dominance 下的冲突仲裁。
2. KAS 不只是 LAS + KV-aware tie-break，还必须有 bounded-progress 的硬进展语义。
3. BPS 的 first-token 保护如果缺少 bridge capacity 保证，会在高 pressure 下被物理容量阻断。

因此，Stage 4I 的结论是：方法论方向仍成立，且当前代码已经在 OPT-13B + ShareGPT 128-request seed0/seed1 上把 rate `1.5` 从 tradeoff 点修成综合改善点。下一步的核心不是继续扩大方法，而是用更多 seed 和机制审计确认该 spot 能否进入正式端到端图。
