# Stage 2：PBC/BPS/KAS 仲裁修复

更新时间：2026-05-27

> 2026-05-28 更新：本文件记录的是第一轮仲裁修复。后续 Stage 4B 验证表明，handoff debt 默认开启和低强度 FCFS fallback 都不是稳定修复；当前默认策略已改为 `PHASESERVE_KAS_HANDOFF_DEBT=0`、`PHASESERVE_KAS_FCFS_FALLBACK_INTENSITY=0`，并采用 short-output FCFS-compatible gate 与 long-output full-KAS gate。最新结论见 `docs/stage4b_scheduler_repair.md`。

## 本阶段目标

Stage 4A 的 OPT-13B prompt-skew metric audit 显示：`bps` 作为单组件能稳定改善 TTFT tail，但 full `phase` 的稳定收益主要落在 TPOT p90，TTFT tail 没有形成稳定窗口。这说明当前代码没有充分执行方法论中的 bottleneck-regime ownership：

- prompt-skew / first-token-limited regime 下，BPS 应是 TTFT owner；
- decode-heavy / KV-swap-limited regime 下，KAS 应是 TPOT 与 feasibility owner；
- soft bridge/first-token pressure 不应在没有 hard KV/swap pressure 时过度破坏 BPS 的 prefill batching。

本阶段目标是修复代码仲裁接口，而不是扩大实验矩阵。

## 需要读取或修改的文件

### 读取文件

| 文件 | 作用 |
|---|---|
| `docs/stage4a_prompt_skew_metric_audit.md` | 读取 Stage 4A 失败模式 |
| `remote_distserve/distserve/phase_scheduler.py` | 定位 PBC pressure-to-budget 映射 |
| `remote_distserve/distserve/decoding_stage_scheduler.py` | 定位 KAS active-set 排序和 handoff debt |
| `remote_distserve/benchmarks/phase_native_benchmark.py` | 确认机制指标汇总入口 |
| `remote_distserve/benchmarks/phase_collect_summaries.py` | 确认 sweep summary 字段 |
| `remote_distserve/benchmarks/phase_analyze_sweep.py` | 确认 paired/grouped analysis 字段 |

### 修改文件

| 文件 | 修改内容 |
|---|---|
| `remote_distserve/distserve/phase_scheduler.py` | 新增 `ttft_debt_weight`；FIRST_TOKEN_LIMITED 且无 hard pressure 时保护 prefill budget；DECODE_HEAVY/KV_SWAP_LIMITED 时立即清空 TTFT debt |
| `remote_distserve/distserve/decoding_stage_scheduler.py` | full `phase` 默认启用 handoff debt，并由 PBC 的 `ttft_debt_weight` 连续控制 |
| `remote_distserve/benchmarks/phase_native_benchmark.py` | 汇总 `budget_ttft_debt_weight`、`effective_handoff_debt_weight`、controller TTFT debt |
| `remote_distserve/benchmarks/phase_collect_summaries.py` | CSV/Markdown 增加 TTFT debt 机制字段 |
| `remote_distserve/benchmarks/phase_analyze_sweep.py` | grouped/paired analysis 增加 TTFT debt 机制字段 |

## 具体实现

### 1. PBC 输出显式 TTFT debt 权重

`AdmissionBudget` 新增：

```text
ttft_debt_weight
```

该字段表示当前 regime 下 decode scheduler 应该给 first-decode-step 请求多少 TTFT debt 保护。

默认规则：

- `FIRST_TOKEN_LIMITED` 或 soft first/bridge pressure 主导且无 hard pressure：`ttft_debt_weight > 0`
- `DECODE_HEAVY`：`ttft_debt_weight = 0`
- `KV_SWAP_LIMITED` 或 hard KV/swap pressure：`ttft_debt_weight = 0`

当 regime 切到 `DECODE_HEAVY/KV_SWAP_LIMITED` 或 hard pressure 出现时，`ttft_debt_weight` 立即清零，不经过 smoothing，避免 prompt-skew 修复污染 decode-heavy 的 TPOT 目标。

### 2. FIRST_TOKEN_LIMITED 下保护 BPS prefill budget

新增默认参数：

```text
PHASESERVE_PBC_FIRST_TOKEN_PREFILL_FLOOR_FRAC=1.0
```

当 context-side PBC 进入 `FIRST_TOKEN_LIMITED` 且 `hard_pressure <= PHASESERVE_PBC_PREFILL_HARD_PRESSURE_THRESHOLD` 时，prefill token budget 至少保持为 `max_prefill_tokens * 1.0`。

这个修改的含义是：如果只有 soft bridge/first-token pressure，而没有真实 KV/swap hard pressure，PBC 不再把 BPS 的 prefill batch shaping 压成更碎的小 batch。hard pressure 出现时，原有 backpressure 仍然生效。

### 3. KAS 默认启用 PBC 控制的 handoff debt

`phase` policy 下：

```text
PHASESERVE_KAS_HANDOFF_DEBT=1
```

默认启用。实际权重由 PBC 的 `ttft_debt_weight` 控制：

```text
effective_handoff_debt_weight =
  PHASESERVE_KAS_HANDOFF_DEBT_WEIGHT * budget.ttft_debt_weight
```

因此 KAS 不再只是被动降低 `kas_intensity`，而是能在 first-token-limited regime 中显式给刚从 prefill 迁移过来的请求连续 TTFT debt；在 decode-heavy 或 hard pressure 下，debt 自动归零。

### 4. 机制指标补充

新增或汇总以下字段：

```text
budget_ttft_debt_weight
effective_handoff_debt_weight
controller_ttft_debt_weight
phase_decode_budget_ttft_debt_weight_mean
phase_decode_effective_handoff_debt_weight_mean
phase_decode_controller_ttft_debt_weight_mean
phase_context_controller_ttft_debt_weight_mean
```

这些字段用于下一轮 Stage 4A 判断修复是否真的被触发，而不是只看端到端 latency。

## 验证结果

### 本地验证

语法检查通过：

```bash
python3 -m py_compile \
  remote_distserve/distserve/phase_scheduler.py \
  remote_distserve/distserve/decoding_stage_scheduler.py \
  remote_distserve/benchmarks/phase_native_benchmark.py \
  remote_distserve/benchmarks/phase_collect_summaries.py \
  remote_distserve/benchmarks/phase_analyze_sweep.py
```

PBC 最小行为检查通过：

```text
context FIRST_TOKEN_LIMITED 2048 0.95 0.0
decode FIRST_TOKEN_LIMITED 0.254 0.95 0.0
decode-heavy DECODE_HEAVY 1.0 0.0 0.0
```

解释：

- context 在 first-token-limited 且无 hard pressure 时保持满 prefill budget `2048`；
- decode 在 first-token-limited 下产生正的 `ttft_debt_weight`；
- decode-heavy 下 `ttft_debt_weight` 立即归零。

### 远程验证

远程同步到：

```text
/root/data/DistServe
```

远程语法检查和同样的 PBC 最小行为检查通过。

远程 OPT-13B 1P1D smoke：

```text
/root/data/phase_scheduler_results/stage2_arbitration_fix_smoke_20260527_230115
```

配置：

- model：`/root/data/models/opt-13b`
- policy：`phase`
- requests：`8`
- prompt mix：`64:0.50,512:0.50`
- output mix：`32:1.0`
- GPU memory utilization：`0.85`

结果：

```text
Completed: 8/8 requests
TTFT median/p90/p95/p99: 0.0851/0.1639/0.1694/0.1738
TPOT median/p90/p95/p99: 0.0257/0.0258/0.0258/0.0258
SLO attainment completed/submitted: 1.0/1.0
```

机制字段已写入 summary：

```text
decode_handoff_ready 8
budget_ttft_debt_weight mean 0.0678, max 0.25
effective_handoff_debt_weight mean 0.0678, max 0.25
context_prefill_budget mean 2037.7, max 2048
```

该 smoke 只验证运行链路和机制字段，不作为性能结论。

## 验收标准

| 验收项 | 结果 |
|---|---|
| PBC budget schema 显式包含 TTFT debt | 通过 |
| FIRST_TOKEN_LIMITED 且无 hard pressure 时 prefill budget 不被 soft bridge pressure 压低 | 通过 |
| DECODE_HEAVY/KV_SWAP_LIMITED 时 TTFT debt 立即归零 | 通过 |
| full `phase` 默认启用 PBC 控制的 handoff debt | 通过 |
| summary/analysis 能记录新机制字段 | 通过 |
| 本地和远程语法检查 | 通过 |
| 远程 OPT-13B phase smoke | 通过 |

## 风险和阻塞点

1. 本阶段只验证代码行为和最小可运行性，还没有证明 TTFT/TPOT 性能改善。
2. `FIRST_TOKEN_PREFILL_FLOOR_FRAC=1.0` 可能在极高 arrival rate 下增加 bridge pressure；但 hard KV/swap pressure 出现时，原有 backpressure 仍会接管。
3. handoff debt 可能改善 first-token tail，但也可能在某些 decode-heavy workload 中影响 TPOT；当前通过 `DECODE_HEAVY/KV_SWAP_LIMITED` 立即清零降低该风险。
4. 下一步必须重跑 Stage 4A 最小矩阵，不能直接把这次修复写成论文结果。

## 下一步入口

下一步回到 Stage 4A，重跑 OPT-13B prompt-skew 最小审计矩阵：

```text
model: opt-13b
policies: fcfs, bps, phase
seeds: 0,1
total rates: 8,10,12,14
requests per run: 64
```

验收重点：

1. full `phase` 是否保留 TPOT p90 window。
2. full `phase` 的 TTFT p75/p90/p95 是否形成连续 rate window。
3. full `phase` 的 TTFT p99 tail transfer 是否收敛。
4. 新字段是否证明修复确实触发：`phase_context_prefill_budget_ratio_mean` 接近 `1.0`，`phase_decode_budget_ttft_debt_weight_mean > 0` 只出现在 first-token-limited/mixed regime。
