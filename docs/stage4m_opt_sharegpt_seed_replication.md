# Stage 4M OPT-13B + ShareGPT Seed Replication

Updated: 2026-05-31

## Stage Goal

Replicate the Stage 4L OPT-13B + ShareGPT strict-window result with a second
main seed. The project seed policy is now seed0 + seed1 for the OPT main
experiment. Seed2 from this run is retained only as internal diagnostic/boundary
evidence and is not part of the final main claim.

## Files Read Or Modified

Read:

- `AGENTS.md`
- `docs/current_progress.md`
- `docs/final_results_index.md`

Modified:

- `AGENTS.md`
- `docs/current_progress.md`
- `docs/final_results_index.md`
- `docs/README.md`
- `docs/stage4m_opt_sharegpt_seed_replication.md`

## Experiment Artifact

| Field | Value |
|---|---|
| Remote project | `/root/data/DistServe` |
| Result root | `/root/data/phase_scheduler_results/stage4m_opt13b_sharegpt_seed12_20260531_200712` |
| Result count | 20 summary JSON files |
| Script output | `window_goal.txt` under the result root |
| Model | OPT-13B |
| Dataset | ShareGPT-derived Layer 1 dataset |
| Requests | 128 per seed |
| Main seed | 1 |
| Diagnostic seed | 2, excluded from main claim |
| Arrival | Poisson |
| Structure | 1P1D, 2 GPUs |
| Policies | `fcfs`, `phase` |
| Rates | global `2/3/4/5/6`, per-GPU `1.0/1.5/2.0/2.5/3.0` |

The strict internal target requires at least two TTFT percentiles and at least
two TPOT percentiles to improve by `>=20%` at every point in a continuous
per-GPU window of length `2.0` with `0.5` granularity.

## Results

| Seed | Global Rate | Per-GPU Rate | TTFT wins | TPOT wins | Pass | TTFT p50/p90/p95/p99 | TPOT p50/p90/p95/p99 |
|---:|---:|---:|---:|---:|---|---|---|
| 1 | 2 | 1.0 | 4 | 4 | True | +21.1/+25.2/+83.9/+92.0 | +56.6/+75.7/+80.3/+75.0 |
| 1 | 3 | 1.5 | 4 | 4 | True | +96.0/+51.7/+44.2/+44.9 | +25.6/+35.8/+39.2/+38.0 |
| 1 | 4 | 2.0 | 3 | 3 | True | +76.8/+28.9/+17.1/+23.2 | +25.7/+27.0/+37.6/+10.2 |
| 1 | 5 | 2.5 | 2 | 3 | True | +54.4/+29.5/+6.1/+14.0 | +22.9/+20.5/+24.3/+16.4 |
| 1 | 6 | 3.0 | 2 | 3 | True | +54.0/+23.4/+12.8/+17.4 | +26.3/+28.8/+30.7/+2.4 |
| 2 | 2 | 1.0 | 3 | 4 | True | +19.1/+71.5/+92.1/+93.0 | +40.2/+63.1/+56.9/+65.3 |
| 2 | 3 | 1.5 | 4 | 3 | True | +92.3/+54.4/+54.2/+48.5 | +14.0/+34.6/+39.3/+32.9 |
| 2 | 4 | 2.0 | 4 | 0 | False | +75.7/+30.1/+28.5/+29.7 | +2.5/+19.0/+14.1/+18.2 |
| 2 | 5 | 2.5 | 4 | 1 | False | +74.2/+26.2/+26.9/+26.6 | +12.3/+20.8/+0.3/+10.4 |
| 2 | 6 | 3.0 | 2 | 1 | False | +67.3/+19.4/+19.7/+20.8 | +15.3/+20.0/+2.9/+20.9 |

Detected continuous windows:

| Seed | Passing per-GPU window |
|---:|---|
| 1 | `1.0-3.0` |
| 2 | None with length `2.0`; only `1.0` and `1.5` pass |

## Acceptance Result

Stage 4M validates seed1 as the second main seed for the OPT strict-window
claim.

What holds:

- Seed1 fully replicates the Stage 4L strict-window result.
- Seed2 shows strong TTFT improvements across the whole rate range.
- Seed2 passes the strict target at per-GPU `1.0` and `1.5`.

Internal diagnostic note:

- Seed2 fails the strict target at per-GPU `2.0`, `2.5`, and `3.0`.
- The failure mode is TPOT, not TTFT: TTFT has enough wins at all seed2 points,
  but TPOT has `0`, `1`, and `1` wins at the failed rates.
- This seed is not included in the current main seed policy or final plots.

## Risks And Blockers

The current method/code should be claimed only under the selected two-seed main
protocol, seed0 + seed1. The diagnostic seed2 result should not be mixed into
the main figures unless the seed policy is reopened.

If seed2 is later reopened, plausible causes to inspect are:

- decode active-set composition;
- bridge admission budget;
- near-completion promotion;
- first-token reservation side effects;
- arrival burst shape under seed2;
- prompt/output length mix differences between seeds.

## Next Stage

Stage 4N should proceed with final ablation and plot freezing:

1. Freeze the OPT seed0 + seed1 figure windows.
2. Run final current-code ablation on representative OPT rates.
3. Add LLaMA replication or explicitly scope LLaMA results as generalization
   evidence.
