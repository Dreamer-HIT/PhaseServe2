# Bucket Breakdown Validation

更新时间：2026-05-26

## 目的

本文档记录 bucket-level 指标补强。目标是把组件消融从“整体 TTFT/TPOT 是否变化”推进到“组件是否改善了它理论上应该改善的 failure mode”：

- BPS 应主要改善 prompt-skew 下的 TTFT，因此重点看 `prompt_bucket -> TTFT p50/p90/p99`。
- KAS 应主要改善 decode/KV pressure 下的 TPOT，因此重点看 `output_bucket -> TPOT p50/p90/p99`。
- 如果某个组件只改善整体均值，却把 tail 转移给某个 bucket，这个 bucket breakdown 应该能暴露出来。

## 实现

改动位置：

- `benchmarks/phase_native_benchmark.py`
- `benchmarks/phase_analyze_sweep.py`

单次 benchmark summary 的 `buckets` 字段现在记录：

- `submitted`、`completed`、`failed`、`goodput`
- `slo_attainment_completed`、`slo_attainment_submitted`
- `prompt_len`、`output_len`
- `ttft_s`、`tpot_s`、`latency_s`
- `context_queue_s`、`context_exec_s`
- `bridge_queue_s`、`migration_s`
- `decode_queue_s`、`decode_exec_s`

Sweep analyzer 现在额外输出：

- `<prefix>.bucket_runs.csv`
- `<prefix>.bucket_grouped.csv`
- `<prefix>.bucket_paired.csv`
- `<prefix>.bucket_paired_summary.csv`
- `<prefix>.bucket.md`

这些文件不会替代原有 run-level 表，而是作为解释 BPS/KAS 归因的第二层证据。

## 回放验证

使用已有实验结果重新生成 bucket 分析，不需要重跑模型：

```bash
python3 benchmarks/phase_analyze_sweep.py \
  /root/data/phase_scheduler_results/bps_internal2_20260526_223425 \
  --output-prefix /root/data/phase_scheduler_results/bps_internal2_20260526_223425/sweep_analysis_v2

python3 benchmarks/phase_analyze_sweep.py \
  /root/data/phase_scheduler_results/hetero_1p1d_ablation2_20260526_212556 \
  --output-prefix /root/data/phase_scheduler_results/hetero_1p1d_ablation2_20260526_212556/sweep_analysis_v2
```

输出：

- BPS prefill-skew：30 runs，180 bucket rows
- KAS ablation：20 runs，160 bucket rows

## BPS：Prompt Bucket 视角

结果目录：

- `/root/data/phase_scheduler_results/bps_internal2_20260526_223425/sweep_analysis_v2.bucket_paired_summary.csv`

下表只看默认 `bps` 相对 `fcfs`，指标为 TTFT p99：

| Rate | Prompt bucket | TTFT p99 delta | TTFT p99 ratio | 观察 |
|---:|---|---:|---:|---|
| 0 | `(0,64]` | -7.201 | 0.421 | 短 prompt 明显改善 |
| 0 | `(256,512]` | -3.143 | 0.774 | 中短 prompt 改善 |
| 0 | `(512,1024]` | -2.182 | 0.809 | 中长 prompt 改善 |
| 0 | `(1024,2048]` | +1.643 | 1.294 | 最长 prompt 变差 |
| 6 | `(0,64]` | -0.189 | 0.975 | 短 prompt 小幅改善 |
| 6 | `(256,512]` | -0.047 | 0.975 | 中短 prompt 小幅改善 |
| 6 | `(512,1024]` | -0.095 | 0.957 | 中长 prompt 小幅改善 |
| 6 | `(1024,2048]` | +0.088 | 1.088 | 最长 prompt 轻微变差 |
| 10 | `(0,64]` | -3.167 | 0.226 | 短 prompt 明显改善 |
| 10 | `(256,512]` | -1.099 | 0.983 | 中短 prompt 改善但 seed 方差较大 |
| 10 | `(512,1024]` | +0.483 | 1.303 | 中长 prompt 变差 |
| 10 | `(1024,2048]` | +0.946 | 1.366 | 最长 prompt 变差 |

结论：

1. BPS 的理论方向是对的：它确实主要作用在 TTFT，而且对短/中 prompt bucket 的 TTFT p99 改善最明显。
2. 但当前 BPS 有 tail transfer：最长 prompt bucket 在多个 rate 下变差，说明当前 score 更偏向提高 batch fill 和短/中 prompt 周转。
3. 因此论文不能只写“BPS 降低 TTFT tail”，更准确的表述是：BPS improves TTFT for dominant prompt buckets under prompt skew, but requires starvation-aware safeguards for the longest prompts.

## KAS：Output Bucket 视角

结果目录：

- `/root/data/phase_scheduler_results/hetero_1p1d_ablation2_20260526_212556/sweep_analysis_v2.bucket_paired_summary.csv`

下表只看 `kas` 相对 `fcfs`，指标为 TPOT p99：

| Rate | Output bucket | TPOT p99 delta | TPOT p99 ratio | 观察 |
|---:|---|---:|---:|---|
| 0 | `(16,64]` | -0.0233 | 0.865 | 改善 |
| 0 | `(64,128]` | -0.0218 | 0.818 | 明显改善 |
| 0 | `(128,256]` | -0.0134 | 0.785 | 明显改善 |
| 0 | `(256,512]` | +0.0037 | 1.097 | 变差，样本较少 |
| 0 | `>512` | +0.0018 | 1.068 | 样本很少，不宜解释 |
| 4 | `(16,64]` | -0.0690 | 0.551 | 显著改善 |
| 4 | `(64,128]` | -0.0227 | 0.701 | 显著改善 |
| 4 | `(128,256]` | -0.0159 | 0.669 | 显著改善 |
| 4 | `(256,512]` | -0.0002 | 0.998 | 基本持平 |
| 4 | `>512` | +0.0062 | 1.296 | 样本很少，不宜解释 |

结论：

1. KAS 的理论方向也成立：在常见 output bucket 上，尤其 rate4 下，TPOT p99 有稳定改善。
2. 当前 heterogeneous workload 的超长 output bucket 样本太少，不能用来支持或否定 KAS 对长输出的效果。
3. 下一轮 KAS 专项实验必须使用 decode-heavy output mix，让 `(256,512]` 和 `>512` 有足够样本，否则无法写出顶会级别的长 decode 结论。

## 对论文实验的影响

最终论文主文应该按 failure mode 组织消融：

1. BPS 专项表：prompt-skew workload，主指标是 prompt bucket 的 TTFT p90/p99。
2. KAS 专项表：decode-heavy workload，主指标是 output bucket 的 TPOT p90/p99。
3. Full-system 表：`phase` vs `bps_kas`，主指标是 SLO/goodput，以及是否避免某些 bucket 被牺牲。

这比只放全局 p50/p90/p99 更像系统论文，因为它解释了每个组件改善了哪类请求、是否把成本转移给了另一类请求。

## 下一步

1. BPS：跑 `rates=4/6/8`，只保留 `fcfs/bps/bps_kas`，用 prompt bucket TTFT 作为主表。
2. KAS：设计 decode-heavy workload，把 output mix 提高到 `64/128/256/512`，用 output bucket TPOT 作为主表。
3. PBC：只在 `phase vs bps_kas` 中讨论，观察 bucket-level SLO 是否更稳，而不是单独 claim 性能主收益。
