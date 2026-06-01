# PhaseServe Current Progress

Updated: 2026-06-01

This file is the current-state entry point. Historical repair logs, tuning notes,
and completed stage plans live under `docs/archive/`.

## Current Status

PhaseServe has converged to a `typed/regime-aware PBC + BPS + bridge-budgeted KAS`
design.

- PBC maps runtime pressure into typed admission budgets, bottleneck regimes,
  conflict ownership, and phase utility intensity.
- BPS is the prefill-side TTFT owner. It performs budgeted known-size batch
  shaping under PBC token/block budgets.
- KAS is the decode-side TPOT/KV owner. It performs KV-feasible active-set
  shaping, with first-token protection, bridge-budgeted admission, and
  near-completion promotion.

The main remaining work is no longer broad method invention. Stage 4O completed
the unified end-to-end paper matrix for OPT-13B + ShareGPT, LLaMA2-13B +
ShareGPT, and LLaMA2-13B + LongBench 4K under seed0 + seed1. Stage 4P completed
the targeted final ablation on the OPT-13B + ShareGPT paper window. The current
complete result preview figures have been generated under
`results/figures/stage4o_stage4p/`. Draft main end-to-end latency figures have
also been generated under `results/figures/stage4q_main_e2e_windows/`, using
linear y axes, TTFT `p50+p90`, TPOT `p90+p95`, and the current selected pressure
windows. The directory contains both separate TTFT/TPOT candidate figures and a
compact combined main figure; `paper/PhaseServe.tex` currently uses the combined
version to avoid a stacked full-width figure wall.

The paper-writing focus has now moved to full narrative alignment. The stale
global-controller Design narrative in `paper/PhaseServe.tex` has been replaced
by a PBC/BPS/KAS Design draft, including a pressure-budget formulation, PBC
decision table, typed pressure-to-budget mapping table, BPS/KAS executor table,
PBC and BPS/KAS algorithm blocks, implementation boundary paragraph, and a
successful `make view` compile. A repair pass has resolved the main PBC
ownership ambiguity: context-limited first-token pressure is owned by BPS,
while bridge/first-decode debt is owned by KAS through first-decode admission,
bridge reserve, and completion drain. The TeX text-box Design figures have been
replaced with image-generated mechanism figures under
`results/figures/mechanism/`; the earlier Python/Matplotlib drafts are now
superseded. The current image-generated pair fixes the previous baseline
BPS/KAS mislabeling and aligns the budget-mechanism mapping with the typed PBC
table.
An independent agent re-review is required after this repair pass before
calling the section stable.

The Abstract and Introduction have also been rewritten around the current
method story. The Abstract no longer reports the stale `9x` TTFT and
`2--2.5x` TPOT speedups from earlier drafts. The Introduction now frames the
remaining gap as follows: phase-disaggregated serving removes direct
co-location interference but leaves runtime pressure propagation through bridge
queues, first-token delay, decode backlog, KV-block scarcity, and swap
feasibility. It introduces PhaseServe
as pressure-budgeted phase scheduling with PBC, BPS, and KAS, adds the ACL 2024
LongBench citation for the long-context workload claim, and adds official
WindServe ISCA 2025 and ShuffleInfer ACM TACO 2025 citations for near-neighbor
phase-disaggregated scheduling work. The Introduction now defers exact
percentile-level gains to Evaluation instead of collapsing them into one global
speedup.

The Background and Motivation section has been rewritten to support the current
PBC-centered problem framing. It now argues that phase disaggregation removes
direct co-location interference but leaves runtime pressure propagation across
context waiting, bridge waiting, first-token debt, decode backlog, KV-block
scarcity, and swap feasibility. The old prefill/decode heterogeneity
microbenchmark figures are no longer the main motivation. A new Stage 4O
baseline-only pressure figure has been generated under
`results/figures/motivation/` and inserted into `paper/PhaseServe.tex`. The
figure has been upgraded from a baseline-only 2x2 plot to a 2x3 motivation
figure: baseline TTFT/TPOT tails and queue stacks motivate runtime pressure
propagation, while instrumented hard-pressure and budget-response panels
justify the typed pressure interface without being used as performance claims.
Sarathi has also been updated from an arXiv-style reference to its OSDI 2024
published citation, and the duplicate Sarathi BibTeX entry has been removed.
The Evaluation, Related Work, and Conclusion sections have now been replaced
with a Stage 4O/4P-aligned draft: old OPT-6.7B/66B, HumanEval, vLLM-baseline,
MLFQ-based decode, and proactive-KV result narratives were removed. A new
claim-evidence gate is recorded in `docs/claim_evidence_audit.md`. The draft
compiles with `make view`; remaining warnings are the existing package/layout
warnings rather than missing figures or references. The next step is visual
inspection and an independent reviewer-style pass before treating the paper as
stable.

A server-retirement backup audit was performed on 2026-06-01. The current
remote implementation and experiment harness have been mirrored into
`remote_distserve/`; current paper figures and figure-source CSVs are local
under `results/`; and the restart checklist is recorded in
`docs/server_retirement_backup.md`. No active PhaseServe/vLLM benchmark process
was left running. Old remote raw result directories are treated as disposable
unless listed in `docs/final_results_index.md`.

## Active Documents

| File | Purpose |
|---|---|
| `docs/methodology.md` | Current method definition for PhaseServe. |
| `docs/design_section_plan.md` | Current Design-section writing contract and figure plan. |
| `paper/PhaseServe.tex` | Current paper draft; `PhaseServe Design` has the new PBC/BPS/KAS narrative, typed mapping table, PBC and BPS/KAS algorithm blocks, and image-generated mechanism figures. |
| `docs/methodology_code_alignment.md` | Current method/code/claim alignment and remaining gaps. |
| `docs/experiment_protocol.md` | Experiment rules, workload layers, metrics, and claim guardrails. |
| `docs/final_results_index.md` | Latest result roots and what each result may be used for. |
| `docs/claim_evidence_audit.md` | Current claim-evidence gate for the rewritten Evaluation, Related Work, and Conclusion. |
| `docs/server_retirement_backup.md` | Minimal local backup and quick-restart checklist for continuing after remote server termination. |
| `docs/stage4p_targeted_ablation.md` | Final OPT-13B + ShareGPT targeted component ablation. |
| `results/figures/stage4o_stage4p/` | Current complete Stage 4O/4P result figures. |
| `results/figures/stage4q_main_e2e_windows/` | Draft main end-to-end latency-window figures, including the current combined paper candidate. |
| `results/figures/motivation/` | Stage 4O pressure propagation figure plus instrumented hard-pressure/budget diagnostic panels for Background/Motivation. |
| `results/figures/mechanism/` | Active image-generated PhaseServe overview and budgeted-mechanism figures for the Design section, plus superseded Python drafts. |
| `docs/stage4l_opt_sharegpt_bridge_budget_repair.md` | Latest OPT-13B + ShareGPT seed0 repair and strict-window result. |
| `docs/stage4m_opt_sharegpt_seed_replication.md` | OPT-13B + ShareGPT seed1 main replication plus internal seed2 diagnostic record. |
| `docs/benchmarking.md` | Benchmark metric definitions and script conventions. |
| `docs/archive/` | Historical stage outputs, tuning logs, and early plans. |

## Current Code Mechanisms

The remote implementation under `/root/data/DistServe` contains the current
default mechanisms:

| Mechanism | Current default / role |
|---|---|
| PBC first/decode conflict owner | Protect first-token/bridge progress when hard decode pressure is safe. |
| BPS budgeted prefill shaping | Uses PBC prefill token and block budgets plus bounded progress. |
| KAS short-output FCFS-compatible gate | `PHASESERVE_KAS_SHORT_OUTPUT_FCFS_THRESHOLD=96` for full `phase`. |
| KAS long-output full gate | `PHASESERVE_KAS_LONG_OUTPUT_FULL_THRESHOLD=512` for full `phase`. |
| Bridge-budgeted decode admission | `PHASESERVE_KAS_BRIDGE_WAITING_BLOCK_PROP=0.20` for full `phase`. |
| Bridge short-output fastlane | Enabled for full `phase`, guarded by long-prompt debt. |
| Bridge fastlane guard | `PHASESERVE_KAS_BRIDGE_FASTLANE_GUARD_WAIT_S=12.0`. |
| Bridge completion drain | Enabled for full `phase`. |
| Near-completion promotion | `PHASESERVE_KAS_BRIDGE_COMPLETION_PROMOTE_REMAINING=8`. |
| First-decode reservation | `PHASESERVE_KAS_BRIDGE_COMPLETION_FIRST_DECODE_FRAC=0.75`. |
| Failed branches kept off by default | `PHASESERVE_KAS_BRIDGE_HOL_BYPASS=0`; bridge eviction disabled by default. |

## Latest Evidence

Use `docs/final_results_index.md` as the authoritative list of result roots.
The current high-level evidence is:

1. **Stage 4O full end-to-end matrix**
   The unified paper matrix completed `240/240` summaries under result root
   `/root/data/phase_scheduler_results/stage4o_e2e_full_matrix_20260531_234957`.
   It covers OPT-13B + ShareGPT, LLaMA2-13B + ShareGPT, and LLaMA2-13B +
   LongBench 4K with seed0 + seed1 and per-GPU `0.25-5.0 req/s/GPU` candidate
   rates. It supersedes older Stage 4L/4M/4N roots for final plot-window
   selection, while those older roots remain useful sanity checks.

2. **Stage 4P targeted final ablation**
   The targeted OPT-13B + ShareGPT ablation completed under root
   `/root/data/phase_scheduler_results/stage4p_targeted_ablation_20260601_101528/opt13b_sharegpt_ablation`.
   The matrix is `w/o PBC`, `w/o BPS`, and `w/o KAS` over seed0 + seed1 and
   per-GPU `0.75-2.5 req/s/GPU`; DistServe and Full PhaseServe are reused from
   Stage 4O E2E for the final merged five-line component analysis. Coverage is
   `48/48` for the targeted ablation and `80/80` after merging with Stage 4O.

3. **LLaMA2-13B + ShareGPT, seed0/seed1**
   PhaseServe improves TTFT broadly on per-GPU `1-5` points. Seed1 also improves
   SLO at all points and improves TPOT p90/p95 at all points; TPOT p99 remains
   workload-sensitive and should not be the headline percentile.

4. **LLaMA2-13B + LongBench 4K, seed0/seed1**
   PhaseServe strongly improves TTFT, TPOT, SLO attainment, and goodput on the
   low-rate sweep. Seed1 required `CONTEXT_MAX_TOKENS_PER_BATCH=4096` because
   LongBench 4K prompts exceed the default 2K prefill batch cap. The high-rate
   sweep is better used as latency/stress evidence because the fixed SLO is too
   strict at overload.

5. **Mechanism evidence**
   Stage 4C ablation remains useful as mechanism evidence for PBC/BPS/KAS
   ownership, but it is not the final end-to-end matrix. The old Stage 4O
   full-rate ablation root stopped at `75/120` and should be treated as partial
   reference only.

6. **Exploratory vLLM SLO baseline**
   A vLLM 0.2.3 OPT-13B + ShareGPT SLO run was completed locally as summary
   data under `results/stage4r_vllm_slo_data/` and plotted under
   `results/figures/stage4r_slo_vllm/`. It follows the DistServe OPT-13B
   convention of one vLLM GPU, but the current fixed SLO does not support a
   positive PhaseServe-vs-vLLM claim. Treat it as exploratory until a redesigned
   SLO-scale protocol is approved.

## Current Gaps

The core method-code gap is small. Remaining gaps are experimental and
presentation-facing:

1. The latest Evaluation, Related Work, and Conclusion rewrite compiles, but
   still needs visual inspection before it can be called stable.
2. The current Design figures are now image-generated mechanism figures, but
   still need independent review for visual clarity and top-tier systems-paper
   polish.
3. Final plot windows are drafted from Stage 4O/4Q, but still need a final
   author decision before camera-ready use.
4. SLO values must be frozen per figure. Stage 4L latency evidence is strong,
   but its SLO numbers should not be mixed with stricter WindServe/DistServe
   SLOs without an explicit SLO-scale analysis.
5. Old tuning directories may disappear with the current remote server. Do not
   cite them unless they are listed in `docs/final_results_index.md` and have a
   local source-data or figure snapshot.

## Proposed Next Step

Proceed with **Paper Narrative Alignment + Plot Freeze and Claim-Evidence Audit**:

1. Inspect figure/table placement in the compiled PDF after the
   Evaluation/Related Work/Conclusion rewrite.
2. Run a stale-claim scan against `docs/claim_evidence_audit.md` and
   `docs/final_results_index.md`.
3. Run independent reviewer-style re-review on Abstract, Introduction,
   Background, Design, Evaluation, Related Work, and Conclusion.
4. Visually polish the current image-generated mechanism figures if the re-review flags
   readability or claim-evidence issues.
5. Freeze or revise the SLO figure plan; do not add vLLM claims unless a new
   matched result root is created.
6. Use `docs/stage4p_targeted_ablation.md` as the final OPT component ablation
   evidence.
7. Finalize Abstract and Conclusion only after the claim-evidence audit passes.
