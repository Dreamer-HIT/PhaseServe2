# PhaseServe 当前进度与下一步计划

更新时间：2026-05-27

## 一句话状态

PhaseServe 的论文方法论已经收敛为 `PBC + BPS + KAS` 三个正文算法；代码已完成可运行的主链路和 1p1d + LLaMA2-7B 初步验证。当前正在补齐方法论代码，优先把 PBC 从单一 `rho_down` 控制升级为 component-wise pressure-to-budget mapping。

## 文档地图

| 文档 | 作用 | 状态 |
|---|---|---|
| `docs/methodology.md` | 论文方法论主文档，定义 PBC/BPS/KAS 三个算法与论文 claim | 在工作区根目录维护 |
| `docs/current_progress.md` | 当前进度、差距和下一步实现计划 | 本文档 |
| `docs/pbc_component_mapping.md` | PBC 分量化预算映射的实现说明 | 已新增 |
| `docs/bucket_breakdown_validation.md` | bucket-level 指标和 BPS/KAS 归因 | 已更新 |
| `docs/cross_stage_pbc_implementation.md` | 跨阶段 PBC 代码实现说明 | 已完成 |
| `docs/cross_stage_pbc_validation.md` | PBC 消融与 tuned/aggressive 参数验证 | 已更新 |
| `docs/decode_heavy_validation.md` | decode-heavy 1p1d 验证、KAS/PBC 归因和 KV append 修复记录 | 已完成 |
| `docs/prefill_skew_validation.md` | prompt-skew/BPS 验证记录 | 已完成初版 |
| `docs/ablation_validation.md` | 组件消融结果记录 | 已完成初版 |

## 已实现

1. **PBC 基础闭环**
   - `distserve/phase_scheduler.py` 中实现 `PressureBudgetController` 和 `AdmissionBudget`。
   - context/decode 两侧共享 budget 对象。
   - decode 侧通过 snapshot 把 pressure 写给 context 侧。
   - 支持 dynamic/static PBC 消融：`phase` vs `bps_kas`。

2. **BPS 初版**
   - `distserve/context_stage_scheduler.py` 中实现 bounded-window cost-compatible prefill scheduler。
   - 支持 prompt bucket、token fill、padding waste、block risk、oldest bonus。
   - 支持 protected oldest request。
   - 接入 PBC 的 `prefill_token_budget` 和 `prefill_block_margin`。

3. **KAS 初版**
   - `distserve/decoding_stage_scheduler.py` 中实现 KV-aware attained-service decode scheduling。
   - 支持 attained-service priority、resident preference、swap budget、scan limit、skip counter。
   - 已修复 CPU swapped request swap-in 后未预留 next-token append KV block 的问题。

4. **实验与分析脚本**
   - `scripts/run_phase_hetero_1p1d.sh`
   - `scripts/run_phase_hetero_sweep.sh`
   - `scripts/run_phase_pbc_sweep.sh`
   - `scripts/run_phase_decode_heavy_sweep.sh`
   - `benchmarks/phase_collect_summaries.py`
   - `benchmarks/phase_analyze_sweep.py`

## 已验证

1. **1p1d + LLaMA2-7B 可运行**
   - FCFS、BPS、KAS、BPS+KAS、Phase 都能跑通。

2. **BPS 方向成立**
   - prompt-skew 下，BPS 对短/中 prompt bucket 的 TTFT tail 有明显改善。
   - 最长 prompt bucket 存在 tail transfer，论文中必须报告。

3. **KAS 方向成立**
   - decode-heavy rate2 下，KAS 相对 FCFS 的全局 TPOT p99 ratio 约 `0.537`，output token throughput ratio 约 `1.084`。
   - 主流 output buckets 的 TPOT p99 ratio 约 `0.52-0.73`。
   - `>512` output bucket 仍可能变差，需要 long-output stress。

4. **PBC 有真实消融语义**
   - `phase` vs `bps_kas` 能改变 prefill budget，并影响 TPOT/SLO。
   - decode-heavy burst 下，`phase` 相比 `bps_kas` 的 TPOT p99 ratio 约 `0.854`，SLO +`1.04 pp`。
   - 代价是 TTFT p90 +`4.886s`，说明旧版 PBC 映射仍偏粗。

## 当前补齐进度

### Step 1：PBC 分量化映射

状态：已实现本地第一版。

改动：

- `AdmissionBudget` 新增 `pressure_bridge/decode/kv/swap/age`。
- 新增 `rho_prefill/rho_memory/rho_swap/rho_scan`。
- `prefill_token_budget` 主要由 `bridge/decode` 控制。
- `prefill_block_margin` 主要由 `kv/swap` 控制。
- `decode_swap_budget_per_iter` 只由 `swap` 控制。
- `decode_scan_limit` 由 `kv/swap` 控制。
- benchmark summary 和 sweep analysis 增加 PBC diagnostics。

待验证：

- `phase` 相比 `bps_kas` 仍能降低 decode-heavy burst 下 TPOT tail。
- TTFT p90 tradeoff 比旧版 `+4.886s` 明显收敛。
- mode switch rate 和 pressure overshoot 不异常升高。

### Step 2：KAS fairness

待实现：

- `infeasible_rounds`，区分“资源不可行”和“被策略跳过”。
- `max_consecutive_skips` 的 bucket-level 报告。
- `starved_admission_ratio`。
- long-output slowdown。
- KV-unaware LAS / pure LAS 对照。

### Step 3：BPS bounded-progress

待实现：

- protected dispatch ratio。
- long-prompt max queue wait。
- long-prompt TTFT p90/p99。
- forced oldest 对吞吐或 TPOT 的 tradeoff。

### Step 4：5 seeds 与专项 workload

只有 Step 1-3 的代码补齐后，再扩实验更划算。

优先实验：

1. decode-heavy：`fcfs kas bps_kas phase`，5 seeds。
2. long-output stress：验证 `>512` output bucket。
3. prompt-skew：验证 BPS long-prompt bounded waiting。
4. PBC sensitivity：`max / weighted / lexicographic` aggregation。
