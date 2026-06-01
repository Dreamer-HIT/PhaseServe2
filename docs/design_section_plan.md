# PhaseServe Design Section Plan

Updated: 2026-06-01

本文档用于约束 PhaseServe 论文中 `PhaseServe Design` 部分的重写。它不是正文草稿，而是写作契约：先固定 Design section 的论证顺序、图表角色、术语边界和 claim-evidence map，再进入 `paper/PhaseServe.tex` 的正式改写。

## 写作目标

Design 部分要让读者在进入 Evaluation 前理解三件事：

1. PhaseServe 解决的是 phase-disaggregated serving 中的 runtime pressure propagation，而不是重新做资源规划、KV architecture 或全局 placement。
2. PhaseServe 的方法闭环是 `PBC -> typed budgets/regime owner -> BPS/KAS budgeted actions -> pressure feedback`。
3. PBC、BPS 和 KAS 是同一个 pressure-budgeted phase scheduling 框架中的三个角色，而不是 backpressure、bucket batching 和 LAS/MLFQ 的简单拼接。

一句话论证：

> PhaseServe is a pressure-budgeted phase scheduler for disaggregated LLM serving: it converts runtime bridge, first-token, decode, KV, and swap pressure into typed budgets and regime ownership, then applies budgeted prefill shaping and KV-feasible decode active-set shaping to reduce regime-local latency bottlenecks.

中文等价表述：

> PhaseServe 是一个面向解耦式 LLM serving 的压力预算调度器：它把 bridge、first-token、decode、KV 和 swap pressure 转化为 typed budgets 和 regime owner，再用受预算约束的 prefill shaping 与 KV 可行的 decode active-set shaping 降低当前 workload regime 的瓶颈延迟。

## Skill-Derived Writing Rules

按 algorithmic systems paper 的写作规则，Design 部分必须分清：

| 内容 | Design 中的角色 | 禁止混入 |
|---|---|---|
| What the system is | PBC/BPS/KAS 的接口、状态、输入输出、控制循环 | 端到端 speedup 结果 |
| Why it works | pressure-budget graph、regime ownership、hard feasibility gates、bounded progress | 没有机制支撑的泛化 claim |
| How well it works | 只作为 ablation hook 和 Evaluation preview | 具体结果数字和精选窗口 |
| Boundary | 不做全局 placement、不改 KV cache architecture、不承诺所有 percentile/rate 提升 | universal superiority |

每个模块使用三段式：

1. **Motivation**：该模块解决什么局部失败模式。
2. **Mechanism**：该模块每轮实际读什么状态、输出什么动作。
3. **Evidence hook**：Evaluation 中哪个消融或机制信号验证它。

## Related-Papers Patterns To Reuse

| Paper | 可借鉴模式 | PhaseServe 对应做法 |
|---|---|---|
| DistServe | 先用 tradeoff/motivation 建立 disaggregation 的必要性，再给 runtime architecture 和 algorithms。Evaluation 图使用 per-GPU rate 与 SLO scale 双视角。 | Background/Motivation 可承接 DistServe：资源解耦已解决直接 interference，但 runtime pressure propagation 仍存在。Design 不重复 placement algorithm。 |
| WindServe | Design 从 overview figure 开始，然后逐个解释 scheduler、trigger、mechanism 和 tradeoff。机制图使用 timeline 解释为何某策略同时影响 TTFT/TPOT。 | PhaseServe Overview 图放在 Design 开头；PBC/BPS/KAS 写成触发条件、预算动作和 tradeoff，而不是泛泛说“优化调度”。 |
| ShuffleInfer | Figure 6 把 existing systems 与 new architecture 放在一张图中，帮助读者理解系统差异；Design 开头用 pillars 概括方法。 | PhaseServe Figure 1 可采用左侧 DistServe-style pressure propagation、右侧 PhaseServe pressure-budget loop 的对比式结构。 |

## Design Section Outline

建议将 `paper/PhaseServe.tex` 中当前 `PhaseServe Design` 整段重写为以下结构。

### 3.1 Overview

目的：用一页内的文字和 Figure 1 建立完整闭环。

内容顺序：

1. 定义 PhaseServe：a pressure-budgeted phase scheduler for phase-disaggregated LLM serving。
2. 说明它运行在 DistServe-style disaggregated runtime 之上，不负责 placement 或模型并行搜索。
3. 给出三组件：
   - PBC observes pressure and emits typed budgets/regime ownership.
   - BPS consumes prefill budgets for known-size batch shaping.
   - KAS consumes decode/KV budgets for unknown-size active-set shaping.
4. 解释 control loop：observe pressure, compute budget, execute budgeted actions, feed back pressure.

建议图：Figure 1。

### 3.2 Pressure-Budget Formulation

目的：把方法从 heuristic 组合提升为统一问题定义。

需要定义：

| Symbol / term | Meaning |
|---|---|
| `p(t)` | pressure vector: context, bridge, first-token, decode backlog, KV, swap, age/skip pressure |
| `b(t)` | typed budget vector: prefill token budget, prefill block margin, decode scan limit, swap budget, bridge budget, decode utility intensity |
| `regime(t)` | bottleneck owner: context-limited, bridge/first-decode-limited, decode-heavy, KV/swap-limited, mixed |
| `A_phase(b(t))` | feasible action set under current typed budgets |
| `Phi(t)` | pressure-drift surrogate used for diagnostics, not a formal optimality guarantee |

Current paper status: `p(t)` now includes context pressure, and the
first-token-limited family is explicitly split into context-limited ownership
(BPS) and bridge/first-decode ownership (KAS). This avoids the earlier ambiguity
where BPS was described as the sole TTFT owner even when the bottleneck was
bridge or first-decode admission.

关键句：

> Unlike ordinary backpressure, PBC does not only decide whether to admit more work; it decides which action space to shrink.

这一节不放具体性能结果，只定义可观测对象和控制目标。

### 3.3 PBC: Regime-Aware Pressure-Budget Controller

目的：解释 PhaseServe 的核心非平凡性。

模块三段式：

| Part | Content |
|---|---|
| Motivation | 独立优化 prefill utilization 或 decode LAS 会把 pressure 转移到 bridge、KV 或 swap。需要统一 controller 决定收缩哪个动作空间。 |
| Mechanism | 读取 pressure vector，归一化 pressure，判断 regime/conflict owner，映射 typed budgets，做 hysteresis/smoothing，输出 budget object。 |
| Evidence hook | Stage 4P `w/o PBC`；机制信号包括 regime shares、budget movement、bridge queue、pressure potential、swap/infeasible rounds。 |

必须写清楚：

1. typed pressure-budget dependency graph。
2. conflict arbitration order。
3. first-token vs decode-tail 冲突时的 owner 选择。
4. PBC 是 online control contract，不声称全局最优。

### 3.4 BPS: Budgeted Prefill Shaping

目的：解释 prefill 侧为什么不是普通 shortest-prompt-first 或 bucket batching。

模块三段式：

| Part | Content |
|---|---|
| Motivation | Prefill cost before execution is known but highly skewed; naive FCFS causes HOL blocking, pure size-aware batching may inject too much KV footprint into decode. |
| Mechanism | 在 PBC 的 token/block budgets 下，从 bounded candidate window 中选择 cost-compatible batch；使用 token-fill、padding waste、block risk、oldest progress。 |
| Evidence hook | Stage 4P `w/o BPS`；机制信号包括 selected prefill tokens、pad waste、protected dispatch ratio、context queue time、TTFT p50/p90。 |

必须写清楚：

1. BPS 优化 TTFT/prefill queue，不单独声明 TPOT 全面提升。
2. protected oldest 可以保护 progress，但不绕过 physical feasibility。
3. PBC budget 收紧时 BPS 降低 pressure injection，而不是只做长度排序。

### 3.5 KAS: KV-Feasible Decode Active-Set Shaping

目的：解释 decode 侧为什么不是普通 LAS/MLFQ。

模块三段式：

| Part | Content |
|---|---|
| Motivation | Decode output length is unknown; LAS 可以保护短请求，但如果不考虑 KV/swap feasibility，可能增加 iteration stall 和 swap pressure。 |
| Mechanism | 每轮先通过 hard feasibility gates，再在可行集合中按 attained service、resident preference、swap cost、skip fairness、decode utility intensity 排序。 |
| Evidence hook | Stage 4P `w/o KAS`；机制信号包括 resident ratio、swap bytes、infeasible rounds、bridge completion drain active ratio、TPOT p90/p95。 |

必须写清楚：

1. hard feasibility gates 在 soft priority 之前。
2. short-output workload 中 KAS 可退化为 FCFS-compatible decode，避免抵消 BPS 的 TTFT 收益。
3. bridge completion drain 是 first-token-limited regime 下的 decode-side action，目标是释放 KV footprint 和 first-decode path，不是无条件 aggressive LAS。
4. TPOT p99 不作为 universal main claim。

### 3.6 Putting PBC, BPS, and KAS Together

目的：把三个模块重新合成系统方法。

内容顺序：

1. 给出每个 scheduling iteration/control epoch 的执行顺序。
2. 说明 PBC budget object 如何被 BPS 和 KAS 同时消费。
3. 说明复杂度和实现开销：低成本 pressure signals、bounded candidate scan、无 heavyweight predictor。
4. 说明与 DistServe 的集成边界：保留 DistServe disaggregation 和 placement；替换/扩展 runtime schedulers。

当前正文采用两个 algorithm blocks：Algorithm 1 给出 PBC 的 pressure-to-budget
controller with owner assignment，Algorithm 2 联合给出 BPS/KAS 如何消费同一个
budget object，并显式说明 empty feasible set / hard-feasibility stall fallback。

### 3.7 Design Boundaries

目的：提前收住 claim，避免审稿人误解。

必须声明：

1. PhaseServe does not solve cluster-level placement.
2. PhaseServe does not require exact output-length prediction.
3. PhaseServe does not introduce a new KV cache architecture.
4. PhaseServe targets pressure windows where prefill/decode/KV pressure propagation is observable.
5. PhaseServe does not claim all-rate or all-percentile dominance.

## Figure Plan

Design 主文使用两张图。

Current status: both figures have been regenerated with the image model and
inserted into `paper/PhaseServe.tex`. The active pair fixes the previous
baseline BPS/KAS mislabeling and makes the PBC budget-mechanism mapping match
the typed table. Earlier Python/Matplotlib mechanism drafts remain only as
superseded internal references.

### Figure 1: PhaseServe Overview and Pressure-Budget Loop

结论：PhaseServe is a closed-loop pressure-budgeted scheduler rather than a static phase-disaggregated runtime.

推荐 layout：full-width two-panel figure。

| Panel | Content | Visual role |
|---|---|---|
| (a) DistServe-style disaggregated runtime with pressure propagation | Prefill queue, bridge/unaccepted queue, decode queue, KV blocks; arrows showing prefill injection causing bridge/decode/KV pressure. | 说明解耦后仍有 pressure propagation。 |
| (b) PhaseServe pressure-budget loop | Pressure sensors -> PBC -> typed budgets/regime owner -> BPS/KAS -> pressure feedback. | 说明 PhaseServe 的闭环方法。 |

视觉要点：

- 使用少量颜色区分 pressure signals、budget knobs、execution policies。
- 不画旧版 global phase controller / KV-state manager 作为主角。
- 箭头上直接标注 budget 类型，例如 `prefill_token_budget`、`block_margin`、`decode_utility_intensity`、`swap_budget`。
- Caption 要写清楚：left shows the remaining problem; right shows the control contract.

### Figure 2: Budgeted Execution Mechanisms

结论：PBC, BPS, and KAS form one coupled action-space control system.

推荐 layout：full-width three-panel figure。

| Panel | Content | Visual role |
|---|---|---|
| (a) PBC typed pressure-budget graph | pressure nodes to budget knobs to constrained actions. | 区分 PBC 和普通 backpressure。 |
| (b) BPS known-size prefill shaping | candidate window, prompt buckets, token/block budget, protected oldest. | 区分 BPS 和普通 bucket batching。 |
| (c) KAS KV-feasible active-set shaping | ready decode requests, hard feasibility gate, resident/swap filters, attained-service ordering, bridge completion drain. | 区分 KAS 和 LAS/MLFQ。 |

视觉要点：

- 不把所有公式塞进图里，图只展示 decision path。
- KAS panel 要明确 hard gate 在 priority ranking 之前。
- BPS panel 要明确 PBC budget 收缩会改变 batch scoring/feasible set。
- 图内只呈现机制；`w/o PBC`、`w/o BPS`、`w/o KAS` 等 evaluation hooks 放在正文或 caption 中连接，不放入 Design 机制图主体。

Current figure artifacts:

| Figure | Current artifact |
|---|---|
| Figure 1 overview | `results/figures/mechanism/phaseserve_overview_imagegen.png` |
| Figure 2 mechanisms | `results/figures/mechanism/phaseserve_budget_mechanisms_imagegen.png` |

## Claim-Evidence Map

| Claim in Design | Evidence source | Status |
|---|---|---|
| PBC provides a typed pressure-to-budget interface rather than binary backpressure. | `docs/methodology.md`, implementation alignment, Stage 4P `w/o PBC`. | Supported as method/code claim; mechanism plot still useful. |
| BPS improves prefill-side known-size shaping under dynamic pressure budgets. | Stage 4P `w/o BPS`, TTFT p50/p90 windows, selected-token/pad-waste diagnostics if available. | Supported for latency; mechanism diagnostics should be extracted before final text if possible. |
| KAS improves decode active-set shaping under KV/swap feasibility. | Stage 4P `w/o KAS`, TPOT p90/p95 windows, resident/swap/infeasible diagnostics if available. | Supported for p90/p95; avoid universal p99 claim. |
| Full PhaseServe improves regime-local end-to-end latency over DistServe. | Stage 4O E2E matrix and Stage 4Q candidate plots. | Supported for selected windows; final figure windows still need confirmation. |
| PhaseServe is compatible with DistServe-style disaggregation. | Implementation on `/root/data/DistServe`; methodology-code alignment. | Supported. |
| PBC optimizes a formal global objective. | None. | Do not claim. Use online control contract / pressure-drift surrogate only. |

## Existing TeX Replacement Notes

Historical note: older versions of `paper/PhaseServe.tex` contained a previous method story:

- global phase controller;
- phase-specific load estimation;
- routing and topology-aware handoff;
- utility-aware prefill without PBC budget coupling;
- MLFQ-style decode with proactive KV-state manager;
- placeholder architecture figure.

These concepts should not return as the main Design narrative unless they are reframed as implementation background. The new Design section should keep PBC/BPS/KAS as the central story. In particular:

| Current text pattern | Rewrite direction |
|---|---|
| `global phase controller` | `PBC: regime-aware pressure-budget controller` |
| `routing and topology-aware handoff` | Move out of Design or omit unless directly implemented/evaluated. |
| `utility-aware batch construction` | Recast as BPS under PBC token/block budgets. |
| `MLFQ-based decode scheduling` | Recast as KAS: intensity-controlled, KV-feasible, attained-service active-set shaping. |
| `KV-state manager` as a standalone main component | Treat KV state as observed feasibility state used by KAS, not as the central contribution. |

## Proposed Writing Order

1. Draw rough Figure 1 and Figure 2 sketches. Current status: done and replaced
   with vector figures.
2. Rewrite `PhaseServe Design` around the outline in this document. Current
   status: done, with PBC ownership repair.
3. Add algorithm blocks for PBC, BPS, and KAS only after the prose stabilizes.
   Current status: done as two compact algorithms in `paper/PhaseServe.tex`
   (`alg:pbc` and `alg:budgeted-executors`).
4. Recompile with `make view` and inspect figure placement. Current status:
   compile succeeds; warnings are non-blocking layout/package warnings.
5. Run independent agent re-review and then a full claim-evidence audit before
   treating the section as stable.

## Acceptance Criteria

The Design section is ready for the next stage when:

1. A reader can explain PhaseServe in one sentence as pressure-budgeted phase scheduling.
2. PBC, BPS, and KAS each have motivation, mechanism, and evaluation hook.
3. The two Design figures each carry one clear visual argument.
4. No paragraph claims unverified all-rate/all-percentile superiority.
5. The section no longer presents global placement, topology-aware routing, or standalone KV manager as the central contribution.
6. The Design text can be mapped to `docs/methodology_code_alignment.md` without a major method-code gap.
7. An independent reviewer-style agent has re-checked PBC ownership semantics,
   hard-vs-soft KV/swap treatment, algorithm fallback behavior, and figure
   clarity after the latest repair.
