# PhaseServe Methodology-Code Alignment

Updated: 2026-05-31

This document records the current alignment between the PhaseServe methodology,
the implemented DistServe extension, and the claims that are supported by the
latest experiments.

## Alignment Summary

There is no major remaining gap where the methodology describes a core mechanism
that the code does not implement. The current implementation includes:

- typed pressure observation and pressure-to-budget mapping;
- regime ownership for first-token, decode-heavy, KV/swap-limited, and mixed
  regimes;
- BPS as budgeted prefill shaping;
- KAS as KV-feasible decode active-set shaping;
- hard KV/swap feasibility before soft utility scoring;
- first/decode conflict arbitration;
- bridge-budgeted decode admission;
- near-completion promotion to release KV without violating first-token
  ownership.

The main remaining gaps are now presentation and final-audit gaps: the current
two-seed Stage 4O matrix, targeted Stage 4P ablation, and result indexing are in
place, but the paper still needs final plot-window/SLO decisions, independent
review, and full claim-evidence audit.

## Current Method Contract

PhaseServe is a `typed regime-aware pressure-budgeted phase scheduling` method
for phase-disaggregated LLM serving.

1. **PBC** observes bridge, first-token, decode, KV, and swap pressure.
2. **PBC** maps pressure into typed budgets: prefill token budget, prefill block
   margin, decode scan limit, decode swap budget, bridge admission budget, and
   decode utility intensity.
3. **PBC** assigns a regime owner. First-token-limited regimes prioritize BPS;
   decode-heavy regimes prioritize KAS; KV/swap-limited regimes prioritize hard
   feasibility; mixed regimes use explicit arbitration.
4. **BPS** uses the budget to form known-size prefill batches while bounding
   padding waste, block risk, and long-prompt starvation.
5. **KAS** uses the budget to select a KV-feasible decode active set while
   protecting first decode, preserving resident requests, and promoting only
   near-completion non-first-decode requests under bridge pressure.

## Implemented Mechanisms

### PBC

Implemented:

- component pressure vector: bridge, first-token, decode, KV, swap;
- typed budget vector: prefill token budget, block margin, decode scan limit,
  swap budget, utility intensity, and bridge admission relaxation;
- regime classification and mode-switch metrics;
- smoothing, hysteresis, and budget floors;
- conflict owner for first-token versus decode-tail pressure;
- pressure-potential and pressure-injection diagnostics.

Boundary:

PBC is an online control contract, not a global optimizer. `pressure_potential`,
`goodput_capacity`, and `progress_debt` are diagnostic or surrogate quantities,
not formal optimality guarantees.

### BPS

Implemented:

- bounded-window candidate selection;
- prompt bucket and cost-compatible prefill batching;
- token-fill, padding-waste, block-risk, and oldest-progress scoring;
- PBC prefill token and block budgets as feasibility gates;
- protected-oldest progress to avoid unbounded long-prompt starvation.

Boundary:

BPS is the TTFT/prefill owner. It should not be claimed as an independent
solution for all TPOT or SLO outcomes. Its mechanism evidence should be reported
with prompt bucket and long-prompt fairness metrics.

### KAS

Implemented:

- attained-service and KV-aware decode scoring;
- resident preference and starvation counters;
- GPU block, swap-count, and swap-byte feasibility gates;
- PBC-controlled decode utility intensity;
- short-output FCFS-compatible eligibility;
- long-output full-KAS eligibility;
- bridge-budgeted admission;
- bridge short-output fastlane with long-prompt debt guard;
- bridge completion drain with near-completion promotion;
- first-decode reservation through `PHASESERVE_KAS_BRIDGE_COMPLETION_FIRST_DECODE_FRAC=0.75`;
- near-completion threshold through `PHASESERVE_KAS_BRIDGE_COMPLETION_PROMOTE_REMAINING=8`.

Boundary:

KAS currently supports TPOT p50/p90 and selected p95 improvements more strongly
than universal TPOT p99 improvement. TPOT p99 should be treated as a boundary or
appendix metric unless later multi-seed evidence stabilizes it.

## Current Default Mechanism State

| Mechanism | Current code state |
|---|---|
| Short-output FCFS-compatible gate | `PHASESERVE_KAS_SHORT_OUTPUT_FCFS_THRESHOLD=96` for full `phase`. |
| Long-output full-KAS gate | `PHASESERVE_KAS_LONG_OUTPUT_FULL_THRESHOLD=512` for full `phase`. |
| Bridge waiting budget | `PHASESERVE_KAS_BRIDGE_WAITING_BLOCK_PROP=0.20` for full `phase`. |
| Bridge short-output fastlane | Enabled for full `phase`, guarded by long-prompt debt. |
| Fastlane guard wait | `PHASESERVE_KAS_BRIDGE_FASTLANE_GUARD_WAIT_S=12.0`. |
| Bridge completion drain | Enabled for full `phase`. |
| Near-completion promotion | `PHASESERVE_KAS_BRIDGE_COMPLETION_PROMOTE_REMAINING=8`. |
| First-decode reservation | `PHASESERVE_KAS_BRIDGE_COMPLETION_FIRST_DECODE_FRAC=0.75`. |
| HOL bypass | Disabled by default. |
| Bridge eviction | Disabled by default. |

## Supported Claims

Currently supported as working claims:

1. PhaseServe has an implemented typed pressure-budget control path rather than
   a loose collection of independent heuristics.
2. BPS and KAS are connected through PBC budgets and conflict ownership.
3. Stage 4O provides the current two-seed end-to-end matrix for OPT-13B +
   ShareGPT, LLaMA2-13B + ShareGPT, and LLaMA2-13B + LongBench 4K.
4. Stage 4Q provides the current draft main latency windows: TTFT `p50/p90` and
   TPOT `p90/p95` over selected pressure windows.
5. Stage 4P provides the current final targeted OPT component ablation for
   `w/o PBC`, `w/o BPS`, and `w/o KAS` over seed0 + seed1.
6. TPOT p99 remains tradeoff-sensitive and should be treated as a boundary or
   secondary metric unless later evidence stabilizes it.

## Claims To Avoid

Do not claim:

1. PhaseServe improves every percentile at every rate.
2. Higher request rate always increases PhaseServe's relative gain.
3. TPOT p99 is universally improved.
4. PBC provides a formal optimality guarantee.
5. Throughput is the primary contribution.
6. Stage 4L seed0 alone is enough for a final paper result without seed1.

## Remaining Work

| Gap | Why it matters | Required action |
|---|---|---|
| Plot/SLO freeze | Main latency windows are drafted; SLO presentation is not frozen. | Use `docs/claim_evidence_audit.md` and `docs/final_results_index.md` before adding or changing claims. |
| Independent review | Major paper sections have been rewritten. | Run reviewer-style pass before treating the draft as stable. |
| Mechanism diagnostics | Mechanism figures are image-generated; some low-level counters are not in main text. | Extract budget timelines/regime shares only if the final narrative needs additional mechanism evidence. |
| Result hygiene | Many remote tuning roots remain. | Cite only roots listed in `docs/final_results_index.md`. |

## Paper-Framing Guidance

The clean paper story is:

```text
phase disaggregation leaves runtime pressure propagation
-> typed pressure-budget control contract
-> regime ownership and conflict arbitration
-> budgeted prefill and KV-feasible decode shaping
-> end-to-end latency/SLO gains in selected pressure windows
-> component evidence and boundary cases
```

The evidence should be tied to model, dataset, seed count, rate window, and
percentile. Boundary cases and tradeoffs should be reported explicitly.
