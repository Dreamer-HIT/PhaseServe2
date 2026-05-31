# Stage 4L：OPT-13B + ShareGPT Bridge Budget Repair

更新时间：2026-05-31

## 本阶段目标

本阶段回到 Layer 1 主端到端真实 workload，目标是在 `OPT-13B + ShareGPT`、1P1D、128 requests、seed0 上先找出一个稳定的 PhaseServe full end-to-end 区间，使 PhaseServe 相比 DistServe/FCFS 在同一请求集合和同一 Poisson arrival 下：

- TTFT 的 `p50/p90/p95/p99` 中至少两个指标改善 `>=20%`；
- TPOT 的 `p50/p90/p95/p99` 中至少两个指标改善 `>=20%`；
- rate 粒度覆盖 `0.5`，并优先寻找连续区间；
- 所有结论只作为 seed0 收敛和代码修复依据，正式论文还需要补 seed1/seed2。

## 读取和修改的文件

读取：

- `remote_distserve/distserve/decoding_stage_scheduler.py`
- `remote_distserve/scripts/run_phase_hetero_1p1d.sh`
- 既有 FCFS baseline summary：
  - `/root/data/phase_scheduler_results/layer1_opt13b_sharegpt_fastlane_fine_20260530_212533/seed_0`
  - `/root/data/phase_scheduler_results/layer1_opt13b_sharegpt_broad_20260530_173036/seed_0_sweep/seed_0`

修改：

- `remote_distserve/distserve/decoding_stage_scheduler.py`

## 诊断结论

旧的 short-output fastlane 能显著改善 TPOT，但在 global rate `3.5` 以后仍会把部分短输出请求提前送入 decode，长 prompt 的 first-token wait 没有足够快地被偿还，导致 TTFT tail 只有 p50 一个指标稳定超过 20%。

进一步调 `fastlane guard wait` 和 `short-output extra block` 后发现：仅收紧 fastlane 不能解决问题。核心瓶颈是 KAS bridge admission 的 waiting-block budget 太保守。原始 `waiting_block_prop_threshold=0.05` 使已经 prefill 完成的请求容易停在 bridge/unaccepted queue；这会直接进入 TTFT，但不会表现为 decode batch 本身的 TPOT 问题。

因此本轮修复把 KAS 的 bridge feasibility budget 从固定保守值改为 pressure-aware 的 bridge waiting budget：

- full `phase` 默认 `PHASESERVE_KAS_BRIDGE_WAITING_BLOCK_PROP=0.20`；
- 只在 bridge/first-token pressure 足够高且 decode hard pressure 未触发时进入 relaxed bridge admission；
- short-output fastlane 保持开启，但加入 long-prompt debt guard；
- full `phase` 默认 `PHASESERVE_KAS_BRIDGE_FASTLANE_GUARD_WAIT_S=12.0`；
- `PHASESERVE_KAS_BRIDGE_HOL_BYPASS=0` 和 bridge eviction 继续保持关闭。

这个修复的语义是：PBC 检测到 first-token/bridge pressure 后，不只是改变 decode ordering，还要扩大进入 decode waiting queue 的可行预算；否则 BPS 已完成的 prefill 会被卡在 bridge，TTFT tail 仍然无法闭环。

## 关键结果

固定 workload：

- Model: `/root/data/models/opt-13b`
- Dataset: `/root/data/phase_scheduler_results/layer1_opt13b_sharegpt_broad_20260530_173036/datasets/opt13b_sharegpt_seed_0_128.ds`
- Requests: 128
- Seed: dataset seed0, benchmark seed0
- Arrival: Poisson
- 1P1D, 2 GPUs

候选配置验证目录：

- `/root/data/phase_scheduler_results/layer1_opt13b_sharegpt_bridge_budget_validate_20260530_234341`

对比口径：

- global rate `2/2.5/3/3.5` 使用 fine sweep 中的同 workload FCFS；
- global rate `4` 使用 broad sweep 中的同 workload FCFS；
- improvement = `(DistServe - PhaseServe) / DistServe`，正数代表 PhaseServe 更好。

| Global Rate | Per-GPU Rate | SLO pp | Goodput Δ | TTFT p50/p90/p95/p99 | TTFT wins | TPOT p50/p90/p95/p99 | TPOT wins |
|---:|---:|---:|---:|---|---:|---|---:|
| 2.0 | 1.00 | +23.4 | +0.277 | +26.8/+97.0/+97.1/+97.3 | 4 | +39.0/+79.1/+80.1/+79.0 | 4 |
| 2.5 | 1.25 | +30.5 | +0.378 | +92.9/+88.1/+79.2/+77.1 | 4 | +36.5/+45.2/+35.9/+51.5 | 4 |
| 3.0 | 1.50 | +19.5 | +0.234 | +97.6/+64.1/+61.5/+62.0 | 4 | +24.8/+41.3/+28.8/+33.2 | 4 |
| 3.5 | 1.75 | +14.1 | +0.162 | +98.0/+53.1/+52.5/+53.4 | 4 | +20.1/+38.2/+29.1/+27.1 | 4 |
| 4.0 | 2.00 | +13.3 | +0.162 | +98.2/+37.6/+34.8/+33.0 | 4 | +19.6/+42.9/+32.4/+14.8 | 2 |

默认代码 smoke：

- Result: `/root/data/phase_scheduler_results/layer1_opt13b_sharegpt_default_bridge_budget_smoke_20260531_000121`
- Global rate `4.0` 不带调参环境变量；
- TTFT improvement: `+98.2/+37.0/+33.3/+32.0`，4 个指标达标；
- TPOT improvement: `+20.1/+41.4/+32.6/+16.5`，3 个指标达标；
- SLO attainment: `+14.8 pp`；
- goodput: `+0.173 req/s`。

## High-Rate Boundary

default code high-rate sweep：

- Phase root: `/root/data/phase_scheduler_results/layer1_opt13b_sharegpt_default_bridge_budget_highrates_20260531_000620`
- FCFS rate 5 root: `/root/data/phase_scheduler_results/layer1_opt13b_sharegpt_fcfs_rate5_20260531_001956`
- FCFS rate 4.5 + Phase rate 4.5 root: `/root/data/phase_scheduler_results/layer1_opt13b_sharegpt_rate45_default_20260531_002356`

| Global Rate | Per-GPU Rate | SLO pp | Goodput Δ | TTFT p50/p90/p95/p99 | TTFT wins | TPOT p50/p90/p95/p99 | TPOT wins | 结论 |
|---:|---:|---:|---:|---|---:|---|---:|---|
| 4.5 | 2.25 | +11.7 | +0.133 | +93.4/+35.6/+33.9/+22.8 | 4 | +14.9/+32.6/+9.1/+11.6 | 1 | TPOT 不达标 |
| 5.0 | 2.50 | +10.2 | +0.111 | +93.1/+32.0/+31.8/+23.1 | 4 | +10.3/+34.2/+15.4/+36.6 | 2 | 单点达标，但与 4.5 不连续 |
| 6.0 | 3.00 | +6.2 | +0.063 | +84.8/+26.9/+27.0/+26.8 | 4 | +2.4/+18.7/+4.3/+21.8 | 1 | TPOT 不达标 |
| 8.0 | 4.00 | +3.9 | +0.028 | +66.5/+26.1/+26.4/+21.3 | 4 | -1.5/+21.4/+14.3/+39.0 | 2 | stress 单点，不作为连续主图 |
| 10.0 | 5.00 | +3.1 | +0.026 | +59.7/+27.0/+26.1/+17.6 | 3 | +2.0/+22.3/+15.2/+34.8 | 2 | stress 单点，不作为连续主图 |

High-rate 结论：

- 当前最干净的连续主图区间仍是 global rate `2.0-4.0`，粒度 `0.5`。
- rate `4.5` 的 TTFT 很强，但 TPOT 只有 p90 达标，因此不能把主图区间直接扩到 `5.0`。
- rate `5.0`、`8.0`、`10.0` 有若干单点达标，但中间存在 `4.5` 和 `6.0` 的 TPOT 断点，只能作为 stress/边界现象，不适合作为连续 positive window。

## 阶段验收

已完成：

- 代码默认配置已同步到服务器，并通过本地和远端 `py_compile`。
- global rate `2.0-4.0`、粒度 `0.5` 的 seed0 连续区间达标。
- default code smoke 证明效果不依赖额外实验环境变量。

未完成：

- 当前连续区间换算成 per-GPU rate 是 `1.0-2.0 req/s/GPU`；若继续坚持 `2.0 req/s/GPU` 宽度，还需要把高 rate 边界继续推到 global `6.0` 或更高。
- 目前只是 seed0；正式图至少补 seed1，最好补 seed2。
- LLaMA2-13B + ShareGPT / LongBench 尚未复验该 bridge budget 默认值。

## 下一步

1. 在 global rate `2.0-4.0` 主图区间上补 seed1/seed2。
2. 基于同一区间做核心消融：Full、w/o PBC、w/o BPS、w/o KAS。
3. 对 rate `4.5-6.0` 做机制分析，解释为什么 TTFT 仍改善但 TPOT 出现断点。
4. 在 LLaMA2-13B + ShareGPT / LongBench 上复验 bridge-budgeted KAS 默认值。
