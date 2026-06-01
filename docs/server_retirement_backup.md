# Server Retirement Backup

Updated: 2026-06-01

This file records the minimal local backup needed if the current remote server
is terminated. It intentionally excludes old tuning runs, raw JSONL traces,
server logs, model files, caches, and large temporary outputs.

## Backup Status

| Item | Status |
|---|---|
| Remote process state | No PhaseServe/vLLM benchmark process was left running at the time of this backup audit. |
| Current remote implementation | Synced into `remote_distserve/` from `/root/data/DistServe`. |
| Current paper draft | Local under `paper/PhaseServe.tex` and companion assets. |
| Current method and progress docs | Local under `AGENTS.md` and `docs/`. |
| Current generated paper figures | Local under `results/figures/`. |
| Current figure source CSVs | Local under `results/figures/**/**/*_source.csv` and `results/stage4o_stage4p_plot_data/`. |
| vLLM SLO exploratory result | Local summary CSV under `results/stage4r_vllm_slo_data/`; do not use as a positive paper claim yet. |
| Old remote raw experiments | Not backed up by default; treat as disposable unless listed in `docs/final_results_index.md`. |

## Local Code Snapshot

The current server-side implementation and benchmark harness are mirrored under
`remote_distserve/`.

Important paths:

| Path | Purpose |
|---|---|
| `remote_distserve/distserve/phase_scheduler.py` | PBC regime/pressure-budget controller logic. |
| `remote_distserve/distserve/context_stage_scheduler.py` | BPS-side prefill admission and budgeted batch shaping integration. |
| `remote_distserve/distserve/decoding_stage_scheduler.py` | KAS-side KV-aware decode selection, bridge budget, completion drain, and instrumentation. |
| `remote_distserve/distserve/config.py` | Runtime configuration knobs used by the current implementation. |
| `remote_distserve/benchmarks/phase_native_benchmark.py` | Main PhaseServe/DistServe latency and SLO benchmark harness. |
| `remote_distserve/benchmarks/phase_collect_summaries.py` | Summary aggregation used by Stage 4O/4P/4R. |
| `remote_distserve/benchmarks/phase_make_trace_dataset.py` | Dataset/trace construction helper. |
| `remote_distserve/benchmarks/phase_vllm_benchmark.py` | vLLM HTTP streaming benchmark harness. |
| `remote_distserve/scripts/run_phase_hetero_1p1d.sh` | 1P1D PhaseServe/DistServe experiment runner. |
| `remote_distserve/scripts/run_stage4r_vllm_slo.sh` | vLLM SLO baseline runner. |

## Local Result Snapshot

| Path | Purpose |
|---|---|
| `results/stage4o_stage4p_plot_data/` | Local Stage 4O/4P summary snapshot used by plotting scripts. |
| `results/figures/stage4o_stage4p/` | Complete Stage 4O matrix and Stage 4P ablation figures plus source CSVs. |
| `results/figures/stage4q_main_e2e_windows/` | Current main end-to-end latency-window candidate figures plus source CSVs. |
| `results/figures/motivation/` | Current Background/Motivation figure plus source CSV. |
| `results/figures/mechanism/` | Current image-generated mechanism figures and superseded drafts. |
| `results/figures/stage4r_slo_vllm/` | Exploratory vLLM SLO figure/source; currently not paper-safe as a positive claim. |
| `results/stage4r_vllm_slo_data/` | Local copy of the vLLM SLO summary CSV. |

## Quick Restart Checklist

For a new Codex session, read these files in order:

1. `AGENTS.md`
2. `docs/current_progress.md`
3. `docs/final_results_index.md`
4. `docs/claim_evidence_audit.md`
5. `docs/server_retirement_backup.md`

Then run:

```bash
git status --short
make -C paper view
```

If a new remote machine is needed, copy or clone the project, then use
`remote_distserve/` as the implementation source to patch a fresh DistServe
checkout. Keep models, Hugging Face caches, datasets, and result directories on
the new data disk rather than the system disk.

## Current Caveats

- The latest official paper evidence remains Stage 4O + Stage 4P.
- The vLLM OPT-13B SLO exploratory run used DistServe's OPT-13B baseline
  convention of one vLLM GPU. Under the current fixed SLO, vLLM is not a
  positive PhaseServe-vs-vLLM claim, so it should remain exploratory until the
  SLO-scale plan is redesigned and rerun.
- LLaMA2-13B + LongBench 4K vLLM probing was interrupted after confirming that
  the runner works; no complete paper-safe vLLM LongBench result exists yet.
- Old remote result directories are deliberately not part of this backup unless
  listed in `docs/final_results_index.md`.
