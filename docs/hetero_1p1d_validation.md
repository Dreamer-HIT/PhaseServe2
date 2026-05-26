# Heterogeneous 1p1d Validation

更新时间：2026-05-26

## 结论

在短/中/长输出混合 workload 上，PhaseServe 的 Phase 策略开始体现比 FCFS 更有论文价值的信号：在 48 个 burst 请求、1p1d、LLaMA2-7B、低 KV cache 容量配置下，Phase 的 SLO goodput 高于 FCFS，并且 TPOT tail 更低。

当前最佳单次 probe 是 `PHASESERVE_PBC_MIN_PREFILL_FRAC=0.5`：

| Policy | Completed | Goodput req/s | SLO submitted | TTFT p50/p95/p99 | TPOT p50/p95/p99 |
|---|---:|---:|---:|---:|---:|
| Phase prefill0.5 | 48/48 | 1.38 | 0.958 | 0.527 / 9.785 / 10.151 | 0.036 / 0.135 / 0.139 |
| FCFS paired run | 48/48 | 1.27 | 0.938 | 0.578 / 10.075 / 10.462 | 0.038 / 0.140 / 0.149 |
| Phase default before prefill tuning | 48/48 | 1.31 | 0.958 | 0.581 / 9.645 / 11.249 | 0.037 / 0.125 / 0.139 |
| FCFS clean baseline | 48/48 | 1.26 | 0.917 | 0.510 / 10.514 / 10.544 | 0.039 / 0.142 / 0.156 |

这里的结论仍然是 probe 级别，不是最终论文实验：需要多 seed、多次重复、arrival-rate sweep 后才能写成正式结果。

## Workload

- 结构：1p1d
- 模型：LLaMA2-7B (`/root/data/models/nous-llama2-7b-hf`)
- 请求数：48
- arrival：burst (`--request-rate 0`)
- prompt mix：64 tokens 17 个，256 tokens 14 个，512 tokens 17 个
- output mix：64 tokens 9 个，128 tokens 17 个，256 tokens 9 个，512 tokens 10 个，1024 tokens 3 个
- `gpu_memory_utilization=0.38`
- `swap-space=8`
- SLO：TTFT 10s，TPOT 1s

数据集路径：

- `/root/data/phase_scheduler_results/hetero_1p1d_clean_20260526_180703/hetero_synthetic.marshal`

## 关键路径

- clean default：`/root/data/phase_scheduler_results/hetero_1p1d_clean_20260526_180703`
- prefill0.5：`/root/data/phase_scheduler_results/hetero_1p1d_prefill05_20260526_181051`
- prefill0.75：`/root/data/phase_scheduler_results/hetero_1p1d_prefill075_20260526_181342`

新增脚本：

- `benchmarks/phase_make_synthetic_dataset.py`
- `scripts/run_phase_hetero_1p1d.sh`

## 解释

第一版 hetero 脚本曾误命中旧服务端口，已修复。脚本现在会在启动前清理同端口旧 DistServe 进程，避免 readiness check 命中旧服务。

干净结果显示，Phase 默认配置已经优于 FCFS 的 SLO goodput，但 TTFT p99 仍被少数请求拖高。进一步分析发现，context 侧 PBC 的 prefill floor 原先为最大 batch token 的 25%，高压下约为 514 tokens；当 workload 中存在大量 512-token prompt 时，BPS 经常一次只能推进一个长 prompt，导致 context queue/bridge queue 增大。

将 `PHASESERVE_PBC_MIN_PREFILL_FRAC` 提到 0.5 后，Phase 的 goodput 提升到 `1.38 req/s`，TTFT p99 降到约 `10.15s`，TPOT p99 保持优于 paired FCFS。继续提高到 0.75 会退化，说明 prefill floor 过高会重新挤压 decode/bridge。

因此当前实现默认采用 0.5 prefill floor：它比 0.25 更适合混合 prompt workload，又没有 0.75 的过度 prefill 风险。

## 下一步

1. 多 seed 重复 `hetero_1p1d`，报告均值、标准差、置信区间。
2. 加 arrival-rate sweep：burst、0.5 rps、1 rps、2 rps、4 rps，观察 SLO goodput 曲线。
3. 加 SLO sensitivity：TTFT 5/10/20s 与 TPOT 0.05/0.1/0.2/1.0s。
4. 继续优化 BPS：把 forced-oldest 从二值触发改成 age-aware score，降低 TTFT p99。
5. 继续优化 KAS victim selection：加入 remaining-output 与 KV footprint，减少不必要 swap。
