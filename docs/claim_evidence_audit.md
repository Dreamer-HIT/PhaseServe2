# PhaseServe Claim-Evidence Audit

Updated: 2026-06-01

This document records the current paper-safe claims after the Evaluation,
Related Work, and Conclusion rewrite. It is a writing gate: claims not mapped
here should not be promoted to headline paper results.

## Evidence Roots

| Evidence | Source |
|---|---|
| Stage 4O E2E matrix | `/root/data/phase_scheduler_results/stage4o_e2e_full_matrix_20260531_234957` |
| Stage 4P targeted ablation | `/root/data/phase_scheduler_results/stage4p_targeted_ablation_20260601_101528/opt13b_sharegpt_ablation` |
| Main E2E figure source | `results/figures/stage4q_main_e2e_windows/stage4q_main_latency_windows_summary_source.csv` |
| Main E2E figure | `results/figures/stage4q_main_e2e_windows/stage4q_main_latency_windows_combined.{pdf,png,svg}` |
| Ablation figure source | `results/figures/stage4o_stage4p/stage4p_ablation_seed_mean_source.csv` |
| Ablation figure | `results/figures/stage4o_stage4p/stage4p_ablation_improvement_heatmap.{pdf,png,svg}` |
| Result index | `docs/final_results_index.md` |
| Ablation summary | `docs/stage4p_targeted_ablation.md` |

## Main End-to-End Claims

| Claim | Evidence | Safe wording |
|---|---|---|
| PhaseServe reduces TTFT and TPOT over a DistServe-style baseline on OPT-13B + ShareGPT. | Stage 4Q combined figure; seed0+seed1; per-GPU `1.00-2.75`; TTFT `p50/p90`, TPOT `p90/p95`. | "In the selected OPT-13B + ShareGPT pressure window, PhaseServe reduces TTFT p50/p90 and TPOT p90/p95 over the DistServe-style baseline." |
| PhaseServe generalizes to LLaMA2-13B + ShareGPT. | Stage 4Q combined figure; seed0+seed1; TTFT window `1.00-2.25`; TPOT window `0.75-2.00`; same percentile set. | "The same latency trend appears on LLaMA2-13B + ShareGPT, with workload-sensitive TPOT tail variation." |
| PhaseServe works in a long-context pressure regime. | Stage 4Q combined figure; LLaMA2-13B + LongBench 4K; seed0+seed1; per-GPU `1.00-3.00`. | "On LongBench 4K, PhaseServe improves both TTFT and TPOT tails in the long-context pressure window." |
| The rate windows differ by workload. | `docs/final_results_index.md`; Stage 4Q source CSV. | "The windows differ because prefill, decode, and KV pressure emerge at different offered loads." |

## Component Claims

| Claim | Evidence | Safe wording |
|---|---|---|
| PBC is needed for robust pressure ownership. | Stage 4P `w/o PBC`, seed0+seed1, per-GPU `0.75-2.50`; SLO, TTFT p90, TPOT p90 positive over every measured rate. | "Removing PBC weakens the coordinated pressure response." |
| BPS is needed for budgeted prefill shaping. | Stage 4P `w/o BPS`; same OPT pressure window. | "Removing BPS weakens TTFT/SLO behavior because prefill injection no longer responds to the PBC token/block budget." |
| KAS is needed for decode active-set shaping. | Stage 4P `w/o KAS`; same OPT pressure window. | "Removing KAS weakens TPOT p90 and decode-side active-set control while preserving the same traces." |
| TPOT p99 is tradeoff-sensitive. | Stage 4P heatmap shows non-uniform TPOT p99 gains for some ablations/rates. | "TPOT p99 is reported as a secondary tradeoff metric, not as the headline ablation claim." |

## Claims To Avoid

| Avoided claim | Reason |
|---|---|
| PhaseServe beats DistServe at every rate. | Current figures intentionally select pressure windows; full-rate behavior includes overload and boundary regimes. |
| PhaseServe improves every percentile. | TPOT p99 is not uniformly improved in component ablation. |
| PhaseServe beats vLLM in the current paper results. | Current authoritative Stage 4O/4P matrix compares against a DistServe-style baseline, not vLLM. |
| HumanEval is part of the current evaluation. | Current authoritative workloads are ShareGPT and LongBench 4K. |
| PBC is a formal optimizer. | PBC is an online pressure-budget control contract, not a proof of optimality. |
| PhaseServe solves placement or model parallelism. | PhaseServe keeps a fixed phase-disaggregated deployment and changes runtime scheduling. |

## Current TeX Integration

| Paper item | Status |
|---|---|
| Evaluation setup | Updated to OPT-13B + ShareGPT, LLaMA2-13B + ShareGPT, and LLaMA2-13B + LongBench 4K. |
| Main latency figure | Uses `stage4q_main_latency_windows_combined.pdf`. |
| Main latency table | Reports improvement ranges from the Stage 4Q summary CSV. |
| Ablation figure | Uses `stage4p_ablation_improvement_heatmap.pdf`. |
| Related Work | Rewritten around LLM serving, phase disaggregation, scheduling, and orthogonal parallelism/kernel work. |
| Conclusion | Rewritten around pressure-budgeted scheduling with explicit boundaries. |

## Remaining Audit Items

1. Re-run `make view` after every figure or caption edit.
2. Decide whether the final submission needs a separate SLO-scale figure; do
   not mix it into the main latency claim until the SLO protocol is frozen.
3. If a vLLM comparison is added later, create a separate result root and
   update `docs/final_results_index.md` before writing any vLLM result claim.
4. Run an independent reviewer-style pass before treating the paper as stable.
