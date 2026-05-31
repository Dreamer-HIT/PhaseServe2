# PhaseServe Methodology-Code Alignment

## 本文档目标

本文档记录当前方法论、代码实现和实验 claim 之间的对齐状态。它不是论文正文，而是项目内部的控制文档，用来避免后续出现三类问题：

1. 方法论写得过强，但代码没有实现。
2. 代码里有效的机制没有上升为方法论语言。
3. 实验结果只支持局部 claim，却被写成全局提升。

当前结论：

> PhaseServe 的核心机制已经在代码中实现，并且代码包含若干由实验反推出来的保守仲裁机制。现在的主要 gap 不是“没有实现方法论”，而是需要把代码中的有效机制重新抽象成方法论，并把论文 claim 绑定到已验证的 workload、rate 和 percentile。

## 当前方法论一句话

PhaseServe 是一个 pressure-budgeted phase scheduling 方法：

1. PBC 观测 runtime pressure。
2. PBC 将 pressure 映射为 typed admission budget、regime 和 utility intensity。
3. BPS 在 prefill 侧按 budget 做 known-size batch shaping，主要负责 TTFT。
4. KAS 在 decode 侧按 budget 做 unknown-size KV-constrained active-set shaping，主要负责 TPOT 与 KV/swap safety。
5. full PhaseServe 的收益来自 regime ownership arbitration，而不是简单叠加 BPS 和 KAS。

## 代码中已经实现的核心机制

### PBC

代码已经实现：

1. component pressure vector：bridge、first-token、decode、KV、swap。
2. typed budget vector：prefill token budget、prefill block margin、decode scan limit、decode swap budget、decode utility intensity。
3. regime classification：first-token-limited、decode-heavy、KV/swap-limited、mixed-SLO 等。
4. pressure potential、pressure injection、goodput capacity、progress debt 等 surrogate 指标。
5. smoothing / hysteresis / budget floor，避免 pressure 噪声导致 budget 抖动。

需要注意：

1. PBC 当前是在线控制器和 surrogate mapping，不是严格求解全局优化问题。
2. `goodput_capacity` 和 `progress_debt` 是解释性/诊断性指标，不应写成理论 guarantee。
3. 当前实验支持 PBC 的动态仲裁价值，但最终消融还需要在 Stage 4D 口径下补代表性 rate。

### BPS

代码已经实现：

1. bounded-window request candidate selection。
2. prompt bucket / cost-compatible prefill batching。
3. token fill、padding waste、block risk、oldest bonus scoring。
4. PBC `prefill_token_budget` 和 `prefill_block_margin` 作为硬 feasibility gate。
5. protected-oldest 机制，避免长 prompt 永久被跳过。

需要注意：

1. BPS 的核心 claim 是降低 TTFT，而不是独立提升所有端到端指标。
2. BPS 单独使用可能把压力转移到 decode 侧，导致 TPOT tail 变差。
3. 论文需要报告 prompt bucket / long-prompt fairness，否则 BPS 容易被看成普通 size-aware batching。

### KAS

代码已经实现：

1. attained-service priority。
2. resident preference。
3. starvation / skip counter。
4. GPU block、swap count、swap bytes 的硬 feasibility gate。
5. PBC-controlled `decode_utility_intensity`。
6. short-output FCFS-compatible gate。
7. long-output full-KAS gate。
8. optional handoff-debt diagnostic path。

需要注意：

1. KAS 的核心 claim 是 TPOT p50/p90、decode-side fairness 和 KV/swap feasibility。
2. 当前结果不支持把 TPOT p95/p99 写成稳定主收益。
3. short-output gate 和 long-output gate 不是额外 trick，而是 KAS 是否接管 decode utility 的 eligibility 条件。

## 代码比旧方法论更成熟的地方

代码中有几类机制是通过实验暴露出来的，应该回写到方法论语言中。

### Regime ownership

旧表达容易被理解为 PBC 同时压所有 pressure。当前代码更准确：

| regime | primary owner | code behavior |
|---|---|---|
| first-token / prompt-skew | BPS | 保留 prefill progress floor，避免 KAS aggressive 重排破坏 TTFT |
| decode-heavy | KAS | 提高或恢复 decode utility intensity，优先处理 TPOT owner |
| KV/swap-limited | hard feasibility | 优先执行 GPU block / swap budget gate |
| mixed-SLO | PBC | 在 BPS 与 KAS 之间做平滑仲裁 |

方法论应该以 regime ownership 为核心，而不是说 BPS/KAS 无条件同时增强。

### Output-tail eligibility

当前代码会根据输出长度区间改变 KAS 接管强度：

1. short-output：KAS 退化为 FCFS-compatible decode，保护 TTFT。
2. middle-output：KAS intensity 由 PBC pressure 连续控制。
3. long-output：恢复 full KAS，保护 TPOT。

这个机制能解释为什么 PhaseServe 在 mixed-regime 下同时改善 TTFT p90 和 TPOT p50/p90。它也解释了为什么极端 decode-heavy workload 下 TPOT p95/p99 仍可能出现 tail transfer。

### Hard pressure before soft utility

当前代码不是把所有 pressure 线性混合，而是让 KV/swap hard constraint 优先：

1. GPU block 不足时，admission feasibility 先拒绝。
2. swap count / swap byte budget 不足时，decode admission 先拒绝。
3. 没有 hard KV/swap pressure 时，不应过度压缩 prefill budget。

这个规则避免了早期 full Phase 在 prompt-skew 下过度牺牲 TTFT。

## 仍然存在的 gap

### Gap 1：PBC 理论表达不能写成严格优化器

方法论中的 pressure potential 和 SLO goodput objective 是设计目标与分析视角。当前代码没有求解一个显式全局优化问题，而是实现了低开销在线控制。

影响：

1. 不影响当前实验效果。
2. 如果论文写成 formal optimizer，会降低可信度。
3. 应写成 typed control contract / online budget mapping。

处理：

1. 在方法论中使用 surrogate objective。
2. 实验报告 `Phi(t)`、budget movement、regime share、SLO goodput。
3. 避免使用 optimal、guarantee 这类强词，除非有证明。

### Gap 2：BPS 机制证据需要补最终口径

代码实现了 BPS，但 Stage 4D 主结果主要报告端到端 TTFT/TPOT/SLO，还没有把 BPS 的 bucket-level 机制证据同步到最终口径。

影响：

1. 不影响 full Phase 端到端结果。
2. 会影响 BPS 作为独立组件的说服力。
3. 容易被看成 size-aware batching。

处理：

1. 补 representative rates 的 prompt bucket breakdown。
2. 报告 selected token fill、pad waste、block risk、protected-oldest ratio。
3. 消融对比 `fcfs`, `spf`, `bps`, `phase`。

### Gap 3：KAS 的 high-tail claim 需要收窄

代码实现了 KAS 的 hard feasibility 和 adaptive intensity，但当前结果主要支持 TPOT p50/p90，不支持 TPOT p95/p99 稳定改善。

影响：

1. 会影响“降低 TPOT tail”这个表述的强度。
2. 如果主图选择 TPOT p99，实验会不稳定。
3. 若要强 claim TPOT p95/p99，需要继续优化 KAS long-output fairness。

处理：

1. 主图使用 TPOT p50/p90。
2. TPOT p95/p99 放到 boundary 或 appendix。
3. 如需扩展，回到 Stage 2 优化 long-output fairness。

### Gap 4：最终消融尚未完全匹配 Stage 4D

Stage 4C 已完成 OPT-13B 消融，说明 BPS、KAS、PBC 的角色可区分。但 Stage 4D 使用了双模型、宽 rate 和新 SLO；这套最终口径下还需要补代表性消融。

影响：

1. 不推翻 Stage 4D 端到端结果。
2. 会影响“每个组件不可或缺”的最终论文强度。
3. 如果只引用 Stage 4C 消融，需要明确它是机制验证，不是最终全矩阵。

处理：

1. 在 OPT-13B 和 LLaMA-13B 上各选 2-3 个 representative rates。
2. 运行 `fcfs`, `bps`, `kas`, `bps_kas`, `phase`。
3. 使用同一 SLO `5s/0.12s` 和同一 mixed-wide workload。

### Gap 5：文档与实验口径曾经不同步

旧文档仍有 `10s/1s` SLO、rate `2/3` 主窗口、只验证 OPT-13B 的表述。Stage 4D 已经更新为双模型、宽 per-GPU rate、新 SLO。

影响：

1. 会导致后续画图或论文写作拿错数字。
2. 会让方法论和结果看起来不一致。

处理：

1. Stage 4D 作为最新端到端入口。
2. `current_progress.md` 指向 Stage 4D。
3. 旧 Stage 4C 文档保留为机制审计和消融历史，不作为最新主结果。

## 当前 supported claims

可以进入主结果：

1. PhaseServe 在 OPT-13B 和 LLaMA-13B mixed-regime workload 中提高 SLO attainment。
2. PhaseServe 稳定改善 TTFT p90。
3. PhaseServe 稳定改善 TPOT p50/p90。
4. full Phase 比静态 BPS+KAS 有动态仲裁价值，但最终口径还需补代表性消融。
5. BPS/KAS 的单组件消融显示它们分别偏向 TTFT/TPOT，PBC 负责端到端 balance。

需要收窄或暂缓：

1. 所有 percentile 都改善。
2. 越高 rate 收益越大。
3. TPOT p95/p99 稳定改善。
4. PBC 有严格最优性或理论 guarantee。
5. throughput 是主要收益。

## 对顶会潜力的影响

这些 gap 不会让 PhaseServe 退化成不可发表的工程报告，但会决定论文从“有希望”到“可信”的距离。

正面因素：

1. 问题 framing 清楚：disaggregation 后仍存在 pressure propagation。
2. 方法结构清楚：PBC、BPS、KAS 分别对应 pressure control、prefill shaping、decode shaping。
3. 最新双模型结果显示 SLO、TTFT p90、TPOT p50/p90 都有稳定收益。
4. 代码中已经有真实的 regime arbitration，而不是简单拼启发式。

风险因素：

1. 如果 PBC 只写成线性 backpressure，会显得不够新。
2. 如果不报告机制指标，BPS/KAS 可能被看成已有调度策略组合。
3. 如果 claim 过强，tail tradeoff 会被抓住。
4. 如果消融没有按最终口径补齐，组件不可替代性不够硬。

因此，正确策略不是继续堆更多泛化 claim，而是把论文组织成：

```text
pressure propagation problem
-> typed pressure-budget control contract
-> regime ownership arbitration
-> BPS/KAS under budget
-> mixed-regime end-to-end SLO and latency gains
-> component and mechanism evidence
-> explicit boundary cases
```

## 下一步文档动作

1. `docs/current_progress.md` 改为以 Stage 4D 为最新入口。
2. `docs/stage3_experiment_design.md` 后续应补充 Stage 4D 的最终 SLO 口径。
3. 图表脚本和论文 outline 使用 Stage 4D 的 supported claims。
4. 消融补跑后新增 `stage4e_final_ablation.md`。
5. 机制指标抽取后新增 `stage4e_mechanism_evidence.md` 或更新 Stage 4C mechanism audit。
