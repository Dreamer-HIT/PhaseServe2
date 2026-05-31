# Stage 1：代码映射与实现计划

## 本阶段目标

Stage 1 的目标是把 `docs/methodology.md` 中的 PBC/BPS/KAS 方法论映射到当前 DistServe 代码结构，区分：

1. 已经实现并可继续使用的代码路径。
2. 已经实现但与最新版方法论存在偏差的部分。
3. 尚未实现、需要进入 Stage 2 的代码项。
4. 每个方法 claim 对应的指标、baseline 和最小验证路径。

本阶段只产出实现计划，不修改调度器代码，不运行实验。

## 本阶段产物

本阶段新增文档：

| 文件 | 作用 |
|---|---|
| `docs/stage1_code_mapping_plan.md` | 记录方法论到代码结构的映射、实现缺口、Stage 2 修改计划和验收标准 |

## 读取文件

本阶段读取了以下文件：

| 文件 | 用途 |
|---|---|
| `docs/methodology.md` | 最新 PBC/BPS/KAS 方法论、claim-baseline contract、指标要求 |
| `docs/current_progress.md` | 当前整体进度、已验证结论、剩余差距 |
| `remote_distserve/docs/current_progress.md` | 远程 DistServe 侧已有实现进度 |
| `remote_distserve/distserve/phase_scheduler.py` | PBC、AdmissionBudget、pressure snapshot、metrics 写入 |
| `remote_distserve/distserve/context_stage_scheduler.py` | BPS / context-stage scheduler 实现 |
| `remote_distserve/distserve/decoding_stage_scheduler.py` | KAS / decode-stage scheduler 实现 |
| `remote_distserve/distserve/config.py` | scheduler policy 配置入口 |
| `remote_distserve/distserve/single_stage_engine.py` | context/decode scheduler 接入 engine 的路径 |
| `remote_distserve/benchmarks/phase_native_benchmark.py` | benchmark summary 与 phase metrics 聚合 |
| `remote_distserve/benchmarks/phase_collect_summaries.py` | 多实验 summary flatten |
| `remote_distserve/scripts/run_phase_hetero_1p1d.sh` | policy 到 context/decode scheduler 的运行映射 |
| `remote_distserve/scripts/run_phase_pbc_sweep.sh` | PBC 消融入口 |
| `remote_distserve/scripts/run_phase_ablation_sweep.sh` | 组件消融入口 |
| `remote_distserve/scripts/run_phase_bps_internal_sweep.sh` | BPS 内部消融入口 |

## 修改文件

本阶段只新增 `docs/stage1_code_mapping_plan.md`。没有修改 `remote_distserve` 下的调度器、benchmark 或实验脚本。

## 当前代码总览

当前代码已经具备可运行的 PhaseServe 主链路：

```text
remote_distserve/distserve/phase_scheduler.py
  -> AdmissionBudget
  -> PressureBudgetController
  -> write_pressure_snapshot / read_pressure_snapshot
  -> append_phase_metric

remote_distserve/distserve/context_stage_scheduler.py
  -> ContextStageFCFSScheduler
  -> ContextStageCostCompatibleScheduler  # BPS

remote_distserve/distserve/decoding_stage_scheduler.py
  -> DecodingStageFCFSScheduler
  -> DecodingStageKVAwareLASScheduler     # KAS

remote_distserve/scripts/run_phase_hetero_1p1d.sh
  -> policy mapping:
     fcfs, bps, kas, bps_kas, bps_pbc, kas_pbc, phase
```

核心策略映射如下：

| 实验 policy | Context scheduler | Decode scheduler | PBC dynamic | 用途 |
|---|---|---|---|---|
| `fcfs` | `fcfs` | `fcfs` | 否 | DistServe FCFS baseline |
| `bps` | `phase` | `fcfs` | 否 | BPS 单组件 |
| `kas` | `fcfs` | `kv-aware-las` | 否 | KAS 单组件 |
| `bps_kas` | `phase` | `kv-aware-las` | 否 | BPS+KAS，静态 budget |
| `bps_pbc` | `phase` | `fcfs` | 是 | PBC+BPS |
| `kas_pbc` | `fcfs` | `kv-aware-las` | 是 | PBC+KAS |
| `phase` | `phase` | `phase` | 是 | PBC+BPS+KAS full |

## PBC 映射

### 已实现

`remote_distserve/distserve/phase_scheduler.py` 已实现：

1. `AdmissionBudget`：
   - `mode`
   - `rho_down`
   - `prefill_token_budget`
   - `prefill_block_margin`
   - `prefer_small_kv_footprint`
   - `decode_swap_budget_per_iter`
   - `decode_scan_limit`
   - `allow_protected_oldest`
   - `pressure_bridge/decode/kv/swap/age`
   - `rho_prefill/rho_memory/rho_swap/rho_scan`
   - `pressure_overshoot`

2. `PressureBudgetController`：
   - `rho_low/rho_high`
   - smoothing via `PHASESERVE_PBC_SMOOTH_LAMBDA`
   - aggregation via `PHASESERVE_PBC_AGG=max|weighted|lexicographic`
   - static budget 消融 via `PHASESERVE_PBC_DISABLE_DYNAMIC`
   - component-wise mapping：
     - `rho_prefill = aggregate(bridge, decode)`
     - `rho_memory = aggregate(kv, swap)`
     - `rho_swap = swap`
     - `rho_scan = aggregate(kv, swap)`

3. 跨阶段 pressure：
   - decode 侧通过 `write_pressure_snapshot("decode", ...)` 写出 pressure。
   - context 侧通过 `read_pressure_snapshot(expected_component="decode")` 读取 decode pressure。
   - snapshot 有 stale / wrong-component 检查。

4. 现有 PBC metrics：
   - `mode_switch_rate`
   - `last_budget_delta`
   - `last_pressure_overshoot`
   - per-component pressure 已能进入 phase metrics summary。

### 与最新版方法论的差距

最新版方法论新增了 `Pressure-Drift Surrogate`，当前代码还没有完整兑现：

| 方法论要求 | 当前代码状态 | Stage 2 动作 |
|---|---|---|
| `Phi(t)` pressure potential | 未计算 | 在 `PressureBudgetController` 中计算并记录 |
| `I_prefill(t)` | context metrics 有 `selected_prompt_tokens`，但没有统一成 surrogate 字段 | 在 context dispatch 后写入 `pressure_injection_prefill` |
| `I_decode_swap(t)` | decode metrics 有 `swap_in_bytes`，但没有统一成 surrogate 字段 | 在 decode dispatch 后写入 `pressure_injection_decode_swap` |
| `GoodputCapacity(b)` | 未实现 | 先用 normalized budget capacity 近似 |
| `SmoothCost(b,b-1)` | 目前有 `last_budget_delta` | 改名或补充为 surrogate 字段 |
| `ProgressDebt(t)` | BPS/KAS 分散记录 protected/starved | 在 controller 或 metrics summary 汇总 |
| budget variance | summary 可从序列算，但当前 collect flatten 不直接输出 | 在 benchmark summary 增加方差字段 |

### Stage 2 PBC 实现计划

优先改动文件：

1. `remote_distserve/distserve/phase_scheduler.py`
   - 扩展 `AdmissionBudget` 字段：
     - `pressure_potential`
     - `pressure_injection_prefill`
     - `pressure_injection_decode_swap`
     - `goodput_capacity`
     - `smooth_cost`
     - `progress_debt`
   - 在 `PressureBudgetController.update()` 内计算 `Phi(t)` 和 normalized capacity。
   - 保留当前 component-wise mapping，不再回退到单一 `rho_down` 控制。

2. `remote_distserve/distserve/context_stage_scheduler.py`
   - 在 BPS dispatch 后计算 `selected_prefill_blocks`。
   - 写入 `I_prefill` 所需字段。

3. `remote_distserve/distserve/decoding_stage_scheduler.py`
   - 在 KAS dispatch 后写入 `I_decode_swap` 所需字段。

4. `remote_distserve/benchmarks/phase_native_benchmark.py`
   - 聚合 `Phi(t)`、`I_prefill`、`I_decode_swap`、`goodput_capacity`。

5. `remote_distserve/benchmarks/phase_collect_summaries.py`
   - flatten surrogate fields，供 sweep CSV/MD 使用。

### PBC 验收标准

1. `phase` vs `bps_kas` 能展示 budget movement 与 pressure drift 的关联。
2. summary 中能直接看到：
   - `phase_context_pressure_potential_mean/p99`
   - `phase_decode_pressure_potential_mean/p99`
   - `phase_context_I_prefill_mean`
   - `phase_decode_I_decode_swap_mean`
   - `mode_switch_rate`
   - `budget_delta`
3. PBC sensitivity 至少覆盖：
   - `max`
   - `weighted`
   - `lexicographic`
4. 低负载或 homogeneous workload 下 overhead/no-regression 可报告。

## BPS 映射

### 已实现

`remote_distserve/distserve/context_stage_scheduler.py` 中 `ContextStageCostCompatibleScheduler` 已实现：

1. bounded candidate window：
   - `PHASESERVE_PREFILL_WINDOW_MULT`
2. prompt-length bucket：
   - `PHASESERVE_PREFILL_BUCKETS`
3. cost-compatible batch construction：
   - request limit
   - token budget
   - GPU block feasibility
   - PBC `prefill_token_budget`
   - PBC `prefill_block_margin`
4. scoring：
   - `token_fill`
   - `pad_waste`
   - `block_risk`
   - `pressure_multiplier = 1 + rho_down`
   - `oldest_bonus`
5. bounded-progress：
   - protected oldest
   - forced single dispatch
   - `protected_blocked`
6. instrumentation：
   - protected dispatch ratio
   - feasible protected dispatch ratio
   - long-prompt wait summaries
   - selected prompt tokens
   - decode snapshot used/stale/age
   - scheduler overhead

### 与最新版方法论的差距

| 方法论要求 | 当前代码状态 | Stage 2 动作 |
|---|---|---|
| `pad_waste` 作为机制信号 | 用于 scoring，但未直接写入 metrics | context dispatch metrics 增加 selected batch `pad_waste` |
| `block_risk` 作为机制信号 | 用于 scoring，但未直接写入 metrics | context dispatch metrics 增加 selected batch `block_risk` |
| selected token distribution | 有 `selected_prompt_tokens` | 保留并在 summary 中加强 p50/p90/p99 |
| shortest-prompt-first baseline | 未实现 policy | 增加 `shortest-prefill` 或脚本级 baseline |
| pure bucket batching baseline | `bucket_only` scoring mode 已有 | 保留为 BPS internal ablation |
| protected oldest claim | 已有 metrics | 需要 prompt-skew smoke 验证字段完整性 |

### Stage 2 BPS 实现计划

优先改动文件：

1. `remote_distserve/distserve/context_stage_scheduler.py`
   - 增加 `_batch_pad_waste()`、`_batch_block_risk()` 辅助函数。
   - 在 dispatch metrics 中写入 selected batch 的 `pad_waste`、`block_risk`、`token_fill`。
   - 可选：新增 `shortest-prefill` policy，作为 SPF baseline。

2. `remote_distserve/distserve/config.py`
   - 如果实现 SPF baseline，增加 context policy 名称。

3. `remote_distserve/scripts/run_phase_hetero_1p1d.sh`
   - 如果实现 SPF baseline，增加 policy mapping。

4. `remote_distserve/benchmarks/phase_native_benchmark.py`
   - 聚合 BPS selected batch mechanism signals。

5. `remote_distserve/benchmarks/phase_collect_summaries.py`
   - flatten `pad_waste/token_fill/block_risk`。

### BPS 验收标准

1. BPS claim 能对应：
   - FCFS
   - shortest-prompt-first
   - pure bucket batching
2. prompt-skew workload 中报告：
   - TTFT p90/p99
   - context queue time
   - pad waste
   - selected prompt token distribution
   - long-prompt max wait
   - protected feasible dispatch ratio
3. dominant prompt buckets 改善时，long prompt tradeoff 同时可解释。

## KAS 映射

### 已实现

`remote_distserve/distserve/decoding_stage_scheduler.py` 中 `DecodingStageKVAwareLASScheduler` 已实现：

1. attained-service priority：
   - `_get_attained_level(request)` 基于 `request.get_output_len().bit_length()`。
2. resident-first tie-break：
   - `_ready_sort_key()` 中 resident request 优先。
3. starved tie-break：
   - `consecutive_skips >= skip_threshold`。
4. PBC decode budget：
   - `decode_scan_limit`
   - `decode_swap_budget_per_iter`
5. hard feasibility gates：
   - batch size
   - token budget
   - GPU append blocks
   - GPU swap blocks
   - swap budget
6. swap-aware admission：
   - CPU-resident request admission 会触发 `swap_in_requests`。
   - 记录 `swap_in_bytes` 和 `iteration_stall_s`。
7. infeasible accounting：
   - `infeasible_gpu_append_blocks`
   - `infeasible_gpu_swap_blocks`
   - `infeasible_swap_budget`
   - `policy_skipped`
8. fairness instrumentation：
   - `max_consecutive_skips`
   - `max_consecutive_infeasible`
   - `starved_ready`
   - `starved_selected`
   - `starved_admission_ratio`
9. eviction：
   - `_evict_resident_requests_for_blocks()` 保守换出低优先级 resident request。

### 与最新版方法论的差距

| 方法论要求 | 当前代码状态 | Stage 2 动作 |
|---|---|---|
| `decode_swap_budget_per_iter` 按 bytes hard gate | 当前 hard gate 是 swap-in request count，bytes 只统计 | 增加 byte-budget hard gate，或在方法中明确 count+bytes 双口径 |
| 显式 attained-service queues | 当前每轮 sort ready set，而非持久多队列 | 可保留实现，但文档/代码注释需说明等价实现；或改为 explicit queues |
| pure LAS baseline | 未实现独立 policy | 增加 `pure-las` / `kv-unaware-las` |
| KV-unaware LAS baseline | 未实现 | 增加 policy，关闭 resident preference 与 KV/swap-aware tie-break |
| long-output slowdown | current progress 说明已有 proxy，但代码映射需确认 summary 字段 | 确认 `phase_native_benchmark.py` bucket 输出，必要时补 flatten |
| swap bytes / iteration stall | 已记录 | 确认 collect/analyze 全链路输出 |

### Stage 2 KAS 实现计划

优先改动文件：

1. `remote_distserve/distserve/decoding_stage_scheduler.py`
   - 增加 `PHASESERVE_DECODE_SWAP_BUDGET_BYTES`。
   - `_check_add_to_las_batch()` 同时检查 swap count 和 swap bytes。
   - 增加 `KV-unaware LAS` policy 变体：
     - 保留 attained-service ordering。
     - 关闭 resident-first tie-break。
     - 关闭 swap-budget admission 或仅做 FCFS-style swap preference。
   - 可选增加 `pure-las` policy。

2. `remote_distserve/distserve/config.py`
   - 增加 decode policy：
     - `pure-las`
     - `kv-unaware-las`

3. `remote_distserve/scripts/run_phase_hetero_1p1d.sh`
   - 增加 policy mapping：
     - `pure_las`
     - `kv_unaware_las`

4. `remote_distserve/benchmarks/phase_native_benchmark.py`
   - 确认 long-output bucket 的 slowdown proxy。
   - 聚合 swap byte budget 相关指标。

5. `remote_distserve/benchmarks/phase_collect_summaries.py`
   - flatten swap byte budget、resident ratio、stall、long-output slowdown。

### KAS 验收标准

1. KAS claim 能对应：
   - FCFS
   - round-robin 或现有等价 baseline
   - pure LAS
   - KV-unaware LAS
2. decode-heavy / memory-pressure workload 中报告：
   - TPOT p90/p99
   - short-output slowdown
   - long-output slowdown
   - resident admission ratio
   - swap bytes
   - iteration stall
   - infeasible reason breakdown
3. `policy_skipped` 与 `infeasible_rounds` 明确分开。

## Benchmark 与实验脚本映射

### 已有能力

`remote_distserve/benchmarks/phase_native_benchmark.py` 已支持：

1. TTFT/TPOT/latency p50/p90/p95/p99。
2. context/decode queue breakdown。
3. SLO attainment。
4. goodput / throughput / per-GPU goodput。
5. prompt/output bucket breakdown。
6. phase metrics summary。

`remote_distserve/benchmarks/phase_collect_summaries.py` 已 flatten：

1. throughput/goodput。
2. TTFT/TPOT percentile。
3. BPS protected metrics。
4. KAS infeasible/fairness metrics。
5. PBC rho/budget/mode metrics。

### 缺口

1. PBC surrogate fields 尚未进入 benchmark summary。
2. BPS `pad_waste/token_fill/block_risk` 尚未 flatten。
3. KAS byte-budget hard gate 尚未 flatten。
4. claim-level minimum success criteria 尚未编码成分析脚本输出。

### Stage 2 脚本计划

1. 在 summary 中增加 `claim_signals` 字段：
   - BPS claim signals
   - KAS claim signals
   - PBC claim signals
2. 在 `phase_analyze_sweep.py` 中增加 claim-level tables：
   - BPS vs FCFS/SPF/bucket
   - KAS vs FCFS/pure-LAS/KV-unaware-LAS
   - PBC full vs static budget
3. 早期 1p1d + LLaMA2-7B smoke 只保留为历史调试记录；Stage 3 之后的实验模型改为 OPT-13B 和 LLaMA2-13B。

## Stage 2 推荐实现顺序

### Step 2.1：PBC surrogate 与参数默认值

原因：这是最新方法论 novelty 的核心，也最影响后续实验解释。

修改文件：

- `remote_distserve/distserve/phase_scheduler.py`
- `remote_distserve/distserve/context_stage_scheduler.py`
- `remote_distserve/distserve/decoding_stage_scheduler.py`
- `remote_distserve/benchmarks/phase_native_benchmark.py`
- `remote_distserve/benchmarks/phase_collect_summaries.py`

最小验证：

```text
python -m py_compile \
  distserve/phase_scheduler.py \
  distserve/context_stage_scheduler.py \
  distserve/decoding_stage_scheduler.py \
  benchmarks/phase_native_benchmark.py \
  benchmarks/phase_collect_summaries.py
```

### Step 2.2：KAS baseline 与 swap byte budget

原因：KAS 是最容易被 reviewer 质疑“只是 LAS + resident tie-break”的部分。

修改文件：

- `remote_distserve/distserve/decoding_stage_scheduler.py`
- `remote_distserve/distserve/config.py`
- `remote_distserve/scripts/run_phase_hetero_1p1d.sh`
- `remote_distserve/benchmarks/phase_native_benchmark.py`
- `remote_distserve/benchmarks/phase_collect_summaries.py`

最小验证：

```text
python -m py_compile distserve/decoding_stage_scheduler.py distserve/config.py
```

### Step 2.3：BPS mechanism metrics 与 SPF baseline

原因：BPS 已经可运行，但 claim-baseline contract 还缺 shortest-prompt-first。

修改文件：

- `remote_distserve/distserve/context_stage_scheduler.py`
- `remote_distserve/distserve/config.py`
- `remote_distserve/scripts/run_phase_hetero_1p1d.sh`
- `remote_distserve/benchmarks/phase_native_benchmark.py`
- `remote_distserve/benchmarks/phase_collect_summaries.py`

最小验证：

```text
python -m py_compile distserve/context_stage_scheduler.py distserve/config.py
```

### Step 2.4：分析脚本 claim tables

原因：顶会论文需要机制归因表，而不是只看 end-to-end p99。

修改文件：

- `remote_distserve/benchmarks/phase_analyze_sweep.py`
- `remote_distserve/benchmarks/phase_collect_summaries.py`

最小验证：

```text
python -m py_compile benchmarks/phase_analyze_sweep.py benchmarks/phase_collect_summaries.py
```

## Stage 1 验收标准

本阶段满足以下验收标准：

1. 已读取方法论文档与当前代码入口。
2. 已明确 PBC/BPS/KAS 对应文件、类、函数和指标链路。
3. 已区分已实现、部分实现、未实现项。
4. 已列出 Stage 2 需要修改的文件。
5. 已给出每个组件的最小验证方式。
6. 未进入代码实现或实验运行。

## 风险和阻塞点

1. **PBC surrogate 是新增方法论要求**：当前代码有 component-wise mapping，但没有 `Phi/I_prefill/I_decode_swap` 统一账本；需要 Stage 2 优先补齐。
2. **KAS byte-budget 与当前实现不完全一致**：当前 hard gate 是 swap-in count，论文方法写的是 bytes；Stage 2 需要统一。
3. **KAS baseline 不足**：缺 pure LAS / KV-unaware LAS，顶会审稿会关注。
4. **BPS baseline 不足**：缺 shortest-prompt-first，pure bucket 已有但还需要汇总表支撑。
5. **已有远程文档和根目录方法论文档存在版本差异**：后续以根目录 `docs/methodology.md` 为准，远程 `docs/current_progress.md` 作为实现历史参考。
6. **Stage 2 会触及多个文件**：调度器、config、脚本、benchmark summary 需要同步修改，避免 claim 已实现但指标链路断裂。

## Stage 1 结论

当前代码已经实现 PhaseServe 的可运行主链路，具备进入 Stage 2 的基础。Stage 2 不应重写系统，而应围绕最新版方法论补齐三类缺口：

```text
PBC: surrogate accounting + default/sensitivity
KAS: byte-level swap budget + pure/KV-unaware LAS baseline
BPS: mechanism metrics + shortest-prompt-first baseline
```

完成这些后，再进入 Stage 3 设计 workload 与实验矩阵更稳。
