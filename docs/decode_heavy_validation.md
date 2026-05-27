# Decode-Heavy 1P1D Validation

更新时间：2026-05-27

## 目的

本文档记录第一轮 decode-heavy workload 验证。这个实验专门服务于 KAS/PBC 的归因：

- KAS 是否在 decode/KV 压力更强时降低 TPOT tail。
- BPS+KAS 是否比 FCFS 有更高的 SLO attainment、goodput 和输出 token 吞吐。
- Full Phase (`BPS+KAS+PBC`) 相比 `BPS+KAS` 是否能通过动态 prefill budget 进一步缓解 decode tail。

这不是最终论文的完整实验规模；它是 1p1d、LLaMA2-7B、2 seed 的方法验证和脚本固化。

## Workload

结果目录：

- `/root/data/phase_scheduler_results/decode_heavy2_20260527_083845`

脚本：

- `scripts/run_phase_decode_heavy_sweep.sh`

默认配置：

- 结构：1p1d
- 模型：LLaMA2-7B (`/root/data/models/nous-llama2-7b-hf`)
- 请求数：48
- seeds：`0 1`
- rates：burst (`0`)、`2` req/s
- policies：`fcfs`、`kas`、`bps_kas`、`phase`
- prompt mix：`64:0.60,256:0.25,512:0.15`
- output mix：`128:0.25,256:0.30,512:0.30,1024:0.15`
- SLO：TTFT 10s，TPOT 1s

这个 workload 故意让输出长度变长、prompt 偏短，从而把压力从 prefill 转到 decode/KV 侧。

## 稳定性修复

初始正式 sweep 中，`phase` 在 `seed=1, rate=0` 出现一次失败：

```text
AssertionError: not enough free blocks on GPU, requested 1, available 0
```

根因是 KAS 的 admission check 只给已经在 GPU 上的 resident request 预留 next-token append block。对于 CPU swapped request，调度器在判断 swap-in 可行性时只计算了 `blocks_to_swap_in`，没有同时预留 swap-in 后马上解码所需的 append block。长输出和 decode-heavy 场景下，这会导致 admission check 通过，但模型真正 append KV block 时 GPU block 不足。

修复位置：

- `distserve/decoding_stage_scheduler.py`

修复内容：

- 新增 `_estimate_append_blocks_needed()`，基于 `input_len + output_len + 1` 估算下一 token 需要的 block。
- resident request 仍使用 DistServe 原生 `get_num_append_blocks_needed()`，并和估算值取更保守的上界。
- non-resident request 的 admission check 改为同时检查：

```text
blocks_to_swap_in + append_needed + selected_append_needed <= available_gpu_blocks
```

验证：

- 修复后单独重跑失败 case：`/root/data/phase_scheduler_results/decode_heavy_phase_fix_20260527_090653`
- `phase, seed=1, rate=0` 完成 `48/48`，SLO attainment `1.0`，无 KV block assertion。
- 已将修复后的该 case 回填进正式结果目录，并重新生成 sweep 分析。

## 聚合结果

### Run-Level Means

| Rate | Policy | Goodput req/s | SLO submitted | Output tok/s | TTFT p90 | TTFT p99 | TPOT p90 | TPOT p99 |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 0 | fcfs | 0.802 | 0.833 | 399.1 | 14.456 | 19.206 | 0.137 | 0.177 |
| 0 | kas | 0.817 | 0.854 | 394.5 | 11.946 | 17.484 | 0.117 | 0.187 |
| 0 | bps_kas | 0.911 | 0.927 | 407.8 | 6.894 | 14.725 | 0.126 | 0.175 |
| 0 | phase | 0.927 | 0.938 | 409.0 | 11.780 | 14.702 | 0.100 | 0.148 |
| 2 | fcfs | 0.875 | 1.000 | 367.0 | 0.054 | 0.421 | 0.0938 | 0.126 |
| 2 | kas | 0.945 | 1.000 | 397.4 | 0.0537 | 0.0670 | 0.0486 | 0.0662 |
| 2 | bps_kas | 0.937 | 1.000 | 394.0 | 0.0556 | 0.0690 | 0.0465 | 0.0641 |
| 2 | phase | 0.929 | 1.000 | 390.2 | 0.0549 | 0.0645 | 0.0462 | 0.0636 |

### Paired Against FCFS

| Rate | Policy | Goodput delta | SLO delta | Output tok/s ratio | TTFT p99 delta | TPOT p99 ratio |
|---:|---|---:|---:|---:|---:|---:|
| 0 | kas | +0.0147 | +2.08 pp | 0.988 | -1.722 | 1.056 |
| 0 | bps_kas | +0.109 | +9.38 pp | 1.021 | -4.482 | 0.985 |
| 0 | phase | +0.125 | +10.42 pp | 1.024 | -4.504 | 0.839 |
| 2 | kas | +0.0696 | 0.00 pp | 1.084 | -0.354 | 0.537 |
| 2 | bps_kas | +0.0614 | 0.00 pp | 1.074 | -0.352 | 0.528 |
| 2 | phase | +0.0540 | 0.00 pp | 1.064 | -0.357 | 0.522 |

## Bucket-Level KAS 归因

rate2 更像持续 decode pressure，因此更适合观察 KAS 的 TPOT 作用。下表只看 output bucket，相对 FCFS：

| Rate | Policy | Output bucket | TPOT p90 delta | TPOT p99 ratio | TTFT p99 ratio |
|---:|---|---|---:|---:|---:|
| 2 | kas | `(64,128]` | -0.0546 | 0.524 | 1.014 |
| 2 | phase | `(64,128]` | -0.0582 | 0.511 | 0.919 |
| 2 | kas | `(128,256]` | -0.0355 | 0.611 | 0.530 |
| 2 | phase | `(128,256]` | -0.0366 | 0.581 | 0.544 |
| 2 | kas | `(256,512]` | -0.0114 | 0.716 | 1.037 |
| 2 | phase | `(256,512]` | -0.0115 | 0.728 | 1.047 |
| 2 | kas | `>512` | +0.0115 | 1.412 | 0.629 |
| 2 | phase | `>512` | +0.0122 | 1.400 | 0.609 |

结论：

1. KAS 的核心收益在主流 output bucket 上成立：`(64,128]`、`(128,256]`、`(256,512]` 的 TPOT p99 ratio 约为 `0.52-0.73`。
2. `>512` bucket 的 TPOT 变差，说明当前 KAS 并没有自然解决超长输出公平性。这个 bucket 每个 seed 约 7 个 request，仍需要更大规模验证。
3. rate2 下 `kas/bps_kas/phase` 的全局 TPOT p99 都约为 FCFS 的一半，并且输出 token 吞吐提升 `6.4%-8.4%`，这是 KAS 相关 claim 的主要证据。

## PBC 归因

PBC 的直接消融是：

```text
phase vs bps_kas
```

### Run-Level Paired `phase - bps_kas`

| Rate | Goodput delta | SLO delta | Output tok/s ratio | TTFT p90 delta | TTFT p99 delta | TPOT p90 ratio | TPOT p99 ratio |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | +0.0154 | +1.04 pp | 1.004 | +4.886 | -0.0227 | 0.795 | 0.854 |
| 2 | -0.0075 | 0.00 pp | 0.990 | -0.0008 | -0.0046 | 0.994 | 0.990 |

### Bucket-Level `phase - bps_kas` at Burst Rate

| Output bucket | SLO delta | TTFT p99 ratio | TPOT p99 ratio | 观察 |
|---|---:|---:|---:|---|
| `(64,128]` | +14.17 pp | 0.425 | 0.898 | 短输出显著改善 |
| `(128,256]` | +2.94 pp | 0.890 | 0.925 | 中短输出改善 |
| `(256,512]` | -2.94 pp | 1.306 | 1.017 | 中长输出变差 |
| `>512` | -5.00 pp | 1.620 | 0.952 | 超长输出 TTFT 变差，TPOT 小幅改善 |

结论：

1. PBC 在 burst decode-heavy 下确实能把资源向 decode tail 倾斜：全局 TPOT p99 ratio 降到 `0.854`，SLO 提升 `1.04 pp`。
2. 代价是明显的 TTFT p90 变差：`+4.886s`。这说明当前 PBC 更像稳定性/压力控制器，而不是无条件 latency optimizer。
3. PBC 的 bucket 行为仍有 tail transfer：短/中短输出改善，但中长和超长输出在 TTFT 上受损。论文中需要把它写成 trade-off-aware control，而不是一味声称全面提升。

## 对论文的影响

当前证据支持如下更稳妥的论文叙事：

1. `BPS`：主张改善 prompt-skew 场景下 dominant prompt buckets 的 TTFT tail，但承认最长 prompt 需要 starvation safeguard。
2. `KAS`：主张在 decode-heavy 场景下显著降低主流 output buckets 的 TPOT tail，并提升 output token throughput。
3. `PBC`：主张作为 cross-stage pressure controller，在 burst 压力下可以把一部分 prefill 预算让给 decode，从而改善 TPOT tail/SLO，但存在 TTFT trade-off，需要单独报告。

当前证据不支持的说法：

- 不应说所有指标都提升。
- 不应说 PBC 是性能主收益来源。
- 不应说 KAS 已经解决超长输出请求的公平性。

## 下一步

1. 扩展到 5 seeds，确认 rate2 下 KAS 的 TPOT p99 ratio 是否稳定。
2. 为 `>512` output bucket 单独设计 long-output stress workload，避免样本过少。
3. 优化 PBC 映射，把 `decode queue pressure` 和 `KV block pressure` 拆成不同控制量，减少 burst 下 TTFT p90 被牺牲的问题。
4. 在主文实验里同时报告 p50/p90/p99、SLO、goodput、output token throughput 和 bucket-level 指标。
