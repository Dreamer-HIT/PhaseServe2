# Stage 2：实现 PBC/BPS/KAS

更新时间：2026-05-27

## 本阶段目标

Stage 2 的目标是把 `docs/stage1_code_mapping_plan.md` 中列出的核心缺口补到代码里，使最新版方法论中的三类机制可以被执行和观测：

1. PBC：补齐 pressure-drift surrogate accounting，让 budget 变化、pressure potential 和 action injection 可被实验脚本读取。
2. BPS：补齐 batch mechanism metrics，并增加 shortest-prompt-first baseline。
3. KAS：补齐 byte-level swap budget、pure LAS / KV-unaware LAS baselines，以及对应的机制指标。

本阶段不扩大实验，不写论文结果，只做实现和最小验证。

## 读取或修改的文件

### 读取文件

| 文件 | 用途 |
|---|---|
| `docs/methodology.md` | 对齐 PBC/BPS/KAS 最新方法论 |
| `docs/stage1_code_mapping_plan.md` | 对齐 Stage 1 映射出的实现缺口 |
| `remote_distserve/distserve/phase_scheduler.py` | PBC budget 与 pressure controller |
| `remote_distserve/distserve/context_stage_scheduler.py` | context-stage BPS/FCFS 调度器 |
| `remote_distserve/distserve/decoding_stage_scheduler.py` | decode-stage KAS/FCFS 调度器 |
| `remote_distserve/distserve/config.py` | scheduler policy allow-list |
| `remote_distserve/benchmarks/phase_native_benchmark.py` | 单次实验 summary 聚合 |
| `remote_distserve/benchmarks/phase_collect_summaries.py` | 多实验 summary flatten |
| `remote_distserve/benchmarks/phase_analyze_sweep.py` | sweep 统计与 markdown 表 |
| `remote_distserve/scripts/run_phase_hetero_1p1d.sh` | 1p1d policy 映射入口 |

### 修改文件

| 文件 | 修改内容 |
|---|---|
| `remote_distserve/distserve/phase_scheduler.py` | 扩展 `AdmissionBudget` 和 `PressureBudgetController` 的 surrogate accounting |
| `remote_distserve/distserve/context_stage_scheduler.py` | 增加 SPF baseline，补齐 BPS action-injection 和 selected-batch metrics |
| `remote_distserve/distserve/decoding_stage_scheduler.py` | 增加 pure LAS/KV-unaware LAS baseline，补齐 byte-level swap feasibility |
| `remote_distserve/distserve/config.py` | 注册新增 context/decode scheduler policy |
| `remote_distserve/benchmarks/phase_native_benchmark.py` | 聚合新增 PBC/BPS/KAS 机制指标 |
| `remote_distserve/benchmarks/phase_collect_summaries.py` | flatten 新增机制指标 |
| `remote_distserve/benchmarks/phase_analyze_sweep.py` | 将新增指标纳入 grouped/paired/markdown 分析 |
| `remote_distserve/scripts/run_phase_hetero_1p1d.sh` | 增加 SPF、pure LAS、KV-unaware LAS policy 映射和 swap byte budget env |

## 具体产物

### PBC

已在 `AdmissionBudget` 中增加：

- `pressure_potential`
- `pressure_injection_prefill`
- `pressure_injection_decode_swap`
- `goodput_capacity`
- `smooth_cost`
- `progress_debt`

已在 `PressureBudgetController` 中增加：

- `Phi(t)` 近似：对 `bridge/decode/kv/swap` 超过阈值的 pressure 做加权二次势能统计。
- `GoodputCapacity(b)` 近似：基于 prefill token budget、prefill block margin、decode swap budget、decode scan limit 的归一化容量。
- `SmoothCost(b,b-1)`：复用 controller 的 budget delta。
- `ProgressDebt(t)`：当前以 age pressure 近似。
- metrics 输出：`last_pressure_potential`、`last_goodput_capacity`、`last_progress_debt`。

### BPS

已在 context-stage 调度中增加：

- selected batch 的 `selected_prefill_blocks`
- `token_fill`
- `pad_waste`
- `block_risk`
- `pressure_injection_prefill`

已增加 `shortest-prefill` / `shortest-prompt-first` context scheduler，用作 shortest-prompt-first baseline。该 baseline 使用全局最短 prompt 优先排序，并沿用 FCFS 的 batch feasibility 检查。

### KAS

已在 decode-stage 调度中增加：

- `pure-las` baseline：只按 attained service 排序，不使用 starvation tie-break、resident preference 或 swap budget。
- `kv-unaware-las` baseline：保留非 resident-aware 的 LAS 排序，不使用 KV resident preference 或 swap budget。
- `PHASESERVE_DECODE_SWAP_BUDGET_BYTES`：可选 byte-level swap budget。
- swap feasibility 同时检查 swap-in count budget 和 byte budget。
- dispatch metrics：`swap_byte_budget`、`swap_byte_budget_ratio`、`pressure_injection_decode_swap`、`policy_variant`。
- `PHASESERVE_KAS_ADAPTIVE_INTENSITY`：full `phase` 默认开启的连续 KAS 强度控制。bridge/first-token pressure 主导且无 hard KV/swap pressure 时，attained-service 和 resident preference 的排序强度下降；decode/swap pressure 主导或 hard pressure 出现时，KAS 强度恢复。
- `PHASESERVE_KAS_HANDOFF_DEBT`：可选 first-decode-step debt 诊断开关，当前默认关闭。
- dispatch metrics：`kas_intensity`、`kas_adaptive_intensity`、`handoff_debt_*`。

### 实验入口与分析脚本

`run_phase_hetero_1p1d.sh` 已支持新增 policy：

- `spf`
- `shortest_prefill`
- `shortest-prompt-first`
- `pure_las`
- `pure-las`
- `kv_unaware_las`
- `kv-unaware-las`

summary/analysis 脚本已接入以下机制指标：

- `phase_context_pressure_potential_mean`
- `phase_context_goodput_capacity_mean`
- `phase_context_pressure_injection_prefill_mean`
- `phase_context_selected_prefill_blocks_mean`
- `phase_context_token_fill_mean`
- `phase_context_pad_waste_mean`
- `phase_context_block_risk_mean`
- `phase_decode_pressure_potential_mean`
- `phase_decode_goodput_capacity_mean`
- `phase_decode_pressure_injection_swap_mean`
- `phase_decode_swap_byte_budget_mean`
- `phase_decode_swap_byte_budget_ratio_mean`
- `phase_decode_kas_intensity_mean`
- `phase_decode_kas_adaptive_intensity_mean`
- `phase_decode_handoff_debt_admission_ratio_mean`
- `phase_decode_handoff_debt_discount_mean`

### Regime-aware PBC 代码对齐

方法论文档已将 PhaseServe 收敛为 `regime-aware PBC + BPS + intensity-controlled KAS`。对应实现已补齐第一轮代码接口：

- `AdmissionBudget` 新增 `regime`、`decode_utility_intensity`、`pressure_first`、`rho_hard`。
- `PressureBudgetController` 新增 regime classification：
  - `FIRST_TOKEN_LIMITED`
  - `DECODE_HEAVY`
  - `KV_SWAP_LIMITED`
  - `MIXED_SLO`
  - `STATIC`
- decode 侧 `_get_decode_budget()` 把 first-token pressure、hard KV/swap pressure 写入 PBC pressure vector。
- KAS 的 `_kas_intensity()` 优先读取 `budget.decode_utility_intensity`，旧的本地计算只作为兼容 fallback。
- context 侧从 decode snapshot 读取 `first` pressure，使 BPS/PBC 能看到 first-token-limited regime。
- summary/analysis 脚本新增 regime/intensity 指标：
  - `phase_decode_budget_decode_utility_intensity_mean`
  - `phase_decode_decode_utility_intensity_mean`
  - `phase_decode_regime_counts`
  - `phase_decode_regime_switch_rate_mean`
  - `phase_decode_intensity_delta_mean`
  - `phase_context_decode_utility_intensity_mean`
  - `phase_context_regime_counts`
  - `phase_context_regime_switch_rate_mean`

实现规则与方法论保持一致：first-token-limited regime 下可降低 KAS intensity；decode-heavy 与 KV/swap-limited regime 下 KAS intensity 立即恢复，避免 TPOT owner 被平滑滞后削弱。

## 验收标准

本阶段的代码级验收标准：

1. 新增 policy 能通过配置 allow-list。
2. 新增 budget/surrogate 字段能被 phase metrics 写入和 summary 聚合。
3. benchmark 汇总脚本能读取新增字段并输出 grouped/markdown 表。
4. 不要求本阶段证明性能提升；性能 claim 留到 Stage 4。

已完成的最小验证：

```bash
python -m py_compile \
  remote_distserve/distserve/phase_scheduler.py \
  remote_distserve/distserve/context_stage_scheduler.py \
  remote_distserve/distserve/decoding_stage_scheduler.py \
  remote_distserve/distserve/config.py \
  remote_distserve/benchmarks/phase_native_benchmark.py \
  remote_distserve/benchmarks/phase_collect_summaries.py \
  remote_distserve/benchmarks/phase_analyze_sweep.py
```

结果：通过。

同时用临时 synthetic summary 验证了 `phase_analyze_sweep.py` 可以读取并聚合新增字段：

- `phase_context_pressure_potential_mean`
- `phase_decode_swap_byte_budget_ratio_mean`

结果：通过。

## 风险和阻塞点

1. 本阶段只做本地语法和 summary smoke test，还没有在远程 1p1d + 13B 模型上运行新增 policy。
2. `GoodputCapacity(b)`、`ProgressDebt(t)` 当前是工程近似，足够支撑机制观测，但后续如果论文要强调理论性质，需要在方法论中明确其 surrogate 定义。
3. `pure-las` 和 `kv-unaware-las` 是 baseline，不代表最终方法；后续实验中需要确认它们能稳定运行，不然不能作为论文对照。
4. `PHASESERVE_DECODE_SWAP_BUDGET_BYTES` 默认关闭，Stage 3 需要决定是否在 workload 中显式打开并设置合理值。
5. BPS 的 SPF baseline 可能改善 TTFT 但损害 long prompt fairness，Stage 4 必须按 prompt bucket 报告，不能只报告全局平均。
6. KAS adaptive intensity 是 Stage 4 反推的修正：OPT-13B W2 pilot 显示它能缓解 rate 10 的 full `phase` TTFT 退化，但 rate 12 仍有轻微 tradeoff，需要继续验证 decode-heavy workload 下是否保留 TPOT tail 优势。

## 下一阶段入口

Stage 2 到此只完成代码实现与最小验证。进入 Stage 3 前，需要确认：

1. Stage 3 的 workload 是否先覆盖 1p1d + OPT-13B / LLaMA2-13B。
2. 新增 baseline 是否纳入第一批实验：`spf`、`pure-las`、`kv-unaware-las`。
3. 是否开启 `PHASESERVE_DECODE_SWAP_BUDGET_BYTES`，以及初始 byte budget 取值。
