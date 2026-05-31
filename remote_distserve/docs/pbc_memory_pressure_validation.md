# PBC/KAS Memory-Pressure Validation

更新时间：2026-05-26

## 结论

本轮验证的核心结论是：加入 block reservation 与 decode scan floor 后，KAS 已经从“只保证完成性”推进到“在 KV 压力下接近 FCFS 吞吐，同时改善 TTFT/TPOT tail”。在 1p1d + LLaMA2-7B 的同质长输出 burst 中，默认 Phase 配置 24/24 完成，goodput 为 `0.599 req/s`，接近 FCFS 的 `0.607 req/s`；同时 TTFT p95 从 FCFS 的 `0.204s` 降到 `0.188s`，TPOT p95 从 `0.060s` 降到 `0.049s`。

因此，后续论文表述应避免写成“KAS 在所有 memory-pressure workload 上提升吞吐”。更稳妥的 claim 是：

1. KAS 在 GPU KV cache 饱和时执行受控 eviction，避免 bridge/context finished-but-unaccepted 请求永久阻塞。
2. PBC 能记录并约束 bridge/decode/KV/swap pressure，为 SLO-goodput 和 tail latency 调参提供可解释信号。
3. 对同质长输出 burst，当前方法的主要收益是 tail latency 与可控 KV residency；goodput 基本追平 FCFS，但还不能宣称稳定大幅提升。
4. 不带 reservation 的激进 scan 会触发 `not enough free blocks on GPU`，因此 reservation 是 KAS 可发表实现中的必要组件。

## 修复内容

实验前，低 KV 容量配置下出现停滞：

- decode GPU blocks 长时间为 `302 / 302`。
- context 有 `12 finished but unaccepted`。
- decode 有 `12 waiting`，但 `0 processing`。
- `swap_ins=0`，没有 swap-out/in 闭环。

修复点位于 `distserve/decoding_stage_scheduler.py`：

- 当高优先级 resident 请求需要追加 KV block 且 GPU block 不足时，KAS 从低优先级 resident 请求中选择 victim。
- victim 被 swap out 到 CPU，释放 GPU KV blocks。
- 后续调度可将 swapped 请求按预算 swap in。
- metrics 中记录 `eviction_count`，用于区分 admission pressure 与真实 KV eviction 行为。

第二轮优化增加了两个关键点：

- KAS 在判断是否 swap-in CPU 请求时，同时扣除已选 resident 请求的 append-block reservation，避免 swap-in 抢占本轮 `allocate_blocks()` 需要的 GPU block。
- PBC 将默认 `decode_scan_limit` 下限设为最大 scan 窗口的 75%，避免高 KV pressure 把 scan 压到过小，导致 decode 并行度不足。

## 验证配置

- 结构：1p1d
- 模型：LLaMA2-7B (`/root/data/models/nous-llama2-7b-hf`)
- 数据集：`/root/data/phase_scheduler_results/pbc_memory_pressure.marshal`
- 请求数：24
- prompt length：约 61-62 tokens
- output length：512/768/1024 混合
- arrival：burst (`--request-rate 0`)
- `gpu_memory_utilization=0.38`
- `swap-space=8`
- decode/context batch size：8
- SLO：TTFT 10s，TPOT 1s

## 结果摘要

| Policy | Completed | Goodput req/s | TTFT p50/p95 | TPOT p50/p95/p99 | Swap-in | Eviction |
|---|---:|---:|---:|---:|---:|---:|
| Phase original stable | 24/24 | 0.319 | 0.178 / 0.213 | 0.059 / 0.097 / 0.120 | 8 | 8 |
| Phase default reserve | 24/24 | 0.599 | 0.154 / 0.188 | 0.037 / 0.049 / 0.053 | 31 | 31 |
| Phase minscan24 reserve | 24/24 | 0.609 | 0.169 / 0.199 | 0.037 / 0.050 / 0.053 | 37 | 37 |
| FCFS | 24/24 | 0.607 | 0.169 / 0.204 | 0.031 / 0.060 / 0.064 | n/a | n/a |
| Phase tuned failed | 9/24 | 0.351 | 0.121 / 0.179 | 0.029 / 0.044 / 0.044 | 63 | 70 |

关键路径：

- Phase stable summary：`/root/data/phase_scheduler_results/memory_pressure_probe_stable/phase_memory_n24_burst.summary.json`
- Phase stable metrics：`/root/data/phase_scheduler_results/memory_pressure_probe_stable/phase_metrics.jsonl`
- Phase default reserve summary：`/root/data/phase_scheduler_results/memory_pressure_probe_default_reserve/phase_memory_n24_burst.summary.json`
- Phase default reserve metrics：`/root/data/phase_scheduler_results/memory_pressure_probe_default_reserve/phase_metrics.jsonl`
- Phase minscan24 reserve summary：`/root/data/phase_scheduler_results/memory_pressure_probe_minscan24_reserve/phase_memory_n24_burst.summary.json`
- FCFS summary：`/root/data/phase_scheduler_results/memory_pressure_probe_fcfs/fcfs_memory_n24_burst.summary.json`
- Failed tuning summary：`/root/data/phase_scheduler_results/memory_pressure_probe_tuned2/phase_memory_n24_burst.summary.json`

## 解释

Phase original stable 的好处是完成性和可观测性：它从原来的 KV 满载停滞变成了 24/24 完成，并产生 8 次 eviction 与 8 次 swap-in。这个结果证明 KAS 的 KV residency 控制路径已经真实执行，而不是只记录指标。

第一版 Phase 慢于 FCFS，原因也很清楚：

- workload 几乎是同质长输出，LAS 的短作业优先收益无法发挥。
- PBC 在高 KV pressure 下将 `decode_scan_limit` 压得很低，Phase stable 的平均 selected 只有约 3.44，而 FCFS 更容易维持较高 decode 并行度。
- 失败调参版把平均 selected 提到约 7.98，TPOT 接近 FCFS，但触发 `not enough free blocks on GPU, requested 1, available 0`，说明 DistServe 当前 swap/allocate 路径还存在边界竞态，需要更严格的 block reservation 才能安全扩大 scan。

reservation 修复后，PBC 可以安全保留更大的 scan floor。默认 reserve 版的平均 scan limit 为约 26.65，平均 selected 为约 6.88，goodput 提升到 `0.599 req/s`；显式 `PHASESERVE_PBC_MIN_DECODE_SCAN=24` 时平均 selected 进一步到约 7.06，goodput 为 `0.609 req/s`。这说明原先的性能瓶颈不是 KAS 思路本身，而是容量边界上的 reservation 缺失与过小 scan floor。

## 后续任务

1. 将 eviction victim 选择从简单反优先级改成 cost-aware：考虑剩余输出、已服务 token、KV footprint、CPU swap 可用量。
2. 增加 heterogenous workload：短/长输出混合，使 LAS 的 tail-latency 目标有更明确发挥空间。
3. 将 memory-pressure workload 纳入自动脚本，要求同时报告 completed rate、goodput、median/p95/p99 TTFT、median/p95/p99 TPOT、swap-in、eviction、max consecutive skips。
4. 增加重复运行，报告均值/置信区间；当前结果是单次 probe，足以指导实现优化，但还不能作为论文最终实验。
5. 继续检查 OOV token warning 与频繁 swap 的关系，确保 swap 语义没有隐藏正确性风险。
