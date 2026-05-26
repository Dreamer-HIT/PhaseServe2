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

## BPS 内部消融

为了判断 BPS 的不稳定来自哪个 scoring 组件，新增了三个只用于内部诊断的变体：

| Policy | 含义 | 论文定位 |
|---|---|---|
| `bps_bucket_only` | 只按 token bucket fill 选 batch，不考虑 padding waste、KV block risk 和 oldest protection | 内部诊断，不进最终主表 |
| `bps_no_oldest_bonus` | 保留 BPS 的 fill/waste/risk score，但移除 fixed oldest bonus | 内部诊断，可作为 appendix 候选 |
| `bps_age_bonus` | 把 fixed oldest bonus 改成随等待时间增长的连续 age bonus | 内部诊断，不进最终主表 |

相关脚本：

- `scripts/run_phase_bps_internal_sweep.sh`

Smoke 结果目录：

- `/root/data/phase_scheduler_results/bps_internal_smoke_20260526_223004`

2-seed 结果目录：

- `/root/data/phase_scheduler_results/bps_internal2_20260526_223425`

配置：

- 1p1d
- LLaMA2-7B
- `NUM_PROMPTS=96`
- `SEEDS="0 1"`
- `RATES="0 6 10"`
- `POLICIES="fcfs bps bps_bucket_only bps_no_oldest_bonus bps_age_bonus"`
- prompt/output mix 与上文 prefill-skew workload 相同

### 聚合结果

| Rate | Policy | Goodput req/s | SLO submitted | TTFT p90 | TTFT p99 | TPOT p90 | TPOT p99 | Output tok/s |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 0 | fcfs | 5.455 | 0.823 | 11.262 | 12.541 | 0.0748 | 0.0852 | 324.5 |
| 0 | bps | 6.045 | 0.932 | 8.883 | 12.085 | 0.0699 | 0.0772 | 322.6 |
| 0 | bps_bucket_only | 5.279 | 0.880 | 10.213 | 12.728 | 0.0726 | 0.0818 | 299.0 |
| 0 | bps_no_oldest_bonus | 5.791 | 0.911 | 9.835 | 12.003 | 0.0713 | 0.0968 | 315.5 |
| 0 | bps_age_bonus | 5.377 | 0.833 | 10.987 | 12.938 | 0.0721 | 0.0872 | 318.3 |
| 6 | fcfs | 5.504 | 1.000 | 0.521 | 0.760 | 0.0464 | 0.0732 | 275.9 |
| 6 | bps | 5.538 | 1.000 | 0.473 | 0.704 | 0.0469 | 0.0643 | 277.7 |
| 6 | bps_bucket_only | 5.594 | 1.000 | 0.453 | 0.885 | 0.0489 | 0.0733 | 280.6 |
| 6 | bps_no_oldest_bonus | 5.536 | 1.000 | 0.467 | 0.726 | 0.0455 | 0.0649 | 277.6 |
| 6 | bps_age_bonus | 5.577 | 1.000 | 0.422 | 0.929 | 0.0486 | 0.0730 | 279.8 |
| 10 | fcfs | 6.396 | 1.000 | 3.423 | 4.078 | 0.0728 | 0.0871 | 319.1 |
| 10 | bps | 6.459 | 1.000 | 3.811 | 4.576 | 0.0787 | 0.0916 | 322.9 |
| 10 | bps_bucket_only | 6.543 | 1.000 | 3.457 | 4.929 | 0.0787 | 0.0900 | 326.9 |
| 10 | bps_no_oldest_bonus | 6.363 | 1.000 | 3.651 | 5.128 | 0.0775 | 0.0917 | 318.2 |
| 10 | bps_age_bonus | 6.478 | 1.000 | 3.798 | 4.567 | 0.0797 | 0.0908 | 323.8 |

### 观察

1. `bps` 默认 score 在 burst/rate0 下最均衡：goodput 相对 `fcfs` 提升约 `15.2%`，SLO submitted 提升 `10.9 pp`，TTFT p90 与 TPOT p99 均下降，output tok/s 基本持平。
2. `bps_bucket_only` 能在 rate6/rate10 拿到最高 throughput，但 tail latency 不稳定，尤其 TTFT p99 在 rate6/rate10 都差于默认 `bps`。
3. `bps_no_oldest_bonus` 在 rate0 的 TTFT p99 略好于默认 `bps`，但 TPOT p99 明显变差；说明 fixed oldest bonus 不是唯一问题，去掉它会把风险转移到 decode-side tail。
4. `bps_age_bonus` 没有带来稳定收益，rate0/rate6 的 TTFT p99 都更差。当前 age bonus 公式不足以替代原有 oldest protection。
5. 这些变体的价值主要是定位 BPS 设计空间，而不是构成最终论文 ablation。最终主文不应展示所有 variant，否则会把贡献叙事稀释成调参实验。

### 结论

BPS 的下一步不应只是继续调 `oldest_bonus`，而应把目标改成更明确的 dual-objective batch selection：在 prefill 端优化 token fill/padding waste 的同时，显式约束进入 decode 的 KV block risk 和尾部请求年龄。当前默认 BPS 仍是三种内部变体中最适合保留的版本，但其 claim 应限定为“在 prompt-skew、中等压力或 burst 场景下改善 prefill-side batching 与 SLO attainment”，不能写成普遍提升所有 tail 指标。

更细的 bucket-level 结果见 `docs/bucket_breakdown_validation.md`。该结果显示 BPS 的 TTFT 收益主要集中在短/中 prompt bucket，最长 prompt bucket 仍可能退化，因此后续 BPS 优化必须加入更强的 long-prompt starvation guard。

## 下一步

1. 在 rate6 附近做更细 sweep：`4/6/8`，用 prompt bucket TTFT 确认 BPS 的有效压力区间。
2. 重新设计 BPS score，使 oldest/age 只作为 starvation guard，并加入 long-prompt protection。
3. 如果改进后 BPS 仍只在窄区间有效，论文中应把 BPS 定位为辅助机制，把 KAS 作为主算法贡献。
