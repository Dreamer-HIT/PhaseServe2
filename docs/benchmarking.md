# PhaseServe Benchmark 脚本说明

日期：2026-05-29

## 主入口

推荐使用：

```bash
python benchmarks/phase_native_benchmark.py \
  --dataset /root/data/phase_scheduler_results/synthetic_phase_sched_small.marshal \
  --num-prompts 8 \
  --sample-mode first \
  --request-rate 2.0 \
  --process-name poisson \
  --seed 11 \
  --max-connections 4 \
  --timeout-s 180 \
  --max-total-tokens 2048 \
  --num-gpus 2 \
  --label script-check-phase \
  --policy phase \
  --model llama2-13b \
  --slo-ttft-s 0.25 \
  --slo-tpot-s 0.05 \
  --output /root/data/phase_scheduler_results/script_check/phase-small-8.exp
```

## 输出文件

一次运行会产生三类文件：

- `.exp`：兼容 DistServe 原有 `RequestResult` JSON 格式，只包含成功请求。
- `.jsonl`：逐请求原始记录，包含成功与失败请求。
- `.summary.json`：汇总指标，用于论文图表和 CSV 汇总。

`.summary.json` 现在包含：

- throughput: offered/submitted/completed request throughput、SLO goodput、per-GPU throughput/goodput、input/output token throughput。
- `latency_s`: median/P50、P90、P95、P99、mean、max。
- `ttft_s`: median/P50、P90、P95、P99、mean、max。
- `tpot_s`: median/P50、P90、P95、P99、mean、max。
- lifecycle breakdown: context queue、context exec、bridge queue、migration、decode queue、decode exec。
- SLO attainment: completed denominator 和 submitted denominator 两种。
- prompt/output bucket breakdown。
- failure records。

## 汇总多次实验

使用：

```bash
python benchmarks/phase_collect_summaries.py \
  /root/data/phase_scheduler_results/script_check \
  --output-csv /root/data/phase_scheduler_results/script_check/summary.csv \
  --output-md /root/data/phase_scheduler_results/script_check/summary.md
```

生成的 CSV 用于画图，Markdown 用于快速检查。

## 真实 Trace / Length Trace 数据集生成

E1 baseline calibration 开始支持 `DATASET_GENERATOR=trace`。该模式通过 `benchmarks/phase_make_trace_dataset.py` 将 ShareGPT、LongBench 或只有长度字段的 CSV/JSON/JSONL 转成 DistServe benchmark 使用的 `.marshal` 数据集，并可同时输出 request metadata。

示例：ShareGPT trace。

```bash
cd /root/data/DistServe
MODEL_NAME=opt-13b MODEL_PATH=/root/data/models/opt-13b \
TRACE_INPUT=/root/data/datasets/sharegpt.json \
TRACE_SOURCE=sharegpt \
TRACE_MAX_TOTAL_TOKENS=2048 \
DATASET_GENERATOR=trace \
POLICIES=fcfs \
SEEDS="0 1" RATES="0.5 1 1.5 2 2.5 3" \
NUM_PROMPTS=256 DATASET_SIZE=256 \
./scripts/run_phase_trace_baseline_sweep.sh
```

示例：LongBench trace。

```bash
cd /root/data/DistServe
MODEL_NAME=llama2-13b MODEL_PATH=/root/data/models/modelscope-llama2-13b-hf \
TRACE_INPUT=/root/data/datasets/longbench.jsonl \
TRACE_SOURCE=longbench \
TRACE_MAX_TOTAL_TOKENS=4096 \
DATASET_GENERATOR=trace \
POLICIES=fcfs \
SEEDS="0 1" RATES="0.25 0.5 0.75 1 1.25 1.5" \
NUM_PROMPTS=256 DATASET_SIZE=256 \
MAX_TOTAL_TOKENS=4096 \
./scripts/run_phase_trace_baseline_sweep.sh
```

示例：LLaMA2-13B + ShareGPT generalization calibration。

```bash
cd /root/data/DistServe
MODEL_NAME=llama2-13b MODEL_PATH=/root/data/models/modelscope-llama2-13b-hf \
TRACE_INPUT=/root/data/datasets/sharegpt.json \
TRACE_SOURCE=sharegpt \
TRACE_MAX_TOTAL_TOKENS=4096 \
DATASET_GENERATOR=trace \
POLICIES=fcfs \
SEEDS="0 1" RATES="0.5 1 1.5 2 2.5 3" \
NUM_PROMPTS=256 DATASET_SIZE=256 \
MAX_TOTAL_TOKENS=4096 \
./scripts/run_phase_trace_baseline_sweep.sh
```

如果只有长度分布文件，可使用 `TRACE_SOURCE=lengths`，文件需要包含 `prompt_len` 和 `output_len` 字段。可通过 `TRACE_PROMPT_LEN_FIELD` 和 `TRACE_OUTPUT_LEN_FIELD` 改字段名。默认会使用 tokenizer 生成相同 token 长度的中性 prompt。

## 指标定义

- TTFT：第一个 token timestamp 减客户端请求 start time。
- TPOT：第一个输出 token 之后的平均 token interval，即 `(last_token_ts - first_token_ts) / (num_tokens - 1)`；若只生成 1 个 token，则记为 0。
- E2E latency：客户端请求 start 到响应 body 完整返回。
- SLO attainment：同时满足 `TTFT <= slo_ttft_s` 和 `TPOT <= slo_tpot_s` 的请求比例。
- Completed throughput：成功完成请求数除以 wall-clock benchmark 时间。
- SLO goodput：同时满足 TTFT/TPOT SLO 的成功请求数除以 wall-clock benchmark 时间。
- Per-GPU goodput：SLO goodput 除以 `--num-gpus`，用于对齐 DistServe 的 per-GPU rate 口径。
- Token throughput：成功请求的 prompt tokens、生成 output tokens、prompt+generated tokens 分别除以 wall-clock benchmark 时间。

注意：lifecycle breakdown 使用服务端 `time.time()` 事件之间的差值；TTFT/TPOT/E2E 使用 API server 返回的 `time.perf_counter()` timestamp，因此不要混合两类绝对时间，只比较差值。

## SLO 口径

早期脚本示例中的 `--slo-ttft-s 0.25` / `--slo-tpot-s 0.05` 只适合 tiny smoke，不适合作为 13B 论文结果。Stage 4D 的 OPT-13B / LLaMA-13B mixed-wide 探索结果使用：

```text
TTFT <= 5s
TPOT <= 0.12s
```

旧口径 `TTFT<=10s, TPOT<=1s` 对 13B mixed-regime 过松，只作为 sanity check、调试或历史记录。最终论文图的 SLO 口径尚未冻结，应以 `docs/final_results_index.md` 中列出的最新结果和后续 Stage 4M 复验为准。tight/medium/loose SLO grid 仍可用于 sensitivity，但主图应固定使用同一 SLO，不按 rate 单独调整。

## 历史 Stage 4D 矩阵

以下矩阵是 Stage 4D mixed-wide 探索实验使用过的配置，后续正式实验入口以 `docs/experiment_protocol.md` 的 E1-E5 为准。

| 维度 | 值 |
|---|---|
| policy | fcfs, phase |
| ablation policy | bps, kas, bps_kas, phase |
| workload | mixed-wide / cross-skew mixed-regime |
| arrival | poisson |
| request rate | TTFT 主窗口 per-GPU `2/3/4/5/6/8` req/s；TPOT 主窗口 per-GPU `2/3/4/5/6/8/10/12/14/16` req/s；SLO scale 固定 per-GPU `6` req/s |
| metrics | SLO attainment, TTFT p90/p95, TPOT p50/p90, throughput/goodput, bucket breakdown |

Stage 4D 已完成 `fcfs` vs `phase` 的双模型、双 seed探索结果，并补充了 TPOT high-rate per-GPU `14/16` 确认矩阵。它保留为历史机制和画图经验。当前可引用结果入口转为 `docs/final_results_index.md`；下一步推荐在最新 Stage 4L 窗口上补 seed 和最终消融，而不是继续扩大旧 Stage 4D rate 搜索。

## 注意事项

- LongBench/LLaMA2 长上下文需要设置 `--max-total-tokens 4096` 或 `--max-total-tokens 0`。
- 当前 LLaMA2 + SwiftTransformer 路径存在 invalid token id workaround，论文级实验需要用 OPT-13B 稳定性对照或根治底层问题。
- `.exp` 只包含成功请求；论文口径的 failure rate 和 submitted-denominator SLO 应以 `.summary.json` 为准。
