# Explorations

Research done before the pipeline was written. None of it is pipeline code: the deliverable lives
in `src/`, `tests/` and `eval/`. All numbers here are PRELIMINARY: they are measured on a
synthetic dev set whose labels are drafts.

## Layout

| Folder | What it holds |
|---|---|
| `lib/` | Shared code. `receipts_safe.py` is the label-stripping loader. `budget.py` handles provider routing, the spend cap, the cache and raw response bodies. `classifier_prompt.py` holds prompt `cls-v1` and its strict schema. `run_trial.py` classifies the dev set with one model. `decision_adapters.py` gives one `ItemClassifier` interface over chat, ollama and decision-model backends |
| `scripts/` | One-off tools: live checks, OpenRouter verification, the determinism check, model listing, the contamination probe, the notebook builder |
| `notebooks/` | Executed notebooks 01–06, built from the py:percent sources in `notebooks/src/` |
| `dev_set/` | DRAFT synthetic dev items (109) and engine edge cases (13), frozen at SHA-256 `2565118c…3ecb` |
| `policy/` | DRAFT rule inventory (41 rules), policy ambiguities, metadata-retriever candidates. The decisions on the ambiguities are in `docs/decisions/` |
| `results/` | Measured outputs: predictions, metrics, trial runs, live checks, the determinism check, and the budget log with every billed call |
| `research/` | Technical spike, model shortlist, live model lists, the experiments plan (E1–E12) and `notes/` with sourced research |

`raw/` (raw provider response bodies) and `cache/` (cached responses) stay local and are
gitignored. With the cache in place, re-running anything here makes no paid call.

## Notebooks

| Notebook | Question |
|---|---|
| `01_rule_inventory` | What do the 41 rules require, which ones override others, and where is the text ambiguous? |
| `02_input_eda` | What do the inputs look like (inputs only, no labels), and which rules could apply to each receipt from metadata alone? |
| `03_synthetic_dev_set` | A dev set written from the taxonomy and policies, checked for contamination against the real descriptions |
| `04_evaluation_study` | Worked examples of every metric and statistical test the evaluation uses, on toy data |
| `06_local_model_trial` | Nine classifier variants plus the OpenRouter runs on the dev set: accuracy with Wilson intervals, cross-provider agreement, repeatability |

## Re-running

From the repository root:

```bash
uv run --no-project --with jupyter --with jupytext --with pyyaml --with pandas --with numpy \
    --with scipy --with matplotlib --with openai --with python-dotenv --with requests \
    python explorations/scripts/build_notebook.py 06_local_model_trial
```

API keys come from `.env` (see `.env.example`). Exploration spend is capped in `lib/budget.py`.
