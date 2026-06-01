# Stage 4P Targeted Ablation Summary

- E2E root: `/root/data/phase_scheduler_results/stage4o_e2e_full_matrix_20260531_234957/opt13b_sharegpt`
- Ablation root: `/root/data/phase_scheduler_results/stage4p_targeted_ablation_20260601_101528/opt13b_sharegpt_ablation`
- Overall complete: `80/80`
- Targeted ablation complete: `48/48`

## PhaseServe vs DistServe

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

## Full PhaseServe vs Component Ablations

Positive latency values mean Full PhaseServe is lower than the ablation. Positive SLO values mean Full PhaseServe has higher attainment.

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
