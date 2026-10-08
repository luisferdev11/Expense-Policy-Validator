# Expense Policy Validator

Classifies itemized expense receipts, applies nine written expense policies with a deterministic
rule engine, raises evidence-grounded exceptions, and assigns each receipt a disposition of flag,
review or pass. The pipeline has five separate components: normalizer, item classifier, policy
retriever, policy engine and exception reporter.

## Non-negotiable rules

1. **Labels are evaluation-only.** `data/receipts.jsonl` contains the correct answers:
   `labels`, `line_items[].labels` and `notes`. Only code under `eval/` may read them. The
   loader strips them before anything else sees a receipt, a test enforces it, and the file is
   never loaded whole into an assistant's context.
2. **Deterministic decisions.** The policy engine, retriever and disposition logic are plain
   Python. No model call decides anything. The same input produces byte-identical output.
3. **Policy text is the source of truth.** Every rule is implemented from `data/policy-docs/`
   and cites its rule ID. No pipeline code references a receipt ID. A change driven by
   evaluation results cites, in its commit message, the policy clause that justifies it.
4. **Evidence or nothing.** Every exception carries `rule_id`, `policy_doc`, `line_ids` and the
   literal policy text it relies on (EXC-04).
5. **Decide on dev, report on test.** Variants are compared on a synthetic dev set against a
   decision rule written before running. The 28 in-scope receipts run once per finalist.
6. **Honest measurement.** Every metric is reported with its N. Every number in the README is
   reproducible from committed outputs with one command and no model calls.
7. **Reproducibility.** Temperature 0, pinned model ID and provider, versioned prompts. Every
   result records the model ID and prompt version.
8. **Separation of components.** Each component lives in its own module behind a typed
   interface. The classifier never sees the declared expense type or the attendee count.
9. **Secrets stay out.** The OpenRouter key lives in `.env`, which is gitignored. Never write a
   key into code, logs, outputs, commits or chat. A pre-commit hook blocks key patterns.
10. **English everywhere.** Code, identifiers, comments, docstrings, commits and docs.

## Code standards

- Python 3.12, managed with uv. Type hints on every public function.
- ruff and mypy clean, pytest green before every commit. The pre-commit hooks enforce what they
  can; do not bypass them with `--no-verify`.
- Small Conventional Commits (`feat`, `fix`, `test`, `docs`, `refactor`, `chore`, `exp` for
  experiments) that show how the work developed.
- Keep `AI_NOTES.md` up to date: every mistake an assistant made, how it was caught, and what
  changed. It is part of the deliverable.

## Commands

```bash
uv sync                      # install dependencies
uv run pytest                # tests
uv run ruff check --fix .    # lint
uv run ruff format .         # format
uv run mypy                  # types, over src/
uv run pre-commit run -a     # every hook, every file
```

## Data

| Path | Contents |
|---|---|
| `data/policy-docs/` | Nine policies, 41 rules with IDs such as `ALC-01`. `regional-addendum.md` overrides some global rules |
| `data/receipts.jsonl` | 32 receipts, 79 line items, **with the correct answers** (see rule 1) |
| `data/category-taxonomy.md` | 21 categories, each restricted or not. Use it as given |
| `data/README.md` | Data dictionary and the conventions the answers follow. Read before writing rules |

The timing rules TIME-01 to TIME-04 and receipts RCP-020, RCP-021, RCP-029 and RCP-030 are out
of scope for scoring.
