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
`results/figures/stage4o_stage4p/`.

## Active Documents

| File | Purpose |
|---|---|
| `docs/methodology.md` | Current method definition for PhaseServe. |
| `docs/methodology_code_alignment.md` | Current method/code/claim alignment and remaining gaps. |
| `docs/experiment_protocol.md` | Experiment rules, workload layers, metrics, and claim guardrails. |
| `docs/final_results_index.md` | Latest result roots and what each result may be used for. |
| `docs/stage4p_targeted_ablation.md` | Final OPT-13B + ShareGPT targeted component ablation. |
| `results/figures/stage4o_stage4p/` | Current complete Stage 4O/4P result figures. |
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

## Current Gaps

The core method-code gap is small. Remaining gaps are experimental and
presentation-facing:

1. Final plot windows still need to be frozen from the Stage 4O E2E matrix.
2. SLO values must be frozen per figure. Stage 4L latency evidence is strong,
   but its SLO numbers should not be mixed with stricter WindServe/DistServe
   SLOs without an explicit SLO-scale analysis.
3. Old tuning directories remain on the remote server for traceability. Do not
   cite them unless they are listed in `docs/final_results_index.md`.

## Proposed Next Step

Proceed with **Plot Freeze and Claim-Evidence Audit**:

1. Freeze the OPT-13B + ShareGPT seed0 + seed1 figure windows from Stage 4O.
2. Freeze the LLaMA2-13B ShareGPT and LongBench 4K seed0 + seed1 generalization
   figure windows.
3. Use `docs/stage4p_targeted_ablation.md` as the final OPT component ablation
   evidence.
4. Run claim-evidence audit before moving to paper outline.
