# Stage 4B：PBC/BPS/KAS 调度仲裁修复记录

更新时间：2026-05-28

## 本阶段目标

Stage 4A 显示 `bps` 在 prompt-skew workload 中能稳定降低 TTFT，但 full `phase` 会把部分收益让给 KAS 的 decode-side 重排，导致 TTFT tail 不稳定。本阶段目标是循环定位并修复 full `phase` 的仲裁逻辑，使它更符合方法论中的 owner 划分：

- 短输出、prompt-skew：BPS 是 TTFT owner，KAS 不应抢占；
- 长输出、decode-heavy：KAS 是 TPOT owner，BPS 不应把 decode tail 当成 first-token 问题；
- context 侧只应响应 typed hard decode/KV/swap pressure，不能被普通 decode queue backlog 误判为 `DECODE_HEAVY`。

## 修改文件

| 文件 | 修改内容 |
|---|---|
| `remote_distserve/distserve/phase_scheduler.py` | context 侧 regime classification 使用 typed/effective decode pressure；默认 soft decode backlog 不再把 context 判成 `DECODE_HEAVY` |
| `remote_distserve/distserve/decoding_stage_scheduler.py` | 默认关闭 handoff debt；修复 intensity fallback 阈值为 0 仍触发的问题；新增 short-output FCFS-compatible gate、long-output full-KAS gate，以及 first-token/mixed regime 下的 relaxed bridge acceptance |
| `remote_distserve/benchmarks/phase_native_benchmark.py` | 汇总 short/long output gate 阈值与平均目标输出长度 |
| `remote_distserve/benchmarks/phase_collect_summaries.py` | CSV/Markdown 增加 short/long output gate 字段 |
| `remote_distserve/benchmarks/phase_analyze_sweep.py` | analysis 增加 short/long output gate 字段 |

## 最终默认策略

当前 full `phase` 的 decode 侧默认规则：

```text
PHASESERVE_KAS_HANDOFF_DEBT=0
PHASESERVE_KAS_FCFS_FALLBACK_INTENSITY=0
PHASESERVE_KAS_SHORT_OUTPUT_FCFS_THRESHOLD=96
PHASESERVE_KAS_LONG_OUTPUT_FULL_THRESHOLD=192
```

含义：

- 平均目标输出长度 `<=96`：进入 short-output gate，decode 侧走 FCFS-compatible path，避免 KAS 破坏 BPS 的 first-token 进度；
- 平均目标输出长度 `>192`：进入 long-output full-KAS path，KAS 强度设为 `1.0`，主攻 TPOT 和 output throughput；
- 中间区域：保留 PBC adaptive KAS intensity；
- `FIRST_TOKEN_LIMITED/MIXED_SLO` 且无 hard KV/swap pressure：decode bridge acceptance 使用 prompt-only waiting block accounting，避免 soft first-token pressure 被误处理成 hard KV reservation；
- hard KV/swap pressure 仍优先于上述 soft gate。

## 关键诊断结论

### 1. `bps_pbc` 证明 context/PBC 不是主要问题

诊断矩阵：

```text
/root/data/phase_scheduler_results/stage4a_bps_pbc_diag_opt13b_20260528_001722
```

OPT-13B prompt-skew，seed0，rate10/12，64 requests。

| rate | policy | TTFT p90 ratio vs FCFS | TPOT p90 ratio vs FCFS |
|---|---:|---:|---:|
| 10 | bps | 0.777 | 0.981 |
| 10 | bps_pbc | 0.745 | 0.976 |
| 10 | phase | 1.067 | 0.937 |
| 12 | bps | 0.792 | 1.011 |
| 12 | bps_pbc | 0.792 | 1.018 |
| 12 | phase | 0.979 | 0.985 |

解释：context 侧 BPS/PBC 可以产生 TTFT 收益；full `phase` 的 TTFT 损失主要来自 KAS 与跨阶段 pressure 仲裁。

### 2. handoff debt 和旧 FCFS fallback 不是正确修复

已验证但未采纳：

- PBC-controlled handoff debt 默认开启：改善不足，且会扰动 prompt-skew TTFT；
- low-intensity FCFS fallback：因为阈值 `0` 仍会触发、且没有区分短输出与长输出，效果不稳定；
- first-token gate：触发率低或过度触发时都不能稳定改善 TTFT；
- 单纯提高 `PHASESERVE_PBC_RHO_HIGH`：rate10 略好，rate12 变差，不适合作为方法论修复。

最终采用 typed pressure + output-tail eligibility。

## 当前性能信号

### Prompt-skew：TTFT owner 是 BPS/short-output gate

结果目录：

```text
/root/data/phase_scheduler_results/stage4a_short_tail_diag_opt13b_20260528_010647
```

OPT-13B prompt-skew，seed0，rates 10/12，64 requests。

| rate | metric | Phase / FCFS |
|---|---|---:|
| 10 | TTFT p90 | 0.847 |
| 10 | TPOT p90 | 1.045 |
| 10 | throughput | 0.971 |
| 12 | TTFT p90 | 0.892 |
| 12 | TPOT p90 | 1.051 |
| 12 | throughput | 0.979 |

结论：短输出 prompt-skew 下，Phase 已能稳定降低 TTFT p90，但 TPOT 不应在该 workload 上作为主 claim。

阈值 96 的复核：

```text
/root/data/phase_scheduler_results/stage4a_short_tail96_pilot_opt13b_20260528_012838
```

phase-only 结果：rate10 TTFT p90 `0.912s`，rate12 TTFT p90 `1.799s`，与阈值 192 基本一致，因此默认收紧为 96。

### Decode-heavy：TPOT owner 是 long-output full KAS

结果目录：

```text
/root/data/phase_scheduler_results/stage4_decode_fullkas_check_opt13b_20260528_015539
```

OPT-13B decode-heavy，seed0，rates 4/6，48 requests。

| rate | metric | Phase / FCFS |
|---|---|---:|
| 4 | TPOT p50 | 0.898 |
| 4 | TPOT p90 | 0.978 |
| 4 | TPOT p95 | 0.973 |
| 4 | throughput | 1.011 |
| 6 | TPOT p50 | 0.900 |
| 6 | TPOT p90 | 0.977 |
| 6 | TPOT p95 | 0.979 |
| 6 | throughput | 1.010 |

结论：decode-heavy 下 TPOT p50 改善约 10%，p90/p95 改善约 2-3%，吞吐小幅提升。当前 tail 改善还不够强，后续应继续寻找更能放大 KAS 价值的 workload 或优化 KAS policy。

## 验收状态

| 验收项 | 当前状态 |
|---|---|
| full `phase` 在 prompt-skew 下不再明显劣于 FCFS TTFT p90 | 通过 |
| full `phase` 在 prompt-skew 下形成 TTFT p90 改善窗口 | 初步通过，seed0/rate10/12 |
| full `phase` 在 decode-heavy 下保留 TPOT 收益 | 初步通过，seed0/rate4/6 |
| short-output gate 不在 decode-heavy 中误触发 | 通过，修复后 fallback count 为 0 |
| benchmark summary 能记录 gate 机制字段 | 通过 |
| 是否达到论文主实验标准 | 未完成，还需要 seed0/1、OPT-13B/LLaMA2-13B 完整矩阵 |

## 下一步

1. 用当前默认策略跑 Stage 4A prompt-skew 最小正式矩阵：
   - OPT-13B，seed0/1，rates 8/10/12/14，policies `fcfs/bps/phase`。
2. 跑 decode-heavy TPOT 正式矩阵：
   - OPT-13B，seed0/1，rates 4/5/6，policies `fcfs/phase`，必要时加入 `kas` 和 `bps_kas`。
3. 如果 decode-heavy 的 TPOT p90/p95 仍只有 2-3%，优先改 KAS workload 或 KAS scoring，而不是继续改 BPS。
4. 通过后再迁移到 LLaMA2-13B / NousResearch LLaMA2-13B。
