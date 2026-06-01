# Stage 4A：OPT-13B Prompt-Skew Metric Audit

更新时间：2026-05-27

## 本阶段目标

本轮属于 Stage 4 的 prompt-skew 复核与指标审计。目标不是继续调参，而是回答三个问题：

1. 在 OPT-13B、1P1D、prompt-skew workload 下，`phase` 是否已经能稳定改善 TTFT 和 TPOT。
2. 哪些 percentile 指标可以作为后续论文端到端图的候选指标，哪些指标必须放进 tradeoff 或 appendix。
3. 当前结果是否支持继续扩大到 LLaMA2-13B final matrix，还是应回到 Stage 2 修正 full `phase` 的仲裁逻辑。

## 读取或修改的文件

### 本阶段读取文件

| 文件 | 作用 |
|---|---|
| `docs/current_progress.md` | 对齐当前阶段和已有实验结论 |
| `docs/stage3_experiment_design.md` | 对齐 Stage 4 triage 规则 |
| `docs/stage4_w2_ttft_calibration.md` | 对比早期 W2 prompt-skew 校准结果 |
| `docs/stage4_decode_regime_validation.md` | 对比 decode-heavy regime 的主收益口径 |

### 本阶段修改文件

| 文件 | 修改内容 |
|---|---|
| `remote_distserve/benchmarks/phase_native_benchmark.py` | summary 增加 `p75` |
| `remote_distserve/benchmarks/phase_collect_summaries.py` | 汇总 CSV/Markdown 增加 TTFT/TPOT `p75` |
| `remote_distserve/benchmarks/phase_analyze_sweep.py` | paired/bucket 分析增加 TTFT/TPOT `p75` |
| `remote_distserve/benchmarks/phase_metric_audit.py` | 新增 metric audit 脚本，用 seed 配对方式筛连续 rate window |
| `docs/stage4a_prompt_skew_metric_audit.md` | 新增本阶段复盘文档 |
| `docs/current_progress.md` | 同步最新 Stage 4A 结论 |

本阶段不修改调度器核心逻辑。

## 代码验证

本地语法验证：

```bash
python3 -m py_compile \
  remote_distserve/benchmarks/phase_native_benchmark.py \
  remote_distserve/benchmarks/phase_collect_summaries.py \
  remote_distserve/benchmarks/phase_analyze_sweep.py \
  remote_distserve/benchmarks/phase_metric_audit.py

bash -n \
  remote_distserve/scripts/run_phase_prefill_skew_sweep.sh \
  remote_distserve/scripts/run_phase_hetero_sweep.sh \
  remote_distserve/scripts/run_phase_hetero_1p1d.sh
```

远程语法验证：

```bash
/root/data/conda-envs/distserve/bin/python -m py_compile \
  benchmarks/phase_native_benchmark.py \
  benchmarks/phase_collect_summaries.py \
  benchmarks/phase_analyze_sweep.py \
  benchmarks/phase_metric_audit.py
```

以上验证均通过。

## 实验配置

结果目录：

```text
/root/data/phase_scheduler_results/stage4a_prompt_skew_metric_audit_opt13b_20260527_212638
```

配置：

| 项目 | 值 |
|---|---|
| model | `/root/data/models/opt-13b` |
| serving | 1P1D，2 x A800 40GB |
| GPU memory utilization | `0.85` |
| workload | prompt-skew synthetic |
| prompt mix | `64/512/1024/1536` |
| output mix | `32/64/128` |
| seeds | `0,1` |
| total request rates | `8,10,12,14 req/s` |
| per-GPU request rates | `4,5,6,7 req/s/GPU` |
| requests per run | `64` |
| policies | `fcfs`, `bps`, `bps_kas`, `phase` |
| SLO | TTFT `10s`, TPOT `1s` |

本轮一共完成 `32/32` 个 runs。

## 具体产物

远程产物：

| 文件 | 作用 |
|---|---|
| `sweep_summary.csv` / `sweep_summary.md` | 全部 run 的绝对指标 |
| `sweep_analysis.*` | paired ratio 与 bucket breakdown |
| `metric_audit_fcfs.*` | 相对 `fcfs` 的指标窗口审计 |
| `metric_audit_bps.*` | 相对 `bps` 的指标窗口审计 |

`metric_audit` 的口径：

- latency ratio = target policy / baseline policy，越低越好。
- 只把两个 seed 都改善的点记为稳定改善，即 `min_seed_fraction=1.0`。
- 只有连续两个及以上 rate 的稳定改善才进入 candidate window，即 `min_window_len=2`。
- 审计指标包含 TTFT/TPOT 的 `p50/p75/p90/p95/p99`。

## 相对 FCFS 的 Candidate Windows

| policy | metric | rates | mean ratio | best ratio | 平均改善 |
|---|---|---|---:|---:|---:|
| `bps` | TPOT p90 | `8,10` | 0.9436 | 0.9396 | 5.6% |
| `bps` | TTFT p75 | `10,12` | 0.9035 | 0.8848 | 9.6% |
| `bps` | TTFT p95 | `10,12,14` | 0.9159 | 0.8649 | 8.4% |
| `bps` | TTFT p99 | `10,12,14` | 0.9566 | 0.9330 | 4.3% |
| `bps_kas` | TPOT p75 | `8,10` | 0.9572 | 0.9552 | 4.3% |
| `bps_kas` | TPOT p90 | `8,10` | 0.9155 | 0.8879 | 8.5% |
| `phase` | TPOT p75 | `8,10` | 0.9630 | 0.9599 | 3.7% |
| `phase` | TPOT p90 | `8,10,12` | 0.9351 | 0.8972 | 6.5% |

### 关键观察

1. `phase` 相比 FCFS 的稳定窗口主要在 TPOT p90，而不是 TTFT tail。
2. `bps` 单独在 TTFT p75/p95/p99 上比 full `phase` 更强，说明 prompt-skew 下 BPS 的主机制成立。
3. `phase` 的 TTFT p50/p75 在单点 rate 上有改善，但没有形成两个 seed 同时改善、连续两个 rate 的稳定 TTFT window。

## 相对 BPS 的 Candidate Windows

| policy | metric | rates | mean ratio | best ratio | 平均改善 |
|---|---|---|---:|---:|---:|
| `bps_kas` | TPOT p75 | `8,10` | 0.9658 | 0.9656 | 3.4% |
| `bps_kas` | TPOT p90 | `10,12` | 0.9495 | 0.9358 | 5.0% |
| `phase` | TPOT p75 | `8,10` | 0.9715 | 0.9702 | 2.8% |
| `phase` | TPOT p90 | `10,12` | 0.9364 | 0.9269 | 6.4% |
| `phase` | TTFT p50 | `8,10` | 0.9916 | 0.9860 | 0.8% |

### 关键观察

1. full `phase` 相比 `bps` 的主要增量是 TPOT p90，而不是 TTFT。
2. full `phase` 相比 `bps` 的 TTFT p50 改善只有约 `0.8%`，不适合作为主图 claim。
3. `phase` 在 TTFT p90/p95/p99 上相对 `bps` 多数 rate 变差，说明 KAS/BPS 仲裁仍会把 BPS 的部分 TTFT 收益转移到 decode-side scheduling tradeoff。

## Per-Rate 诊断

相对 FCFS，`phase` 的代表性 per-rate ratio 如下：

| total rate | TTFT p50 | TTFT p75 | TTFT p90 | TTFT p95 | TTFT p99 | TPOT p75 | TPOT p90 | TPOT p95 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 8 | 0.9015 | 1.0290 | 0.9765 | 1.0047 | 1.0277 | 0.9660 | 0.9508 | 1.0174 |
| 10 | 0.8939 | 0.9212 | 1.0615 | 1.0296 | 1.1168 | 0.9599 | 0.8972 | 0.9822 |
| 12 | 0.8350 | 0.8910 | 0.9785 | 0.9046 | 1.0890 | 0.9874 | 0.9572 | 0.9752 |
| 14 | 1.0022 | 0.7974 | 1.0002 | 1.0073 | 1.1068 | 0.8946 | 0.9759 | 1.0021 |

这张表解释了为什么不能直接宣称 full `phase` 在 prompt-skew 下全面降低 TTFT：

- TTFT p50/p75 在部分 rate 有收益。
- TTFT p90 只有 rate12 两个 seed 都改善，不能形成连续稳定窗口。
- TTFT p99 持续变差，说明仍有 tail transfer。
- TPOT p90 在 rate8/10/12 连续改善，是当前 full `phase` 在 prompt-skew 下最稳定的端到端收益。

## 当前结论

本轮结果支持以下有限 claim：

1. **BPS 组件有效**：在 prompt-skew workload 下，`bps` 相比 FCFS 有稳定 TTFT tail 窗口，尤其是 TTFT p75/p95/p99。
2. **full Phase 的 TPOT 保护有效**：`phase` 相比 FCFS 在 TPOT p90 上形成 `8/10/12` 的连续稳定窗口，平均改善约 `6.5%`。
3. **full Phase 还不是 prompt-skew 下的 TTFT 主结果**：`phase` 没有形成稳定 TTFT tail window，并且 TTFT p99 存在持续回退。
4. **当前不应直接扩展 final matrix**：如果马上跑 LLaMA2-13B，风险是只复现“BPS 有 TTFT、Phase 有 TPOT、full Phase TTFT 不稳”的结论，无法支撑顶会主 claim。

## 验收标准

| 验收项 | 结果 |
|---|---|
| 32 个 OPT-13B 1P1D runs 全部完成 | 通过 |
| summary/analysis/audit 产物生成 | 通过 |
| TTFT/TPOT p75 纳入统计链路 | 通过 |
| 能用 seed 配对方式筛出连续 rate window | 通过 |
| 找到 full `phase` 的稳定 TTFT window | 未通过 |
| 找到 full `phase` 的稳定 TPOT window | 通过 |
| 判断下一步是否继续扩 final matrix | 通过：应先回 Stage 2 修仲裁 |

## 风险和阻塞点

1. **full Phase 的 TTFT p99 风险仍未解决**：当前 KAS/TPOT 保护会在 prompt-skew 下制造 first-token tail transfer。
2. **BPS 和 Phase 的论文定位要区分**：BPS 可以作为 prompt-skew 下 TTFT owner，full Phase 目前更像 TPOT/SLO tradeoff controller。
3. **metric selection 不能事后 cherry-pick**：后续主图可从 p50/p75/p90/p95/p99 中选择，但必须满足连续 rate、跨 seed、机制可解释三条规则。
4. **SLO 当前不适合作为本轮主结论**：TTFT `10s`、TPOT `1s` 过松，所有 run 基本达成，后续需要更合理的 SLO grid 或 goodput 口径。

## 下一步建议

本阶段建议回到 Stage 2，而不是继续扩大实验。需要修的不是 BPS 本身，而是 full `phase` 中 KAS 与 BPS 的冲突：

1. 在 KAS scoring 中显式加入 first-decode-step debt，让刚从 prefill 迁移过来的请求在无 hard KV/swap pressure 时获得保护。
2. 把 `decode_utility_intensity` 从“降低 KAS 强度”扩展为“在 TTFT debt、attained-service fairness、KV feasibility 之间连续调权”。
3. 保留 hard constraint 优先级：swap/KV hard pressure 出现时，KAS 的 feasibility 优先于 TTFT debt。
4. 修复后只重跑本轮 Stage 4A 的最小矩阵：OPT-13B prompt-skew，seed `0/1`，rate `8/10/12/14`，policies `fcfs/bps/phase`。只有当 full `phase` 至少不明显破坏 BPS 的 TTFT tail，同时保留 TPOT p90 window 时，再进入双模型 final matrix。
