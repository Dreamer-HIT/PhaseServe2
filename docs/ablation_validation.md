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
