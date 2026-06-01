# Stage 4P Targeted Ablation

Updated: 2026-06-01

## Goal

Stage 4P replaces the earlier exhaustive full-rate ablation with a
paper-calibrated component ablation. The goal is to evaluate whether PBC, BPS
and KAS are needed in the same OPT-13B + ShareGPT pressure window used for the
main end-to-end claim.

## Protocol

| Field | Value |
|---|---|
| Model | OPT-13B |
| Dataset | ShareGPT-derived Stage 4O request sets |
| Structure | 1P1D, 2 GPUs |
| Seeds | seed0 + seed1 |
| Requests | 128 per run |
| Arrival | Poisson |
| Global rates | `1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5` req/s |
| Per-GPU rates | `0.75-2.50` req/s/GPU |
| SLO | TTFT `0.25s`, TPOT `0.10s` |
| Baseline/full data | Reused from Stage 4O E2E |
| Ablation variants | `w/o PBC`, `w/o BPS`, `w/o KAS` |

The ablation variants use the exact Stage 4O OPT seed0/seed1 request files:

| Seed | Dataset |
|---:|---|
| 0 | `/root/data/phase_scheduler_results/stage4o_e2e_full_matrix_20260531_234957/opt13b_sharegpt/datasets/opt13b_sharegpt_seed_0_128.ds` |
| 1 | `/root/data/phase_scheduler_results/stage4o_e2e_full_matrix_20260531_234957/opt13b_sharegpt/datasets/opt13b_sharegpt_seed_1_128.ds` |

## Result Roots

| Role | Root |
|---|---|
| Stage 4O E2E OPT root | `/root/data/phase_scheduler_results/stage4o_e2e_full_matrix_20260531_234957/opt13b_sharegpt` |
| Stage 4P targeted ablation root | `/root/data/phase_scheduler_results/stage4p_targeted_ablation_20260601_101528/opt13b_sharegpt_ablation` |
| Coverage file | `/root/data/phase_scheduler_results/stage4p_targeted_ablation_20260601_101528/opt13b_sharegpt_ablation/stage4p_ablation_coverage.json` |
| Merged ablation summary | `/root/data/phase_scheduler_results/stage4p_targeted_ablation_20260601_101528/opt13b_sharegpt_ablation/stage4p_merged_ablation.md` |
| Merged CSV prefix | `/root/data/phase_scheduler_results/stage4p_targeted_ablation_20260601_101528/opt13b_sharegpt_ablation/stage4p_merged_ablation.*.csv` |

Coverage audit:

- Stage 4P targeted ablation complete: `48/48`.
- Stage 4O E2E + Stage 4P merged coverage: `80/80`.
- Missing runs: `0`.
- Incomplete runs: `0`.
- No remote `screen`, benchmark or DistServe server process remained after the run.

## PhaseServe vs DistServe

Values are seed0+seed1 averages. Positive latency percentages mean PhaseServe is
lower than DistServe. Positive SLO values are percentage-point gains.

| Per-GPU rate | SLO +pp | TTFT p90 % | TTFT p99 % | TPOT p90 % | TPOT p99 % | Goodput % |
|---:|---:|---:|---:|---:|---:|---:|
| 0.75 | 21.5 | 2.2 | 1.0 | 87.8 | 90.9 | 18.2 |
| 1.00 | 25.0 | 94.3 | 95.9 | 77.0 | 82.4 | 28.5 |
| 1.25 | 30.1 | 88.8 | 72.4 | 46.5 | 50.9 | 79.8 |
| 1.50 | 14.8 | 61.3 | 52.9 | 42.1 | 41.9 | 32.8 |
| 1.75 | 14.1 | 40.5 | 34.4 | 35.4 | 15.5 | 36.0 |
| 2.00 | 11.7 | 28.6 | 30.5 | 34.2 | 13.3 | 30.7 |
| 2.25 | 11.7 | 30.7 | 23.3 | 29.4 | 8.4 | 33.0 |
| 2.50 | 8.2 | 30.2 | 22.2 | 31.5 | 21.1 | 19.2 |

## Component Ablation

Positive latency percentages mean Full PhaseServe is lower than the ablation.
Positive SLO values mean Full PhaseServe has higher attainment than the
ablation.

| Per-GPU rate | Ablation | SLO +pp | TTFT p90 % | TTFT p99 % | TPOT p90 % | TPOT p99 % |
|---:|---|---:|---:|---:|---:|---:|
| 0.75 | w/o PBC | 17.6 | 2.3 | -0.3 | 85.1 | 86.8 |
| 0.75 | w/o BPS | 17.6 | 1.6 | 1.6 | 84.7 | 86.6 |
| 0.75 | w/o KAS | 21.9 | 1.3 | -0.1 | 88.3 | 91.4 |
| 1.00 | w/o PBC | 27.0 | 95.0 | 96.6 | 77.4 | 77.3 |
| 1.00 | w/o BPS | 26.2 | 94.9 | 96.4 | 76.7 | 79.0 |
| 1.00 | w/o KAS | 25.8 | 94.7 | 96.1 | 77.8 | 82.4 |
| 1.25 | w/o PBC | 27.3 | 90.3 | 74.5 | 46.6 | 27.4 |
| 1.25 | w/o BPS | 27.7 | 88.9 | 74.7 | 49.4 | 39.1 |
| 1.25 | w/o KAS | 29.7 | 88.5 | 72.8 | 51.0 | 52.2 |
| 1.50 | w/o PBC | 15.2 | 65.4 | 60.3 | 39.5 | 18.2 |
| 1.50 | w/o BPS | 16.0 | 62.0 | 55.5 | 41.0 | 24.9 |
| 1.50 | w/o KAS | 14.8 | 63.3 | 55.7 | 43.7 | 30.9 |
| 1.75 | w/o PBC | 12.5 | 44.7 | 43.7 | 34.3 | -26.5 |
| 1.75 | w/o BPS | 13.3 | 43.1 | 38.5 | 38.8 | -11.8 |
| 1.75 | w/o KAS | 13.3 | 41.7 | 45.4 | 39.9 | -1.8 |
| 2.00 | w/o PBC | 10.2 | 33.8 | 40.3 | 32.5 | -27.5 |
| 2.00 | w/o BPS | 9.8 | 29.7 | 32.1 | 33.0 | -11.2 |
| 2.00 | w/o KAS | 11.3 | 30.8 | 38.5 | 35.9 | 0.5 |
| 2.25 | w/o PBC | 9.4 | 32.9 | 32.6 | 26.3 | -32.9 |
| 2.25 | w/o BPS | 10.5 | 33.5 | 28.3 | 29.3 | -23.9 |
| 2.25 | w/o KAS | 10.5 | 32.4 | 31.8 | 31.4 | 7.1 |
| 2.50 | w/o PBC | 5.9 | 35.4 | 31.4 | 22.6 | 4.3 |
| 2.50 | w/o BPS | 7.0 | 32.5 | 25.5 | 30.5 | -2.3 |
| 2.50 | w/o KAS | 6.6 | 34.0 | 29.9 | 39.1 | 27.3 |

## Interpretation

Stage 4P supports the final component story in the target window:

1. Full PhaseServe improves SLO attainment, TTFT p90/p99 and TPOT p90/p99 over
   DistServe at every measured rate in the selected window.
2. Full PhaseServe improves SLO attainment, TTFT p90 and TPOT p90 over every
   component ablation at every measured rate.
3. TPOT p99 is the main tradeoff-sensitive metric in the ablation table. Full
   PhaseServe is not uniformly better than every component ablation on TPOT p99,
   especially around per-GPU `1.75-2.25` for `w/o PBC` and `w/o BPS`.
4. The paper-safe claim is therefore: PBC/BPS/KAS are jointly needed for robust
   SLO, TTFT tail and TPOT p90 improvements in the OPT ShareGPT pressure window;
   TPOT p99 should be reported as a tradeoff-sensitive secondary metric rather
   than the only ablation headline.

## Next Step

Use this result as the final OPT component ablation source, then freeze the
main end-to-end plotting windows from Stage 4O for OPT-13B + ShareGPT,
LLaMA2-13B + ShareGPT and LLaMA2-13B + LongBench 4K.
