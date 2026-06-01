# Documentation Index

This directory keeps only the current research entry points at the top level.
Completed stage plans, tuning logs, and exploratory notes are stored under
`docs/archive/`.

## Current Entry Points

| File | Purpose |
|---|---|
| `methodology.md` | Current PhaseServe method definition. |
| `methodology_code_alignment.md` | Current method/code/claim alignment and remaining validation gaps. |
| `experiment_protocol.md` | Experiment rules, workload layers, metrics, and claim guardrails. |
| `final_results_index.md` | Latest result roots and what each result may be used for. |
| `current_progress.md` | Short current-state summary and next step. |
| `stage4p_targeted_ablation.md` | Final targeted OPT-13B + ShareGPT component ablation summary. |
| `stage4l_opt_sharegpt_bridge_budget_repair.md` | Latest OPT-13B + ShareGPT seed0 repair and strict-window result. |
| `stage4m_opt_sharegpt_seed_replication.md` | OPT-13B + ShareGPT seed1 main replication plus internal seed2 diagnostic record. |
| `benchmarking.md` | Benchmark commands, metric definitions, and script conventions. |

Current generated figures live under `results/figures/stage4o_stage4p/`.

## Archive

| Path | Contents |
|---|---|
| `archive/stages/` | Completed Stage 1/2/3 plans, Stage 4 repair logs, tuning records, and mechanism audits. |
| `archive/validation/` | Early validation and smoke notes. |
| `archive/plans/` | Older high-level research plans superseded by the current protocol. |

## Citation Rule

For current analysis, cite result roots only if they appear in
`final_results_index.md`. Other remote result directories are retained for
traceability but should be treated as historical/debug artifacts.
