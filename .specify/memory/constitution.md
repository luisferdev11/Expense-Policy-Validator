# Expense Policy Validator Constitution

## Core Principles

### I. Labels Are Evaluation-Only

`data/receipts.jsonl` holds the correct answers in `labels`, `line_items[].labels` and `notes`.

- Only code under `eval/` MAY read those fields.
- The loader MUST strip them before any other component receives a receipt, and a test MUST
  fail if any pipeline module can reach them.
- The file MUST NOT be loaded whole into an assistant's context or pasted into a prompt.
- The firewall applies to traces: labels, `notes` and per-receipt answers MUST NOT reach a trace
  outside `eval/`. Evaluation writes its results as scores.

**Rationale.** A pipeline that has seen its answers cannot be measured honestly.

### II. Deterministic Decisions

- The policy engine, the policy retriever and the disposition logic MUST be plain Python.
- No model call decides an exception or a disposition. Models only produce structured inputs,
  such as an item's category, that the engine then reads.
- The same input MUST produce byte-identical output, and a test MUST prove it.

**Rationale.** Every flag must be explainable and repeatable. A reviewer must be able to re-run a
decision and get the same answer.

### III. Policy Text Is the Source of Truth

- Every rule MUST be implemented from `data/policy-docs/` and MUST cite its rule ID (for example
  `ALC-01`).
- Where the text admits more than one reading, the choice MUST be recorded in an ADR with an ID
  that the implementation cites (ADR 0001, decisions A1 to A8, mirrored in
  `docs/decisions/policy_decisions.yaml`).
- No pipeline code MAY reference a receipt ID.
- A change driven by evaluation results MUST cite, in its commit message, the policy clause that
  justifies it.

**Rationale.** Tuning the engine to the scored receipts would be overfitting with extra steps.

### IV. Evidence or Nothing

Every exception MUST carry `rule_id`, `policy_doc`, `line_ids` and the literal policy text it
relies on (EXC-04). An exception without evidence MUST NOT be emitted.

**Rationale.** A finance reviewer acts on the evidence, not on the flag.

### V. Decide on Dev, Report on Test

- Variants (models, prompts, thresholds, retrievers, reporters) MUST be compared on the synthetic
  dev set, against a decision rule written before the run.
- The 28 in-scope receipts run once per finalist and MUST NOT be used to choose between variants.

**Rationale.** With 28 receipts, choosing on the test set guarantees an optimistic number.

### VI. Honest Measurement

- Every metric MUST be reported with its N, and with an interval where one applies.
- The base rate MUST be computed and reported alongside precision and recall.
- Every number in the README MUST be reproducible from committed outputs with one command and no
  model calls.
- Preliminary results MUST be labelled as such.

**Rationale.** Honest numbers beat high ones.

### VII. Reproducibility

- Temperature 0 wherever the pinned endpoint supports it.
- Every result MUST record the model ID, the pinned provider and the prompt version.
- Prompts MUST be versioned.
- Model responses MUST be cached under a key built from the normalised input, the model ID and
  the prompt version, so that a re-run makes no paid call and the same decision.

**Rationale.** A result that cannot be re-run cannot be defended.

### VIII. Separation of Components

- The normaliser, item classifier, policy retriever, policy engine and exception reporter, plus
  evaluation and the viewer, MUST each live in its own module behind a typed interface.
- The classifier MUST NOT see the declared expense type or the attendee count.
- A component MAY depend only on the typed outputs of the components before it, never on their
  internals.

**Rationale.** Each stage can then be tested, measured and replaced on its own, and every failure
can be attributed to one stage.

### IX. Secrets Stay Out

- The OpenRouter key and the Langfuse keys live only in `.env`, which is gitignored.
- No key MAY appear in code, logs, outputs, traces, commits or chat.
- A pre-commit hook blocks key patterns and MUST NOT be bypassed.

### X. Observability of Every Model Call

- Every call to a generative or decision model, in the pipeline, in evaluation and in
  explorations, MUST be traced in Langfuse. Code that calls a model is instrumented with the
  Langfuse SDK from the start.
- One receipt or dev item is one trace, with one span per component and one `generation` per model
  call.
- Each generation records:
  - the model and the exact input (system prompt and messages, or decision payload);
  - the output and any reasoning;
  - token usage and billed cost;
  - the linked versioned prompt;
  - the OpenRouter request id.
- Observation names MUST be stable and verb-first (for example `classify-item`), never model
  names.
- Langfuse MUST NOT gate a run. If it is unavailable, the pipeline still runs and writes its
  committed outputs. Langfuse is the lab notebook, not the source of truth.
- How to observe the parts that call no model (engine, retriever, viewer, infrastructure) is
  decided in a later ADR.

**Rationale.** No model call is invisible, and the panel can inspect every one.

### XI. Iterative Delivery

- A working end-to-end MVP comes first. The system then improves in small, reviewable iterations.
- Every iteration MUST end runnable, with passing tests and an updated evaluation report.
- The scope, exit criteria and deferred items of each iteration live in `docs/roadmap.md`. Each
  iteration is its own specify → plan → tasks cycle, with its own ADR when it changes the
  architecture.
- Seams for likely changes, such as a queue between ingestion and validation, authentication in
  front of the viewer, or a replacement for the Streamlit viewer, MAY be designed in. They MUST
  NOT be built before their iteration: no speculative abstractions, and no unused interfaces
  beyond the seam itself.

**Rationale.** A thin system that runs beats a wide one that does not, and every iteration can be
shown.

## Constraints

- **Stack:** Python 3.12 managed with uv. Type hints on every public function.
- **Model access:** only through OpenRouter, within the brief's budget cap. Spend is measured, not
  estimated. The delivered pipeline does not use Anthropic models, as the team asked.
- **Retrieval:** no vector database, per the brief.
- **Scoring scope:**
  - Rules TIME-01 to TIME-04 are out of scope for scoring.
  - Receipts RCP-020, RCP-021, RCP-029 and RCP-030 are out of scope for scoring.
  - Scoring covers the remaining 28 receipts.
- **Language:**
  - Every artifact is written in English: code, identifiers, comments, docstrings, commits,
    pull requests, docs, ADRs, and every Spec Kit artifact (constitution, specs, plans,
    checklists, tasks).
  - The conversation with Luis is in Spanish. Anything quoted from it into the repo is translated.
  - `/speckit-analyze` checks this before implementation.
- **Test-first:** TODO(TEST_FIRST): whether, and for which components, work is test-first is
  decided in the architecture discussion and recorded in `docs/decisions/0002-architecture.md`.
  This constitution is amended to match.

## Development Workflow

- **Decisions first.** Every decision is recorded before it is implemented: ADRs in
  `docs/decisions/`, where policy decisions carry the IDs the engine cites.
- **What gets logged.**
  - Important prompts go in `docs/ai/prompt-log.md`.
  - Every mistake an assistant made goes in `AI_NOTES.md`, with how it was caught and what
    changed.
- **Commits.** Small Conventional Commits (`feat`, `fix`, `test`, `docs`, `refactor`, `chore`,
  and `exp` for experiments) that show how the work developed.
- **Branches.** One branch per complete unit of work, merged through a pull request.
- **Quality gates.** Before every commit, ruff and mypy are clean and pytest is green. The
  pre-commit hooks MUST NOT be bypassed with `--no-verify`.

## Governance

- This constitution supersedes every other practice in the repository. Where `CLAUDE.md` (the
  runtime guidance file for assistants) and this constitution disagree, the constitution wins.
  `CLAUDE.md` is then corrected in the same change.
- Amendments are made through a pull request that updates this file, bumps the version and states
  why. Versioning is semantic:
  - MAJOR: a principle is removed or redefined.
  - MINOR: a principle or section is added or materially expanded.
  - PATCH: wording only.
- Every plan passes the Constitution Check in the plan template before design and again after it.
  `/speckit-analyze` reports any conflict with a principle as critical.
- Complexity that a principle does not require MUST be justified in the plan's Complexity
  Tracking table.

**Version**: 1.0.0 | **Ratified**: 2026-10-08 | **Last Amended**: 2026-10-08
