# PhaseServe Ablation Validation

更新时间：2026-05-26

## 目的

本文档记录 PhaseServe 当前 ablation 框架和第一轮 attribution probe。它不是最终论文实验结果，而是用于回答一个更基础的问题：当前端到端收益到底来自 BPS、KAS、PBC，还是它们的组合。

## Ablation Policy 定义

| Policy | Context scheduler | Decode scheduler | Dynamic PBC | 目的 |
|---|---|---|---|---|
| `fcfs` | FCFS | FCFS | off | DistServe baseline |
| `bps` | BPS | FCFS | static budget | 隔离 prefill shaping |
| `kas` | FCFS | KAS | static budget | 隔离 decode active-set shaping |
| `bps_kas` | BPS | KAS | static budget | 隔离两个局部 scheduler 的组合 |
| `phase` | BPS | KAS | on | 当前 PhaseServe full |

其中 static budget 通过 `PHASESERVE_PBC_DISABLE_DYNAMIC=1` 实现。它保留 BPS/KAS 的局部调度逻辑，但关闭 pressure-to-budget 动态收缩，用来判断 PBC 是否真的贡献了额外收益。

## 论文呈现原则

最终论文主文不应展示所有内部 variant。主文 ablation 需要回答的是“核心机制是否必要”，而不是“每个调参项是否有效”。建议主文保留以下 4 到 5 个 policy：

| Policy | 用途 |
|---|---|
| `fcfs` | DistServe baseline |
| `kas` | 验证 decode-side KV-aware active-set scheduling 的独立贡献 |
| `bps_kas` | 验证 prefill-side batch shaping 与 KAS 的组合效果 |
| `phase` | 验证完整系统，包括动态 PBC |
| `bps` | 只在 prefill-skew workload 中保留，用于说明 BPS 的适用边界 |

`bps_bucket_only`、`bps_no_oldest_bonus`、`bps_age_bonus` 这类变体只作为内部诊断或 appendix 候选。除非其中某个变体成为最终采用的算法版本，否则不进入主文核心表格。主文最多用一张小型 “BPS design sensitivity” 图说明 BPS 对 scoring 设计敏感，避免把论文叙事变成大规模参数搜索。

最终主文的机制归因应结合 `docs/bucket_breakdown_validation.md`：BPS 用 prompt bucket 的 TTFT 证明，KAS 用 output bucket 的 TPOT 证明，PBC 用 `phase` vs `bps_kas` 的 full-system 稳定性证明。

相关脚本：

- `scripts/run_phase_hetero_1p1d.sh`
- `scripts/run_phase_hetero_sweep.sh`
- `scripts/run_phase_ablation_sweep.sh`
- `benchmarks/phase_analyze_sweep.py`

## Smoke Test

Smoke 配置：

- 1p1d
- LLaMA2-7B
- `NUM_PROMPTS=8`
- `SEEDS=0`
- `RATES=0`
- `POLICIES="fcfs bps kas bps_kas phase"`

结果目录：

- `/root/data/phase_scheduler_results/hetero_1p1d_ablation_smoke_20260526_205535`

结果：五个 policy 均可启动、完成 benchmark、产出 summary 和 paired analysis。

## Seed0 Attribution Probe

Probe 配置：

- 1p1d
- LLaMA2-7B
- `NUM_PROMPTS=48`
- `SEEDS=0`
- `RATES="0 4"`
- `POLICIES="fcfs bps kas bps_kas phase"`
- `gpu_memory_utilization=0.38`
- SLO：TTFT 10s，TPOT 1s

结果目录：

- `/root/data/phase_scheduler_results/hetero_1p1d_ablation_seed0_20260526_210010`

注意：这是 single-seed attribution probe，只能用于发现方向，不能写成最终论文结论。

## 聚合结果

| Rate | Policy | Goodput req/s | SLO submitted | TTFT p90 | TTFT p99 | TPOT p90 | TPOT p99 | Output tok/s |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 0 | fcfs | 1.267 | 0.917 | 9.358 | 10.438 | 0.139 | 0.149 | 381.4 |
| 0 | bps | 1.206 | 0.958 | 8.541 | 11.461 | 0.142 | 0.157 | 347.4 |
| 0 | kas | 1.350 | 0.958 | 8.710 | 10.312 | 0.116 | 0.135 | 388.8 |
| 0 | bps_kas | 1.273 | 0.938 | 7.120 | 15.057 | 0.112 | 0.178 | 374.7 |
| 0 | phase | 1.322 | 0.938 | 9.468 | 10.955 | 0.112 | 0.138 | 389.3 |
| 4 | fcfs | 1.408 | 1.000 | 0.142 | 4.258 | 0.157 | 0.172 | 388.6 |
| 4 | bps | 1.403 | 1.000 | 0.075 | 3.848 | 0.158 | 0.173 | 387.2 |
| 4 | kas | 1.464 | 1.000 | 0.070 | 0.335 | 0.092 | 0.100 | 404.1 |
| 4 | bps_kas | 1.441 | 1.000 | 0.066 | 0.362 | 0.094 | 0.102 | 397.8 |
| 4 | phase | 1.428 | 1.000 | 0.067 | 0.432 | 0.093 | 0.101 | 394.0 |

## 初步观察

1. `kas` 是当前收益的主来源。rate0 下，`kas` 相比 `fcfs` 的 goodput 提升约 `6.6%`，TPOT p99 降低约 `9.5%`；rate4 下，goodput 提升约 `4.0%`，TTFT p99 从 `4.258s` 降到 `0.335s`，TPOT p99 从 `0.172s` 降到 `0.100s`。
2. `bps` 单独收益不稳定。rate0 下它提高了 SLO submitted，但 goodput 和 output tok/s 下降，TTFT p99 变差；rate4 下它对 TTFT tail 有小幅帮助，但 TPOT 基本没有改善。
3. `bps_kas` 没有稳定优于 `kas`。这说明当前 BPS 可能与 KAS 的 decode-side 收益存在交互副作用，尤其在 burst/rate0 下 TTFT p99 被放大。
4. `phase` 没有稳定优于 `kas`。这说明当前动态 PBC 还不能 claim 为主要收益来源；PBC 在论文中若要作为核心贡献，需要进一步证明 pressure chain 和 full-system ablation 收益。

## 对方法论的影响

当前证据支持把 KAS 作为近期实现优化重点，而不是马上扩展更复杂的全局 PBC。更准确的阶段判断是：

- KAS 的 KV-constrained attained-service scheduling 已经有明确端到端信号。
- BPS 需要重新检查 scoring、protected-oldest 触发和 prefill token budget，避免与 decode tail 优化互相抵消。
- PBC claim 需要降级或继续强化。仅有当前结果还不能证明 full PhaseServe 的动态 budget 优于静态局部 scheduler。

## 下一步

1. 把 ablation 扩展到 5 seeds，至少覆盖 rate0/rate4。
2. 增加 `kas_no_evict` 和 `kas_no_nexttoken_reserve`，拆分 KAS 内部贡献。
3. 调整 BPS：降低 oldest bonus 或改成 age-aware score，避免 burst 下长 prompt 牵引过强。
4. 增加 PBC observability：mode switch rate、budget variance、pressure overshoot、bridge queue p90/p99。
5. 若 5-seed 仍显示 `kas >= phase`，则论文方法论应把 PBC 从核心贡献降级为系统稳定性机制，或重新设计统一 PBC。

## 2-Seed Ablation Probe

Probe 配置：

- 1p1d
- LLaMA2-7B
- `NUM_PROMPTS=48`
- `SEEDS="0 1"`
- `RATES="0 4"`
- `POLICIES="fcfs bps kas bps_kas phase"`
- `gpu_memory_utilization=0.38`
- SLO：TTFT 10s，TPOT 1s

结果目录：

- `/root/data/phase_scheduler_results/hetero_1p1d_ablation2_20260526_212556`

注意：这仍然只是 2-seed probe，不能替代最终 5-seed/多规模实验；但它已经能检验 single-seed 观察是否完全偶然。

### 聚合结果

| Rate | Policy | Goodput req/s | SLO submitted | TTFT p90 | TTFT p99 | TPOT p90 | TPOT p99 | Output tok/s |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 0 | fcfs | 1.481 | 0.958 | 7.299 | 9.298 | 0.148 | 0.164 | 368.0 |
| 0 | bps | 1.439 | 0.958 | 6.403 | 11.354 | 0.148 | 0.189 | 354.7 |
| 0 | kas | 1.579 | 0.979 | 6.825 | 8.935 | 0.126 | 0.143 | 383.8 |
| 0 | bps_kas | 1.568 | 0.958 | 6.087 | 12.509 | 0.127 | 0.171 | 386.5 |
| 0 | phase | 1.499 | 0.979 | 7.137 | 8.170 | 0.113 | 0.152 | 366.6 |
| 4 | fcfs | 1.634 | 1.000 | 0.100 | 2.203 | 0.112 | 0.153 | 388.7 |
| 4 | bps | 1.631 | 1.000 | 0.066 | 1.979 | 0.113 | 0.154 | 388.2 |
| 4 | kas | 1.716 | 1.000 | 0.063 | 0.192 | 0.066 | 0.085 | 408.0 |
| 4 | bps_kas | 1.724 | 1.000 | 0.060 | 0.188 | 0.067 | 0.087 | 409.2 |
| 4 | phase | 1.703 | 1.000 | 0.059 | 0.240 | 0.068 | 0.086 | 404.4 |

### Paired 相对 FCFS

| Rate | Policy | Goodput ratio | SLO delta | TTFT p99 delta | TPOT p90 ratio | TPOT p99 ratio | Output tok/s ratio |
|---:|---|---:|---:|---:|---:|---:|---:|
| 0 | bps | 0.965 | 0.000 | +2.056 | 0.999 | 1.160 | 0.966 |
| 0 | kas | 1.067 | +0.0208 | -0.363 | 0.854 | 0.871 | 1.043 |
| 0 | bps_kas | 1.052 | 0.000 | +3.211 | 0.856 | 1.051 | 1.053 |
| 0 | phase | 1.018 | +0.0208 | -1.128 | 0.770 | 0.926 | 0.995 |
| 4 | bps | 0.999 | 0.000 | -0.223 | 1.007 | 1.006 | 0.999 |
| 4 | kas | 1.050 | 0.000 | -2.010 | 0.601 | 0.556 | 1.050 |
| 4 | bps_kas | 1.053 | 0.000 | -2.014 | 0.609 | 0.573 | 1.053 |
| 4 | phase | 1.040 | 0.000 | -1.963 | 0.616 | 0.564 | 1.040 |

### 2-Seed 观察

1. `kas` 的贡献进一步坐实。rate0 下 goodput 平均提升 `6.7%`，SLO submitted 提升 `2.08 pp`，TPOT p99 降低约 `12.9%`；rate4 下 goodput 提升 `5.0%`，TPOT p99 降低约 `44.4%`，TTFT p99 降低约 `2.01s`。
2. `phase` 不是当前最强组合。它在 rate0 下有最好的 TTFT p99 和 TPOT p90，但 goodput/output tok/s 低于 `kas`；rate4 下也没有超过 `kas` 或 `bps_kas`。
3. `bps` 单独仍然不稳定。rate0 下 TPOT p99 和 TTFT p99 都变差，rate4 下基本只是略微改善 TTFT tail。
4. `bps_kas` 在 rate4 接近最强，但 rate0 下 TTFT p99/TPOT p99 不稳定，说明 BPS 与 KAS 的组合还没有调好。

### 决策

当前不应继续把 PBC 作为“已验证核心贡献”来扩写。下一步更合理的是：

1. 先拆 KAS 内部 ablation：`kas_no_evict`、`kas_no_nexttoken_reserve`、`kas_no_resident_preference`。
2. 重新调 BPS，优先降低 burst 下对 TTFT p99 的伤害。
3. 如果后续 5-seed 仍是 `kas >= phase`，方法论文档需要改成 KAS-first：PBC 作为稳定性/预算接口，而不是主收益来源。

## BPS 内部变体结论

内部诊断脚本 `scripts/run_phase_bps_internal_sweep.sh` 已覆盖 `bps_bucket_only`、`bps_no_oldest_bonus`、`bps_age_bonus`。2-seed prefill-skew 结果见 `docs/prefill_skew_validation.md`，结果目录为：

- `/root/data/phase_scheduler_results/bps_internal2_20260526_223425`

结论是：默认 `bps` 在 burst/rate0 和 rate6 下比三个内部变体更均衡；`bucket_only` 有时吞吐更高但 tail 更差；`no_oldest_bonus` 会把部分风险转移到 TPOT tail；`age_bonus` 没有稳定改善。因此，当前最终论文 ablation 不需要包括全部内部变体。更合理的结构是：

1. 主文：`fcfs`、`kas`、`bps_kas`、`phase`，必要时在 prefill-skew workload 加 `bps`。
2. Appendix 或技术报告：只放一个 BPS sensitivity 小表，说明为什么没有把 `bucket_only/age_bonus` 作为最终算法。
3. 后续若 BPS 被重新设计并显著优于当前默认版本，则用新 BPS 替换 `bps` policy，而不是追加更多 variant。
