# AGENTS.md

本文件给后续 AI agent 提供项目级上下文。它只记录可公开进入仓库的工作规则、当前阶段、路径和文档入口；不要在这里写入密码、token、私钥或任何可直接登录的凭据。

## 项目目标

PhaseServe 是基于 DistServe 的系统研究项目，目标是在 prefill/decode 解耦服务中，通过 `PBC + BPS + KAS` 的阶段感知调度，在合适 workload 和 rate 区间内改善 TTFT、TPOT 和 SLO attainment。

当前状态是 **Stage 5 paper narrative rewrite in progress**。当前重点不是继续发明新方法，而是在已完成的 Stage 4O 端到端矩阵和 Stage 4P 最终消融之上，统一论文 PBC/BPS/KAS 叙事、冻结论文图表窗口并做 claim-evidence audit。

## 进度更新规则

每次发生项目进度变化时，都要同步更新本文件的“当前进度快照”和必要的文档索引。这里的进度变化包括：阶段切换、实验结果新增或废弃、方法论/代码 gap 变化、远端 result root 变化、主实验窗口变化、重要脚本或实现路径变化、文档清理或归档。

`AGENTS.md` 只记录短摘要和入口，不承载完整实验表格。详细数据继续写入 `docs/final_results_index.md`、阶段 summary 或对应实验文档。若只是回答概念问题、解释已有结果，且没有改变项目状态，则不需要改动本文件。

## 当前进度快照

| Item | Current State |
|---|---|
| Stage | Stage 5 paper narrative rewrite in progress; Abstract, Introduction, Background, Design, Evaluation, Related Work, and Conclusion rewritten against current Stage 4O/4P evidence |
| Main objective | 基于 Stage 4O/4P 结果和当前 PBC/BPS/KAS 方法，统一论文叙事，继续冻结主图窗口、SLO 展示策略与 claim-evidence audit，并处理全论文一致性和排版问题。 |
| Primary model/dataset | OPT-13B + ShareGPT 是当前主实验候选；LLaMA2-13B + ShareGPT/LongBench 4K 是泛化验证候选。 |
| Strongest current evidence | Stage 4O 统一协议端到端完整矩阵已完成 `240/240`；历史 Stage 4L/4M/4N 结果只作为窗口选择和 sanity-check 参考。 |
| Main blockers | Stage 4P 消融已完成；Stage 4Q 主端到端延迟候选图已按当前窗口生成，并已生成 related-papers 风格的 combined 主图插入 `paper/PhaseServe.tex`。新版 `PhaseServe Design`、Abstract、Introduction 与 Background 已改为 PBC/BPS/KAS pressure-budgeted 叙事；Design 现包含 PBC 和 BPS/KAS 两个 algorithm blocks、typed pressure-to-budget mapping table，并已用 image-generated 机制图替换 TeX 文本占位。Evaluation、Related Work、Conclusion 已删除旧 OPT-6.7B/66B、HumanEval、vLLM baseline、MLFQ/proactive-KV 叙事，改为 Stage 4O/4P 证据边界，并已通过 `make view` 编译。服务器停租前备份审计已完成，当前远程实现已镜像到 `remote_distserve/`，当前图和图源已在本地。剩余 blocker 是独立审稿式复查、SLO 单图策略和最终全论文 claim-evidence audit。 |
| Authoritative result index | `docs/final_results_index.md` |
| Latest experiment | Stage 4P targeted ablation root: `/root/data/phase_scheduler_results/stage4p_targeted_ablation_20260601_101528/opt13b_sharegpt_ablation`; merged Stage 4O+4P summary: `/root/data/phase_scheduler_results/stage4p_targeted_ablation_20260601_101528/opt13b_sharegpt_ablation/stage4p_merged_ablation.md`. Stage 4O E2E root: `/root/data/phase_scheduler_results/stage4o_e2e_full_matrix_20260531_234957`. Stage 4R vLLM OPT-13B + ShareGPT exploratory root: `/root/data/phase_scheduler_results/stage4r_vllm_slo_opt13b_sharegpt_20260601_203255`; local summary copied, but not paper-safe as a positive claim under current fixed SLO. |
| Last AGENTS.md update | 2026-06-01 21:35 CST: performed server-retirement backup audit; synced current remote implementation and phase benchmark scripts to `remote_distserve/`; added `docs/server_retirement_backup.md`; recorded vLLM SLO exploratory status and local backup boundaries. |

## 重要文档索引

优先读取这些文件，再决定是否需要翻 archive：

| Priority | File | When to read | Role |
|---|---|---|---|
| P0 | `AGENTS.md` | 每次接手项目时先读 | 全局状态、工作纪律、安全规则、重要入口。 |
| P0 | `docs/current_progress.md` | 判断当前阶段和下一步时 | 当前进度、下一步和最新缺口。 |
| P0 | `docs/design_section_plan.md` | 重写 PhaseServe Design 或画 Design 图前 | Design section 的写作契约、图表计划、claim-evidence map 和 TeX 替换规则。 |
| P0 | `docs/final_results_index.md` | 引用任何实验结果前 | 当前可引用 result root 的唯一权威索引。 |
| P0 | `docs/claim_evidence_audit.md` | 写或审查论文 claim 前 | 当前 Evaluation/Related Work/Conclusion 重写后的 claim-evidence gate。 |
| P0 | `docs/server_retirement_backup.md` | 服务器停租后重启项目或迁移远端前 | 最小本地备份清单、可丢弃旧数据边界和快速恢复步骤。 |
| P0 | `docs/experiment_protocol.md` | 设计或运行实验前 | 实验规则、workload 层次、指标和 claim 约束。 |
| P0 | `results/figures/stage4o_stage4p/` | 查看当前完整结果图时 | Stage 4O 完整端到端图、Stage 4P 消融曲线与消融 heatmap。 |
| P0 | `results/figures/stage4q_main_e2e_windows/` | 查看当前主端到端候选图时 | 线性 y 轴；TTFT 用 `p50+p90`，TPOT 用 `p90+p95`；包含 combined 主图和 TTFT/TPOT 分图，当前 `paper/PhaseServe.tex` 使用 combined 图。 |
| P0 | `results/figures/motivation/` | 查看当前 Background/Motivation 图时 | Stage 4O baseline pressure propagation plus instrumented hard-pressure/budget diagnostic figure。 |
| P0 | `results/figures/mechanism/` | 查看当前 Design 机制图时 | Active image-generated PhaseServe overview and budgeted-mechanism figures used by `paper/PhaseServe.tex`; Python/Matplotlib mechanism drafts are superseded. |
| P1 | `remote_distserve/` | 服务器失效后恢复实现或迁移新机器时 | 当前 DistServe 修改版实现、benchmark harness 和实验脚本的本地镜像。 |
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
- 新增或修改参考文献前，必须优先查官方 venue、publisher、DBLP、ACM、USENIX、IEEE 或 ACL Anthology 等正式记录；已经正式发表的论文不要继续引用 arXiv/preprint 版本。
- 重大方法论、论文 Design、核心实验图或算法修复后，不要只凭主 agent 自评结束；至少启动一个独立子 agent 复审。若修复涉及顶会 claim、机制图或 PBC/BPS/KAS 算法语义，优先要求复审给出 `Reject / Weak Reject / Borderline / Weak Accept / Accept / Strong Accept` 等级和 P0/P1 风险。
- 官方端到端对比必须保证 DistServe/FCFS 和 PhaseServe 使用同一请求集合、同一 arrival trace、同一模型、同一 GPU 拓扑和同一统计脚本。
- 若修改了代码、workload、SLO 或统计口径，必须在对应 summary 或 `docs/final_results_index.md` 记录变化原因。不要把不同协议下的结果混成一张主图。
- 进入论文 outline/初稿前，至少完成一次 claim-evidence audit：逐条检查实验 claim 是否有结果、脚本和配置支撑。
- 最终图表前，至少完成一次当前代码的最终消融和一次跨 seed 检查；不能只依赖 Stage 4L seed0。
- 论文图表进入正文后，必须检查源数据、绘图脚本、导出 PDF/SVG/PNG、caption 语义和 TeX 编译结果；图中若混合 baseline 结果与 instrumented diagnostics，caption 必须明确区分。

## 研究 Skill 参考

本文件按以下本地研究类 skill 的规则做过轻量校准：

- `academic-research-suite`: 用作研究、实验、论文和审稿流程的总入口；后续若任务跨多个阶段，优先按它的 router 判断该读哪个 workflow。
- `academic-pipeline`: 用作阶段门禁参考，尤其是“每阶段完成后先总结并等待确认”“完整性检查”“review/re-review”“claim-evidence audit”。
- `experiment-agent`: 用作实验执行和验证参考，尤其是实验计划、运行监控、复现验证、异常记录和统计解释边界。
- `nature-writing`: 用作 Introduction/Background/Design 的方法论文叙事约束，尤其是一段一个任务、claim 靠近证据、方法模块 motivation/mechanism/evidence hook。
- `nature-figure`: 用作论文图表工作流约束；当前主 Design 机制图按用户要求改用 image model 生成，Python/Matplotlib 机制图仅保留为 superseded draft。

后续如果任务变成论文写作、审稿模拟、最终图表或引用核查，应按任务类型再打开对应 skill，而不是只依赖本文件。

## 当前结论边界

- PBC/BPS/KAS 已有当前代码实现；核心方法-代码 gap 较小。
- 最终当前代码消融已完成；Design 机制图已切换为 image-generated 版本，仍需补强的是最终图表窗口和全论文 claim-evidence audit。
- 不要声称 PhaseServe 在所有 rate、所有 workload、所有 percentile 上都提升。
- 主实验 seed 政策已收敛为 seed0 + seed1；不要把 seed2 写入主实验 claim 或最终图表。
- 只引用 `docs/final_results_index.md` 中列出的 result roots。其他远端历史目录只作为 debug/traceability。

## 下一步默认任务

如果用户没有改变方向，优先执行 **Paper Narrative Alignment + Plot/SLO Freeze and Review**：

1. 检查 `make view` 生成的 PDF 中 Evaluation/Related Work/Conclusion 新图表位置。
2. 扫描旧叙事残留，尤其是 OPT-6.7B/66B、HumanEval 评测、vLLM baseline、MLFQ、proactive KV。
3. 复审当前正式 image-generated 机制图和 Stage 4Q/4P 图是否达到系统顶会论文可读性，必要时继续视觉微调。
4. 冻结或重画 SLO 单图；若要加入 vLLM，必须先补独立 result root，不可直接写结果 claim。
5. 使用 `docs/claim_evidence_audit.md` 和 `docs/stage4p_targeted_ablation.md` 做最终全论文 claim-evidence audit。
6. 独立审稿式复查通过后，再打磨 Abstract 和 Conclusion 的最终数值表达。

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
- 如果当前远端服务器停租，优先使用 `docs/server_retirement_backup.md`
  和 `remote_distserve/` 在新机器恢复；旧 raw result directories 可丢弃。

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
