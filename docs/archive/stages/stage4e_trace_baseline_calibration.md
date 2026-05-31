# Stage 4E：真实 Trace Baseline Calibration

更新时间：2026-05-29

## 本阶段目标

本阶段对应 `docs/experiment_protocol.md` 中的 E1：只运行 DistServe/FCFS baseline，寻找每个真实 workload setting 的压力窗口。这个阶段不评价 PhaseServe 是否有效，也不根据 PhaseServe 结果选择 rate。

压力窗口按 baseline 行为定义：

1. 稳定区：SLO 接近 100%，TTFT/TPOT tail 尚未明显放大。
2. 退化区：SLO 开始下降，TTFT 或 TPOT tail 出现可诊断压力。
3. 过载边界：大多数请求仍完成，但 SLO/goodput/tail 已明显恶化。

当前脚本中的 `RATES` 是 benchmark 输入的全局 arrival rate；1P1D 使用 `--num-gpus 2`。论文图的横轴若写 `Per-GPU Rate`，应将 offered rate 换算为 `RATES / 2`，并同时保留 summary 中的 measured per-GPU goodput。

## 读取或修改的文件

读取和使用：

- `evaluation/docs/repro-dataset.md`
- `evaluation/2-benchmark-serving/0-prepare-dataset.py`
- `docs/experiment_protocol.md`
- `docs/benchmarking.md`

修改：

- `remote_distserve/benchmarks/phase_make_trace_dataset.py`
- `remote_distserve/scripts/run_phase_hetero_1p1d.sh`
- `remote_distserve/scripts/run_phase_trace_baseline_sweep.sh`
- `remote_distserve/scripts/run_phase_hetero_sweep.sh`

关键脚本修复：

- `run_phase_hetero_1p1d.sh` 新增 `BLOCK_SIZE`、`MAX_NUM_BLOCKS_PER_REQ`、`CONTEXT_MAX_BATCH_SIZE`、`CONTEXT_MAX_TOKENS_PER_BATCH`、`DECODING_MAX_BATCH_SIZE`、`DECODING_MAX_TOKENS_PER_BATCH` 环境变量。
- 目的：LLaMA2-13B + LongBench-4K 不能继续硬编码 `context-max-tokens-per-batch=2048`，否则 4K prompt 的结果会混入脚本限制。
- 本地和远端 `bash -n` 均已通过。

## 数据集状态

| Setting | Dataset | 生成方式 | 样本数 | prompt avg/p50/p90/p99 | output avg/p50/p90/p99 |
|---|---|---|---:|---|---|
| OPT-13B + ShareGPT | `/root/data/datasets/distserve_eval/processed/opt13b_sharegpt.ds` | DistServe 原始预处理脚本 + OPT tokenizer | 5147 | 566.7 / 435 / 1325 / 1846 | 184.1 / 104 / 454 / 824 |
| LLaMA2-13B + ShareGPT | `/root/data/datasets/distserve_eval/processed/llama13b_sharegpt.ds` | DistServe 原始预处理脚本 + LLaMA tokenizer | 5046 | 586.4 / 458 / 1364 / 1888 | 196.9 / 110 / 487 / 934 |
| LLaMA2-13B + LongBench-4K | `/root/data/datasets/distserve_eval/processed/llama13b_longbench_4k.ds` | raw LongBench + LLaMA tokenizer + 4K length trace | 2048 | 2837.6 / 2834 / 3595 / 3771 | 76.4 / 12 / 348 / 512 |

说明：

- DistServe 仓库不直接包含原始数据，但提供 ShareGPT/LongBench 下载说明和预处理脚本。
- DistServe 自带 LongBench 预处理是 OPT/2K cap 口径，不适合 LLaMA2-13B + LongBench-4K；因此这里使用 raw LongBench + LLaMA tokenizer 生成 4K trace。
- 当前 LLaMA2-13B 使用 `/root/data/models/modelscope-llama2-13b-hf`；官方 Meta repo 目录仅包含 tokenizer/config，不包含完整权重。

## OPT-13B + ShareGPT baseline 结果

结果目录：

`/root/data/phase_scheduler_results/e1_opt13b_sharegpt_fcfs_fine_20260529_152721`

配置：

- Model：`/root/data/models/opt-13b`
- Dataset：`opt13b_sharegpt.ds`
- Policy：`fcfs`
- Seeds：`0`
- Num prompts：`128`
- Process：Poisson
- SLO：`TTFT <= 0.25s, TPOT <= 0.10s`
- Server：1P1D, `num_gpus=2`

| Script rate | Offered per-GPU rate | SLO | completed req/s | per-GPU goodput | TTFT p50 | TTFT p90 | TTFT p99 | TPOT p50 | TPOT p90 | TPOT p99 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.50 | 0.25 | 97.7% | 0.502 | 0.245 | 0.091 | 0.211 | 0.256 | 0.025 | 0.028 | 0.032 |
| 0.75 | 0.375 | 95.3% | 0.736 | 0.351 | 0.092 | 0.194 | 0.263 | 0.027 | 0.030 | 0.109 |
| 1.00 | 0.50 | 87.5% | 0.960 | 0.420 | 0.083 | 0.202 | 0.264 | 0.028 | 0.086 | 0.778 |
| 1.25 | 0.625 | 80.5% | 1.172 | 0.471 | 0.091 | 0.209 | 0.263 | 0.031 | 0.294 | 1.715 |
| 1.50 | 0.75 | 59.4% | 1.269 | 0.377 | 0.088 | 0.211 | 0.309 | 0.060 | 0.721 | 3.146 |
| 2.00 | 1.00 | 42.2% | 1.335 | 0.282 | 0.235 | 10.375 | 12.233 | 0.080 | 0.954 | 4.098 |

初步结论：

- 稳定区：script rate `0.50-0.75`，即 offered per-GPU `0.25-0.375`。
- 退化区：script rate `1.00-1.25`，即 offered per-GPU `0.50-0.625`。这一区间适合 E2 主实验优先比较 PhaseServe。
- 过载边界：script rate `1.50-2.00`，即 offered per-GPU `0.75-1.00`。rate `2.00` 出现 TTFT p90/p99 突增，适合边界分析，不适合作为主图核心 claim。
- 退化主要先从 TPOT tail 出现，随后在 rate `2.00` 扩散到 TTFT tail。

## LLaMA2-13B + LongBench-4K smoke

结果目录：

`/root/data/phase_scheduler_results/e1_llama13b_longbench_smoke_20260529_155214`

配置：

- Model：`/root/data/models/modelscope-llama2-13b-hf`
- Dataset：`llama13b_longbench_4k.ds`
- Policy：`fcfs`
- Num prompts：`16`
- Script rate：`0.25`
- `MAX_TOTAL_TOKENS=4096`
- `CONTEXT_MAX_TOKENS_PER_BATCH=4096`
- SLO：`TTFT <= 5s, TPOT <= 0.12s`

结果：

- Completed：`16/16`
- SLO：`93.75%`
- TTFT p50/p90/p99：`0.402 / 0.488 / 0.542s`
- TPOT p50/p90/p99：`0.029 / 0.036 / 2.902s`
- 日志中已出现 2K-3.7K prompt prefill，并触发过 KV swap，说明 LongBench-4K 能给 decode/KV 侧施加真实压力。

## LLaMA2-13B + LongBench-4K baseline 结果

结果目录：

`/root/data/phase_scheduler_results/e1_llama13b_longbench_fcfs_20260529_155658`

配置：

- Model：`/root/data/models/modelscope-llama2-13b-hf`
- Dataset：`llama13b_longbench_4k.ds`
- Policy：`fcfs`
- Seeds：`0`
- Num prompts：`96`
- Process：Poisson
- `MAX_TOTAL_TOKENS=4096`
- `CONTEXT_MAX_TOKENS_PER_BATCH=4096`
- SLO：`TTFT <= 5s, TPOT <= 0.12s`
- Server：1P1D, `num_gpus=2`

| Script rate | Offered per-GPU rate | SLO | completed req/s | per-GPU goodput | TTFT p50 | TTFT p90 | TTFT p99 | TPOT p50 | TPOT p90 | TPOT p99 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.20 | 0.10 | 97.9% | 0.209 | 0.102 | 0.382 | 0.494 | 0.587 | 0.030 | 0.040 | 0.155 |
| 0.25 | 0.125 | 97.9% | 0.259 | 0.127 | 0.385 | 0.489 | 0.564 | 0.030 | 0.041 | 0.350 |
| 0.35 | 0.175 | 95.8% | 0.358 | 0.171 | 0.387 | 0.494 | 0.752 | 0.031 | 0.045 | 3.873 |
| 0.50 | 0.25 | 86.5% | 0.489 | 0.212 | 0.380 | 0.518 | 0.759 | 0.033 | 0.263 | 5.233 |
| 0.75 | 0.375 | 46.9% | 0.676 | 0.158 | 0.473 | 3.677 | 7.308 | 0.105 | 1.268 | 11.946 |

初步结论：

- 稳定区：script rate `0.20-0.25`，即 offered per-GPU `0.10-0.125`。
- 轻度 tail 区：script rate `0.35`，即 offered per-GPU `0.175`。SLO 仍高，但 TPOT p99 已出现明显 outlier。
- 主退化区：script rate `0.50`，即 offered per-GPU `0.25`。SLO 降到 `86.5%`，TPOT p90/p95/p99 均明显上升，而 TTFT 仍相对稳定。
- 过载边界：script rate `0.75`，即 offered per-GPU `0.375`。TTFT 和 TPOT tail 同时扩散，SLO 下降到 `46.9%`。
- 1.0 未继续运行；0.75 已经足够定义过载边界，继续运行会浪费 GPU 且不增加 E1 的窗口信息。

SLO grid 已生成：

- `longbench_tight`: `TTFT <= 5s, TPOT <= 0.12s`
- `longbench_mid`: `TTFT <= 8s, TPOT <= 0.16s`
- `longbench_loose`: `TTFT <= 10s, TPOT <= 0.20s`

在 `longbench_tight` 下，baseline SLO 从 rate `0.35` 的 `95.8%` 降到 rate `0.50` 的 `86.5%`，再降到 rate `0.75` 的 `46.9%`。这个区间适合 E2 主实验优先比较 PhaseServe。

## LLaMA2-13B + ShareGPT baseline 结果

结果目录：

`/root/data/phase_scheduler_results/e1_llama13b_sharegpt_fcfs_20260529_163146`

配置：

- Model：`/root/data/models/modelscope-llama2-13b-hf`
- Dataset：`llama13b_sharegpt.ds`
- Policy：`fcfs`
- Seeds：`0`
- Num prompts：`128`
- Process：Poisson
- SLO：`TTFT <= 0.25s, TPOT <= 0.10s`
- Server：1P1D, `num_gpus=2`

| Script rate | Offered per-GPU rate | SLO | completed req/s | per-GPU goodput | TTFT p50 | TTFT p90 | TTFT p99 | TPOT p50 | TPOT p90 | TPOT p99 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.50 | 0.25 | 96.1% | 0.497 | 0.239 | 0.091 | 0.198 | 0.271 | 0.026 | 0.029 | 0.040 |
| 0.75 | 0.375 | 93.0% | 0.733 | 0.341 | 0.084 | 0.199 | 0.272 | 0.027 | 0.035 | 0.148 |
| 1.00 | 0.50 | 83.6% | 0.960 | 0.401 | 0.081 | 0.198 | 0.277 | 0.029 | 0.168 | 0.896 |
| 1.25 | 0.625 | 72.7% | 1.132 | 0.411 | 0.083 | 0.199 | 0.283 | 0.041 | 0.459 | 1.777 |

初步结论：

- 稳定区：script rate `0.50-0.75`，即 offered per-GPU `0.25-0.375`。
- 主退化区：script rate `1.00-1.25`，即 offered per-GPU `0.50-0.625`。
- 与 OPT-13B + ShareGPT 相似，退化主要由 TPOT tail 驱动；TTFT p90/p99 到 `1.25` 仍相对稳定。
- 1.5/2.0 未继续运行；`1.25` 已经足够定义强退化边界，继续运行不增加 E1 窗口信息。

SLO grid 已生成：

- `distserve`: `TTFT <= 0.25s, TPOT <= 0.10s`
- `loose`: `TTFT <= 0.50s, TPOT <= 0.15s`
- `interactive`: `TTFT <= 1.0s, TPOT <= 0.20s`

在 `distserve` SLO 下，baseline SLO 从 rate `0.75` 的 `93.0%` 降到 rate `1.00` 的 `83.6%`，再降到 rate `1.25` 的 `72.7%`。这个区间适合 E2 中验证 PhaseServe 是否能稳定改善 ShareGPT TPOT tail 和 SLO。

## 验收标准

本阶段完成需要：

1. OPT-13B + ShareGPT 已有可复现 baseline pressure window。
2. LLaMA2-13B + LongBench-4K 已有可复现 baseline pressure window。
3. LLaMA2-13B + ShareGPT 已有可复现 baseline pressure window。
4. 每个 setting 的 rate 选择说明来自 baseline 行为，而不是 PhaseServe 结果。
5. E2 只能在 E1 固定的 workload/rate/seed 上比较 DistServe 和 PhaseServe。

## 风险和阻塞点

- 当前只有 seed 0，正式图需要补 seed 1 或更多 seed 后再报告均值/误差。
- `NUM_PROMPTS=96/128` 的长上下文实验耗时较长，E1 可以先用 seed 0 找窗口，再在候选区间补 seed。
- LLaMA2-13B + LongBench-4K 的 TPOT tail 可能由少数长输出或 KV swap 主导，后续必须用 bucket breakdown 解释。
- 如果 LLaMA2-13B + LongBench 的所有 rate 都过载，应降低 rate 或增大 SLO，而不是直接修改 PhaseServe 方法。
