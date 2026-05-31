# PhaseServe 当前进度与下一步计划

更新时间：2026-05-30

## 一句话状态

PhaseServe 的方法论和代码已收敛到 `typed/regime-aware PBC + BPS + bridge-budgeted KAS`：PBC 负责 typed pressure-to-budget、regime ownership 和 first/decode 冲突仲裁，BPS 作为 first-token/prefill 侧 TTFT owner，KAS 作为 decode 侧 TPOT owner，并在 bridge/first-token pressure 下扩大 admission feasibility budget。最新 OPT-13B + ShareGPT 128-request seed0 已在 global rate `2.0-4.0` 连续区间内同时让 TTFT 与 TPOT 至少两个分位超过 20% 改善；该区间在 1P1D/2 GPU 下对应 per-GPU rate `1.0-2.0`。High-rate 边界显示 `4.5` 和 `6.0` 存在 TPOT 断点，因此主图区间暂定 `2.0-4.0`；下一步是补 seed1/seed2 和核心消融。

## 文档地图

当前文档分为两层：

| 文档 | 作用 | 状态 |
|---|---|---|
| `docs/methodology.md` | 论文方法论主文档，定义 regime-aware PBC、BPS、intensity-controlled KAS、first/decode conflict owner 和 bridge completion drain | 已与当前默认代码机制同步 |
| `docs/stage1_code_mapping_plan.md` | 方法论到 DistServe 代码结构的映射和 Stage 2 实现计划 | 已完成 |
| `docs/stage2_implementation_summary.md` | Stage 2 实现内容、验收、风险和 Stage 3 入口 | 已完成 |
| `docs/archive/stages/stage2_arbitration_fix.md` | Stage 4A 反推的 PBC/BPS/KAS 仲裁修复、验证和下一轮 Stage 4A 入口 | 已完成 |
| `docs/stage3_experiment_design.md` | OPT-13B / LLaMA2-13B 双模型实验设计、workload、policy matrix 和 Stage 4 triage 规则 | 已完成 |
| `docs/experiment_protocol.md` | 最新实验协议与迭代原则，定义真实 trace 主线、baseline calibration、消融、ShuffleInfer-style baseline、失败诊断和返工规则 | 当前后续实验总入口 |
| `docs/archive/stages/stage4e_trace_baseline_calibration.md` | 真实 ShareGPT/LongBench trace 的 E1 baseline calibration 记录，包含数据集状态、OPT-13B+ShareGPT、LLaMA2-13B+LongBench 和 LLaMA2-13B+ShareGPT baseline pressure window | 已完成 seed0 初始窗口 |
| `docs/archive/stages/stage4f_e2_main_end_to_end.md` | E2 主端到端实验进展，记录 PhaseServe full 在 E1 固定窗口上与 DistServe/FCFS 的对比 | 已完成 seed0 初始结果 |
| `docs/archive/stages/stage4_w0_smoke_triage.md` | OPT-13B W0 smoke 结果、验收、风险和 LLaMA2-13B 阻塞记录 | OPT-13B 已完成，LLaMA2-13B 待授权 |
| `docs/archive/stages/stage4_w2_ttft_calibration.md` | OPT-13B prompt-skew 高压 TTFT 校准，定位 BPS 有效区间、full Phase 仲裁冲突、typed PBC 修复和 KAS gating 试验 | 已完成 seed 0 校准与修复收口 |
| `docs/archive/stages/stage4_decode_regime_validation.md` | regime-aware PBC 代码对齐后的 OPT-13B decode-heavy seed0/rate2 性能验证 | 已完成最小验证 |
| `docs/archive/stages/stage4a_prompt_skew_metric_audit.md` | OPT-13B prompt-skew seed0/1 指标审计，筛选 TTFT/TPOT candidate windows 并判断是否需要回到 Stage 2 | 已完成，结论是先修 full Phase 仲裁 |
| `docs/archive/stages/stage4b_scheduler_repair.md` | Stage 4A 之后的 PBC/BPS/KAS 仲裁循环修复，记录 short-output gate、long-output full-KAS gate 和最新 seed0 验证 | 已完成初步收口 |
| `docs/archive/stages/stage4c_mixed_regime_end_to_end.md` | OPT-13B mixed-regime full Phase vs FCFS 端到端验证 | 已完成 |
| `docs/archive/stages/stage4c_mechanism_audit.md` | Stage 4C mechanism audit，解释 mixed-regime 中 PBC/BPS/KAS 的机制链路 | 已完成 |
| `docs/archive/stages/stage4c_mixed_regime_ablation.md` | Stage 4C mixed-regime 组件消融，比较 `fcfs/bps/kas/bps_kas/phase` | 已完成 |
| `docs/archive/stages/stage4c_tpot_exploration.md` | Stage 4C TPOT rate fine sweep 与 decode-heavy stress，筛选 TPOT 辅助窗口 | 已完成 |
| `docs/archive/stages/stage4d_13b_mixed_wide_summary.md` | 最新双模型 13B mixed-wide 端到端汇总，包含新 SLO、OPT/LLaMA rate 表和论文 claim 边界 | 已完成 |
| `docs/archive/stages/stage4d_tpot_highrate_pilot.md` | TPOT high-rate pilot 与确认矩阵，检查 per-GPU `14/16` 是否可纳入 TPOT 主图 | 已完成 |
| `docs/archive/stages/stage4h_opt_sharegpt_phase512_repair.md` | OPT-13B + ShareGPT 上修复 full Phase TTFT/TPOT tradeoff，记录 long-output full KAS threshold 从 `192` 调整到 `512` 的诊断、代码改动和 seed0/1 验证 | 已完成 |
| `docs/archive/stages/stage4i_tpot_diagnostic_and_kas_bridge_repair.md` | OPT-13B + ShareGPT 128-request 诊断，修复 bridge/unaccepted pressure transfer，记录 PBC conflict-first 和 KAS bridge completion drain 的 spot validation | 已完成 seed0/seed1 rate1.5 spot |
| `docs/archive/stages/stage4j_opt_sharegpt_final128_pergpu1to5.md` | 最终默认代码在 OPT-13B + ShareGPT 128-request、per-GPU `1-5` 上的两 seed 复测，判断 Phase512 旧结果能否直接沿用 | 已完成 |
| `docs/archive/stages/stage4l_opt_sharegpt_bridge_budget_repair.md` | OPT-13B + ShareGPT Layer 1 上的 bridge budget 修复、global rate `2.0-4.0` 连续区间和 default smoke | 已完成 seed0 |
| `docs/methodology_code_alignment.md` | 方法论、代码实现和实验 claim 的对齐审计，记录当前 gap 与收窄策略 | 已完成 |
| `docs/research_plan.md` | 早期研究计划、指标口径和实验阶段 | 需要后续按当前方法论更新 |
| `remote_distserve/docs/bucket_breakdown_validation.md` | bucket-level 指标和 BPS/KAS 归因 | 已更新 |
| `remote_distserve/docs/cross_stage_pbc_implementation.md` | 跨阶段 PBC 代码实现说明 | 已完成 |
| `remote_distserve/docs/cross_stage_pbc_validation.md` | PBC 消融与 tuned/aggressive 参数验证 | 已更新 |
| `remote_distserve/docs/decode_heavy_validation.md` | decode-heavy 1p1d 验证、KAS/PBC 归因和 KV append 修复记录 | 已完成 |
| `remote_distserve/docs/prefill_skew_validation.md` | prompt-skew/BPS 验证记录 | 已完成初版 |
| `remote_distserve/docs/ablation_validation.md` | 组件消融结果记录 | 已完成初版 |
| `remote_distserve/docs/kas_fairness_implementation.md` | KAS fairness instrumentation 与 long-output slowdown proxy | 已新增 |
| `remote_distserve/docs/bps_bounded_progress_implementation.md` | BPS bounded-progress instrumentation 与 protected-oldest 修正 | 已新增 |

## 当前代码进度

### 已实现

1. **PBC 基础闭环**
   - `distserve/phase_scheduler.py` 中实现 `PressureBudgetController` 和 `AdmissionBudget`。
   - context/decode 两侧共享 budget 对象。
   - decode 侧通过 snapshot 把 pressure 写给 context 侧。
   - 支持 dynamic/static PBC 消融：`phase` vs `bps_kas`。
   - 已补齐 `pressure_potential`、`pressure_injection_prefill`、`pressure_injection_decode_swap`、`goodput_capacity`、`smooth_cost`、`progress_debt` 等 surrogate 字段。
   - 已新增 first/decode conflict arbitration：`PHASESERVE_PBC_FIRST_DECODE_CONFLICT_POLICY=first`，在 first-token/bridge pressure 与 decode pressure 同时较高且 hard pressure 未触发时，优先由 first-token owner 处理。

2. **BPS 初版**
   - `distserve/context_stage_scheduler.py` 中实现 bounded-window cost-compatible prefill scheduler。
   - 支持 prompt bucket、token fill、padding waste、block risk、oldest bonus。
   - 支持 protected oldest request。
   - 接入 PBC 的 `prefill_token_budget` 和 `prefill_block_margin`。
   - 已补齐 selected-batch 的 `token_fill/pad_waste/block_risk/selected_prefill_blocks/pressure_injection_prefill` 指标。
   - 已新增 `shortest-prefill` / `shortest-prompt-first` baseline。

3. **KAS 初版**
   - `distserve/decoding_stage_scheduler.py` 中实现 KV-aware attained-service decode scheduling。
   - 支持 attained-service priority、resident preference、swap budget、scan limit、skip counter。
   - 修复了 CPU swapped request swap-in 后未预留 next-token append KV block 的问题。
   - 已新增 `pure-las` 与 `kv-unaware-las` baselines。
   - 已接入可选 byte-level swap budget：`PHASESERVE_DECODE_SWAP_BUDGET_BYTES`。
   - 已补齐 `swap_byte_budget/swap_byte_budget_ratio/pressure_injection_decode_swap/policy_variant` 指标。
   - 已接入可选 workload-aware first-token gate 与诊断指标；当前默认关闭，因为 OPT-13B pilot 没有稳定收益。
   - 已接入 adaptive KAS intensity；中间输出长度区间保留 PBC 控制的强度调节。
   - 已接入 short-output FCFS-compatible gate：full `phase` 默认 `PHASESERVE_KAS_SHORT_OUTPUT_FCFS_THRESHOLD=96`，用于保护 prompt-skew 的 TTFT owner。
   - 已接入 long-output full-KAS gate：full `phase` 默认 `PHASESERVE_KAS_LONG_OUTPUT_FULL_THRESHOLD=512`，用于让 decode-heavy workload 中 KAS 接管 TPOT owner，同时避免真实 ShareGPT 上的中长输出过早 full-KAS 化。
   - 已接入 PBC-controlled handoff debt 作为可选诊断机制；当前默认关闭 `PHASESERVE_KAS_HANDOFF_DEBT=0`，因为 OPT-13B prompt-skew pilot 中它没有稳定改善 TTFT。
   - 已接入 bridge completion drain：full `phase` 默认开启 `PHASESERVE_KAS_BRIDGE_COMPLETION_DRAIN=1`，当 bridge/first-token pressure 高且 hard pressure 未触发时，优先首 token、resident、短剩余输出和可释放 KV 的请求。
   - 已接入 bridge-budgeted admission：full `phase` 默认 `PHASESERVE_KAS_BRIDGE_WAITING_BLOCK_PROP=0.20`，在 bridge-dominant 且 decode hard pressure 安全时扩大 decode waiting queue 的 KV feasibility budget，避免 prefill 已完成请求长期停在 bridge。
   - 已接入 short-output bridge fastlane：full `phase` 默认 `PHASESERVE_KAS_BRIDGE_SHORT_OUTPUT_FASTLANE=1`、`PHASESERVE_KAS_BRIDGE_SHORT_OUTPUT_THRESHOLD=128`，并通过 long-prompt debt guard 控制，默认 `PHASESERVE_KAS_BRIDGE_FASTLANE_GUARD_WAIT_S=12.0`。
   - 已关闭失败分支默认值：`PHASESERVE_KAS_BRIDGE_HOL_BYPASS=0`，bridge eviction 继续默认关闭。

4. **实验与分析脚本**
   - `scripts/run_phase_hetero_1p1d.sh`
   - `scripts/run_phase_hetero_sweep.sh`
   - `scripts/run_phase_pbc_sweep.sh`
   - `scripts/run_phase_decode_heavy_sweep.sh`
   - `benchmarks/phase_collect_summaries.py`
   - `benchmarks/phase_analyze_sweep.py`
   - `benchmarks/phase_metric_audit.py`
   - Stage 2/4B 新增字段已接入 `phase_native_benchmark.py`、`phase_collect_summaries.py`、`phase_analyze_sweep.py`。
   - Stage 4A 已把 TTFT/TPOT `p75` 接入 benchmark summary、sweep summary 和 paired/bucket analysis。

5. **指标补强**
   - TTFT/TPOT p50/p75/p90/p95/p99。
   - SLO attainment、goodput、request throughput、output token throughput。
   - prompt/output bucket breakdown。
   - PBC budget、mode switch、decode snapshot、prefill budget ratio。
   - PBC `ttft_debt_weight`、decode effective handoff debt weight。
   - short-output gate、long-output full-KAS gate、平均目标输出长度。

### 已验证

1. **早期 1p1d + LLaMA2-7B 可运行**
   - FCFS、BPS、KAS、BPS+KAS、Phase 都能跑通。
   - 该结果只作为早期调试记录；Stage 3 之后的实验模型改为 OPT-13B 和 LLaMA2-13B。

2. **BPS 方向成立**
   - prompt-skew 下，BPS 对短/中 prompt bucket 的 TTFT tail 有明显改善。
   - 但最长 prompt bucket 存在 tail transfer，论文中必须报告。

3. **KAS 方向成立**
   - decode-heavy rate2 下，KAS 相对 FCFS 的全局 TPOT p99 ratio 约 `0.537`，output token throughput ratio 约 `1.084`。
   - 主流 output buckets 的 TPOT p99 ratio 约 `0.52-0.73`。
   - `>512` output bucket 仍可能变差，需要 long-output stress。

4. **PBC 有真实消融语义**
   - `phase` vs `bps_kas` 能改变 prefill budget，并影响 TPOT/SLO。
   - decode-heavy burst 下，`phase` 相比 `bps_kas` 的 TPOT p99 ratio 约 `0.854`，SLO +`1.04 pp`。
   - 代价是 TTFT p90 +`4.886s`，说明当前 PBC 映射仍偏粗。

5. **OPT-13B W0 policy smoke 已通过**
   - 模型 `facebook/opt-13b` 已通过 `huggingface-cli` 下载到 `/root/data/models/opt-13b`。
   - `fcfs/spf/pure-las/kv-unaware-las/bps/kas/bps_kas/phase` 8 个 policy 均完成，`completed=16`, `failed=0`。
   - `summary.md/csv`、`sweep_summary.md/csv`、`sweep_analysis.md`、`sweep_analysis.bucket.md` 已生成。
   - `phase` 中 `phase_context_prefill_budget_mean=1941`、`phase_context_prefill_budget_ratio_mean=0.947754`，说明 PBC budget 在 13B smoke 中实际生效。
   - 该结果仅用于可运行性和指标链路验证，不作为论文结论。

6. **OPT-13B W2 TTFT high-rate calibration 已完成**
   - 结果目录：`/root/data/phase_scheduler_results/w2_opt13b_ttft_highrate_20260527_153750`。
   - workload：prompt-skew，prompt mix 为 `64/512/1024/1536`，output mix 为 `32/64/128`。
   - policies：`fcfs/bps/phase`，rates：total `6/8/10/12`，per-GPU 约 `3/4/5/6 req/s`，seed `0`。
   - `bps` 在 per-GPU `5/6 req/s` 的 TTFT p90 相比 `fcfs` 分别下降约 `20.6%/16.2%`。
   - 修复前 `phase` 在 rate `8/10/12` 的 TTFT p90/p99 不稳定且经常差于 `fcfs`，说明完整策略的 PBC/BPS/KAS 仲裁未过关。
   - 已完成 typed hard-pressure 修复：context 侧 PBC 只有在 swap 或 GPU free block 低于硬阈值时才强收缩 prefill budget；无硬压力时默认保留 `0.90` prefill progress floor。
   - 修复后 rate 10 的 full `phase` TTFT p90 从 `1.351s` 降到 `0.915s`，优于 FCFS 的 `1.052s`；rate 12 从 `2.298s` 降到 `2.042s`，基本持平 FCFS 的 `2.053s`。
   - 已验证 KAS workload-aware gating：threshold `0.25/0.65` 均未稳定优于默认 typed-PBC phase，当前默认关闭 `PHASESERVE_KAS_WORKLOAD_GATING`。
   - 已完成 adaptive KAS intensity 小矩阵：`bridge_discount=0.25` 是当前保守默认，能改善 rate10 的 full `phase` TTFT，但 rate12 仍有轻微回退。
   - 详见 `docs/archive/stages/stage4_w2_ttft_calibration.md`。

7. **OPT-13B Stage 4A prompt-skew metric audit 已完成**
   - 结果目录：`/root/data/phase_scheduler_results/stage4a_prompt_skew_metric_audit_opt13b_20260527_212638`。
   - workload：prompt-skew，prompt mix 为 `64/512/1024/1536`，output mix 为 `32/64/128`。
   - policies：`fcfs/bps/bps_kas/phase`，seeds：`0/1`，total rates：`8/10/12/14`，共 `32/32` runs 完成。
   - `bps` 相比 FCFS 的稳定 candidate windows：TTFT p75 rate `10/12` 平均 ratio `0.9035`，TTFT p95 rate `10/12/14` 平均 ratio `0.9159`，TTFT p99 rate `10/12/14` 平均 ratio `0.9566`。
   - full `phase` 相比 FCFS 的稳定 candidate windows：TPOT p75 rate `8/10` 平均 ratio `0.9630`，TPOT p90 rate `8/10/12` 平均 ratio `0.9351`。
   - full `phase` 相比 `bps` 的增量主要是 TPOT p90 rate `10/12` 平均 ratio `0.9364`；TTFT p50 只有 rate `8/10` 平均 ratio `0.9916`，不适合作为主图 claim。
   - 当前结论：BPS 是 prompt-skew 的 TTFT owner，full `phase` 当前更像 TPOT/SLO tradeoff controller，还不能 claim prompt-skew 下稳定降低 TTFT tail。
   - 详见 `docs/archive/stages/stage4a_prompt_skew_metric_audit.md`。

8. **Stage 2 PBC/BPS/KAS 仲裁修复已完成**
   - 修复文档：`docs/archive/stages/stage2_arbitration_fix.md`。
   - PBC 新增 `ttft_debt_weight`，用于把 first-token-limited regime 显式传给 KAS。
   - context-side PBC 新增 `PHASESERVE_PBC_FIRST_TOKEN_PREFILL_FLOOR_FRAC=1.0`，在无 hard pressure 的 `FIRST_TOKEN_LIMITED` 下不再因 soft bridge pressure 压低 BPS prefill token budget。
   - decode-side KAS 在 full `phase` 下默认启用 handoff debt，实际 `effective_handoff_debt_weight = PHASESERVE_KAS_HANDOFF_DEBT_WEIGHT * budget.ttft_debt_weight`。
   - `DECODE_HEAVY/KV_SWAP_LIMITED` 或 hard pressure 出现时，`ttft_debt_weight` 立即归零，避免影响 TPOT/KV feasibility owner。
   - 本地和远程 `py_compile` 均通过；远程 OPT-13B 8-request phase smoke 完成 `8/8`，新机制字段已进入 summary。

## 当前差距

### PBC：代码已补，效果待验证

PBC 已具备 component-wise budget mapping 和 surrogate accounting。下一步差距不再是“字段缺失”，而是要在真实 1p1d workload 中验证：

- pressure potential 是否会随 PBC 动作下降。
- `phase` 相比 `bps_kas` 是否能降低 decode/swap pressure。
- TTFT tradeoff 是否可控，而不是简单牺牲 prefill。
- `max / weighted / lexicographic` aggregation 的差异是否足以形成 sensitivity study。

### KAS：baseline 已补，长输出风险待验证

KAS 已有 `pure-las`、`kv-unaware-las`、byte-level swap budget 和 starvation/infeasible 指标。下一步要验证：

- KAS 相比 pure LAS 是否不是单纯 LAS 效应。
- KAS 相比 KV-unaware LAS 是否真正减少 swap/stall。
- long-output bucket 是否出现不可解释的 starvation 或 TPOT tail transfer。
- `PHASESERVE_DECODE_SWAP_BUDGET_BYTES` 是否需要默认开启。

### BPS：机制指标已补，prompt-skew 待验证

BPS 已输出 selected batch 的 `token_fill/pad_waste/block_risk` 和 protected-oldest 指标，并新增 SPF baseline。下一步要验证：

- BPS 相比 SPF 是否不只是“短请求优先”。
- BPS 是否降低 padding waste 或 block risk。
- prompt-skew workload 下，长 prompt 的 max queue wait 和 TTFT tail 是否受控。
- protected-oldest 触发是否带来可解释的吞吐/TPOT tradeoff。

## 下一步计划

当前处于 Stage 4L：OPT-13B + ShareGPT Layer 1 主端到端修复已经得到 seed0 连续有效区间。根据对 `related_papers/` 中 DistServe、WindServe 和 ShuffleInfer 的重新审阅，后续正式实验仍以 `docs/experiment_protocol.md` 为准：主端到端实验回到 `ShareGPT` / `LongBench` 真实长度分布，先做 DistServe-only baseline calibration，再在相同 pressure window 下比较 PhaseServe。workload 已明确分为三层：Layer 1 真实主端到端 workload、Layer 2 ShuffleInfer-style controlled regime workload、Layer 3 诊断与 stress workload。既有 mixed-wide / cross-skew / first-128 mixed-order 结果保留为 exploratory 和机制线索，不再作为唯一主实验设计来源。

当前内部优化目标仍保留为 strict 2-wide：在 Layer 1 主端到端真实 workload 上，找到至少一个长度为 `2.0 req/s/GPU`、粒度至少为 `0.5 req/s/GPU` 的连续 per-GPU rate 区间；该区间内每个点，PhaseServe 相比 DistServe 在 TTFT 的 `p50/p90/p95/p99` 中至少两个指标改善 `>=20%`，并在 TPOT 的 `p50/p90/p95/p99` 中至少两个指标改善 `>=20%`。该目标是内部收敛标准，不是预先承诺的论文 claim；若真实 workload 无法满足，需要先完成测量、pressure window、实现对齐和方法 claim 审计，再决定是否把 strict 2-wide 目标移动到 Layer 2 Mixed-pressure controlled regime 或收窄 Layer 1 claim。

下一步不应继续盲目搜索 workload 或 rate，而应按下面顺序推进：

1. Stage 4L seed 扩展：在 global rate `2.0-4.0` 主图区间补 seed1/seed2，至少形成两 seed 结果。
2. E3 消融：在代表性 pressure rate 上跑 `w/o PBC`、`w/o BPS`、`w/o KAS` 和 full PhaseServe。
3. High-rate 机制分析：解释 global rate `4.5/6.0` 为什么 TTFT 仍强但 TPOT 出现断点。
4. LLaMA2-13B 复验：在 `LLaMA2-13B + ShareGPT` 和 `LLaMA2-13B + LongBench` 上检查 bridge-budgeted KAS 默认值是否稳定。
5. E4 ShuffleInfer-style baseline：构造 LPLD/LPHD/HPLD/HPHD/Mixed，加入 same-engine length-aware prefill/decode baseline。
6. E5 机制分析：抽取 queue breakdown、pressure-to-budget timeline、bucket tail 和 KV/swap feasibility 证据。

Stage 3 已完成产物：

1. `docs/stage3_experiment_design.md`：定义 workload、policy matrix、seed、rate、SLO、指标和验收标准。
2. 1p1d + OPT-13B / LLaMA2-13B 最小验证矩阵：
   - main policies：`fcfs`、`bps`、`kas`、`bps_kas`、`phase`
   - new baselines：`spf`、`pure-las`、`kv-unaware-las`
3. workload 分层：
   - balanced sanity workload
   - prompt-skew workload for BPS
   - decode-heavy workload for KAS/PBC
   - long-output stress workload for KAS fairness
4. 指标分层：
   - end-to-end：TTFT/TPOT p50/p90/p99、SLO attainment、goodput、request throughput、token throughput
   - mechanism：pressure potential、pressure injection、budget ratio、pad waste、block risk、swap byte budget ratio、resident admission、starved admission
   - fairness：prompt/output bucket breakdown、long prompt max wait、long output TPOT tail

Stage 4 当前状态：

1. OPT-13B W0 policy smoke 已通过，详见 `docs/archive/stages/stage4_w0_smoke_triage.md`。
2. OPT-13B W1 balanced pilot 已显示 TPOT/SLO/goodput 信号，但未找到稳定 TTFT 下降区间。
3. OPT-13B W2 prompt-skew high-rate calibration 已找到 `bps` 的 TTFT p90 下降区间；full `phase` 经 typed hard-pressure 修复后在 rate 10 已优于 FCFS，但 rate 12 仍未追上 BPS。
4. LLaMA2-13B 计划使用 `NousResearch/Llama-2-13b-hf` 作为可运行 fallback，并保留官方 `meta-llama/Llama-2-13b-hf` 后台慢速下载；两者都必须在 artifact 中记录精确 repo/source。
5. 已用接入 `regime`、`decode_utility_intensity`、regime switch/intensity metrics 的版本完成 OPT-13B decode-heavy seed0/rate2 最小验证：`phase` 的 TPOT p99 ratio vs FCFS 为 `0.954`，保留了 KAS 的 p99 tail 优势；但 rate2 下 SLO attainment 全部为 `1.0`，下一步需要跑 seed1 和 rate3/rate4 找到更有区分度的区间。
6. 已完成 OPT-13B decode-heavy seed0/1、total rate3/4 小矩阵：16/16 runs 完成。跨 seed/rate 平均，`phase` 相比 FCFS 的 TPOT p50/p90/p95/p99 ratio 为 `0.9072/0.9112/0.9396/0.9110`，completed req/s 和 output tok/s ratio 为 `1.0404`；TTFT p90/p95 基本持平或小幅改善，但 TTFT p99 ratio 为 `1.0787`。当前结论是 decode-heavy regime 的主收益是 TPOT 和吞吐，不应把 TTFT p99 作为该 workload 的主要 claim。详见 `docs/archive/stages/stage4_decode_regime_validation.md`。
7. 已实现并 smoke 验证 regime-shift workload：新增按 `prefill_skew -> decode_heavy -> mixed_slo -> prefill_recovery` 顺序生成请求的 dataset/metadata 生成器，并让 benchmark 支持 per-phase arrival rate 与 `buckets.workload_phase`。OPT-13B 小规模 smoke 中 `fcfs/bps_kas/phase` 均完成，`phase` 的 PBC metrics 出现 `DECODE_HEAVY/FIRST_TOKEN_LIMITED/MIXED_SLO`，而 `bps_kas` 保持 `STATIC`。该结果仅证明链路和机制指标可用，不作为论文性能结论。详见 `docs/archive/stages/stage4_regime_shift_workload.md`。
8. 已完成 regime-shift 高压 pilot：rate scale `1.5`、seed0、每 phase 24 个请求、`fcfs/bps_kas/phase`。FCFS 的 SLO 降到 `66.7%`，说明高 rate 确实更有区分度。`phase` 相比 FCFS 的 TTFT p90/p95 ratio 为 `0.962/0.953`，SLO +`1.04 pp`；在 `mixed_slo` phase 同时改善 TTFT p90 和 TPOT p90。但 TPOT p95/p99 ratio 为 `1.085/1.075`，output throughput ratio 为 `0.946`，说明该区间已经进入明显 tradeoff。正式矩阵建议扫 `1.25/1.5/1.75`，而不是只固定一个极高 rate。
9. 已完成 OPT-13B prompt-skew Stage 4A metric audit：seed0/1、total rate `8/10/12/14`、`fcfs/bps/bps_kas/phase` 共 32 runs。`bps` 的 TTFT p75/p95/p99 windows 成立；full `phase` 的稳定窗口主要是 TPOT p90，TTFT tail 仍不稳定。下一步应先修 full `phase` 的 KAS/BPS 仲裁，再重跑最小 audit matrix。
10. 已完成 Stage 2 仲裁修复并通过远程 OPT-13B smoke。下一步 Stage 4A 应重跑 `fcfs/bps/phase`、seed `0/1`、total rate `8/10/12/14`，重点检查 full `phase` 是否同时保留 TPOT p90 window 并减少 TTFT tail transfer。
11. 已完成 Stage 4C mixed-regime OPT-13B end-to-end 验证。新增 `cross_skew_v1` workload，将 long-prompt/short-output 和 short-prompt/long-output 合并到同一请求流；修复了 `PHASE_RATE_SCALE` 未传递到 metadata rate 的脚本问题，并将 13B 默认 `GPU_MEMORY_UTILIZATION` 调整为 `0.85`。rate `2`、seed `0/1` 下，full `phase` 相比 FCFS 的平均 TTFT p90/p95 ratio 为 `0.773/0.751`，TPOT p90/p95 ratio 为 `0.803/0.902`，SLO attainment 平均 +`4.69 pp`，completed throughput ratio 为 `1.050`。rate `3` 可作为 SLO/TTFT 辅助窗口；rate `4/6` 属于 overload/tradeoff 边界。详见 `docs/archive/stages/stage4c_mixed_regime_end_to_end.md`。
12. 已完成 Stage 4C mechanism audit。新增 `remote_distserve/benchmarks/phase_mechanism_audit.py`，输出远端 `/root/data/phase_scheduler_results/stage4_mixed_regime_mechanism_audit_opt13b.md/csv`。审计显示，context 侧 `FIRST_TOKEN_LIMITED` 占比为 `98.7%-99.9%`，但 prefill budget ratio 维持约 `0.999`；decode 侧 rate `2` 的 `DECODE_HEAVY` share 平均 `73.3%`，selected effective KAS intensity 平均 `0.939`。这支持 mixed-regime 中 BPS 负责 TTFT、KAS 负责 TPOT 的机制解释。TPOT p99 不稳定集中在部分中长 output buckets，应作为 tradeoff 指标报告。详见 `docs/archive/stages/stage4c_mechanism_audit.md`。
13. 已完成 Stage 4C mixed-regime 组件消融。结果目录：`/root/data/phase_scheduler_results/stage4c_mixed_regime_ablation_opt13b_20260528_145013`。OPT-13B、1P1D、`cross_skew_v1`、`fcfs/bps/kas/bps_kas/phase`、rate `2/3`、seed `0/1` 共 `20/20` runs 完成。消融显示，`bps` 单独更偏 TTFT 但会伤 TPOT，`kas` 单独更偏 TPOT 但会伤 TTFT，静态 `bps_kas` 有部分 balance，但 full `phase` 在 rate `2/3` 均进一步改善 SLO、goodput、TTFT tail 和 TPOT p90。rate `2` 下 full `phase` 相比 FCFS 的 TTFT p50/p90/p95/p99 下降 `46.96%/19.43%/23.09%/44.01%`，TPOT p50/p90/p95/p99 下降 `14.52%/18.37%/11.03%/2.50%`。详见 `docs/archive/stages/stage4c_mixed_regime_ablation.md`。
14. 已完成 Stage 4C TPOT-focused exploration。结果目录：`/root/data/phase_scheduler_results/stage4c_tpot_rate_finesweep_opt13b_20260528_155734` 和 `/root/data/phase_scheduler_results/stage4c_tpot_cross_decode_opt13b_20260528_155734`。`cross_skew_v1` rate `2.5/3.5` 共 `8/8` runs 完成，`cross_decode_v1` rate `2/2.5/3` 共 `18/18` runs 完成。结论是 rate `2.5` 可作为 TPOT 辅助窗口：full `phase` 相比 FCFS 的 TPOT p90/p95 下降 `15.12%/11.96%`，TTFT p90/p95 下降 `14.15%/14.07%`，SLO +`4.69 pp`，goodput +`10.77%`。更 decode-heavy 的 `cross_decode_v1` 只稳定改善 TPOT p50/p90，TPOT p95/p99 变差，适合作为 stress/boundary 而不是主结果。详见 `docs/archive/stages/stage4c_tpot_exploration.md`。
15. 已完成 Stage 4D 13B mixed-wide 双模型汇总与主图草稿。OPT-13B 和 LLaMA-13B 均使用 1P1D、mixed-wide workload、seed `0/1`、per-GPU rate `1/2/3/4/5/6/8/10/12`，并将主 SLO 更新为 `TTFT<=5s, TPOT<=0.12s`。Phase 相比 FCFS 在 OPT-13B 上平均 SLO +`17.5 pp`、TTFT p90 -`29.0%`、TPOT p50/p90 -`47.7%/-21.1%`；在 LLaMA-13B 上平均 SLO +`17.8 pp`、TTFT p90 -`31.2%`、TPOT p50/p90 -`46.1%/-18.0%`。主图按 TTFT/TPOT 分列：TTFT 使用 per-GPU `2/3/4/5/6/8`，TPOT 使用 per-GPU `2/3/4/5/6/8/10/12/14/16`；SLO 使用 scale sensitivity，避免固定 SLO rate-sweep 的平线问题。详见 `docs/archive/stages/stage4d_13b_mixed_wide_summary.md`。
16. 已完成 TPOT high-rate pilot 与确认矩阵。结果目录：pilot 为 `/root/data/phase_scheduler_results/stage4d_opt13b_tpot_highrate_pilot_20260529_115851`，确认矩阵为 `/root/data/phase_scheduler_results/stage4d_tpot_highrate_confirm_20260529_135452`。合并两个 seed 后，per-GPU `14/16` 上 OPT-13B 的 TPOT p90 分别下降 `26.0%/21.2%`，LLaMA-13B 分别下降 `26.6%/20.3%`。seed-level TPOT p50/p90 全部为正，但 seed1 的 TTFT p90 明显退化，因此 high-rate 点只用于 TPOT pressure 展示，不用于 TTFT 主 claim。详见 `docs/archive/stages/stage4d_tpot_highrate_pilot.md`。
17. 已完成方法论-代码对齐审计。当前代码已经实现核心 PBC/BPS/KAS，并包含由实验反推的 regime ownership、output-tail eligibility 和 hard-pressure-first 仲裁；主要 gap 转为 claim 收窄、最终消融和机制证据同步。详见 `docs/methodology_code_alignment.md`。
18. 已完成 E2B OPT-13B + ShareGPT broad rate stress sweep。结果目录：`/root/data/phase_scheduler_results/e2b_opt13b_sharegpt_broad_20260529_185758`。seed0、64 requests、`fcfs/phase`、global rate `1/2/4/6/8/10/12/16/20/0` 全部完成。当前最干净综合点是 per-GPU `1`：SLO +`6.2 pp`，TTFT p90 -`4.0%`，TPOT p90/p95/p99 -`56.6%/-68.9%/-77.5%`，goodput +`11.3%`。per-GPU `3-6` 更像 TPOT/压力边界辅助区，per-GPU `8-10` 和 burst 属于过载/stress 区。详见 `docs/archive/stages/stage4g_broad_rate_stress.md`。
19. 已完成 E2B LLaMA2-13B + ShareGPT per-GPU `1/2/3/4/5` 粗粒度复查。结果目录：`/root/data/phase_scheduler_results/e2b_llama13b_sharegpt_pergpu1to5_20260529_201651`。seed0、64 requests、`fcfs/phase`、global rate `2/4/6/8/10` 全部完成。Phase 在 per-GPU `3/4/5` 开始持续改善 SLO 和 goodput；其中 per-GPU `4` 最干净，SLO +`7.8 pp`，goodput +`24.9%`，TTFT p50/p90/p95/p99 全部下降，TPOT p50/p90/p95 下降。TPOT p99 仍不稳定，后续正式主图不应把 TPOT p99 作为主要 positive claim。详见 `docs/archive/stages/stage4g_broad_rate_stress.md`。
20. 已完成 OPT-13B + ShareGPT Phase512 修复。诊断显示 old `phase` 在真实 ShareGPT 上的 TTFT tail 问题来自 KAS 对中长输出过早 full 接管，导致 bridge/context 反压放大。已将 full Phase 的 `PHASESERVE_KAS_LONG_OUTPUT_FULL_THRESHOLD` 默认值从 `192` 调整为 `512`。seed0/1 在 per-GPU `1/2/3/4/5` 的两 seed 平均结果均显示 TTFT p90/p95/p99、TPOT p90/p99、SLO 和 goodput 同时改善；其中 per-GPU `2` 的 SLO +`3.9 pp`，TTFT p90/p95/p99 下降 `27.3%/68.3%/45.0%`，TPOT p90/p95/p99 下降 `19.3%/6.8%/13.4%`，goodput +`11.1%`；per-GPU `4/5` 作为 high-pressure extension，goodput 分别 +`12.3%/+18.4%`。详见 `docs/archive/stages/stage4h_opt_sharegpt_phase512_repair.md`。
21. 已完成 OPT-13B + ShareGPT 128-request TPOT 诊断和 KAS bridge 修复。结果目录包括 `/root/data/phase_scheduler_results/opt13b_sharegpt_tpot_diag128_20260529_224028`、`/root/data/phase_scheduler_results/opt13b_sharegpt_conflict_first128_r140c_20260530_1010`、`/root/data/phase_scheduler_results/opt13b_sharegpt_conflict_first128_r15_20260530_100008`、`/root/data/phase_scheduler_results/opt13b_sharegpt_conflict_first128_r15_seed1_20260530_1015`。诊断显示 early Phase 在 global rate `1.5` 出现 decode queue 被清空、bridge/unaccepted queue 积压的 pressure transfer，导致 TTFT tail 变差。最终修复包括：KAS `starved` primary、bridge-dominant eviction、PBC `FIRST_DECODE_CONFLICT_POLICY=first`、KAS bridge completion drain，并关闭失败的 HOL bypass / short-output fastlane 默认值。seed0 global rate `1.5` 的 final `phase` 相比 FCFS 同时改善 TTFT p50/p90/p95/p99 `5.3%/4.4%/6.2%/10.3%`、TPOT p50/p90/p95/p99 `19.6%/34.3%/18.8%/48.3%`，SLO 从 `59.4%` 提升到 `71.1%`，goodput +`13.9%`；seed1 global rate `1.5` 进一步改善 TTFT p50/p90/p95/p99 `7.0%/1.2%/0.1%/7.3%`，TPOT p50/p90/p95/p99 `3.9%/23.1%/38.2%/27.0%`，SLO +`1.56 pp`。下一步需要扩 `1.40/1.50` 的 seed/rate，并决定端到端主图的 percentile 选择。详见 `docs/archive/stages/stage4i_tpot_diagnostic_and_kas_bridge_repair.md`。
22. 已完成最终默认代码的 OPT-13B + ShareGPT 128-request per-GPU `1-5` 两 seed 复测。结果目录：`/root/data/phase_scheduler_results/opt13b_sharegpt_final128_pergpu1to5_20260530_111232`。两 seed 平均显示 per-GPU `1` 是最干净正向窗口：SLO +`8.2 pp`，goodput +`0.075 req/s`，TTFT p50/p90/p95/p99 下降 `36.3%/34.6%/30.8%/26.5%`，TPOT p50/p90/p95/p99 下降 `7.1%/14.5%/29.7%/3.6%`。per-GPU `2-4` 已进入明显过载，Phase 仍改善 TTFT tail 和 TPOT p95/p99，但 SLO/goodput/TPOT p90 不总是提升；per-GPU `5` 属于 overload/failure-boundary。结论是 Stage 4H 的 64-request per-GPU `1-5` 不能直接作为最终主图区间，后续主图应围绕 per-GPU `0.75/1.0/1.25/1.5` 细扫。详见 `docs/archive/stages/stage4j_opt_sharegpt_final128_pergpu1to5.md`。
23. 已完成 OPT-13B + ShareGPT first-128 mixed-order 端到端窗口验证。新增 `remote_distserve/benchmarks/phase_make_sharegpt_mixed_order.py`，保持 ShareGPT first `128` 请求集合不变，只交错 long-prompt、long-output、short-prompt/long-output 请求来构造 mixed pressure。KAS completion-aware 默认值已更新为 `PHASESERVE_KAS_BRIDGE_COMPLETION_PRESSURE=0.0`、`PHASESERVE_KAS_BRIDGE_COMPLETION_REMAINING=0`。在 global rate `1.9`，两 seed 平均 TTFT p90/p95/p99 下降 `53.5%/67.5%/67.7%`，TPOT p90/p95/p99 下降 `27.7%/27.9%/25.4%`；在 global rate `2.0`，两 seed 平均 TTFT p90/p95/p99 下降 `79.7%/74.8%/46.8%`，TPOT p90/p95/p99 下降 `26.1%/22.4%/20.2%`。global rate `2.1` 的 TTFT 仍强，但 TPOT 只剩 p95 超过 20%，因此当前主 positive window 是 global `1.9-2.0`（per-GPU `0.95-1.0`）。同时已按更严格的 “Per-GPU rate 区间长度为 2、粒度 0.5” 检查 per-GPU `0.5/1.0/1.5/2.0/2.5`，seed0 即显示该 strict 2-wide 目标未达成：低 rate TTFT 无压力，高 rate TPOT/TTFT tail 不能同时保持两个指标超过 20%。详见 `docs/archive/stages/stage4k_opt_sharegpt_mixed_order_window.md`。

## 当前风险判断

目前 Stage 4D 已经证明 full Phase 在双 13B mixed-regime workload 上有端到端收益。主要风险从“方法是否有效”转为“论文 claim 是否足够精确、机制证据是否足够硬”：

1. Stage 4D 主结果支持 SLO、TTFT p90、TPOT p50/p90；不支持所有 percentile 全面提升。
2. TPOT p95/p99 和高压 TTFT p95 仍存在 tradeoff，不能作为主图核心 claim。
3. Stage 4C 已有 OPT-13B 消融，但 Stage 4D 最终口径下还需要补代表性消融，证明 PBC/BPS/KAS 在新 SLO 和双模型下仍有可区分贡献。
4. BPS/KAS 的机制指标需要同步到 Stage 4D 口径，尤其是 prompt/output bucket、budget ratio、KAS intensity 和 pressure potential。
5. throughput 平均为正但不稳定，应作为辅助指标而不是主要贡献。
6. LLaMA-13B 本轮使用 ModelScope 镜像来源，artifact 中必须明确记录模型来源，避免和官方 gated repo 混淆。
7. 当前仍是 1P1D，后续若要扩大系统 claim，需要补更多 P/D 配比或多副本结构。
8. 后续论文 claim 必须按模型、workload、rate 区间和 percentile 明确表达，不能写成所有压力点、所有分位全面提升。
9. OPT-13B + ShareGPT 128-request 诊断暴露出的 bridge/unaccepted pressure transfer 已通过 conflict-first PBC 与 KAS bridge completion drain 初步修复，并已有 seed1 rate `1.5` 复验；当前风险转为扩 seed/rate 和图表 claim 收窄，而不是默认策略仍会秒级恶化。
10. OPT-13B + ShareGPT 128-request 的 per-GPU `1-5` 复测显示，最终代码的最干净正向窗口集中在 per-GPU `1` 附近；per-GPU `2-5` 在 128-request 下已经是过载压力扫描，不能按 64-request Phase512 旧表解释为同质主图区间。
11. first-128 mixed-order trace 已经给出 TTFT/TPOT 同窗口改善，但它是 ShareGPT-derived arrival-order workload，不是原始 first-order trace；论文中必须把它表述为 mixed-pressure trace，并补 LLaMA2-13B 复验与 KAS completion-aware drain 消融。
