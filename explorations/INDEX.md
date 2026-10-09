# Explorations

Research done before the pipeline was written. None of it is pipeline code: the deliverable lives
in `src/`, `tests/` and `eval/`. All numbers here are PRELIMINARY: they are measured on a
synthetic dev set whose labels are drafts.

**Every model call goes through OpenRouter**, the gateway the brief provides. An earlier trial
used other providers while the case's key was expired; it is frozen in
`archive/multi-provider-2026-10-07/`.

## Layout

| Folder | What it holds |
|---|---|
| `lib/` | Shared code: `receipts_safe.py`, `budget.py`, `classifier_prompt.py`, `decision_adapters.py` and `run_trial.py` (see below) |
| `scripts/` | One-off tools: OpenRouter live check and verification, model pinning, the determinism check, the contamination probe, the notebook builder |
| `notebooks/` | Executed notebooks, built from the py:percent sources in `notebooks/src/` |
| `dev_set/` | DRAFT synthetic dev items (109) and engine edge cases (13), frozen at SHA-256 `2565118c…3ecb` |
| `policy/` | DRAFT rule inventory (41 rules), policy ambiguities, metadata-retriever candidates. The decisions on the ambiguities are in `docs/decisions/` |
| `results/` | Measured outputs: trial runs, metrics, live checks, the determinism check, and the budget log with every billed call |
| `research/` | Technical spike, the experiments plan, the OpenRouter catalogue snapshot and provider pins, and `notes/` with sourced research |
| `archive/` | Frozen records that no longer run against `lib/` |

The `lib/` modules:
- `receipts_safe.py`: the label-stripping loader.
- `budget.py`: OpenRouter calls with the spend cap, pinned endpoints, cache, call log and raw bodies.
- `classifier_prompt.py`: prompt `cls-v1` and its strict schema.
- `decision_adapters.py`: one `ItemClassifier` interface over generative models (chat with JSON) and decision models (`/api/alpha/decisions`).
- `run_trial.py`: classifies the dev set with one model.

**Ported into `src/`, not imported (iteration 1).** The pipeline re-implements these modules,
with tests, and `explorations/` stays frozen research:
- `receipts_safe.py` became `expense_validator/loader.py`;
- `classifier_prompt.py` (cls-v1) became `classification/prompt.py` (cls-v2);
- the pinning, cap and cost reading of `budget.py` became `classification/openrouter.py`;
- the `ItemClassifier` idea from `decision_adapters.py` became `classification/port.py`;
- the prompt sync in `scripts/langfuse_log_e13.py` became `classification/prompt_sync.py`.

The 13 engine cases were converted into `tests/engine_cases/fixtures/`.

`raw/` (raw response bodies) and `cache/` (cached responses) stay local and are gitignored. With
the cache in place, re-running anything here makes no paid call.

## Notebooks

| Notebook | Question |
|---|---|
| `01_rule_inventory` | What do the 41 rules require, which ones override others, and where is the text ambiguous? |
| `02_input_eda` | What do the inputs look like (inputs only, no labels), and which rules could apply to each receipt from metadata alone? |
| `03_synthetic_dev_set` | A dev set written from the taxonomy and policies, checked for contamination against the real descriptions |
| `04_evaluation_study` | Every metric and statistical test the evaluation uses, explained step by step |
| `05_model_trial` | Generative and decision models through OpenRouter on the dev set: accuracy, calibration, cost and latency |

## Re-running

Each notebook's first cell holds its own re-run command, which works from anywhere inside the
repository. To rebuild a notebook from its source:

```bash
uv run --no-project --with jupyter --with jupytext --with pyyaml --with pandas --with numpy \
    --with scipy --with matplotlib --with openai --with python-dotenv --with requests \
    python "$(git rev-parse --show-toplevel)/explorations/scripts/build_notebook.py" 02_input_eda
```

The OpenRouter key comes from `.env` (see `.env.example`). Exploration spend is capped in
`lib/budget.py`.
