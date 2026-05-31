# PhaseServe 实验协议与迭代原则

更新时间：2026-05-30

## 文档目的

本文档定义 PhaseServe 后续实验的总流程、图表规划、失败诊断规则和回退原则。它不是某一次实验的结果记录，而是后续 Stage 3/4 循环的规则书。后续新增实验、代码修复和方法论收敛应优先对齐本文档，避免根据单次结果临时调整 workload、rate 或 claim。

## 总原则

1. 实验协议先于实验结果确定。模型、数据集、baseline、rate 选择规则、SLO 规则、metrics、seeds 和图表结构应先写清楚，再开始正式矩阵。
2. 主实验优先使用真实 workload 分布。`ShareGPT` 和 `LongBench` 是端到端主实验的最低要求；synthetic 或 mixed-regime workload 只作为机制和压力实验。
3. rate 区间由 baseline 压力决定。优先选择 DistServe 从稳定进入退化的连续区间，例如 SLO attainment 从接近 100% 下降到 50%-90% 的范围，而不是按 PhaseServe 最好看的点选择。
4. 效果不好时先诊断，不直接改方法论。只有当测量、workload 压力、实现对齐和参数合理性都排查后，才允许回到方法论层面收窄或修改 claim。
5. 代码修改必须绑定诊断证据。不能因为某个指标不好就泛化调参；每次修改都要说明对应的 pressure、budget、admission、KV/swap 或 queue 现象。
6. 论文结果只基于已实现和已验证内容。未验证的机制只能作为设计或假设，不能写成实验结论。
7. 所有阶段产物必须可追溯。每个正式实验要记录 commit/代码状态、模型路径、数据源、参数、seed、rate、raw result、summary、分析脚本和图表版本。

## 相关论文对齐

后续实验设计以 DistServe、WindServe 和 ShuffleInfer 的实验范式为参照。

| 论文 | 对 PhaseServe 的启发 |
|---|---|
| DistServe | 使用 `ShareGPT/HumanEval/LongBench`、Poisson arrival、SLO attainment、per-GPU goodput、SLO Scale；重点证明 disaggregation/goodput 优势 |
| WindServe | 使用 `ShareGPT/LongBench`、OPT/LLaMA2、DistServe/vLLM chunked-prefill baseline；报告 TTFT P50/P99、TPOT P90/P99 和 SLO attainment |
| ShuffleInfer | 使用 LPLD/LPHD/HPLD/HPHD/Mixed workload taxonomy；需要 length-aware same-engine baseline 来排除“只是长短请求调度”的解释 |

## Workload 分层协议

后续 workload 采用三层设计。不同层级承担不同证据职责，不能混用表述。

### Layer 1：主端到端真实 workload

Layer 1 是论文主端到端实验的默认来源。它用于回答 PhaseServe 在真实公开数据分布上是否优于 DistServe。

| Workload | Model | Dataset | 请求集合 | Arrival | 目的 |
|---|---|---|---|---|---|
| E2-A Chatbot | OPT-13B | ShareGPT | 从完整 processed ShareGPT 中按固定 seed 采样 | Poisson | 对齐 DistServe/WindServe chatbot |
| E2-B Long-context | LLaMA2-13B | LongBench | LongBench 4K trace，按固定 seed 采样 | Poisson | 对齐 WindServe long-context summarization |
| E2-C Generalization | LLaMA2-13B | ShareGPT | 从完整 processed ShareGPT 中按固定 seed 采样 | Poisson | 检查 ShareGPT 结果是否跨模型成立 |

Layer 1 不允许为了 PhaseServe 的效果手工挑选长度集合或改变 arrival order。只允许做可解释的数据清洗，例如模型上下文长度过滤、空样本过滤、非法 token 或异常样本过滤。所有 policy 必须使用完全相同的请求集合、arrival trace、seed、rate 和 SLO 口径。

### Layer 2：ShuffleInfer-style controlled regime workload

Layer 2 用于机制解释和强 baseline 对照。它允许按长度构造请求集合，但必须提前公开 taxonomy、阈值和采样规则。请求仍应优先来自 ShareGPT 或 LongBench，而不是纯手写长度。

默认 taxonomy：

| Regime | Prompt rule | Output rule | 目的 |
|---|---|---|---|
| LPLD | prompt <= 512 | output <= 128 | 低压力 sanity check |
| LPHD | prompt <= 512 | output >= 512 | decode-heavy，验证 KAS/KV 控制 |
| HPLD | prompt >= 1024 | output <= 128 | prefill-heavy，验证 BPS/PBC prefill budget |
| HPHD | prompt >= 1024 | output >= 512 | 双压力边界和 KV 压力 |
| Mixed-pressure | 四类均衡混合 | 四类均衡混合 | 验证 PBC+BPS+KAS 在混合压力下的耦合 |

如果某个 dataset 中符合阈值的样本不足，可以按固定规则逐步放宽阈值，并在实验记录中写明。Layer 2 的结论应表述为 controlled regime 下的机制证据，不替代 Layer 1 的真实 workload 结论。

### Layer 3：诊断与 stress workload

Layer 3 用于定位实现问题、做参数敏感性和解释失败边界。它可以更人工，但不能单独支撑主端到端 claim。

| Workload | 构造方式 | 主要用途 |
|---|---|---|
| Prefill-skew | 多短 prompt + 少量长 prompt | 诊断 BPS、pad waste、prefill queue 和 TTFT tail |
| Decode-heavy | 短/中 prompt + 长 output | 诊断 KAS、decode queue、KV pressure 和 TPOT tail |
| Mixed-order | 固定真实请求集合，只改变 arrival order | 诊断 pressure propagation 与 arrival burst/order 敏感性 |
| Burst | 请求集中到达 | 诊断 starvation、bounded progress 和高压边界 |

旧的 synthetic、mixed-wide、first-128 mixed-order 和 cross-skew 结果均保留为 Layer 3 或 exploratory 证据。它们不废弃为无效结果，但不再作为主端到端实验的唯一依据。

## 主端到端目标与回退规则

当前内部优化目标仍设为：

- 在 Layer 1 主端到端真实 workload 上，找到至少一个长度为 `2.0 req/s/GPU` 的连续 per-GPU rate 区间；
- rate 粒度至少为 `0.5 req/s/GPU`；
- 区间内每个 rate 点，PhaseServe 相比 DistServe 在 TTFT 的 `p50/p90/p95/p99` 中至少两个指标改善 `>=20%`；
- 同一区间内每个 rate 点，PhaseServe 相比 DistServe 在 TPOT 的 `p50/p90/p95/p99` 中至少两个指标改善 `>=20%`；
- 每个点至少使用两个 seed；最终论文主结果优先补到三个 seed。

该目标是内部收敛标准，不是预先承诺的论文 claim。若 Layer 1 真实 workload 无法满足该 strict 2-wide 目标，不能直接切换到手工挑选长度集合来满足目标，而应按顺序处理：

实验记录必须同时写清楚 global offered rate 和 per-GPU rate。当前 1P1D 设置使用 2 GPUs，因此 global rate `2.0-4.0` 对应 per-GPU rate `1.0-2.0`；如果讨论“长度为 2 的 rate 区间”，必须明确是 global 口径还是 per-GPU 口径，避免把内部优化目标和画图横轴混用。

1. 检查 E0 测量链路和统计口径。
2. 检查 E1 baseline pressure window 是否覆盖稳定区、退化区和过载边界。
3. 检查实现是否与方法论一致，尤其是 PBC budget、BPS admission、KAS feasibility 和 KV/swap 约束。
4. 若真实 workload 的瓶颈天然只触发 TTFT 或 TPOT 单侧压力，则将 strict 2-wide 目标移动到 Layer 2 Mixed-pressure controlled regime，并把 Layer 1 claim 收窄为真实 workload 下的 SLO/goodput 或单侧 tail 改善。
5. 任何 claim 收窄都必须记录原因、数据证据和替代图表。

## 实验阶段

### E0：协议与测量 sanity

目标：

- 固定实验协议和图表清单。
- 确认 benchmark 对 TTFT、TPOT、throughput、SLO attainment、per-GPU rate、failure 的统计正确。
- 确认 raw JSONL 到 summary CSV/Markdown 的链路可复现。

产物：

- 本文档。
- `docs/benchmarking.md` 中的指标口径保持同步。
- 一个小规模 sanity run，证明 summary 字段完整。

验收标准：

- 所有正式指标都有明确定义。
- `.jsonl`、`.summary.json`、`.csv`、`.md` 可以互相追溯。
- SLO attainment 同时支持 completed denominator 和 submitted denominator，并明确论文使用哪一种。

### E1：Baseline calibration

目标：

- 只跑 DistServe baseline，找到每个 model/dataset 的压力区间。
- 不在这个阶段评价 PhaseServe 是否有效。

推荐矩阵：

| 优先级 | Model | Dataset | Arrival | Baseline | 作用 |
|---|---|---|---|---|---|
| P0 | OPT-13B | ShareGPT | Poisson | DistServe/FCFS | 对齐 DistServe/WindServe chatbot 主设置 |
| P0 | LLaMA2-13B | LongBench | Poisson | DistServe/FCFS | 对齐 WindServe long-context summarization 主设置 |
| P1 | LLaMA2-13B | ShareGPT | Poisson | DistServe/FCFS | 解耦模型与 dataset，证明 ShareGPT 结果不只依赖 OPT |
| P2 | OPT-13B | LongBench | Poisson | DistServe/FCFS | 可选；受 OPT 2K context 限制，通常需要截断 |

可选扩展：

- vLLM chunked-prefill baseline。

rate 选择规则：

1. 从低 rate 开始，逐步增加 per-GPU request rate。
2. 保留能覆盖以下状态的连续区间：
   - baseline 基本稳定；
   - baseline 开始出现 TTFT/TPOT tail 或 SLO 下降；
   - baseline 明显过载但仍有大多数请求完成。
3. 如果所有线都很平，说明压力不足，需要扩大 rate 或换 workload，而不是直接判断 PhaseServe 无效。
4. 如果 baseline 大面积失败，说明 rate 太高，应回退到可诊断区间。

实现口径：

- 当前 `run_phase_hetero_sweep.sh` 中的 `RATES` 是 benchmark 输入的全局 arrival rate。
- 当前 1P1D 实验使用 `--num-gpus 2`，论文图如果使用 `Per-GPU Rate` 作为横轴，应换算为 `RATES / 2`。
- summary 中的 `per_gpu_goodput_req_s` 是 measured goodput，不等同于横轴 offered rate；两者需要分别记录。

产物：

- 每个 model/dataset 的 baseline pressure window。
- baseline-only summary 表。
- 选择 rate 区间的文字说明。

验收标准：

- 至少两个真实 workload setting 找到可区分的压力区间。
- rate 区间选择规则可复现，不依赖 PhaseServe 结果。

### E2：主端到端实验

目标：

- 在 E1 固定的相同 workload、rate、seed 下比较 DistServe 和 PhaseServe。
- 回答 PhaseServe 在真实 workload 下是否改善 SLO/goodput 和 TTFT/TPOT。

主矩阵：

| 场景 | Model | Dataset | Policies |
|---|---|---|---|
| Chatbot | OPT-13B | ShareGPT | DistServe, PhaseServe |
| Summarization | LLaMA2-13B | LongBench | DistServe, PhaseServe |
| Generalization | LLaMA2-13B | ShareGPT | DistServe, PhaseServe |

强基线：

- `vLLM chunked-prefill`：若工程上可运行，作为非 disaggregated 强 baseline。
- `ShuffleInfer-style`：同引擎 length-aware baseline，见 E4。

主指标：

- SLO attainment。
- per-GPU goodput。
- completed request throughput。
- output token throughput。
- TTFT P50/P99。
- TPOT P90/P99。

主图：

| 图 | 横轴 | 纵轴 | 说明 |
|---|---|---|---|
| Fig. E2-1 | Per-GPU Rate | SLO Attainment | 主 goodput/SLO 图，标 90% attainment |
| Fig. E2-2 | Per-GPU Rate | TTFT P50/P99 | 同一子图内放两个 percentile |
| Fig. E2-3 | Per-GPU Rate | TPOT P90/P99 | 同一子图内放两个 percentile |
| Fig. E2-4 | SLO Scale | SLO Attainment | 固定压力 rate，展示严格 SLO 下的稳定性 |

验收标准：

- 每个主 setting 至少有 2-3 个有区分度的 rate 点。
- PhaseServe 的收益和 tradeoff 都要报告；不能只报告改善指标。
- 如果 TPOT/TTFT 的改善出现在不同 rate 区间，可以分开解释，但 rate 选择必须来自 E1 baseline pressure window。

### E3：组件消融

目标：

- 证明 PBC、BPS、KAS 对最终结果分别有贡献。
- 判断是否存在某个组件只引入 tradeoff 而没有可解释收益。

主文消融只保留核心组件，不展示过多内部调参。

| Variant | 含义 |
|---|---|
| DistServe | 原始 FCFS baseline |
| PhaseServe Full | PBC + BPS + KAS |
| w/o PBC | BPS + KAS 使用静态 budget |
| w/o BPS | PBC + KAS，prefill batching 回到默认策略 |
| w/o KAS | PBC + BPS，decode admission 回到默认策略 |
| ShuffleInfer-style | length-aware prefill/decode baseline，无 PBC 统一预算 |

消融不需要扫完整 rate 区间，优先选择：

- DistServe 已经开始掉 SLO 但未完全崩的 rate；
- TTFT-limited rate；
- TPOT/decode-limited rate；
- mixed-pressure rate。

主指标：

- SLO attainment。
- TTFT P99。
- TPOT P99。
- per-GPU goodput。
- throughput。

机制指标：

- `prefill_budget_ratio`。
- `pressure_potential`。
- `pressure_injection_prefill`。
- `pressure_injection_decode_swap`。
- `phase_decode_kas_intensity`。
- `swap_in_bytes` / `swap_byte_budget_ratio`。
- prompt/output bucket tail。

验收标准：

- Full PhaseServe 相比任一单组件不一定所有指标都最好，但必须有可解释的整体收益。
- 若某个组件在主 setting 中没有贡献，需要修改实现、收窄 claim，或把该组件移到机制/特定 regime claim。

### E4：ShuffleInfer-style regime 实验

目标：

- 排除 PhaseServe 只是 length-aware scheduling 的解释。
- 在受控 prefill/decode regime 下解释 PhaseServe 的压力预算机制。

workload taxonomy：

| Workload | Prompt | Output | 目的 |
|---|---|---|---|
| LPLD | light | light | chat-like low-pressure sanity |
| LPHD | light | heavy | decode pressure |
| HPLD | heavy | light | prefill pressure |
| HPHD | heavy | heavy | 双压力和 KV 压力 |
| Mixed | mixed | mixed | 多 regime 混合 |

baseline：

- DistServe。
- SJF/SPF prefill。
- output-length-aware decode。
- ShuffleInfer-style same-engine。
- PhaseServe Full。

完整 ShuffleInfer 系统对比：

- 若源码和环境可稳定复现，可以作为强 baseline。
- 若无法公平复现，主文应使用 same-engine ShuffleInfer-style baseline，并在 related work / experimental setup 中说明边界。

验收标准：

- 至少在 Mixed 或两个不同 quadrant 中证明 PhaseServe 的收益不是单一 length-aware heuristic。
- 必须报告失败或边界 workload，例如 HPHD 下如果收益有限，应解释为 overhead/双压力边界。

### E5：机制分析

目标：

- 解释 PhaseServe 为什么有效，而不仅展示最终曲线。

建议图表：

| 图 | 内容 |
|---|---|
| Mechanism-1 | request lifecycle breakdown：prefill queue、prefill exec、bridge/migration、decode queue、decode exec |
| Mechanism-2 | pressure-to-budget timeline：pressure、budget、regime、KAS intensity 随时间变化 |
| Mechanism-3 | bucket breakdown：短/长 prompt、短/长 output 的 TTFT/TPOT tail |
| Mechanism-4 | KV/swap feasibility：swap bytes、infeasible rounds、resident admission |

验收标准：

- 机制图能解释主实验中至少一个 TTFT 改善和一个 TPOT/SLO 改善。
- 如果主实验有 tradeoff，机制图也要解释 tradeoff 来源。

## 效果不好时的诊断决策树

当 PhaseServe 没有效果，按下面顺序处理。

### 1. 测量问题

症状：

- 指标异常平。
- throughput 和 SLO 对 rate 不敏感。
- percentile 与 raw JSONL 不一致。
- completed denominator 和 submitted denominator 混用。

动作：

- 检查 benchmark、summary、plot 脚本。
- 手动抽查 raw JSONL。
- 不修改调度代码，不修改方法论。

### 2. 压力问题

症状：

- DistServe 本身没有退化。
- TTFT/TPOT/SLO 在全 rate 区间都接近不变。

动作：

- 扩大 rate sweep。
- 换到更合适的真实 workload。
- 设计 E4 controlled regime workload。
- 记录为什么该 workload/rate 能触发问题。

### 3. 实现对齐问题

症状：

- PBC 输出 budget，但 BPS/KAS 没消费。
- BPS/KAS 指标为空或没有触发。
- KAS 没使用 KV/swap feasibility。
- BPS 没根据 pressure 改变 batch scoring。

动作：

- 回到代码映射和方法论对齐文档。
- 修代码。
- 跑最小 smoke 和 targeted rerun。
- 不修改方法论。

### 4. 参数问题

症状：

- 机制触发了，但过强或过弱。
- TTFT 好而 TPOT 明显坏，或 TPOT 好而 TTFT 明显坏。
- pressure smoothing/hysteresis 导致响应太慢。

动作：

- 小矩阵调节明确参数。
- 每次只改一个参数族。
- 记录 tradeoff。
- 不扩大 claim。

### 5. 方法问题

症状：

- 测量正确。
- baseline 有压力。
- 代码完整实现方法论。
- 参数已经合理。
- 机制日志显示策略按设计触发，但结果仍不支持 claim。

动作：

- 回到方法论。
- 收窄 claim，例如从“同时改善 TTFT/TPOT”改成“在 pressure propagation regime 下改善 SLO goodput 和 tail stability”。
- 删除或弱化无贡献组件。
- 重新定义组件边界或实验问题。

## 返工规则

| 发现的问题 | 返工层级 |
|---|---|
| 统计或图表错误 | 改脚本 |
| benchmark 未记录必要字段 | 改 benchmark/instrumentation |
| 方法未真正进入调度决策 | 改代码 |
| workload 没有触发目标压力 | 改 workload/rate，但保留选择规则 |
| 单个参数导致 tradeoff | 做参数 sensitivity |
| 完整实现仍无法支持 claim | 改方法论或收窄 claim |

## 下一步入口

从本文档开始，下一步应进入 E1：Baseline calibration。

具体顺序：

1. 检查当前 benchmark 是否支持从真实 trace 或 length trace 构造 ShareGPT/LongBench workload。
2. 如果缺失，先实现 trace loader 或 length-trace generator。
3. 对 `OPT-13B + ShareGPT` 跑 DistServe-only pilot sweep。
4. 对 `LLaMA2-13B + LongBench` 跑 DistServe-only pilot sweep。
5. 对 `LLaMA2-13B + ShareGPT` 跑 DistServe-only pilot sweep。
6. 固定每个 setting 的 baseline pressure window。
7. 只有 E1 完成后，才进入 E2 跑 PhaseServe full 对比。
