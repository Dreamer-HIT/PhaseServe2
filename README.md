# PhaseServe Research Workspace

This repository contains the PhaseServe research workspace: the current methodology notes, the modified DistServe code, experiment scripts, lightweight result summaries, and the paper draft.

For AI-agent context that should survive conversation compaction, see `AGENTS.md`.

## Layout

- `remote_distserve/`: modified DistServe source and benchmark harnesses.
- `docs/`: current methodology, implementation mapping, experiment protocol, and progress notes.
- `results/`: lightweight, curated result summaries used to support current claims.
- `scripts/`: local plotting utilities.
- `paper/`: LaTeX paper draft and figure assets required by the draft.
- `related_papers/`: local copies and extracted text for comparison papers.

## Current Snapshot

The pre-cleanup checkpoint is preserved as:

- commit: `a5176d7278599ae80ea5ae4f6a6c6c236b787f48`
- tag: `snapshot/stage4l-bridge-budget-20260531`
- remote branch: `codex/stage4l-bridge-budget-snapshot`

Use that tag to recover the exact state before repository cleanup.

## Working Rule

Keep source code, curated summaries, and reproducible scripts in git. Keep raw logs, JSONL traces, server logs, generated figures, local caches, model files, and one-off temporary outputs outside git.
