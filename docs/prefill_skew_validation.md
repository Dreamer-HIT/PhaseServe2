# Prefill-Skew BPS Validation

更新时间：2026-05-26

## 目的

本文档记录一次专门给 BPS 设计的 prefill-skew workload。此前 heterogeneous workload 更偏 decode/KV pressure，因此 KAS 信号明显，而 BPS 作用不稳定。本实验把 prompt length skew 放大、输出长度缩短，尽量让瓶颈更接近 prefill/context queue。

## Workload

- 结构：1p1d
- 模型：LLaMA2-7B (`/root/data/models/nous-llama2-7b-hf`)
- 请求数：96
- seeds：`0 1`
- rates：burst (`0`)、`6`、`10` req/s
- policies：`fcfs`、`bps`
- prompt mix：`64:0.45,512:0.25,1024:0.20,1536:0.10`
- output mix：`32:0.60,64:0.30,128:0.10`
- `MAX_TOTAL_TOKENS=1800`
- SLO：TTFT 10s，TPOT 1s

注意：最初尝试过 `2048` prompt，但 DistServe context engine 在执行时会出现 `2049` length，超过 `context-max-tokens-per-batch=2048`，导致 FCFS 队首请求不可调度并卡住。因此本 workload 将最大 prompt length 改为 `1536`，避免测到配置边界而非调度策略。

相关脚本：

- `scripts/run_phase_prefill_skew_sweep.sh`
- `scripts/run_phase_hetero_sweep.sh`
- `scripts/run_phase_hetero_1p1d.sh`

结果目录：

- `/root/data/phase_scheduler_results/prefill_skew_bps2_20260526_221201`

## Smoke Test

Smoke 配置：

- `NUM_PROMPTS=12`
- `SEEDS=0`
- `RATES=0`
- `POLICIES="fcfs bps"`

结果目录：

- `/root/data/phase_scheduler_results/prefill_skew_smoke_20260526_221005`

结果：`fcfs` 与 `bps` 均能完成，数据集包含 `64/512/1024/1536` prompt 和 `32/64/128` output。

## 2-Seed 聚合结果

| Rate | Policy | Goodput req/s | SLO submitted | TTFT p50 | TTFT p90 | TTFT p99 | TPOT p90 | TPOT p99 | Output tok/s |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | fcfs | 5.587 | 0.828 | 4.525 | 11.157 | 11.926 | 0.0633 | 0.0822 | 328.8 |
| 0 | bps | 5.468 | 0.865 | 4.204 | 10.325 | 12.867 | 0.0826 | 0.111 | 312.4 |
| 6 | fcfs | 5.464 | 1.000 | 0.0848 | 0.611 | 0.910 | 0.0475 | 0.0728 | 273.7 |
| 6 | bps | 5.530 | 1.000 | 0.0580 | 0.479 | 0.729 | 0.0476 | 0.0645 | 277.3 |
| 10 | fcfs | 6.406 | 1.000 | 1.838 | 3.400 | 4.054 | 0.0729 | 0.0871 | 319.6 |
| 10 | bps | 6.472 | 1.000 | 0.388 | 3.644 | 5.067 | 0.0781 | 0.0924 | 323.5 |

## Paired BPS 相对 FCFS

| Rate | Goodput ratio | SLO delta | TTFT p90 delta | TTFT p99 delta | TPOT p90 ratio | TPOT p99 ratio | Output tok/s ratio |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 1.005 | +0.0365 | -0.832 | +0.941 | 1.305 | 1.342 | 0.952 |
| 6 | 1.013 | 0.000 | -0.132 | -0.181 | 0.990 | 0.904 | 1.013 |
| 10 | 1.016 | 0.000 | +0.244 | +1.013 | 1.091 | 1.065 | 1.016 |

## 观察

1. BPS 的最佳信号出现在 rate6：goodput 和 output tok/s 提升约 `1.3%`，TTFT p90/p99 下降，TPOT p99 下降约 `9.6%`。
2. burst/rate0 下 BPS 提升 SLO submitted，但 output tok/s 下降，TTFT p99 和 TPOT tail 变差。说明 burst 下 BPS 的 batch shaping 可能牺牲了部分尾部请求。
3. rate10 下 BPS goodput 略高，但 TTFT p90/p99 和 TPOT tail 变差。说明提高 rate 并不会自动放大 BPS 收益；当压力过高时，当前 BPS scoring 仍可能做出不利于 tail 的组合。
4. 因此，之前 “rate 不够导致 BPS 不明显” 只解释了一部分。更准确的判断是：BPS 需要 prefill-skew workload 才有机会发挥，但当前算法对 arrival order、oldest protection 和 batch scoring 很敏感。

## 对方法论的影响

当前证据还不能支持“BPS 稳定改善 prefill tail”这个强 claim。更稳妥的写法是：

> BPS 在 prompt-skew 且中等压力场景下可以改善 TTFT tail 和 goodput，但当前实现仍需要更稳健的 age-aware scoring，以避免 burst 或过高 arrival rate 下的 tail regression。

这意味着 BPS 仍值得保留，但需要改进后再进入最终论文主贡献。相比之下，KAS 的贡献目前更稳。

## 下一步

1. 调整 BPS scoring：降低固定 `oldest_bonus`，改成连续 age-aware bonus，避免 protected oldest 在 burst 下过强牵引 batch。
2. 增加 BPS 内部 ablation：`bucket_only`、`no_oldest_bonus`、`age_bonus`。
3. 增加 prompt-bucket breakdown：分别统计短 prompt 与长 prompt 的 TTFT p90/p99，判断 BPS 是否在不同 prompt bucket 之间转移尾延迟。
4. 在 rate6 附近做更细 sweep：`4/6/8`，确认 BPS 的有效压力区间。
5. 如果改进后 BPS 仍只在窄区间有效，论文中应把 BPS 降级为辅助策略，把 KAS 作为主算法贡献。
