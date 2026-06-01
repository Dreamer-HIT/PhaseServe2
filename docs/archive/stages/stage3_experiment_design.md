# Stage 3：实验设计与 workload 构造

更新时间：2026-05-27

## Material Passport

- Origin Skill: experiment-agent
- Origin Mode: plan
- Verification Status: UNVERIFIED
- Version Label: phaseserve_stage3_experiment_design_v1

## 本阶段目标

Stage 3 的目标是把 PhaseServe 的方法 claim 转化为可执行、可证伪、可回退的实验设计。这个阶段只设计 workload、policy matrix、指标口径和 Stage 4 分析规则，不运行完整实验，不写论文结果。

核心原则是：

1. 每个 claim 必须绑定一个 workload、一个主要 baseline、一个机制指标和一个端到端指标。
2. 每个新增 policy 必须先做 smoke run，再进入多 seed sweep。
3. 实验结果不好时，先归因，再决定回到 Stage 0/1/2/3 的哪一层。
4. 论文只能写 Stage 4 已验证的结果；本阶段不把预期收益写成结论。

## 需要读取或修改的文件

### 已读取文件

| 文件 | 用途 |
|---|---|
| `docs/methodology.md` | 抽取 PBC/BPS/KAS 的论文 claim 和机制指标 |
| `docs/stage1_code_mapping_plan.md` | 对齐 claim-baseline contract |
| `docs/stage2_implementation_summary.md` | 对齐已实现 policy、指标和风险 |
| `docs/current_progress.md` | 对齐当前状态和下一步缺口 |
| `remote_distserve/scripts/run_phase_hetero_1p1d.sh` | 确认 1p1d 执行入口、policy 映射和 env 参数 |
| `remote_distserve/scripts/run_phase_hetero_sweep.sh` | 确认 seed/rate sweep 入口 |
| `remote_distserve/scripts/run_phase_prefill_skew_sweep.sh` | 确认 BPS prompt-skew workload |
| `remote_distserve/scripts/run_phase_decode_heavy_sweep.sh` | 确认 KAS/PBC decode-heavy workload |
| `remote_distserve/scripts/run_phase_ablation_sweep.sh` | 确认主组件消融入口 |
| `remote_distserve/scripts/run_phase_pbc_sweep.sh` | 确认 PBC 消融入口 |
| `remote_distserve/scripts/run_phase_bps_internal_sweep.sh` | 确认 BPS 内部消融入口 |
| `remote_distserve/benchmarks/phase_native_benchmark.py` | 确认 TTFT/TPOT、throughput、bucket 和 SLO 口径 |
| `remote_distserve/benchmarks/phase_collect_summaries.py` | 确认 summary flatten 字段 |
| `remote_distserve/benchmarks/phase_analyze_sweep.py` | 确认 grouped/paired/bucket 分析输出 |

### 本阶段修改文件

| 文件 | 修改内容 |
|---|---|
| `docs/stage3_experiment_design.md` | 新增本阶段实验设计文档 |
| `docs/current_progress.md` | 同步 Stage 3 状态和 Stage 4 入口 |
| `remote_distserve/scripts/run_phase_hetero_1p1d.sh` | 将默认模型从 7B 改为 13B，并用 `MODEL_NAME` 写入 summary |

本阶段不修改调度器和 benchmark。由于实验模型从 LLaMA2-7B 改为 OPT-13B/LLaMA2-13B，运行脚本需要修正默认模型路径和 summary model label。

## 实验问题与 claim 映射

| Claim | 要回答的问题 | Workload | 主要 baseline | 端到端指标 | 机制指标 |
|---|---|---|---|---|---|
| BPS | BPS 是否不只是 shortest-prompt-first，而是在控制 pad waste / block risk 的同时改善 prompt-skew 下 TTFT | prompt-skew | `fcfs`, `spf`, `bps_bucket_only` | TTFT p50/p90/p99, context queue p90/p99, SLO, throughput | `pad_waste`, `block_risk`, `token_fill`, `protected_dispatch_ratio`, `long_prompt_max_wait` |
| KAS | KAS 是否不只是 LAS，而是通过 KV-aware active-set 降低 decode tail | decode-heavy, long-output stress | `fcfs`, `pure-las`, `kv-unaware-las` | TPOT p50/p90/p99, decode queue p90/p99, output token throughput | `resident_admission_ratio`, `swap_ins`, `swap_in_bytes`, `swap_byte_budget_ratio`, `starved_admission_ratio`, `infeasible_rounds` |
| PBC | PBC 是否能把 decode/KV/swap pressure 转成有效 budget，降低 pressure propagation | decode-heavy burst | `bps_kas`, `bps_pbc`, `kas_pbc` | SLO goodput, TPOT tail, TTFT tradeoff, throughput | `pressure_potential`, `pressure_injection_prefill`, `pressure_injection_decode_swap`, `prefill_budget_ratio`, `decode_scan_limit`, `rho_*` |
| Full PhaseServe | PBC+BPS+KAS 是否在混合 workload 下给出更好的瓶颈指标，同时没有不可解释的 tail/fairness 退化 | balanced hetero | `fcfs`, `bps`, `kas`, `bps_kas` | SLO goodput, TTFT/TPOT p50/p90/p99, request throughput, token throughput | 以上机制指标的组合 |

## 模型维度

Stage 3 之后的所有实验都按两个模型维度设计：

| Model label | HF repo | 建议 `MODEL_NAME` | 建议 `MODEL_PATH` | 用途 |
|---|---|---|---|---|
| LLaMA2-13B | `meta-llama/Llama-2-13b-hf` | `llama2-13b` | `/root/data/models/llama2-13b-hf` | 主模型之一，替代早期 LLaMA2-7B 验证 |
| OPT-13B | `facebook/opt-13b` | `opt-13b` | `/root/data/models/opt-13b` | 第二主模型，用于验证方法不依赖 LLaMA 系列结构 |

LLaMA2-13B 的 canonical repo 是 Meta 官方的 `meta-llama/Llama-2-13b-hf`，通常需要 HuggingFace token 和 license access。`NousResearch/Llama-2-13b-hf` 只作为官方 repo 下载失败时的工程 fallback；若使用 fallback，Stage 4 triage memo 和论文 artifact 需要明确记录 repo 来源。

如果远程实际模型目录不同，Stage 4 只需要替换 `MODEL_PATH`。当前 `run_phase_hetero_1p1d.sh` 会优先使用显式传入的 `MODEL_NAME`；如果未传入，则会根据 `MODEL_PATH` 自动推断 `llama2-13b` 或 `opt-13b` 并写入 summary。

执行顺序建议：

1. W0 policy smoke 对两个模型都跑。
2. W1-W3 pilot 先跑 LLaMA2-13B；如果机制指标正常，再跑 OPT-13B。
3. Final 5-seed 只对 Stage 4 triage 后保留下来的核心矩阵在两个模型上展开。

## Workload 设计

### W0：Policy Smoke

目标：确认 Stage 2 新增 policy 在远程 1p1d + 13B 模型上能启动、跑完、写出 summary 和 phase metrics。后续实验模型固定为 `OPT-13B` 和 `LLaMA2-13B`，不再使用 `LLaMA2-7B`。

| 项 | 设置 |
|---|---|
| seeds | `0` |
| rates | `0` |
| num prompts | `16` 或 `24` |
| process | burst，`REQUEST_RATE=0` |
| prompt mix | 默认 hetero：`64:0.50,256:0.30,512:0.20` |
| output mix | 默认 hetero：`64:0.30,128:0.30,256:0.20,512:0.15,1024:0.05` |
| policies | `fcfs spf pure-las kv-unaware-las bps kas bps_kas phase` |

验收标准：

1. 所有 policy 完成且 `failed=0`，或失败原因明确。
2. 非 FCFS policy 生成 `phase_metrics.jsonl`。
3. `summary.csv`、`summary.md`、`sweep_analysis.md`、`sweep_analysis.bucket.md` 生成。
4. 新增字段非空：BPS 至少有 `phase_context_pad_waste_mean`，KAS 至少有 `phase_decode_pressure_injection_swap_mean`。

建议命令：

```bash
cd /root/data/DistServe
MODEL_NAME=llama2-13b MODEL_PATH=/root/data/models/llama2-13b-hf \
SEEDS="0" RATES="0" NUM_PROMPTS=16 DATASET_SIZE=16 \
POLICIES="fcfs spf pure-las kv-unaware-las bps kas bps_kas phase" \
./scripts/run_phase_hetero_sweep.sh

MODEL_NAME=opt-13b MODEL_PATH=/root/data/models/opt-13b \
SEEDS="0" RATES="0" NUM_PROMPTS=16 DATASET_SIZE=16 \
POLICIES="fcfs spf pure-las kv-unaware-las bps kas bps_kas phase" \
./scripts/run_phase_hetero_sweep.sh
```

### W1：Balanced Heterogeneous Sanity

目标：测试完整方法在混合 prompt/output 下是否有基本收益或明显退化。

| 项 | 设置 |
|---|---|
| seeds | pilot: `0 1`; final: `0 1 2 3 4` |
| rates | pilot: `0 1 2`; final 根据 pilot 保留 2-3 个压力点 |
| num prompts | `48` |
| process | `poisson`，其中 `rate=0` 表示 burst |
| prompt mix | `64:0.50,256:0.30,512:0.20` |
| output mix | `64:0.30,128:0.30,256:0.20,512:0.15,1024:0.05` |
| policies | `fcfs bps kas bps_kas phase` |

主要指标：

- SLO attainment submitted
- goodput req/s
- completed req/s
- generated output tokens/s
- total generated tokens/s
- TTFT p50/p90/p99
- TPOT p50/p90/p99

### SLO 口径修正

原始脚本默认 `SLO_TTFT_S=10`、`SLO_TPOT_S=1`。该设置对 13B 1p1d 实验过松，容易让所有 policy 的 SLO attainment 都变成 `1.0`，只能表示没有明显失败，不能区分调度效果。

Stage 4 之后采用两层口径：

1. 主指标仍然报告 TTFT/TPOT 的 p50/p90/p99、request throughput、token throughput 和 bucket breakdown。
2. SLO-goodput 采用 post-hoc grid，从每次 run 的 raw JSONL 重新计算，不为不同 SLO 重跑实验。

默认 SLO grid 为：

| label | TTFT SLO | TPOT SLO | 用途 |
|---|---:|---:|---|
| tight | 1.0s | 0.10s | 区分低尾延迟策略，可能牺牲部分长输出请求 |
| medium | 1.5s | 0.20s | 作为 13B balanced/decode-heavy pilot 的主 SLO 观察点 |
| loose | 2.0s | 0.30s | 检查策略在较宽松服务目标下是否仍有 goodput 差异 |

Stage 4D 之后的最新端到端主结果采用额外的 interactive SLO：

| label | TTFT SLO | TPOT SLO | 用途 |
|---|---:|---:|---|
| stage4d-main | 5.0s | 0.12s | OPT-13B / LLaMA-13B mixed-wide 主图口径，能稳定区分 DistServe FCFS 与 PhaseServe |

该 SLO 不替代上面的 tight/medium/loose grid；它是 Stage 4D 根据双模型 mixed-wide 结果选择的主图口径。后续论文图表应固定使用同一模型内一致的 SLO，不按 rate 单独调阈值。

脚本产物：

- `slo_grid.csv`
- `slo_grid.md`
- `slo_grid.grouped.csv`
- `slo_grid.grouped.md`

后续论文主图使用 Stage 4D 的固定 SLO 口径，同时保留 SLO grid 作为 sensitivity。若所有 policy 在某一档 SLO 下均为 `1.0`，该档只作为 sanity check，不作为主要对比。

机制指标：

- context/decode `pressure_potential`
- `prefill_budget_ratio`
- `pressure_injection_prefill`
- `pressure_injection_decode_swap`
- `phase_decode_rho_memory_mean`
- `phase_decode_rho_swap_mean`

建议命令：

```bash
cd /root/data/DistServe
MODEL_NAME=llama2-13b MODEL_PATH=/root/data/models/llama2-13b-hf \
SEEDS="0 1" RATES="0 1 2" NUM_PROMPTS=48 DATASET_SIZE=48 \
POLICIES="fcfs bps kas bps_kas phase" \
./scripts/run_phase_hetero_sweep.sh
```

### W2：Prompt-Skew for BPS

目标：验证 BPS 的收益是否来自 cost-compatible batching，而不是简单短 prompt 优先。

| 项 | 设置 |
|---|---|
| seeds | pilot: `0 1`; final: `0 1 2 3 4` |
| rates | pilot: `0 6 10`; final 根据 pilot 选择 2-3 个压力点 |
| num prompts | `96` |
| process | `poisson`，`rate=0` 为 burst |
| prompt mix | `64:0.45,512:0.25,1024:0.20,1536:0.10` |
| output mix | `32:0.60,64:0.30,128:0.10` |
| policies | `fcfs spf bps bps_bucket_only bps_no_oldest_bonus bps_age_bonus` |

主要比较：

1. `bps` vs `fcfs`：是否改善 prompt-skew 下 TTFT 和 context queue。
2. `bps` vs `spf`：是否优于纯短 prompt 优先，尤其看 long prompt tail。
3. `bps` vs `bps_bucket_only`：cost scoring 是否比只做 bucket grouping 更有效。
4. `bps` vs `bps_no_oldest_bonus` / `bps_age_bonus`：bounded-progress 机制是否必要。

主要指标：

- 全局 TTFT p50/p90/p99
- prompt bucket TTFT p90/p99
- context queue p90/p99/max
- long prompt max wait
- SLO attainment
- input token throughput 和 total token throughput

机制指标：

- `phase_context_token_fill_mean`
- `phase_context_pad_waste_mean`
- `phase_context_block_risk_mean`
- `phase_context_protected_dispatch_ratio_mean`
- `phase_context_protected_feasible_dispatch_ratio_mean`
- `phase_context_long_prompt_max_wait_mean`

建议命令：

```bash
cd /root/data/DistServe
MODEL_NAME=llama2-13b MODEL_PATH=/root/data/models/llama2-13b-hf \
SEEDS="0 1" RATES="0 6 10" \
POLICIES="fcfs spf bps bps_bucket_only bps_no_oldest_bonus bps_age_bonus" \
./scripts/run_phase_prefill_skew_sweep.sh
```

Stage 4 判断规则：

- 如果 `bps` 只赢 `fcfs` 但输给 `spf`，说明方法 claim 需要收窄或 BPS scoring 需要回 Stage 2 修改。
- 如果 `bps` 改善短 prompt 但 long prompt max wait 显著失控，必须回 Stage 0 收窄 claim 或回 Stage 2 强化 bounded-progress。
- 如果 `pad_waste/block_risk` 没变化但 TTFT 变化明显，说明当前机制指标解释力不足，需要回 Stage 3 补指标或回 Stage 2 改 instrumentation。

### W3：Decode-Heavy for KAS/PBC

目标：验证 KAS 是否通过 KV-aware attained-service active-set 降低 TPOT tail，并验证 PBC 是否能限制 decode pressure propagation。

| 项 | 设置 |
|---|---|
| seeds | pilot: `0 1`; final: `0 1 2 3 4` |
| rates | pilot: `0 2`; final 可加 `3` 或 `4`，但先以不大量失败为准 |
| num prompts | `48` |
| process | `poisson`，`rate=0` 为 burst |
| prompt mix | `64:0.60,256:0.25,512:0.15` |
| output mix | `128:0.25,256:0.30,512:0.30,1024:0.15` |
| policies | `fcfs pure-las kv-unaware-las kas bps_kas phase` |

主要比较：

1. `kas` vs `fcfs`：KAS 是否降低 TPOT tail。
2. `kas` vs `pure-las`：是否不只是 attained-service/LAS 的收益。
3. `kas` vs `kv-unaware-las`：KV-aware tie-break 和 swap feasibility 是否必要。
4. `phase` vs `bps_kas`：PBC 是否在 BPS+KAS 基础上进一步降低 pressure 或改善 SLO。

主要指标：

- TPOT p50/p90/p99
- output bucket TPOT p90/p99
- decode queue p90/p99
- generated output tokens/s
- SLO attainment
- TTFT p50/p90/p99 作为 tradeoff

机制指标：

- `phase_decode_swap_ins`
- `phase_decode_evictions`
- `phase_decode_pressure_injection_swap_mean`
- `phase_decode_swap_byte_budget_ratio_mean`
- `phase_decode_starved_admission_ratio_mean`
- `phase_decode_infeasible_rounds_mean`
- `phase_decode_policy_skipped_mean`
- `phase_decode_rho_memory_mean`
- `phase_decode_rho_swap_mean`

建议命令：

```bash
cd /root/data/DistServe
MODEL_NAME=llama2-13b MODEL_PATH=/root/data/models/llama2-13b-hf \
SEEDS="0 1" RATES="0 2" \
POLICIES="fcfs pure-las kv-unaware-las kas bps_kas phase" \
./scripts/run_phase_decode_heavy_sweep.sh
```

Stage 4 判断规则：

- 如果 `kas` 和 `pure-las` 接近，KAS 的 KV-aware claim 需要弱化，或必须证明 overhead/fairness 更好。
- 如果 `kas` 不优于 `kv-unaware-las`，说明 resident preference / swap budget 的设计需要回 Stage 2。
- 如果 `phase` 降 TPOT 但 TTFT 大幅恶化，PBC claim 要写成 tradeoff-aware，或回 Stage 2 调整 budget mapping。

### W4：Long-Output Stress

目标：验证 KAS 在长输出请求上没有不可解释的 starvation，并观察 long-output bucket 的 TPOT tail。

| 项 | 设置 |
|---|---|
| seeds | pilot: `0 1` |
| rates | `0 1` |
| num prompts | `40` |
| process | `poisson` |
| prompt mix | `64:0.70,256:0.30` |
| output mix | `256:0.20,512:0.35,1024:0.45` |
| max total tokens | `1400` 或更高，避免数据构造失败 |
| policies | `fcfs pure-las kv-unaware-las kas phase` |

建议命令：

```bash
cd /root/data/DistServe
MODEL_NAME=llama2-13b MODEL_PATH=/root/data/models/llama2-13b-hf \
SEEDS="0 1" RATES="0 1" NUM_PROMPTS=40 DATASET_SIZE=40 \
PROMPT_MIX="64:0.70,256:0.30" \
OUTPUT_MIX="256:0.20,512:0.35,1024:0.45" \
MAX_TOTAL_TOKENS=1400 TIMEOUT_S=2400 \
POLICIES="fcfs pure-las kv-unaware-las kas phase" \
./scripts/run_phase_hetero_sweep.sh
```

主要指标：

- output bucket `>512` 的 TPOT p90/p99
- output bucket `>512` 的 decode queue p90/p99
- `phase_decode_max_skip_max`
- `phase_decode_max_infeasible_max`
- `phase_decode_starved_admission_ratio_mean`
- failure rate 和 timeout

Stage 4 判断规则：

- 如果 long-output bucket 明显退化但 short/medium bucket 改善，论文必须显式报告 tail transfer。
- 如果 `max_skip` 或 `max_infeasible` 异常高，回 Stage 2 调 KAS fairness 或 swap feasibility。
- 如果失败率升高，先回 Stage 3 降低 rate/num prompts 或调整 max total tokens，不先改方法论。

### W5：PBC Sensitivity

目标：验证 PBC 不是固定阈值 heuristic，而是可解释 pressure-to-budget controller。

第一批只比较 dynamic vs static：

| 项 | 设置 |
|---|---|
| workload | decode-heavy |
| policies | `bps_kas bps_pbc kas_pbc phase` |
| baseline | `bps_kas` |
| seeds | pilot: `0 1` |
| rates | `0 2` |

建议命令：

```bash
cd /root/data/DistServe
MODEL_NAME=llama2-13b MODEL_PATH=/root/data/models/llama2-13b-hf \
SEEDS="0 1" RATES="0 2" \
POLICIES="bps_kas bps_pbc kas_pbc phase" \
BASELINE_POLICY="bps_kas" \
./scripts/run_phase_decode_heavy_sweep.sh
```

第二批再做 aggregation sensitivity：

```bash
cd /root/data/DistServe
MODEL_NAME=llama2-13b MODEL_PATH=/root/data/models/llama2-13b-hf \
PHASESERVE_PBC_AGG=max \
SEEDS="0 1" RATES="0 2" POLICIES="bps_kas phase" BASELINE_POLICY="bps_kas" \
./scripts/run_phase_decode_heavy_sweep.sh

MODEL_NAME=llama2-13b MODEL_PATH=/root/data/models/llama2-13b-hf \
PHASESERVE_PBC_AGG=weighted \
SEEDS="0 1" RATES="0 2" POLICIES="bps_kas phase" BASELINE_POLICY="bps_kas" \
./scripts/run_phase_decode_heavy_sweep.sh

MODEL_NAME=llama2-13b MODEL_PATH=/root/data/models/llama2-13b-hf \
PHASESERVE_PBC_AGG=lexicographic \
SEEDS="0 1" RATES="0 2" POLICIES="bps_kas phase" BASELINE_POLICY="bps_kas" \
./scripts/run_phase_decode_heavy_sweep.sh
```

注意：aggregation sensitivity 不建议第一轮就跑 5 seeds。只有当 `phase` vs `bps_kas` 已经表现出可解释差异时，再扩展。

## Byte-Level Swap Budget 策略

`PHASESERVE_DECODE_SWAP_BUDGET_BYTES` 在 Stage 2 默认关闭。Stage 3 建议采用两步：

1. 第一批 W0/W1/W2/W3 先保持默认 `0`，避免新增 byte budget 影响已有 KAS 主链路。
2. 如果 W3 中 swap pressure 或 swap bytes 较高，再做 sensitivity：

```bash
PHASESERVE_DECODE_SWAP_BUDGET_BYTES=1073741824
```

`1073741824` 是 1 GiB，用作 13B 模型 1p1d 的保守初值。它不是论文参数结论，只是 sensitivity 起点。Stage 4 需要报告 byte budget 是否开启、具体值和对 swap/stall/TPOT 的影响。

## Rate 与 Seed 规则

### Rate 解释

在当前 benchmark 中：

- `REQUEST_RATE=0` 表示所有请求尽快提交，是 burst 压力测试，不是 0 req/s。
- 正数 rate 表示 Poisson 到达时的 offered request rate，单位是 requests/s。

因此论文和文档中不要把 `rate=0` 写成“零负载”，应写成 “burst arrival”。

### Seed 解释

每个 seed 同时控制 dataset generation 和 benchmark sampling：

- `DATASET_SEED`
- `BENCHMARK_SEED`

当前 sweep 脚本让两者相同。论文中可以说每个 seed 对应一个独立 synthetic trace。

### 扩 seed 策略

1. Smoke：`seed=0`。
2. Pilot：`seed=0 1`。
3. Final：只对通过 pilot 的核心矩阵扩到 `seed=0 1 2 3 4`。

不建议所有矩阵都直接 5 seeds。系统实验更应该先保证机制信号成立，再扩统计稳定性。

## 指标口径

### 端到端指标

必须报告：

- TTFT p50/p90/p99
- TPOT p50/p90/p99
- SLO attainment submitted
- goodput req/s
- completed req/s
- generated output tokens/s
- total generated tokens/s
- failure rate

其中吞吐量优先级：

1. `goodput_req_s`：满足 TTFT/TPOT SLO 的请求吞吐。
2. `completed_req_s`：完成请求吞吐。
3. `generated_output_tokens_s`：decode token throughput。
4. `total_generated_tokens_s`：input + generated token throughput。

### Bucket 指标

必须按 bucket 报告：

- prompt bucket：TTFT p90/p99、context queue p90/max、SLO attainment。
- output bucket：TPOT p90/p99、decode queue p90、decode per output token p99、SLO attainment。

### 机制指标

PBC：

- `phase_context_pressure_potential_mean`
- `phase_decode_pressure_potential_mean`
- `phase_context_pressure_injection_prefill_mean`
- `phase_decode_pressure_injection_swap_mean`
- `phase_context_prefill_budget_ratio_mean`
- `phase_decode_goodput_capacity_mean`
- `phase_context_goodput_capacity_mean`

BPS：

- `phase_context_token_fill_mean`
- `phase_context_pad_waste_mean`
- `phase_context_block_risk_mean`
- `phase_context_protected_dispatch_ratio_mean`
- `phase_context_protected_feasible_dispatch_ratio_mean`
- `phase_context_long_prompt_max_wait_mean`

KAS：

- `phase_decode_swap_ins`
- `phase_decode_evictions`
- `phase_decode_swap_byte_budget_ratio_mean`
- `phase_decode_starved_admission_ratio_mean`
- `phase_decode_policy_skipped_mean`
- `phase_decode_infeasible_rounds_mean`
- `phase_decode_max_infeasible_mean`

## Stage 4 分析顺序

Stage 4 不应先看全局平均。建议按以下顺序分析：

1. **Correctness gate**：completed、failed、timeout、summary 文件是否完整。
2. **Smoke gate**：新增 policy 是否都有机制指标。
3. **End-to-end bottleneck**：按 workload 看 TTFT/TPOT/SLO/goodput。
4. **Bucket attribution**：看收益是否集中在目标 bucket，是否产生 tail transfer。
5. **Mechanism attribution**：看机制指标是否支持方法解释。
6. **Tradeoff accounting**：明确哪些指标改善，哪些指标变差。
7. **Loop decision**：决定进入下一轮 Stage 0/1/2/3，还是扩 seeds。

## Stage 4 Result Triage 模板

每次 Stage 4 结束必须写一个 triage memo，格式如下：

```text
Result Triage Memo

Experiment:
Workload:
Policies:
Seeds/Rates:

Supported claims:
- ...

Weakened claims:
- ...

Unexpected results:
- ...

Mechanism evidence:
- PBC:
- BPS:
- KAS:

Tradeoffs:
- ...

Decision:
- Continue to more seeds
- Return to Stage 0: revise methodology/claim
- Return to Stage 1: remap method to code
- Return to Stage 2: modify implementation
- Return to Stage 3: modify workload/metrics
```

## 风险和阻塞点

1. 新增 `spf/pure-las/kv-unaware-las` 只做过本地编译验证，远程 smoke 可能失败。
2. `rate=0` burst 容易放大 tail，也可能掩盖 steady-state 行为；必须和 Poisson rate 一起报告。
3. Prompt-skew 与 decode-heavy 的 rate 数值不可直接横向比较，因为 prompt/output token distribution 不同。
4. 1p1d + 13B 双模型仍是最小验证，不足以直接支撑所有顶会主文 claim；通过后仍需要考虑更多 GPU 结构。
5. 当前 workload 是 synthetic trace，论文中需要清楚说明它验证的是机制控制能力，不等价于真实生产 trace。

## 本阶段验收标准

Stage 3 完成的条件：

1. 每个主要 claim 都有 workload、baseline、指标和失败回退规则。
2. W0 smoke run 能覆盖所有 Stage 2 新增 policy。
3. W1-W5 能覆盖 balanced、prompt-skew、decode-heavy、long-output stress 和 PBC sensitivity。
4. 明确哪些是 expected improvement，哪些是 tradeoff/diagnostic。
5. 明确 Stage 4 分析顺序和 result triage 模板。

本阶段到此为实验设计完成。是否进入 Stage 4，需要先确认从 W0 smoke 开始执行。
