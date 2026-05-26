# Cross-Stage PBC Validation

更新时间：2026-05-26

## 目的

本文档记录跨阶段 PBC 闭环后的第一轮验证。核心问题是：

```text
phase = BPS + KAS + dynamic cross-stage PBC
bps_kas = BPS + KAS + static budget
```

因此 PBC 的关键消融是：

```text
phase vs bps_kas
```

本实验不是最终论文结果，而是确认 PBC 是否具备真实消融语义，以及当前 pressure-to-budget 映射是否过激。

## Workload

- 结构：1p1d
- 模型：LLaMA2-7B (`/root/data/models/nous-llama2-7b-hf`)
- 请求数：48
- seeds：`0 1`
- rates：burst (`0`)、`4` req/s
- policies：`bps_kas`、`phase`
- prompt mix：`64:0.50,256:0.30,512:0.20`
- output mix：`64:0.30,128:0.30,256:0.20,512:0.15,1024:0.05`
- SLO：TTFT 10s，TPOT 1s

相关脚本：

- `scripts/run_phase_pbc_sweep.sh`
- `scripts/run_phase_hetero_sweep.sh`
- `scripts/run_phase_hetero_1p1d.sh`

## Aggressive PBC Probe

结果目录：

- `/root/data/phase_scheduler_results/cross_stage_pbc2_20260526_233205`

配置：

- `PHASESERVE_PBC_RHO_LOW=0.20`
- `PHASESERVE_PBC_RHO_HIGH=0.40`
- `PHASESERVE_PBC_MIN_PREFILL_FRAC=0.50`

### 聚合结果

| Rate | Policy | Goodput req/s | SLO submitted | TTFT p90 | TTFT p99 | TPOT p90 | TPOT p99 | Output tok/s | Prefill budget mean |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | bps_kas | 1.420 | 0.979 | 5.765 | 7.776 | 0.135 | 0.159 | 347.8 | 2048 |
| 0 | phase | 1.425 | 0.938 | 7.913 | 8.748 | 0.108 | 0.154 | 361.7 | ~1029 |
| 4 | bps_kas | 1.683 | 1.000 | 0.0596 | 0.266 | 0.0701 | 0.0898 | 399.8 | 2048 |
| 4 | phase | 1.696 | 1.000 | 0.0579 | 0.321 | 0.0695 | 0.0903 | 402.2 | ~1193 |

### 观察

1. `phase` 能明显改变预算：rate0 下 prefill budget 从 2048 收缩到约 1029，说明跨阶段 feedback 生效。
2. aggressive PBC 在 rate0 改善 TPOT p90/p99 倾向，但 SLO submitted 下降 `4.17 pp`，TTFT p90/p99 变差。
3. 这说明 PBC 不是“没起作用”，而是 pressure-to-budget 映射太硬，过早牺牲 prefill admission。

## Tuned PBC Probe

结果目录：

- `/root/data/phase_scheduler_results/cross_stage_pbc_tuned2_20260526_234340`

配置：

- `PHASESERVE_PBC_RHO_LOW=0.45`
- `PHASESERVE_PBC_RHO_HIGH=0.65`
- `PHASESERVE_PBC_MIN_PREFILL_FRAC=0.75`

### 聚合结果

| Rate | Policy | Goodput req/s | SLO submitted | TTFT p90 | TTFT p99 | TPOT p90 | TPOT p99 | Output tok/s | Prefill budget mean |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | bps_kas | 1.436 | 0.979 | 6.028 | 9.402 | 0.109 | 0.156 | 351.7 | 2048 |
| 0 | phase | 1.437 | 0.969 | 6.358 | 7.523 | 0.0966 | 0.152 | 356.2 | ~1540 |
| 4 | bps_kas | 1.701 | 1.000 | 0.0578 | 0.241 | 0.0694 | 0.0904 | 403.8 | 2048 |
| 4 | phase | 1.700 | 1.000 | 0.0582 | 0.313 | 0.0689 | 0.0898 | 403.1 | ~1621 |

### Paired `phase - bps_kas`

| Rate | Goodput delta | SLO delta | Output tok/s ratio | TTFT p90 delta | TTFT p99 delta | TPOT p90 ratio | TPOT p99 ratio |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | +0.001 | -0.0104 | 1.012 | +0.330 | -1.879 | 0.892 | 1.018 |
| 4 | -0.001 | 0.000 | 0.998 | +0.0004 | +0.0716 | 0.989 | 0.992 |

### 观察

1. Tuned PBC 比 aggressive PBC 更合理：rate0 下 TTFT p99 改善约 `1.88s`，TPOT p90 降低约 `10.8%`，output tok/s 提升约 `1.2%`。
2. 代价仍然存在：rate0 的 SLO submitted 下降 `1.04 pp`，TTFT p90 小幅上升。
3. rate4 下 `phase` 基本与 `bps_kas` 持平，说明在中等压力下动态 PBC 不会明显破坏整体性能，但收益也不强。
4. 当前 PBC 已经有可解释的 pressure-budget 行为，但还不能作为“稳定大幅提升性能”的核心 claim。

## 决策

后续默认使用 tuned PBC 参数：

```bash
PHASESERVE_PBC_RHO_LOW=0.45
PHASESERVE_PBC_RHO_HIGH=0.65
PHASESERVE_PBC_MIN_PREFILL_FRAC=0.75
```

这组参数已经写入 `scripts/run_phase_hetero_1p1d.sh` 默认值。

论文叙事上，PBC 当前应写成：

> PBC converts downstream decode pressure into a prefill admission budget. It can reduce decode-side tail pressure and sometimes improve TTFT p99/output throughput, but its benefit depends on the pressure-to-budget mapping and should be evaluated as a stability/control mechanism rather than an unconditional latency optimizer.

## 下一步

1. 设计 decode-heavy workload，让 decode pressure 更强，否则 rate4 下 `phase` 与 `bps_kas` 太接近，PBC 信号弱。
2. 修改 PBC 映射：不要只用 `max(bridge, decode, kv, swap)`，而是区分 `kv/swap` 对 prefill token budget 和 block margin 的影响，避免 TTFT p90 被过度牺牲。
3. 做 5-seed PBC 验证，并报告 `prefill_budget_ratio`、`budget_delta`、`mode_switch_rate`、`pressure_decode/kv/swap`。
