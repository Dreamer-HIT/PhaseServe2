# PBC/KAS Memory-Pressure Validation

更新时间：2026-05-26

## 结论

本轮验证的核心结论是：当前 KAS 已经具备可观测的 KV eviction/swap 闭环，但在同质长输出 burst 压力下还不能声称优于 FCFS。它的研究价值暂时体现在“避免 KV 满载停滞，并暴露可控的 residency/admission 行为”，而不是吞吐或 TPOT 的直接提升。

因此，后续论文表述应避免写成“KAS 在所有 memory-pressure workload 上提升吞吐”。更稳妥的 claim 是：

1. KAS 在 GPU KV cache 饱和时执行受控 eviction，避免 bridge/context finished-but-unaccepted 请求永久阻塞。
2. PBC 能记录并约束 bridge/decode/KV/swap pressure，为 SLO-goodput 和 tail latency 调参提供可解释信号。
3. 同质长输出 burst 是当前方法的反例/压力失败模式，需要后续优化 decode 并行度和 swap 竞态。

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
| Phase stable | 24/24 | 0.319 | 0.178 / 0.213 | 0.059 / 0.097 / 0.120 | 8 | 8 |
| FCFS | 24/24 | 0.607 | 0.169 / 0.204 | 0.031 / 0.060 / 0.064 | n/a | n/a |
| Phase tuned failed | 9/24 | 0.351 | 0.121 / 0.179 | 0.029 / 0.044 / 0.044 | 63 | 70 |

关键路径：

- Phase stable summary：`/root/data/phase_scheduler_results/memory_pressure_probe_stable/phase_memory_n24_burst.summary.json`
- Phase stable metrics：`/root/data/phase_scheduler_results/memory_pressure_probe_stable/phase_metrics.jsonl`
- FCFS summary：`/root/data/phase_scheduler_results/memory_pressure_probe_fcfs/fcfs_memory_n24_burst.summary.json`
- Failed tuning summary：`/root/data/phase_scheduler_results/memory_pressure_probe_tuned2/phase_memory_n24_burst.summary.json`

## 解释

Phase stable 的好处是完成性和可观测性：它从原来的 KV 满载停滞变成了 24/24 完成，并产生 8 次 eviction 与 8 次 swap-in。这个结果证明 KAS 的 KV residency 控制路径已经真实执行，而不是只记录指标。

但 FCFS 在该 workload 上更快，原因也很清楚：

- workload 几乎是同质长输出，LAS 的短作业优先收益无法发挥。
- PBC 在高 KV pressure 下将 `decode_scan_limit` 压得很低，Phase stable 的平均 selected 只有约 3.44，而 FCFS 更容易维持较高 decode 并行度。
- 失败调参版把平均 selected 提到约 7.98，TPOT 接近 FCFS，但触发 `not enough free blocks on GPU, requested 1, available 0`，说明 DistServe 当前 swap/allocate 路径还存在边界竞态，需要更严格的 block reservation 才能安全扩大 scan。

## 后续任务

1. 在 KAS 中加入显式 block reservation，而不是只用当前 available blocks 做即时判断。
2. 将 eviction victim 选择从简单反优先级改成 cost-aware：考虑剩余输出、已服务 token、KV footprint、CPU swap 可用量。
3. 将 PBC 的 decode scan 和 admission budget 解耦：KV pressure 不应无条件缩小 scan，scan 应服务于寻找可推进请求。
4. 增加一个 heterogenous workload：短/长输出混合，使 LAS 的 tail-latency 目标有发挥空间。
5. 将 memory-pressure workload 纳入自动脚本，要求同时报告 completed rate、goodput、median/p95/p99 TTFT、median/p95/p99 TPOT、swap-in、eviction、max consecutive skips。
