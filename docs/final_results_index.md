# PhaseServe Final Results Index

Updated: 2026-06-01

This file is the authoritative index for result roots that may be cited in
current analysis. Remote tuning directories that are not listed here should be
treated as historical/debug artifacts.

## Result Tiers

| Tier | Meaning |
|---|---|
| Main candidate | May become a main paper result after seed expansion and final plotting. |
| Generalization candidate | Useful for cross-model or cross-dataset support; may need more seeds. |
| Mechanism evidence | Useful for ablation or mechanism explanation, not as the main end-to-end claim. |
| Boundary/stress | Useful for explaining limits and tradeoffs. |
| Historical/debug | Kept for traceability only; do not cite in paper results. |

## Main Candidate Results

### Stage 4O + Stage 4P, Current Paper Matrix

Purpose: current authoritative source for final plot-window selection and final
OPT-13B + ShareGPT component ablation.

| Field | Value |
|---|---|
| Tier | Main candidate |
| Stage 4O E2E root | `/root/data/phase_scheduler_results/stage4o_e2e_full_matrix_20260531_234957` |
| Stage 4P targeted ablation root | `/root/data/phase_scheduler_results/stage4p_targeted_ablation_20260601_101528/opt13b_sharegpt_ablation` |
| Stage 4P summary doc | `docs/stage4p_targeted_ablation.md` |
| Models/datasets in Stage 4O | OPT-13B + ShareGPT; LLaMA2-13B + ShareGPT; LLaMA2-13B + LongBench 4K |
| Seeds | seed0 + seed1 |
| Stage 4O policies | `fcfs`, `phase` |
| Stage 4P policies | `w/o PBC`, `w/o BPS`, `w/o KAS` |
| Stage 4O coverage | `240/240` summaries |
| Stage 4P coverage | `48/48` targeted ablation summaries |
| Stage 4O + Stage 4P OPT merged coverage | `80/80` summaries |
| Supported use | Final E2E plot-window selection; final OPT component ablation; claim-evidence audit |
| Not supported | All-rate superiority claims, hidden rate cherry-picking without baseline pressure-window rationale, or TPOT p99-only ablation conclusions |

Stage 4P merged OPT-13B + ShareGPT summary:

| Artifact | Path |
|---|---|
| Coverage JSON | `/root/data/phase_scheduler_results/stage4p_targeted_ablation_20260601_101528/opt13b_sharegpt_ablation/stage4p_ablation_coverage.json` |
| Merged Markdown | `/root/data/phase_scheduler_results/stage4p_targeted_ablation_20260601_101528/opt13b_sharegpt_ablation/stage4p_merged_ablation.md` |
| Per-seed CSV | `/root/data/phase_scheduler_results/stage4p_targeted_ablation_20260601_101528/opt13b_sharegpt_ablation/stage4p_merged_ablation.per_seed.csv` |
| Seed-mean CSV | `/root/data/phase_scheduler_results/stage4p_targeted_ablation_20260601_101528/opt13b_sharegpt_ablation/stage4p_merged_ablation.mean.csv` |
| Comparison CSV | `/root/data/phase_scheduler_results/stage4p_targeted_ablation_20260601_101528/opt13b_sharegpt_ablation/stage4p_merged_ablation.comparisons.csv` |

Local figure outputs generated from the Stage 4O/4P data:

| Figure | Path |
|---|---|
| Complete end-to-end full matrix | `results/figures/stage4o_stage4p/stage4o_end_to_end_full_matrix.{png,svg,pdf}` |
| Targeted ablation raw curves | `results/figures/stage4o_stage4p/stage4p_ablation_raw_curves.{png,svg,pdf}` |
| Targeted ablation improvement heatmap | `results/figures/stage4o_stage4p/stage4p_ablation_improvement_heatmap.{png,svg,pdf}` |
| Plotting script | `scripts/plot_stage4o_stage4p_figures.py` |
| Local source-data snapshot | `results/stage4o_stage4p_plot_data/` |

Draft main end-to-end latency-window figure:

| Figure | Path |
|---|---|
| Main E2E combined latency windows | `results/figures/stage4q_main_e2e_windows/stage4q_main_latency_windows_combined.{png,svg,pdf}` |
| Main E2E TTFT latency windows | `results/figures/stage4q_main_e2e_windows/stage4q_main_ttft_latency_windows.{png,svg,pdf}` |
| Main E2E TPOT latency windows | `results/figures/stage4q_main_e2e_windows/stage4q_main_tpot_latency_windows.{png,svg,pdf}` |
| Main E2E per-seed source CSV | `results/figures/stage4q_main_e2e_windows/stage4q_main_latency_windows_per_seed_source.csv` |
| Main E2E seed-mean source CSV | `results/figures/stage4q_main_e2e_windows/stage4q_main_latency_windows_summary_source.csv` |
| Main E2E plotting script | `scripts/plot_stage4q_main_e2e_windows.py` |

Current draft window policy:

| Model/dataset | TTFT window | TPOT window | Metrics |
|---|---:|---:|---|
| OPT-13B + ShareGPT | `1.00-2.75` | `1.00-2.75` | TTFT `p50+p90`; TPOT `p90+p95` |
| LLaMA2-13B + ShareGPT | `1.00-2.25` | `0.75-2.00` | TTFT `p50+p90`; TPOT `p90+p95` |
| LLaMA2-13B + LongBench 4K | `1.00-3.00` | `1.00-3.00` | TTFT `p50+p90`; TPOT `p90+p95` |

Background motivation and Design mechanism figures:

| Figure | Path |
|---|---|
| Pressure propagation motivation + diagnostics | `results/figures/motivation/background_pressure_motivation.{png,svg,pdf}` |
| Motivation source CSV | `results/figures/motivation/background_pressure_motivation_source.csv` |
| Motivation plotting script | `scripts/plot_background_pressure_motivation.py` |
| PhaseServe overview mechanism figure | `results/figures/mechanism/phaseserve_overview_imagegen.png` |
| Budgeted mechanisms figure | `results/figures/mechanism/phaseserve_budget_mechanisms_imagegen.png` |
| Superseded Python overview draft | `results/figures/mechanism/phaseserve_overview_best.{png,pdf}` |

Exploratory vLLM SLO baseline:

| Artifact | Path |
|---|---|
| vLLM OPT-13B + ShareGPT summary CSV | `results/stage4r_vllm_slo_data/stage4r_vllm_slo_opt13b_sharegpt_20260601_203255/sweep_summary.csv` |
| Exploratory vLLM SLO figure | `results/figures/stage4r_slo_vllm/stage4r_slo_vllm_opt13b_sharegpt.{png,svg,pdf}` |
| vLLM SLO source CSV | `results/figures/stage4r_slo_vllm/stage4r_slo_vllm_opt13b_sharegpt_source.csv` |
| vLLM plotting script | `scripts/plot_stage4r_slo_vllm.py` |
| Supported use | Protocol/debug evidence and future SLO-scale planning only. |
| Not supported | Positive PhaseServe-vs-vLLM SLO claim under the current fixed SLO. |
| Superseded Python mechanism draft | `results/figures/mechanism/phaseserve_budget_mechanisms.{png,svg,pdf}` |

Supported use: motivate runtime pressure propagation in a DistServe-style
baseline using Stage 4O seed0 + seed1 summaries, and show that instrumented
hard-pressure counters and budget movement are separate from ordinary queue
latency. Panels (c) and (f) of the motivation figure are diagnostics, not
PhaseServe performance comparisons. The active mechanism figures are
image-generated Design schematics; they support the Design section only and are
not result figures.

Stage 4P main interpretation:

- Full PhaseServe improves SLO attainment, TTFT p90/p99 and TPOT p90/p99 over
  DistServe at every measured rate in per-GPU `0.75-2.50 req/s/GPU`.
- Full PhaseServe improves SLO attainment, TTFT p90 and TPOT p90 over every
  component ablation at every measured rate.
- TPOT p99 is tradeoff-sensitive in the component ablation table; report it,
  but do not use it as the only mechanism headline.

### OPT-13B + ShareGPT, Stage 4L, Latest Code

Purpose: current strongest OPT-13B + ShareGPT end-to-end window.

| Field | Value |
|---|---|
| Tier | Main candidate |
| Model | OPT-13B |
| Dataset | ShareGPT-derived Layer 1 dataset, seed0, 128 requests |
| Dataset path | `/root/data/phase_scheduler_results/layer1_opt13b_sharegpt_broad_20260530_173036/datasets/opt13b_sharegpt_seed_0_128.ds` |
| Arrival | Poisson |
| Structure | 1P1D, 2 GPUs |
| Current seed state | main seed policy is seed0 + seed1 |
| Current positive window | seed0 and seed1 pass per-GPU `1.0-3.0 req/s/GPU`, granularity `0.5` |
| Supported use | Main OPT candidate evidence for TTFT and TPOT improvement over a two-seed protocol |
| Not yet supported | Claims beyond the selected two-seed protocol, all-rate superiority, or all-percentile superiority |

Current result roots:

| Role | Root |
|---|---|
| FCFS broad baseline | `/root/data/phase_scheduler_results/layer1_opt13b_sharegpt_broad_20260530_173036` |
| FCFS fine baseline | `/root/data/phase_scheduler_results/layer1_opt13b_sharegpt_fastlane_fine_20260530_212533` |
| FCFS rate 3 supplemental | `/root/data/phase_scheduler_results/goal_opt13b_sharegpt_pgpu1to3_20260531_104709/fcfs_r3` |
| FCFS rate 5 supplemental | `/root/data/phase_scheduler_results/layer1_opt13b_sharegpt_fcfs_rate5_20260531_001956` |
| Phase rates 2-5 | `/root/data/phase_scheduler_results/final_completion_sort_opt13b_sharegpt_r2to5_20260531_135535` |
| Phase rate 6 | `/root/data/phase_scheduler_results/r6_completion_first_sort_default_opt13b_sharegpt_20260531_135157` |
| Stage summary | `docs/stage4l_opt_sharegpt_bridge_budget_repair.md` |

Current seed0 strict-window result:

| Global Rate | Per-GPU Rate | TTFT wins | TPOT wins | TTFT p50/p90/p95/p99 | TPOT p50/p90/p95/p99 |
|---:|---:|---:|---:|---|---|
| 2.0 | 1.0 | 4 | 4 | +26.7/+97.1/+97.4/+97.3 | +46.8/+82.8/+82.5/+88.9 |
| 3.0 | 1.5 | 4 | 4 | +97.8/+72.3/+67.1/+67.0 | +32.6/+47.0/+36.5/+42.9 |
| 4.0 | 2.0 | 4 | 3 | +97.1/+48.8/+47.4/+42.7 | +21.2/+35.9/+31.4/+19.9 |
| 5.0 | 2.5 | 4 | 2 | +90.2/+36.4/+34.9/+32.1 | +11.5/+23.2/+22.8/+15.0 |
| 6.0 | 3.0 | 4 | 3 | +77.8/+36.4/+34.2/+33.1 | +3.8/+29.2/+31.0/+29.4 |

### OPT-13B + ShareGPT, Stage 4M, Seed1 Main Replication

Purpose: add the second main seed for the OPT strict-window result. Seed2 from
the same run is retained only as internal diagnostic/boundary evidence and is
not part of the main seed policy.

| Field | Value |
|---|---|
| Tier | Main candidate replication |
| Model | OPT-13B |
| Dataset | ShareGPT-derived Layer 1 dataset, 128 requests |
| Dataset roots | `/root/data/phase_scheduler_results/stage4m_opt13b_sharegpt_seed12_20260531_200712/datasets` |
| Arrival | Poisson |
| Structure | 1P1D, 2 GPUs |
| Policies | `fcfs`, `phase` |
| Rates | global `2/3/4/5/6`, per-GPU `1.0/1.5/2.0/2.5/3.0` |
| Result root | `/root/data/phase_scheduler_results/stage4m_opt13b_sharegpt_seed12_20260531_200712` |
| Stage summary | `docs/stage4m_opt_sharegpt_seed_replication.md` |
| Script output | `window_goal.txt` under the result root |
| Strict target | At each rate, at least two TTFT percentiles and at least two TPOT percentiles improve by `>=20%`; continuous per-GPU window length `2.0` with step `0.5` |

Stage 4M seed1 strict-window check:

| Seed | Global Rate | Per-GPU Rate | TTFT wins | TPOT wins | Pass | TTFT p50/p90/p95/p99 | TPOT p50/p90/p95/p99 |
|---:|---:|---:|---:|---:|---|---|---|
| 1 | 2 | 1.0 | 4 | 4 | True | +21.1/+25.2/+83.9/+92.0 | +56.6/+75.7/+80.3/+75.0 |
| 1 | 3 | 1.5 | 4 | 4 | True | +96.0/+51.7/+44.2/+44.9 | +25.6/+35.8/+39.2/+38.0 |
| 1 | 4 | 2.0 | 3 | 3 | True | +76.8/+28.9/+17.1/+23.2 | +25.7/+27.0/+37.6/+10.2 |
| 1 | 5 | 2.5 | 2 | 3 | True | +54.4/+29.5/+6.1/+14.0 | +22.9/+20.5/+24.3/+16.4 |
| 1 | 6 | 3.0 | 2 | 3 | True | +54.0/+23.4/+12.8/+17.4 | +26.3/+28.8/+30.7/+2.4 |

Interpretation: seed1 replicates the Stage 4L seed0 strict-window result over
per-GPU `1.0-3.0`. Together, seed0 and seed1 are the current two-seed main OPT
evidence.

Internal diagnostic note: seed2 was also run under the same result root, but it
is excluded from the main seed policy and should not be used in final figures or
main claims unless the seed policy is reopened.

## Generalization Candidate Results

### LLaMA2-13B + ShareGPT, Latest Code

| Field | Value |
|---|---|
| Tier | Generalization candidate |
| Model | LLaMA2-13B, ModelScope mirror |
| Dataset | `/root/data/datasets/distserve_eval/processed/llama13b_sharegpt.ds` |
| Requests | 128 |
| Seeds | seed0 + seed1 |
| Rates | global `2/4/6/8/10`, per-GPU `1/2/3/4/5` |
| Seed0 result root | `/root/data/phase_scheduler_results/llama13b_sharegpt_completion_sort_pgpu1to5_20260531_153445` |
| Seed1 result root | `/root/data/phase_scheduler_results/stage4n_llama_seed1_20260531_213102/llama13b_sharegpt_seed1` |
| Supported use | Cross-model ShareGPT support |
| Main limitation | TPOT p99 remains workload-sensitive; use TTFT p50/p90/p95/p99 and TPOT p90/p95 as stronger latency claims |

Seed0 summary:

| Per-GPU Rate | SLO delta | TTFT p50/p90/p95/p99 | TPOT p50/p90/p95/p99 |
|---:|---:|---|---|
| 1 | +28.1 pp | +90.2/+61.2/+60.4/+58.9 | +28.7/+40.1/+38.6/+32.0 |
| 2 | +16.4 pp | +67.9/+24.3/+20.2/+21.9 | +9.0/+20.7/+32.7/+2.0 |
| 3 | +10.9 pp | +60.4/+19.0/+15.9/+20.8 | +10.3/+10.4/+32.6/-6.1 |
| 4 | +8.6 pp | +57.2/+23.3/+22.3/+20.4 | +7.5/+14.9/+37.7/-2.0 |
| 5 | +10.2 pp | +53.5/+25.7/+22.7/+21.7 | +0.2/+7.8/+34.3/-1.1 |

Seed1 summary:

| Per-GPU Rate | SLO delta | Goodput ratio | TTFT p50/p90/p95/p99 | TPOT p50/p90/p95/p99 |
|---:|---:|---:|---|---|
| 1 | +19.5 pp | 1.08x | +14.9/+80.8/+79.4/+72.4 | +30.0/+35.5/+42.4/+55.0 |
| 2 | +10.2 pp | 1.02x | +26.8/+21.9/+23.7/+23.5 | +7.3/+24.7/+20.3/+14.8 |
| 3 | +4.7 pp | 0.92x | +26.2/+16.8/+19.0/+18.6 | +3.7/+15.8/+16.1/-0.2 |
| 4 | +13.3 pp | 1.19x | +18.7/+15.1/+17.4/+18.0 | -2.2/+18.2/+28.5/-8.6 |
| 5 | +18.0 pp | 1.33x | +54.9/+15.1/+15.9/+16.1 | +0.0/+11.5/+27.9/+9.2 |

### LLaMA2-13B + LongBench 4K, Low-Rate Sweep

| Field | Value |
|---|---|
| Tier | Main/generalization candidate |
| Model | LLaMA2-13B, ModelScope mirror |
| Dataset | `/root/data/datasets/distserve_eval/processed/llama13b_longbench_4k.ds` |
| Requests | 96 |
| Seeds | seed0 + seed1 |
| SLO | `TTFT<=5s`, `TPOT<=0.12s` |
| Seed0 result root | `/root/data/phase_scheduler_results/llama13b_longbench4k_current_ctx4096_r05to10_20260531_164842` |
| Seed1 result root | `/root/data/phase_scheduler_results/stage4n_llama_seed1_20260531_213102/llama13b_longbench4k_low_seed1` |
| Supported use | Long-context main evidence after seed expansion |
| Main limitation | SLO is tight and should be plotted as a workload-specific long-context SLO, not mixed with ShareGPT SLOs |

Seed0 summary:

| Per-GPU Rate | SLO delta | TTFT p50/p90/p95/p99 | TPOT p50/p90/p95/p99 |
|---:|---:|---|---|
| 0.25 | +8.3 pp | +0.9/-1.4/-2.6/-0.0 | -0.4/+80.4/+84.1/+96.3 |
| 0.30 | +17.7 pp | +1.1/-14.3/-13.8/-30.2 | +11.1/+84.9/+77.1/+92.1 |
| 0.35 | +29.2 pp | +5.8/+44.8/+78.1/+75.5 | +33.6/+80.6/+59.6/+90.4 |
| 0.375 | +41.7 pp | +22.7/+80.8/+86.6/+82.8 | +67.6/+80.5/+61.5/+84.6 |
| 0.40 | +50.0 pp | +76.9/+88.9/+89.5/+87.4 | +76.4/+79.0/+60.7/+76.1 |
| 0.45 | +63.5 pp | +93.3/+89.4/+77.4/+75.2 | +78.4/+64.1/+59.8/+74.1 |
| 0.50 | +60.4 pp | +95.0/+84.7/+80.7/+75.8 | +74.6/+48.5/+63.9/+73.1 |

Seed1 summary:

| Per-GPU Rate | SLO delta | Goodput ratio | TTFT p50/p90/p95/p99 | TPOT p50/p90/p95/p99 |
|---:|---:|---:|---|---|
| 0.25 | +25.0 pp | 1.34x | +3.3/+25.1/+63.7/+88.2 | -1.5/+93.6/+96.3/+98.8 |
| 0.30 | +30.2 pp | 1.47x | +3.7/+79.3/+80.9/+74.9 | +7.8/+95.2/+94.3/+96.1 |
| 0.35 | +35.4 pp | 1.63x | +17.1/+86.9/+86.5/+58.2 | +5.9/+95.1/+92.7/+95.9 |
| 0.375 | +37.5 pp | 1.75x | +49.5/+90.3/+88.9/+58.4 | +13.3/+92.1/+91.4/+87.1 |
| 0.40 | +46.9 pp | 2.28x | +86.5/+87.5/+86.3/+59.0 | +28.4/+91.5/+91.5/+86.8 |
| 0.45 | +63.5 pp | 6.71x | +95.1/+88.0/+81.9/+61.4 | +52.9/+78.6/+84.6/+85.1 |
| 0.50 | +58.3 pp | 10.15x | +94.3/+66.7/+60.3/+58.4 | +53.2/+74.2/+74.7/+70.4 |

### LLaMA2-13B + LongBench 4K, High-Rate Sweep

| Field | Value |
|---|---|
| Tier | Boundary/stress plus latency evidence |
| Model | LLaMA2-13B, ModelScope mirror |
| Dataset | `/root/data/datasets/distserve_eval/processed/llama13b_longbench_4k.ds` |
| Requests | 96 |
| Seeds | seed0 + seed1 |
| SLO | `TTFT<=5s`, `TPOT<=0.12s` |
| Seed0 result root | `/root/data/phase_scheduler_results/llama13b_longbench4k_pgpu1to5_ctx4096_20260531_184841` |
| Seed1 result root | `/root/data/phase_scheduler_results/stage4n_llama_seed1_20260531_213102/llama13b_longbench4k_high_seed1` |
| Supported use | High-pressure latency/stress evidence |
| Main limitation | SLO too strict to be a main attainment plot at high pressure; use primarily as latency/stress evidence |

Seed0 summary:

| Per-GPU Rate | SLO delta | TTFT p50/p90/p95/p99 | TPOT p50/p90/p95/p99 |
|---:|---:|---|---|
| 1 | -1.1 pp | +39.8/+36.6/+36.2/+42.1 | +34.6/+16.0/+43.2/+63.9 |
| 2 | -1.0 pp | +28.5/+26.5/+26.8/+31.8 | +36.3/+15.2/+42.8/+63.6 |
| 3 | -1.0 pp | +28.6/+26.6/+26.7/+31.4 | +38.2/+17.7/+43.7/+64.9 |
| 4 | -1.0 pp | +26.3/+24.3/+24.5/+29.1 | +37.7/+16.3/+43.2/+64.2 |
| 5 | -1.0 pp | +25.9/+23.9/+24.0/+28.5 | +38.3/+15.9/+43.0/+63.8 |

Seed1 summary:

| Per-GPU Rate | SLO delta | Goodput ratio | TTFT p50/p90/p95/p99 | TPOT p50/p90/p95/p99 |
|---:|---:|---:|---|---|
| 1 | +9.4 pp | 2.96x | +60.0/+43.8/+43.0/+41.7 | +10.5/+65.9/+64.7/+73.7 |
| 2 | +9.4 pp | 3.00x | +44.7/+30.9/+30.8/+30.5 | +13.6/+67.2/+65.3/+74.0 |
| 3 | +8.3 pp | 2.81x | +41.2/+28.4/+27.8/+27.6 | +13.2/+66.6/+65.4/+74.0 |
| 4 | +8.3 pp | 2.81x | +39.6/+27.1/+26.5/+26.3 | +10.3/+66.6/+65.0/+73.7 |
| 5 | +8.3 pp | 2.72x | +28.3/+27.4/+22.8/+22.4 | +38.2/+60.4/+70.0/+58.5 |

## Mechanism Evidence

### OPT-13B Synthetic Mixed-Regime Ablation

| Field | Value |
|---|---|
| Tier | Mechanism evidence |
| Result root | `/root/data/phase_scheduler_results/stage4c_mixed_regime_ablation_opt13b_20260528_145013` |
| Policies | `fcfs`, `bps`, `kas`, `bps_kas`, `phase` |
| Supported use | Explains PBC/BPS/KAS ownership and dynamic arbitration |
| Limitation | Older synthetic/mixed-regime workload; not the final end-to-end matrix |

Representative seed0 result:

| Global Rate | Policy | SLO | TTFT p90 vs FCFS | TPOT p90 vs FCFS |
|---:|---|---:|---:|---:|
| 2 | bps | 90.6% | +2.7% | -6.9% |
| 2 | kas | 92.2% | +5.6% | +10.5% |
| 2 | bps_kas | 96.9% | +20.1% | +11.0% |
| 2 | phase | 98.4% | +18.2% | +16.2% |
| 3 | bps | 73.4% | -15.7% | -13.2% |
| 3 | kas | 71.9% | +2.1% | +4.3% |
| 3 | bps_kas | 73.4% | +9.8% | +6.4% |
| 3 | phase | 73.4% | +12.3% | +9.9% |

## Historical / Do Not Cite As Current Main Result

The following classes of results should remain in archives only:

- early LLaMA2-7B smoke runs;
- PBC/BPS/KAS unit smokes from 2026-05-26;
- Stage 4A/4B prompt-skew tuning runs;
- Stage 4D mixed-wide plots when superseded by Stage 4L for OPT ShareGPT;
- failed HOL-bypass, bridge-eviction, and aggressive short-output fastlane
  tuning attempts;
- remote `latest_*` pointers not listed above.

## Next Results To Add

1. Final frozen E2E plotting windows selected from Stage 4O for OPT-13B +
   ShareGPT, LLaMA2-13B + ShareGPT, and LLaMA2-13B + LongBench 4K.
2. Claim-evidence audit table mapping each planned paper claim to result root,
   script, metric, seed and rate window.
3. Optional ShuffleInfer-style controlled regime baseline.
