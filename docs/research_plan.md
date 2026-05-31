# PhaseServe 下一阶段研究计划

日期：2026-05-26

## 目标

PhaseServe 的目标不应只是在 DistServe 上增加两个调度启发式，而是证明：在 phase-disaggregated LLM serving 中，仅靠静态资源切分和 FCFS admission 不足以同时控制 prefill 排队、decode KV 压力和尾延迟；PhaseServe 通过在线、低开销、阶段感知的请求调度，在不改变模型并行配置的前提下提升瓶颈指标。

这里的“瓶颈指标”需要由 workload 决定，而不是承诺所有指标同时提升：

- prefill-heavy workload：主要目标是 TTFT median/tail 和 prefill queueing。
- decode/KV-pressure workload：主要目标是 TPOT P90/P99、decode queueing、swap/迁移压力。
- mixed workload：主要目标是 SLO goodput 和不同长度 bucket 的公平性。
- 允许 tradeoff：例如为了降低 TPOT tail，TTFT median 可能轻微上升；论文需要量化 tradeoff，而不是掩盖它。

## 参考论文口径

### DistServe

DistServe 的主指标是 goodput 和 SLO attainment：

- 以满足 TTFT 和 TPOT 两个 SLO 的请求比例作为 SLO attainment。
- 重点报告 90% SLO attainment 下的最大 per-GPU request rate。
- 还报告可承受的最严格 SLO scale。
- 端到端评估使用 ShareGPT、HumanEval、LongBench。
- 表格给出应用、模型、TTFT SLO、TPOT SLO、数据集。
- 额外报告 latency breakdown：prefill queuing、prefill execution、transmission、decoding queuing、decoding execution。

DistServe 使用的数据/场景：

| 应用 | 模型 | TTFT SLO | TPOT SLO | 数据集 |
|---|---|---:|---:|---|
| Chatbot | OPT-13B | 0.25s | 0.1s | ShareGPT |
| Chatbot | OPT-66B | 2.5s | 0.15s | ShareGPT |
| Chatbot | OPT-175B | 4.0s | 0.2s | ShareGPT |
| Code Completion | OPT-66B | 0.125s | 0.2s | HumanEval |
| Summarization | OPT-66B | 15s | 0.15s | LongBench |

### WindServe

WindServe 在 DistServe 口径上补充了更细的 latency distribution：

- TTFT: median/P50 和 P99。
- TPOT: P90 和 P99。
- SLO attainment：同时满足 TTFT 与 TPOT SLO 的请求比例。
- 使用 Poisson arrival 模拟请求到达。
- 使用 ShareGPT 做 chatbot，LongBench 做 summarization。
- 明确报告数据集 prompt/output token 分布的 avg、median、P90。

WindServe 使用的数据/场景：

| 数据集 | Prompt Avg | Prompt Median | Prompt P90 | Output Avg | Output Median | Output P90 |
|---|---:|---:|---:|---:|---:|---:|
| ShareGPT | 768.2 | 695 | 1556 | 195.9 | 87 | 518 |
| LongBench | 2890.4 | 2887 | 3792 | 97.4 | 12 | 369 |

WindServe 的 SLO 表：

| 模型 | Attention | TTFT SLO | TPOT SLO | 数据集 |
|---|---|---:|---:|---|
| LLaMA2-13B | MHA | 4s | 0.1s | LongBench |
| LLaMA2-70B | GQA | 15s | 0.5s | LongBench |
| OPT-13B | MHA | 0.25s | 0.1s | ShareGPT |
| OPT-66B | MHA | 0.8s | 0.15s | ShareGPT |

## 我们的指标口径

后续实验必须同时报告三类指标。

### 1. Latency distribution

主图至少包含：

- TTFT median/P50、P90、P95、P99。
- TPOT median/P50、P90、P95、P99。
- E2E latency median/P50、P90、P95、P99。

其中 median TTFT 用来说明 prefill admission 和排队优化是否真的改善普通请求体验；TPOT tail 用来说明 decode scheduler 是否缓解 KV 压力和长输出请求的扰动。

### 2. SLO/goodput

必须报告：

- request rate sweep 下的 SLO attainment 曲线。
- 90% SLO attainment 下的最大 per-GPU goodput。
- 可选：99% SLO attainment 下的最大 per-GPU rate。
- SLO scale sweep：在固定 rate 下同时缩放 TTFT/TPOT SLO，比较系统能承受的最严格 SLO。
- request throughput、token throughput 和 SLO goodput 分开报告，避免把“完成得多”和“满足 SLO 得多”混在一起。

### 3. Mechanism diagnostics

为了证明方法论不是黑盒调参，需要增加：

- prefill queueing / execution / KV migration / decode queueing / decode execution breakdown。
- scheduler overhead：每次调度决策的 average、P95、P99 latency。
- invalid token guard count：LLaMA2/SwiftTransformer 当前 workaround 的触发次数，论文实验中需单独说明或避免依赖该路径。
- decode KV residency：GPU KV blocks used、CPU swapped blocks、swap in/out count。
- fairness：不同 prompt/output length bucket 的 TTFT/TPOT 分布。

## 实验阶段

### Phase 0：工程稳定性

目标是让 1P1D + 13B 模型成为可重复 smoke test。

已完成：

- 修复系统盘 100% 问题，将运行缓存和 Ray 临时目录迁往数据盘。
- 加入 token id 合法性 guard，避免 SwiftTransformer 偶发越界 token id 被写回请求状态并导致 CUDA crash。
- FCFS 与 Phase policy 均可跑通 small workload。

下一步：

- 把 benchmark 脚本补齐 median/P90/P95/P99 TTFT/TPOT 统计输出。
- 把每次实验的启动命令、git commit、模型路径、数据集路径写入结果 JSON。
- 加入自动健康检查和失败日志归档。

### Phase 1：1P1D 13B 可控验证

目标是验证算法方向，而不是追求最终大模型数字。

配置：

- 模型：LLaMA2-13B 与 OPT-13B，不再使用 LLaMA2-7B 作为后续实验模型。
- 架构：1 prefill GPU + 1 decode GPU。
- 数据：合成 ShareGPT-like 分布，构造 prompt/output length bucket。
- 到达：Poisson arrival，覆盖低负载、中负载、接近饱和三段。

对比：

- FCFS / DistServe baseline。
- PS-Prefill only。
- PS-Decode only。
- PS-Prefill + PS-Decode。

要回答的问题：

- PS-Prefill 是否降低 median/P90 TTFT？
- PS-Decode 是否降低 P90/P99 TPOT？
- 两者叠加是否提高 90% SLO goodput？
- 调度开销是否低到不会抵消收益？

### Phase 2：复现论文级 workload

目标是和 DistServe/WindServe 的数据口径接轨。

优先级：

1. ShareGPT chatbot：prompt/output 长度分布宽，适合证明 prefill batching 与 median TTFT 改善。
2. LongBench summarization：长 prompt、短 output，适合证明 prefill admission 与 KV migration 控制。
3. HumanEval/code completion：TTFT SLO 严格，适合作为边界案例。

模型优先级：

1. OPT-13B：最贴近两篇论文，也更可能稳定。
2. LLaMA2-13B：用于和 WindServe LongBench 口径对齐。
3. LLaMA2-7B：仅保留为早期调试记录，不进入后续实验矩阵。

### Phase 3：论文主张成型

论文主线建议改成：

> Static phase disaggregation removes prefill-decode interference, but it does not solve runtime imbalance inside each phase. PhaseServe adds stage-aware online scheduling that jointly reduces prefill queueing and decode KV contention while preserving low scheduling overhead.

主图建议：

1. Motivation：FCFS/DistServe 下不同 prompt/output bucket 的 TTFT/TPOT 分化。
2. End-to-end ShareGPT：SLO attainment vs request rate。
3. End-to-end ShareGPT：TTFT median/P99 和 TPOT P90/P99 vs request rate。
4. LongBench：长 prompt 下 TTFT/TPOT 与 SLO attainment。
5. Ablation：PS-Prefill only、PS-Decode only、both。
6. Diagnostics：latency breakdown、scheduler overhead、KV block usage。

## 近期任务清单

1. 扩展 benchmark 统计脚本，输出 median/P90/P95/P99 TTFT、TPOT、latency。
2. 生成 ShareGPT-like 和 LongBench-like 的可控小数据集，先在 1P1D + LLaMA2-13B / OPT-13B 上跑通。
3. 使用 OPT-13B 稳定性对照，确认 invalid token guard 不是实验收益来源。
4. 做 FCFS、PS-Prefill、PS-Decode、Phase 四组 ablation。
5. 把实验结果整理成一张 CSV/JSON 汇总表，后续直接画图。
