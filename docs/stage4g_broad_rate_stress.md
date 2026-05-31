# Stage 4G Broad Rate Stress Sweep

## 目标

补充一轮宽 rate 压力扫描，覆盖从低负载到明显过载的完整区间，避免只在窄压力窗口内观察 PhaseServe 的效果。

这轮实验不直接替代主端到端图的 rate 选择。主图仍应选择 DistServe 从稳定进入退化、但尚未完全崩溃的连续区间；宽 rate 扫描用于确定这个区间，并展示高压边界。

## Rate 语义

当前脚本中的 `RATES` 是全局请求到达率。

当前实验配置是 1P1D，共 2 张 GPU，因此论文图中的 `Per-GPU Rate` 应按如下方式换算：

```text
Per-GPU Rate = RATES / 2
```

因此，如果需要覆盖 per-GPU `0-10 req/s`，脚本中的全局 `RATES` 至少需要覆盖到 `20 req/s`。

另外，benchmark 中 `rate=0` 的语义不是 0 负载，而是 zero inter-arrival / burst，即所有请求尽快发出。它应被视为一个极端压力点。

## 首轮执行

先用 OPT-13B + ShareGPT 做小样本 broad sweep，验证高 rate 下脚本、server 和统计是否稳定。

配置：

| 项 | 设置 |
|---|---|
| 模型 | OPT-13B |
| 数据集 | ShareGPT trace |
| 结构 | 1P1D |
| Policies | `fcfs`, `phase` |
| Seeds | `0` |
| 全局 `RATES` | `1 2 4 6 8 10 12 16 20 0` |
| 对应 per-GPU rates | `0.5, 1, 2, 3, 4, 5, 6, 8, 10, burst` |
| 请求数 | `64` |
| 目的 | 找到稳定区、退化区和过载区 |

如果高 rate 全部 timeout 或 failure，则缩短正式图的展示区间，并将高 rate 结果作为过载边界说明；如果高 rate 下 Phase 仍稳定改善，则扩展主图 rate 范围。

## 验收标准

- 每个 rate 至少完成 `fcfs` 与 `phase` 两个 policy 的结果文件。
- 汇总表包含 TTFT p50/p90/p95/p99、TPOT p50/p90/p95/p99、SLO attainment、completed throughput、output token throughput。
- 明确标出：
  - Phase 明显优于 FCFS 的 rate 区间；
  - 二者都接近稳定的低压区；
  - 二者都明显过载的高压区；
  - Phase 是否在高压区出现 TTFT/TPOT tradeoff。

## 首轮结果

结果目录：

```text
/root/data/phase_scheduler_results/e2b_opt13b_sharegpt_broad_20260529_185758
```

完成情况：

- `20/20` runs 完成。
- 每个 global rate 均包含 `fcfs` 与 `phase`。
- `rate=0` 是 burst/stress 点，不应和连续 Poisson rate 曲线混画。
- 表中延迟项为 Phase 相对 FCFS 的下降比例，正数表示 Phase 更好；SLO/goodput 为 Phase 相对 FCFS 的提升。

| Global Rate | Per-GPU Rate | SLO Submitted | TTFT p50 | TTFT p90 | TTFT p95 | TTFT p99 | TPOT p50 | TPOT p90 | TPOT p95 | TPOT p99 | Goodput |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0.5 | +0.0 pp | -1.2% | +7.8% | +3.0% | +6.4% | -2.8% | -3.3% | -2.2% | -2.4% | -0.8% |
| 2 | 1 | +6.2 pp | -1.2% | +4.0% | -1.3% | +2.1% | -2.0% | +56.6% | +68.9% | +77.5% | +11.3% |
| 4 | 2 | +0.0 pp | +4.1% | +1.4% | -86.9% | -71.9% | +13.7% | -3.6% | +8.5% | +10.7% | -0.2% |
| 6 | 3 | +1.6 pp | +3.5% | -42.6% | -9.0% | -21.8% | +15.9% | +6.1% | +3.2% | +8.9% | +5.9% |
| 8 | 4 | +1.6 pp | +3.4% | +15.4% | -9.3% | -8.8% | +14.5% | +3.3% | +4.2% | +8.0% | +5.2% |
| 10 | 5 | +0.0 pp | +8.7% | +8.6% | -9.3% | -13.6% | +10.7% | +8.7% | +3.9% | +6.5% | +0.1% |
| 12 | 6 | +1.6 pp | +19.9% | +10.8% | -9.2% | -11.2% | +12.4% | +9.2% | +3.5% | +10.2% | +4.8% |
| 16 | 8 | -3.1 pp | +0.1% | +13.7% | -8.2% | -8.7% | +10.7% | -1.7% | +9.5% | +6.0% | -8.6% |
| 20 | 10 | +6.2 pp | -11.4% | +0.2% | +16.6% | -0.4% | +6.4% | -5.2% | +6.4% | +17.1% | +129.7% |
| 0 | burst | +12.5 pp | +3.7% | -25.8% | +0.1% | +1.5% | +7.2% | +6.9% | +5.3% | -35.1% | FCFS 为 0 |

## 结论

1. 低压区不是最终主图重点。Per-GPU `0.5` 下 SLO 没有拉开，Phase 只改善 TTFT tail，TPOT 略差。
2. Per-GPU `1` 是当前最干净的综合收益点：SLO +`6.2 pp`，TTFT p90 下降 `4.0%`，TPOT p90/p95/p99 分别下降 `56.6%/68.9%/77.5%`，goodput +`11.3%`。
3. Per-GPU `2` 之后进入 tradeoff 区。Phase 常能改善 TPOT p50/p95/p99 或 TTFT p90，但 TTFT p95/p99 经常变差，不能 claim 全 tail 同时改善。
4. Per-GPU `3-6` 更适合做 TPOT/压力边界辅助图，而不是主端到端综合图。这里 Phase 对 TPOT p50/p90 多数有收益，但 TTFT tail 不稳定。
5. Per-GPU `8-10` 已经是过载区。它们可以证明高压边界和 failure mode，但不适合当主图中心区间。
6. Burst 点单独作为 stress case。Phase 从 `0%` submitted SLO 恢复到 `12.5%`，但 TTFT p90 更差，不能和 Poisson rate 曲线混合解释。

## 对主图区间的影响

OPT-13B + ShareGPT 的主端到端图不应机械展示 per-GPU `0-10` 全区间。更合理的做法是：

- 主综合图：围绕 per-GPU `0.5-2` 做细扫，尤其补 `0.75/1.0/1.25/1.5`。
- TPOT 压力辅助图：可以展示 per-GPU `3-6`，强调 TPOT 和 goodput/served-request recovery。
- Stress/appendix：展示 per-GPU `8/10` 与 burst，说明系统过载边界和 tradeoff。

后续正式矩阵需要至少补 seed `1`，并将该结论复查到 LLaMA2-13B + ShareGPT / LongBench。

## LLaMA2-13B + ShareGPT per-GPU 1-5 复查

根据宽扫结果，进一步按用户指定的粗粒度完成 LLaMA2-13B + ShareGPT 的 per-GPU `1/2/3/4/5` 扫描。

结果目录：

```text
/root/data/phase_scheduler_results/e2b_llama13b_sharegpt_pergpu1to5_20260529_201651
```

配置：

| 项 | 设置 |
|---|---|
| 模型 | LLaMA2-13B, ModelScope mirror `/root/data/models/modelscope-llama2-13b-hf` |
| 数据集 | ShareGPT trace |
| 结构 | 1P1D |
| Policies | `fcfs`, `phase` |
| Seeds | `0` |
| 全局 `RATES` | `2 4 6 8 10` |
| 对应 per-GPU rates | `1, 2, 3, 4, 5` |
| 请求数 | `64` |
| SLO | `TTFT <= 0.25s`, `TPOT <= 0.10s` |

表中延迟项为 Phase 相对 FCFS 的下降比例，正数表示 Phase 更好；SLO/goodput 为 Phase 相对 FCFS 的提升。

| Per-GPU Rate | SLO Submitted | TTFT p50 | TTFT p90 | TTFT p95 | TTFT p99 | TPOT p50 | TPOT p90 | TPOT p95 | TPOT p99 | Goodput |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | -1.6 pp | -1.7% | +1.3% | -9.8% | -9.4% | +1.5% | -2.6% | -22.4% | +0.4% | -6.0% |
| 2 | -4.7 pp | -2.4% | +4.7% | +71.9% | +7.9% | +11.5% | +5.9% | +9.6% | -8.9% | -11.3% |
| 3 | +4.7 pp | +3.4% | +8.2% | +8.2% | +14.1% | +13.9% | -1.4% | -1.5% | -3.5% | +7.3% |
| 4 | +7.8 pp | +15.9% | +1.2% | +2.3% | +9.3% | +13.0% | +9.2% | +7.8% | -9.4% | +24.9% |
| 5 | +6.2 pp | -1.5% | -0.6% | -1.2% | +3.8% | +6.3% | +5.5% | +0.3% | -13.0% | +14.2% |

### 观察

1. Per-GPU `1` 仍属于低压/弱区分区。Phase 没有拉开 SLO 和 goodput，TTFT/TPOT 也只是个别分位小幅改善。
2. Per-GPU `2` 是 tradeoff 点。Phase 明显压低 TTFT p95 和 TPOT p50/p90/p95，但 SLO/goodput 下降，TPOT p99 变差。
3. Per-GPU `3-5` 开始进入更有区分度的高压区。Phase 在 SLO 和 goodput 上持续优于 FCFS，其中 per-GPU `4` 最干净：SLO +`7.8 pp`，goodput +`24.9%`，TTFT p50/p90/p95/p99 均改善，TPOT p50/p90/p95 均改善。
4. TPOT p99 仍不稳定。per-GPU `3/4/5` 的 TPOT p99 都变差，因此最终论文主图不应选择 TPOT p99 作为主要 positive claim；更合理的是展示 TPOT p50+p90 或 p50+p95，并把 p99 作为 tail tradeoff/appendix。
5. LLaMA2-13B + ShareGPT 的主图候选区间比 OPT 更偏高压：TTFT/SLO 候选可优先看 per-GPU `3-4`，TPOT 候选可优先看 per-GPU `4-5`，但正式结果仍需要补 seed `1` 和更细 rate。
