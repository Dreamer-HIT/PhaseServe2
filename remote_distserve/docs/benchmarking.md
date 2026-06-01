# PhaseServe Benchmark 脚本说明

日期：2026-05-26

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
  --model llama2-7b \
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

## 推荐实验矩阵

当前先做 1P1D + LLaMA2-7B/OPT 对照：

| 维度 | 值 |
|---|---|
| policy | fcfs, cost-compatible-prefill, kv-aware-las-decode, phase |
| workload | tiny, small, ShareGPT-like, LongBench-like |
| arrival | poisson |
| request rate | low, medium, near saturation |
| metrics | TTFT median/P99, TPOT median/P90/P99, SLO attainment, breakdown |

每个 policy/rate 至少跑 3 个 seed，并用 `phase_collect_summaries.py` 汇总。

## 注意事项

- LongBench/LLaMA2 长上下文需要设置 `--max-total-tokens 4096` 或 `--max-total-tokens 0`。
- 当前 LLaMA2 + SwiftTransformer 路径存在 invalid token id workaround，论文级实验需要用 OPT 稳定性对照或根治底层问题。
- `.exp` 只包含成功请求；论文口径的 failure rate 和 submitted-denominator SLO 应以 `.summary.json` 为准。
