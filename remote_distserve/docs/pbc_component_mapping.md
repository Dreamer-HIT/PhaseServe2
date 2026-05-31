# PBC Component-Wise Budget Mapping

更新时间：2026-05-27

## 目的

本文档记录 PBC 从单一 `rho_down` 控制改为分量化 pressure-to-budget mapping 的实现。这个改动对应 `docs/current_progress.md` 中的 Step 1。

旧实现把：

```text
rho_down = aggregate(bridge, decode, kv, swap)
```

同时用于 prefill token budget、prefill block margin、decode swap budget 和 decode scan limit。这样能证明 PBC 有闭环语义，但会把不同压力混在一起。例如 decode/KV 压力可能过度收缩 prefill token budget，造成 TTFT p90 tradeoff。

新实现保留 `rho_down` 作为全局 mode/hysteresis 信号，但把具体预算拆成分量化映射。

## 新映射

实现位置：

- `distserve/phase_scheduler.py`

预算映射：

| Budget | 主要 pressure | 目的 |
|---|---|---|
| `prefill_token_budget` | `rho_prefill = aggregate(bridge, decode)` | bridge/decode backlog 高时减少新的 prefill handoff 注入 |
| `prefill_block_margin` | `rho_memory = aggregate(kv, swap)` | KV/swap 压力高时为 decode 保留更多 block 空间 |
| `decode_swap_budget_per_iter` | `rho_swap = swap` | swap 压力高时减少每轮 swap-in |
| `decode_scan_limit` | `rho_scan = aggregate(kv, swap)` | memory/swap 压力高时优先选择便宜 active set |
| `allow_protected_oldest` | `age` | 保持 bounded-progress override |

`rho_down = aggregate(bridge, decode, kv, swap)` 仍用于：

- `OPEN/BACKPRESSURE` mode 判断。
- `pressure_overshoot` 诊断。
- `prefer_small_kv_footprint` 的全局 backpressure hint。

## 新增诊断字段

`AdmissionBudget` 现在额外记录：

- `pressure_bridge`
- `pressure_decode`
- `pressure_kv`
- `pressure_swap`
- `pressure_age`
- `rho_prefill`
- `rho_memory`
- `rho_swap`
- `rho_scan`
- `pressure_overshoot`

`benchmarks/phase_native_benchmark.py` 会汇总这些字段，`benchmarks/phase_analyze_sweep.py` 的 markdown 现在新增 `Phase Diagnostics` 表，用来观察：

- prefill budget 是否主要随 `bridge/decode` 改变。
- block margin 是否主要随 `kv/swap` 改变。
- `phase` 是否降低 pressure overshoot。
- 新映射是否降低旧版 PBC 的 TTFT p90 tradeoff。

## 消融语义

新实现不改变 policy 命名：

| Policy | 语义 |
|---|---|
| `bps_kas` | BPS + KAS + static budget，仍会记录 pressure 但不动态改变预算 |
| `phase` | BPS + KAS + component-wise dynamic PBC |

因此 PBC 关键消融仍然是：

```text
phase vs bps_kas
```

## 验收标准

下一轮 smoke/验证应检查：

1. `phase_context_rho_prefill` 与 `phase_context_prefill_budget` 负相关。
2. `phase_context_rho_memory` 与 `phase_context_prefill_block_margin` 正相关。
3. `phase_decode_rho_swap` 与 `decode_swap_budget_per_iter` 负相关。
4. decode-heavy burst 下，`phase` 相比 `bps_kas` 仍降低 TPOT tail。
5. 相比旧版 PBC，TTFT p90 tradeoff 应明显收敛。
