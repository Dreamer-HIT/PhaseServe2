# Heterogeneous 1p1d Validation

更新时间：2026-05-26

## 结论

在 1p1d、LLaMA2-7B、低 KV cache 容量配置下，PhaseServe 当前 Phase 策略已经形成一个可以继续写论文的实验信号：它不保证每个负载点的所有指标都优于 FCFS，但在异构输出长度和 KV 压力较高时，能够稳定降低 decode tail latency，并在 burst/high-pressure 场景提升 SLO goodput。

5-seed arrival-rate sweep 的核心结果如下：

- burst/rate0：Phase 平均 goodput 比 FCFS 高 `10.7%`，SLO submitted 高 `4.17 pp`，TPOT p99 降低 `18.3%`。
- rate1：两者 SLO 都为 1.0，Phase goodput 基本持平，TPOT p99 降低 `18.4%`。
- rate2：两者 SLO 都为 1.0，Phase goodput 基本持平，TPOT p99 降低 `42.1%`。
- rate4：两者 SLO 都为 1.0，Phase goodput 高 `4.3%`，TTFT p99 降低约 `1.44s`，TPOT p99 降低 `38.6%`。

这说明当前方法的更准确主张应是：PhaseServe 通过 phase-aware batching 和 KV-pressure-aware decode scheduling 改善异构请求下的 tail latency isolation，而不是追求所有 arrival rates 上的平均吞吐全面领先。

## 实验设置

- 结构：1p1d
- 模型：LLaMA2-7B (`/root/data/models/nous-llama2-7b-hf`)
- 请求数：48
- arrival rates：burst (`0`)、`1`、`2`、`4` req/s
- seeds：`0 1 2 3 4`
- prompt mix：每个 seed 从 `64/256/512` tokens 中采样
- output mix：每个 seed 从 `64/128/256/512/1024` tokens 中采样
- `gpu_memory_utilization=0.38`
- `swap-space=8`
- SLO：TTFT 10s，TPOT 1s

结果目录：

- `/root/data/phase_scheduler_results/hetero_1p1d_sweep5_nexttoken_20260526_191635`

新增/相关脚本：

- `benchmarks/phase_make_synthetic_dataset.py`
- `benchmarks/phase_collect_summaries.py`
- `benchmarks/phase_analyze_sweep.py`
- `scripts/run_phase_hetero_1p1d.sh`
- `scripts/run_phase_hetero_sweep.sh`

## 5-Seed Sweep 结果

按 arrival rate 聚合均值：

| Rate | Policy | n | Goodput req/s | SLO submitted | TTFT p99 | TPOT p95 | TPOT p99 |
|---:|---|---:|---:|---:|---:|---:|---:|
| 0 | Phase | 5 | 1.503 | 0.988 | 9.585 | 0.143 | 0.153 |
| 0 | FCFS | 5 | 1.364 | 0.946 | 9.722 | 0.174 | 0.193 |
| 1 | Phase | 5 | 0.920 | 1.000 | 0.078 | 0.0185 | 0.0203 |
| 1 | FCFS | 5 | 0.923 | 1.000 | 0.075 | 0.0233 | 0.0298 |
| 2 | Phase | 5 | 1.350 | 1.000 | 0.080 | 0.0384 | 0.0434 |
| 2 | FCFS | 5 | 1.347 | 1.000 | 0.077 | 0.0673 | 0.0795 |
| 4 | Phase | 5 | 1.533 | 1.000 | 0.712 | 0.0984 | 0.109 |
| 4 | FCFS | 5 | 1.468 | 1.000 | 2.157 | 0.162 | 0.177 |

Paired Phase minus FCFS：

| Rate | n | Goodput delta | SLO delta | TTFT p99 delta | TPOT p95 delta | TPOT p99 delta | Goodput ratio | TPOT p99 ratio |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 5 | +0.138 | +0.0417 | -0.136 | -0.0310 | -0.0399 | 1.107 | 0.817 |
| 1 | 5 | -0.0029 | 0.0000 | +0.0038 | -0.0047 | -0.0094 | 0.997 | 0.816 |
| 2 | 5 | +0.0028 | 0.0000 | +0.0026 | -0.0289 | -0.0361 | 1.002 | 0.579 |
| 4 | 5 | +0.0647 | 0.0000 | -1.445 | -0.0635 | -0.0678 | 1.043 | 0.614 |

## 解释

第一版 hetero 脚本曾误命中旧服务端口，已修复。脚本现在会在启动前清理同端口旧 DistServe 进程，避免 readiness check 命中旧服务。

早期单次 probe 显示，context 侧 PBC 的 prefill floor 原先为最大 batch token 的 25%，高压下约为 514 tokens；当 workload 中存在大量 512-token prompt 时，BPS 经常一次只能推进一个长 prompt，导致 context queue/bridge queue 增大。将 `PHASESERVE_PBC_MIN_PREFILL_FRAC` 提到 0.5 后，Phase 的 burst goodput 和 TTFT tail 更稳；继续提高到 0.75 会退化，说明 prefill floor 过高会重新挤压 decode/bridge。

随后暴露出的 decode 崩溃来自 KV append 预留不足：调度器在把 CPU resident 请求 swap in 回 GPU 时，只满足了当前 append 需求，没有为即将生成的 next token 预留增长空间，导致 decode worker 在极端 KV 压力下出现 `not enough free blocks on GPU`。当前实现改为按 `input_len + output_len + 1` 估计下一 token 的 KV block 需求，从而避免用固定全局 margin 换稳定性的粗暴做法。

新的 5-seed sweep 表明，Phase 的主要收益来自两个机制的组合：

- BPS 的 prefill floor 避免 context 侧在异构 prompt 下过度碎片化，burst 场景下改善 SLO goodput。
- KAS 的 decode admission/eviction 更偏向保护即将产生尾延迟的 decode 请求，在 rate2/rate4 上显著降低 TPOT p95/p99。

## 论文含义

当前结果可以支撑下一阶段论文主张，但还不能直接作为最终实验：

- 主张应聚焦于 tail-latency isolation、SLO goodput 和异构输出长度，而不是平均吞吐全面提升。
- 低负载 rate1/rate2 的 goodput 与 TTFT 基本持平或略有代价，需要在论文中如实呈现，并解释这是调度器为 decode tail 保护付出的轻微 trade-off。
- rate4 同时改善 TTFT p99 和 TPOT p99，是后续写 high-pressure case study 的重点。
- 目前只有 48 请求规模，需要扩大请求数、模型规模、KV 压力档位和 SLO sensitivity 才能达到系统顶会实验标准。

## 下一步

1. 扩展请求规模：从 48 提到 128/256，验证 tail improvement 是否随负载规模保持。
2. 加 SLO sensitivity：TTFT 5/10/20s 与 TPOT 0.05/0.1/0.2/1.0s。
3. 增加 KV pressure sweep：`gpu_memory_utilization` 覆盖 0.34/0.38/0.42/0.50。
4. 增加模型规模或长上下文场景：至少补 LLaMA2-13B 或 Qwen2.5-14B。
5. 做 ablation：Phase full、BPS only、KAS only、FCFS。
6. 继续优化 BPS：把 forced-oldest 从二值触发改成 age-aware score，降低 TTFT p99。
7. 继续优化 KAS victim selection：加入 remaining-output 与 KV footprint，减少不必要 swap。
