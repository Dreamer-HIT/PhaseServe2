# AGENTS.md

本文件给后续 AI agent 提供项目级上下文。它只记录可公开进入仓库的工作规则、当前阶段、路径和文档入口；不要在这里写入密码、token、私钥或任何可直接登录的凭据。

## 项目目标

PhaseServe 是基于 DistServe 的系统研究项目，目标是在 prefill/decode 解耦服务中，通过 `PBC + BPS + KAS` 的阶段感知调度，在合适 workload 和 rate 区间内改善 TTFT、TPOT 和 SLO attainment。

当前状态是 **Stage 4P completed; plot freeze next**。当前重点不是继续发明新方法，而是在已完成的 Stage 4O 端到端矩阵和 Stage 4P 最终消融之上，冻结论文图表窗口并做 claim-evidence audit。

## 进度更新规则

每次发生项目进度变化时，都要同步更新本文件的“当前进度快照”和必要的文档索引。这里的进度变化包括：阶段切换、实验结果新增或废弃、方法论/代码 gap 变化、远端 result root 变化、主实验窗口变化、重要脚本或实现路径变化、文档清理或归档。

`AGENTS.md` 只记录短摘要和入口，不承载完整实验表格。详细数据继续写入 `docs/final_results_index.md`、阶段 summary 或对应实验文档。若只是回答概念问题、解释已有结果，且没有改变项目状态，则不需要改动本文件。

## 当前进度快照

| Item | Current State |
|---|---|
| Stage | Stage 4P targeted paper ablation completed; plot freeze next |
| Main objective | 基于 Stage 4O 完整端到端矩阵和 Stage 4P 最终消融，冻结论文图表窗口并做 claim-evidence audit。 |
| Primary model/dataset | OPT-13B + ShareGPT 是当前主实验候选；LLaMA2-13B + ShareGPT/LongBench 4K 是泛化验证候选。 |
| Strongest current evidence | Stage 4O 统一协议端到端完整矩阵已完成 `240/240`；历史 Stage 4L/4M/4N 结果只作为窗口选择和 sanity-check 参考。 |
| Main blockers | Stage 4P 消融已完成；Stage 4O/4P 完整结果展示图已生成。下一步需要人工确认最终论文图窗口，并做 claim-evidence audit。 |
| Authoritative result index | `docs/final_results_index.md` |
| Latest experiment | Stage 4P targeted ablation root: `/root/data/phase_scheduler_results/stage4p_targeted_ablation_20260601_101528/opt13b_sharegpt_ablation`; merged Stage 4O+4P summary: `/root/data/phase_scheduler_results/stage4p_targeted_ablation_20260601_101528/opt13b_sharegpt_ablation/stage4p_merged_ablation.md`. Stage 4O E2E root: `/root/data/phase_scheduler_results/stage4o_e2e_full_matrix_20260531_234957`. Old full-rate ablation root `/root/data/phase_scheduler_results/stage4o_final_ablation_20260531_234957` is partial reference only (`75/120`). |
| Last AGENTS.md update | 2026-06-01 12:04 CST: generated complete Stage 4O end-to-end and Stage 4P ablation figures under `results/figures/stage4o_stage4p/`; plotting script is `scripts/plot_stage4o_stage4p_figures.py`. |

## 重要文档索引

优先读取这些文件，再决定是否需要翻 archive：

| Priority | File | When to read | Role |
|---|---|---|---|
| P0 | `AGENTS.md` | 每次接手项目时先读 | 全局状态、工作纪律、安全规则、重要入口。 |
| P0 | `docs/current_progress.md` | 判断当前阶段和下一步时 | 当前进度、下一步和最新缺口。 |
| P0 | `docs/final_results_index.md` | 引用任何实验结果前 | 当前可引用 result root 的唯一权威索引。 |
| P0 | `docs/experiment_protocol.md` | 设计或运行实验前 | 实验规则、workload 层次、指标和 claim 约束。 |
| P0 | `results/figures/stage4o_stage4p/` | 查看当前完整结果图时 | Stage 4O 完整端到端图、Stage 4P 消融曲线与消融 heatmap。 |
| P1 | `docs/methodology.md` | 修改方法、解释方法、写论文方法节前 | 当前 PhaseServe 方法定义。 |
| P1 | `docs/methodology_code_alignment.md` | 判断方法和代码是否一致前 | 方法、实现和可声明结论之间的对应关系。 |
| P1 | `docs/stage4l_opt_sharegpt_bridge_budget_repair.md` | 查看 OPT 当前最佳 seed0 证据时 | 最新 OPT-13B + ShareGPT seed0 strict-window 结果。 |
| P1 | `docs/stage4m_opt_sharegpt_seed_replication.md` | 查看 OPT seed1 和内部 seed2 复现记录时 | Stage 4M 复现结果；seed1 是 main evidence，seed2 仅作内部诊断/边界记录。 |
| P1 | `docs/stage4p_targeted_ablation.md` | 查看最终 OPT 组件消融时 | Stage 4P 最终 targeted ablation，含 `48/48` 覆盖和五线组件表。 |
| P2 | `docs/benchmarking.md` | 查 benchmark 指标或脚本约定时 | benchmark 指标、脚本和统计口径。 |
| P2 | `docs/README.md` | 查看文档目录结构时 | docs 顶层入口和 archive 说明。 |
| Archive | `docs/archive/` | 追溯历史调参、失败尝试或阶段记录时 | 历史阶段记录、调参记录和早期计划；默认不要当成当前结论。 |

## 研究流程门禁

后续工作遵循阶段化研究流程。每个阶段完成时必须给出：

- 本阶段目标。
- 读取或修改的关键文件。
- 具体产物。
- 验收标准。
- 风险和阻塞点。
- 是否需要进入下一阶段的用户确认。

不要在阶段完成后自动跳到下一阶段，除非用户在当前上下文里明确要求连续推进。若实验效果不好，可以从 Stage 4 回退到 Stage 0/1/2，但必须记录回退原因：是方法假设、实现 gap、workload、rate 区间、SLO、统计口径还是系统噪声。

## 证据和完整性门禁

- 写论文结果前，必须能把每个 claim 映射到 `docs/final_results_index.md` 中的 result root、数据集、rate 窗口、seed、指标和脚本口径。
- 未复现、未补 seed、只在单点成立或来自历史 debug run 的结果，只能写成候选证据或风险，不能写成最终结论。
- 官方端到端对比必须保证 DistServe/FCFS 和 PhaseServe 使用同一请求集合、同一 arrival trace、同一模型、同一 GPU 拓扑和同一统计脚本。
- 若修改了代码、workload、SLO 或统计口径，必须在对应 summary 或 `docs/final_results_index.md` 记录变化原因。不要把不同协议下的结果混成一张主图。
- 进入论文 outline/初稿前，至少完成一次 claim-evidence audit：逐条检查实验 claim 是否有结果、脚本和配置支撑。
- 最终图表前，至少完成一次当前代码的最终消融和一次跨 seed 检查；不能只依赖 Stage 4L seed0。

## 研究 Skill 参考

本文件按以下本地研究类 skill 的规则做过轻量校准：

- `academic-research-suite`: 用作研究、实验、论文和审稿流程的总入口；后续若任务跨多个阶段，优先按它的 router 判断该读哪个 workflow。
- `academic-pipeline`: 用作阶段门禁参考，尤其是“每阶段完成后先总结并等待确认”“完整性检查”“review/re-review”“claim-evidence audit”。
- `experiment-agent`: 用作实验执行和验证参考，尤其是实验计划、运行监控、复现验证、异常记录和统计解释边界。

后续如果任务变成论文写作、审稿模拟、最终图表或引用核查，应按任务类型再打开对应 skill，而不是只依赖本文件。

## 当前结论边界

- PBC/BPS/KAS 已有当前代码实现；核心方法-代码 gap 较小。
- 最终当前代码消融已完成；仍需补强的是最终图表窗口、机制图和 claim-evidence audit。
- 不要声称 PhaseServe 在所有 rate、所有 workload、所有 percentile 上都提升。
- 主实验 seed 政策已收敛为 seed0 + seed1；不要把 seed2 写入主实验 claim 或最终图表。
- 只引用 `docs/final_results_index.md` 中列出的 result roots。其他远端历史目录只作为 debug/traceability。

## 下一步默认任务

如果用户没有改变方向，优先执行 **Plot Freeze and Claim-Evidence Audit**：

1. 在 OPT-13B + ShareGPT、LLaMA2-13B + ShareGPT、LLaMA2-13B + LongBench 4K 上冻结端到端图表窗口。
2. 使用 `docs/stage4p_targeted_ablation.md` 作为最终 OPT 组件消融依据。
3. 完成 claim-evidence audit 后再进入论文 outline/初稿。

## 远端执行约定

- 远端项目路径：`/root/data/DistServe`
- 大文件和下载优先放数据盘：`/root/data`
- 当前常用 Python：`/root/data/conda-envs/distserve/bin/python`
- 模型目录：
  - `/root/data/models/opt-13b`
  - `/root/data/models/modelscope-llama2-13b-hf`
- 数据集目录：
  - `/root/data/datasets/distserve_eval/processed/llama13b_sharegpt.ds`
  - `/root/data/datasets/distserve_eval/processed/llama13b_longbench_4k.ds`
  - OPT 当前主实验数据集以 `docs/final_results_index.md` 为准。
- 结果根目录：`/root/data/phase_scheduler_results`
- 运行长实验时优先使用 `tmux`/`screen` 或后台任务，避免本地断网导致实验中止。
- LLaMA2-13B + LongBench 4K 的 prefill prompt 超过 2K 时，必须将 `CONTEXT_MAX_TOKENS_PER_BATCH` 提高到至少 `4096`，否则请求会停在 context waiting 而不进入 prefill。
- 可以清理明显无用的系统盘旧缓存或旧库来释放空间，但不要删除当前 conda 环境、模型、数据集、脚本或未归档结果。

## Git 和安全

- Git remote: `git@github.com:Dreamer-HIT/PhaseServe2.git`
- 使用机器上已配置的外部 SSH 凭据；不要把 SSH 私钥、公钥材料、密码、Hugging Face token、ModelScope token 或云服务器登录信息写进仓库。
- 如果用户让你“记录 key”，只能记录“凭据在仓库外部配置”，不能记录 key 内容。
- 提交前检查 `git status --short`。已有 `.codex/skills/...` 删除可能是无关本地状态，除非用户明确要求，否则不要处理。
- 不要把 raw logs、JSONL traces、server logs、模型文件、缓存、大型结果目录或临时输出加入 git。

## 文档治理

- 顶层 `docs/` 只保留当前入口文档。
- 完成的阶段计划、调参记录、失败尝试和早期设计放到 `docs/archive/`。
- 新增结果先写到轻量 summary 或 `docs/final_results_index.md`，不要把大日志搬进仓库。
- 删除旧文档前先判断是否仍是 traceability 证据；对远端结果目录尤其要谨慎，默认先归档索引，不直接删除。

## 实验纪律

- FCFS/DistServe 和 PhaseServe 必须共享同一请求集合和 arrival trace，除非文档明确说明是不同实验。
- `seed` 必须说明控制了什么：请求抽样、请求顺序、arrival 生成或全部。
- 主结果优先报告 TTFT、TPOT、SLO attainment 和吞吐量；不要只挑单一指标。
- 如果实验效果不好，先判断是 workload、rate 区间、SLO、统计口径、实现缺口还是方法假设问题，再决定是否回到 Stage 0/1/2。
- 未验证的假设只能写成计划或风险，不能写成实验结论。
