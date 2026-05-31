# Stage 4：W0 Policy Smoke Triage

更新时间：2026-05-27

## 本阶段目标

Stage 4 的第一步是运行 W0 policy smoke，确认 Stage 2 新增的 policy、metrics、summary 和分析脚本能在真实 1p1d + 13B 模型上跑通。本轮只验证可运行性和指标链路，不把轻负载结果写成论文结论。

本轮已完成 `OPT-13B` W0 smoke。`LLaMA2-13B` 官方 Meta 模型仍被 HuggingFace gated access 阻塞，需要 token/授权，或由我们明确决定是否使用 `NousResearch/Llama-2-13b-hf` 作为工程 fallback。

## 需要读取或修改的文件

### 已读取文件

| 文件或路径 | 用途 |
|---|---|
| `/root/data/DistServe/scripts/run_phase_hetero_sweep.sh` | 远程 W0 sweep 入口 |
| `/root/data/DistServe/scripts/run_phase_hetero_1p1d.sh` | 单次 1p1d policy 运行入口 |
| `/root/data/phase_scheduler_results/w0_opt13b_gpu085_20260527_135526/sweep_summary.md` | W0 policy summary |
| `/root/data/phase_scheduler_results/w0_opt13b_gpu085_20260527_135526/sweep_analysis.md` | grouped/paired 分析 |
| `/root/data/phase_scheduler_results/w0_opt13b_gpu085_20260527_135526/sweep_analysis.bucket.md` | prompt/output bucket 分析 |
| `/root/data/phase_scheduler_results/w0_opt13b_gpu085_20260527_135526/seed_0/rate_0/*/server.log` | policy 内部指标和启动状态 |

### 本阶段修改文件

| 文件 | 修改内容 |
|---|---|
| `remote_distserve/scripts/run_phase_hetero_1p1d.sh` | 将 `DISTSERVE_CACHE`、`TMPDIR`、`RAY_TMPDIR` 默认放到 `/root/data`，避免系统盘被 13B 权重转换和 Ray 临时文件写满 |
| `docs/stage4_w0_smoke_triage.md` | 记录本次 W0 smoke 结果、验收、风险和下一步 |
| `docs/current_progress.md` | 同步 Stage 4 当前状态 |

## 运行配置

| 项 | 值 |
|---|---|
| server | `js4.blockelite.cn:15330` |
| repo | `/root/data/DistServe` |
| data disk | `/root/data` |
| model | `facebook/opt-13b` |
| model path | `/root/data/models/opt-13b` |
| structure | `1p1d` |
| seed | `0` |
| rate | `0` |
| num prompts | `16` |
| process | `poisson` with burst rate `0` |
| policies | `fcfs spf pure-las kv-unaware-las bps kas bps_kas phase` |
| GPU memory utilization | `0.85` |
| result root | `/root/data/phase_scheduler_results/w0_opt13b_gpu085_20260527_135526` |

模型下载遵循云服务器教程：只使用 `huggingface-cli`。`facebook/opt-13b` 通过内网 `HF_ENDPOINT=http://192.168.50.202:18090` 下载到数据盘；供应商列出的高速 cache 列表中没有 `facebook/opt-13b` 和 `meta-llama/Llama-2-13b-hf`。

## 具体产物

远程已生成：

| 产物 | 路径 |
|---|---|
| per-policy summaries | `/root/data/phase_scheduler_results/w0_opt13b_gpu085_20260527_135526/seed_0/rate_0/*/*.summary.json` |
| per-rate summary | `/root/data/phase_scheduler_results/w0_opt13b_gpu085_20260527_135526/seed_0/rate_0/summary.md` |
| sweep summary | `/root/data/phase_scheduler_results/w0_opt13b_gpu085_20260527_135526/sweep_summary.md` |
| sweep analysis | `/root/data/phase_scheduler_results/w0_opt13b_gpu085_20260527_135526/sweep_analysis.md` |
| bucket analysis | `/root/data/phase_scheduler_results/w0_opt13b_gpu085_20260527_135526/sweep_analysis.bucket.md` |

本地文档产物：

| 产物 | 路径 |
|---|---|
| Stage 4 W0 triage | `docs/stage4_w0_smoke_triage.md` |

## 验收标准

| 验收项 | 状态 | 说明 |
|---|---|---|
| 8 个 policy 全部完成 | 通过 | `fcfs/spf/pure-las/kv-unaware-las/bps/kas/bps_kas/phase` 均 `completed=16`, `failed=0` |
| summary 文件生成 | 通过 | `summary.md/csv`、`sweep_summary.md/csv`、`sweep_analysis.md`、`sweep_analysis.bucket.md` 均生成 |
| BPS 指标非空 | 通过 | `phase_context_token_fill_mean`、`phase_context_pad_waste_mean`、`phase_context_block_risk_mean` 等已写入 |
| KAS 指标非空 | 通过 | `phase_decode_pressure_potential_mean`、`phase_decode_policy_skipped`、`phase_decode_starved_ready`、`phase_decode_infeasible_rounds` 等已写入 |
| PBC 指标非空 | 通过 | `phase_context_prefill_budget_mean=1941`、`phase_context_prefill_budget_ratio_mean=0.947754`，说明 full `phase` 中 PBC budget 生效 |
| 数据盘约束 | 通过 | `/` 为 `52%`，`/root/data` 为 `49%`；DistServe cache 和 Ray tmp 已在数据盘 |
| LLaMA2-13B W0 | 未通过 | 官方 `meta-llama/Llama-2-13b-hf` 需要 HuggingFace 授权或 token |

## OPT-13B W0 结果摘要

这些数字只用于 smoke triage，不用于论文结论。当前 workload 太小、rate 太低，不能证明最终方法优劣。

| policy | completed | goodput req/s | TTFT p50 | TTFT p90 | TTFT p99 | TPOT p50 | TPOT p90 | TPOT p99 | SLO |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| fcfs | 16 | 0.507573 | 0.574545 | 0.604925 | 0.628633 | 0.028589 | 0.078761 | 0.078876 | 1.0 |
| spf | 16 | 0.487311 | 0.259914 | 0.532454 | 0.592184 | 0.026656 | 0.047312 | 0.060216 | 1.0 |
| pure-las | 16 | 0.516494 | 0.462973 | 0.576150 | 0.577950 | 0.033656 | 0.050563 | 0.058365 | 1.0 |
| kv-unaware-las | 16 | 0.526063 | 0.471493 | 0.583393 | 0.585197 | 0.036459 | 0.047209 | 0.051106 | 1.0 |
| bps | 16 | 0.482265 | 0.422210 | 0.600276 | 0.602465 | 0.027905 | 0.063150 | 0.075850 | 1.0 |
| kas | 16 | 0.508651 | 0.489018 | 0.517236 | 0.541035 | 0.035783 | 0.052686 | 0.061661 | 1.0 |
| bps_kas | 16 | 0.507451 | 0.437182 | 0.614589 | 0.615231 | 0.038112 | 0.047190 | 0.049280 | 1.0 |
| phase | 16 | 0.507782 | 0.433875 | 0.611344 | 0.613659 | 0.038240 | 0.048169 | 0.048898 | 1.0 |

相对 `fcfs` 的 paired smoke 信号：

| policy | goodput ratio | TTFT p99 delta | TPOT p99 ratio | 解释 |
|---|---:|---:|---:|---|
| bps | 0.950 | -0.026s | 0.962 | BPS 路径可运行，轻负载下吞吐略低，需 W2 prompt-skew 验证 |
| kas | 1.002 | -0.088s | 0.782 | KAS 路径可运行，轻负载下已有 TPOT tail 改善信号 |
| bps_kas | 1.000 | -0.013s | 0.625 | BPS+KAS 组合可运行，TPOT p99 降低但 TPOT p50 变高 |
| phase | 1.000 | -0.015s | 0.620 | PBC+BPS+KAS 可运行，PBC budget 生效，但需要更高压力 workload 验证 |

## 机制指标检查

### BPS

`bps` 的 context 指标已写入：

- `phase_context_prefill_budget_mean=2048`
- `phase_context_token_fill_mean=0.525391`
- `phase_context_pad_waste_mean=0`
- `phase_context_block_risk_mean=0.111894`
- `phase_context_protected_dispatch_ratio=1`

在 W0 中 `pad_waste=0` 是轻负载和小 batch 的合理结果，不代表 BPS 的主要收益已经被验证。BPS 需要 W2 prompt-skew workload 来制造 prompt size heterogeneity 和 batching tradeoff。

### KAS

`kas` 的 decode 指标已写入：

- `phase_decode_starved_ready=104`
- `phase_decode_starved_selected=78`
- `phase_decode_policy_skipped=882`
- `phase_decode_infeasible_rounds=0`
- `phase_decode_pressure_potential_mean=0.0179449`
- `phase_decode_pressure_injection_swap_mean=0`

W0 中没有 swap-in 和 infeasible rounds，说明压力还不够。KAS 的 KV/swap hard constraint 需要 W3 decode-heavy 和 W4 long-output stress 验证。

### PBC

`phase` 的 PBC 指标已写入：

- `phase_context_prefill_budget_mean=1941`
- `phase_context_prefill_budget_ratio_mean=0.947754`
- `phase_context_goodput_capacity_mean=0.959074`
- `phase_decode_goodput_capacity_mean=0.984645`
- `phase_decode_pressure_potential_mean=0.0188281`

这说明 PBC 已经不只是静态 `bps_kas`，而是在 full `phase` 中收缩了 context prefill budget。当前 W0 压力太低，不能判断这种收缩是否带来端到端收益。

## 风险和阻塞点

1. **LLaMA2-13B gated access**：官方 `meta-llama/Llama-2-13b-hf` 需要 HuggingFace 授权。云服务器的 HF 代理只解决下载路径和速度，不绕过授权。当前不能把 LLaMA2-13B 写成已验证模型。
2. **W0 负载过轻**：所有 policy 的 SLO 都是 `1.0`，且没有 swap pressure。它只能证明可运行，不能证明方法有效。
3. **BPS 主 claim 尚未验证**：W0 下 `pad_waste=0`，说明没有触发 BPS 的主要场景。必须跑 W2 prompt-skew。
4. **KAS hard constraint 尚未充分验证**：W0 下 `swap_ins=0`、`infeasible_rounds=0`。必须跑 W3/W4 才能证明 KV-aware feasibility 的价值。
5. **PBC tradeoff 仍需解释**：`phase` 的 TPOT p99 比 `fcfs` 好，但 TPOT p50 更高。后续需要在更高压力下结合 pressure potential 和 budget ratio 解释。

## 下一步建议

Stage 4 仍未完成，因为 W0 的双模型目标只完成了 OPT-13B。下一步有两个选择：

1. **先继续 OPT-13B pilot**：用已下载好的 OPT-13B 跑 W1 balanced、W2 prompt-skew、W3 decode-heavy 的 2-seed pilot，先验证机制信号。
2. **先解决 LLaMA2-13B**：提供可访问 `meta-llama/Llama-2-13b-hf` 的 HuggingFace token，或明确允许使用 `NousResearch/Llama-2-13b-hf` fallback，并在 artifact 中记录来源。

我建议先走选择 1，同时等待 LLaMA2-13B 授权。这样不会因为 gated model 卡住方法验证循环，也不会把非官方 fallback 混进主实验。
