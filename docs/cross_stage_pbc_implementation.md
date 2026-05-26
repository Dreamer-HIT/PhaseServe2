# Cross-Stage PBC Implementation

更新时间：2026-05-26

## 目的

本文档记录 PhaseServe 的第一版跨阶段 PBC 闭环实现。此前代码中 PBC 已存在，但 context 侧和 decode 侧基本是两个局部控制器；这会导致 `phase` 和 `bps_kas` 的差异不够符合方法论，因为方法论文档要求 PBC 将 decode-side pressure 反馈到 prefill admission budget。

本次实现把 `phase` 改成：

```text
decode KAS observes downstream pressure
  -> writes pressure snapshot
  -> context BPS/PBC reads snapshot
  -> context PBC shrinks/expands prefill token budget and block margin
```

这样 `phase` 才代表完整 PhaseServe；`bps_kas` 仍代表 BPS+KAS 但关闭动态 PBC 的静态组合。

## 实现位置

- `distserve/phase_scheduler.py`
  - 新增 `write_pressure_snapshot`
  - 新增 `read_pressure_snapshot`
  - snapshot 使用 JSON 文件和 `os.replace` 原子更新，避免跨进程读到半写入内容。
- `distserve/decoding_stage_scheduler.py`
  - KAS 每次计算 decode budget 后写出 decode pressure snapshot。
  - 即使没有 ready requests，也会刷新 snapshot，避免 context 读取陈旧压力。
- `distserve/context_stage_scheduler.py`
  - BPS/PBC 读取 decode snapshot。
  - 若 snapshot 可用且未过期，则将 `decode/kv/swap/bridge` 纳入 context PBC pressure vector。
- `scripts/run_phase_hetero_1p1d.sh`
  - 每个 policy run 设置 `PHASESERVE_PRESSURE_SNAPSHOT_PATH=${run_dir}/pressure_snapshot.json`。
  - 每次启动前清理旧 snapshot。
- `benchmarks/phase_native_benchmark.py`
  - context phase metrics 汇总 `decode_snapshot_used`、`decode_snapshot_stale`、`decode_snapshot_age_s`。
- `benchmarks/phase_collect_summaries.py`
  - summary 表增加 snapshot 使用情况。
- `benchmarks/phase_analyze_sweep.py`
  - sweep run rows 增加 snapshot 使用情况。

## 运行时接口

新增环境变量：

| 变量 | 默认值 | 含义 |
|---|---:|---|
| `PHASESERVE_PRESSURE_SNAPSHOT_PATH` | unset | 跨阶段 pressure snapshot 文件路径 |
| `PHASESERVE_PRESSURE_SNAPSHOT_MAX_AGE_S` | `2` | context 侧接受 snapshot 的最大年龄 |

snapshot 内容包括：

- `component`
- `timestamp`
- `pressures`
- `budget`
- `unaccepted`
- `waiting`
- `swapped`
- `processing`
- `available_gpu_blocks`
- `max_gpu_blocks`

## 语义

Context 侧本地 pressure：

```text
bridge = local context unaccepted queue pressure
kv     = local context reserved block pressure
age    = oldest prefill wait pressure
```

Decode snapshot pressure：

```text
bridge = decode unaccepted queue pressure
decode = decode waiting/swapped pressure
kv     = decode GPU KV pressure
swap   = decode swapped/swap-in pressure
age    = max decode skip pressure
```

Context 合并规则：

```text
bridge = max(context_bridge, decode_bridge)
decode = decode_snapshot.decode
kv     = max(context_kv, decode_snapshot.kv)
swap   = decode_snapshot.swap
age    = context_oldest_prefill_age
```

这让 PBC 的 prefill token budget 和 block margin 由下游 decode pressure 共同决定。

## 消融含义

新语义下，关键 policy 的含义是：

| Policy | 含义 |
|---|---|
| `fcfs` | DistServe baseline |
| `bps` | BPS only，decode FCFS，无 decode snapshot |
| `kas` | KAS only，context FCFS |
| `bps_kas` | BPS + KAS，但 `PHASESERVE_PBC_DISABLE_DYNAMIC=1`，用于隔离静态组合 |
| `phase` | BPS + KAS + dynamic PBC + cross-stage decode pressure feedback |

因此，PBC 的核心消融应看：

```text
phase vs bps_kas
```

如果 `phase` 不能稳定优于 `bps_kas`，说明跨阶段 PBC 仍需调参或重新设计，而不是 BPS/KAS 本身无效。

## 验证重点

下一轮实验应至少检查：

1. `phase_metrics.context.decode_snapshot_used > 0`
2. context budget 中 `pressures.decode/swap/kv` 非零且随 decode pressure 变化
3. `phase` 的 `prefill_token_budget` 在 decode pressure 高时低于 `bps_kas`
4. `phase vs bps_kas` 是否降低 bridge queue、swap pressure、TPOT tail 或提升 SLO goodput

## Smoke Test

配置：

- 1p1d
- LLaMA2-7B
- `NUM_PROMPTS=12`
- `REQUEST_RATE=4`
- `POLICIES="bps_kas phase"`

结果目录：

- `/root/data/phase_scheduler_results/cross_stage_pbc_smoke_20260526_232708`

关键观测：

| Policy | Context dispatches | Snapshot used | Snapshot stale | Context decode pressure mean | Prefill budget mean | Block margin mean |
|---|---:|---:|---:|---:|---:|---:|
| `bps_kas` | 12 | 12 | 0 | 0.0833 | 2048.0 | 0.0 |
| `phase` | 12 | 12 | 0 | 0.0833 | 1796.7 | 7.5 |

解释：

- 两个 policy 都能读到 decode snapshot，说明跨阶段通信链路可用。
- `bps_kas` 设置了 `PHASESERVE_PBC_DISABLE_DYNAMIC=1`，因此即使读到 decode pressure，prefill budget 仍保持静态最大值。
- `phase` 启用 dynamic PBC，因此同样的 decode pressure 会收缩 prefill token budget 并提高 block margin。
- 这证明当前 `phase vs bps_kas` 已经具备 PBC 消融语义；smoke 只验证链路，不作为性能结论。

## 当前限制

1. snapshot 是文件级轻量通信，不是低延迟控制面。它适合 1p1d 实验和论文原型，但未来多实例部署应换成共享控制面或 actor message。
2. 当前 context 合并 decode pressure 使用 max/override 规则，仍是启发式。后续需要根据 `phase vs bps_kas` 的结果调权重。
3. snapshot 对 FCFS decode 不生效，因此 `bps` policy 仍是纯 prefill 侧实验。
