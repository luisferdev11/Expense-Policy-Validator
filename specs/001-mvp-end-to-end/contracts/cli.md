# Contract: `epv` command line

One entry point, declared in `[project.scripts]`. Every command runs from the repository root.
Exit code 0 means success.

## `epv run`

Validates every receipt in `data/receipts.jsonl` and writes `outputs/results.jsonl`.

| Option | Default | Effect |
|---|---|---|
| `--classifier {openrouter,keyword}` | `openrouter` | `keyword` writes to `outputs/baselines/keyword_classifier/results.jsonl` instead |
| `--offline` | off | Never calls a model. A cache miss becomes an unclassified item (EXC-03). Needs no key |
| `--no-trace` | off | Forces the no-op tracer |
| `--only RECEIPT_ID ...` | off | Development only: validates just the given receipts, writing to `outputs/dev/results.jsonl` (never `outputs/results.jsonl`). It still writes cache rows. Used for the thin-path cold run (task T039). The receipt IDs come from the command line, never from pipeline code |

**Guarantees.**
- **Byte-identical output** for the same inputs, cache, prompt, model and rules.
- **No paid call on a warm cache.**
- **Langfuse unreachable:** one warning on stderr, the same output, exit 0.
- **The spend cap** (USD 1.00 for this iteration) is checked before every billed call. At the
  cap, calls are refused and the affected items become unclassified.
- **Stderr summary:** receipts processed, model calls made, cache hits, billed USD, tracer state.
  Never a key.

**Before the first billed call** of a run, `epv run` makes sure the prompt `classify-item-chat`
at label `cls-v2` exists in Langfuse Prompt Management, so every `classify-item` generation can
link it. This is skipped when the tracer is no-op.

## `epv eval`

Reads `outputs/results.jsonl`, the baseline results and, through `eval/` only, the answers. It
writes these files under `outputs/eval/`:
- `comparison.jsonl`;
- `metrics.json`;
- `report.md`.

**Guarantees.**
- No model call, and no key needed.
- Deterministic: re-running reproduces the committed files byte for byte.
- Scores only the 28 in-scope receipts.

**Sub-steps.**
- When the keyword baseline results are missing, it runs `epv run --classifier keyword`
  in-process. That needs no model.
- It computes `keyword-flagger` inside `eval/`.

## `epv view`

Runs `streamlit run viewer/app.py`. The viewer:
- reads only committed outputs, through `expense_validator.results` and `outputs/eval/`;
- needs no network and no key.
