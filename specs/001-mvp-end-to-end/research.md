# Phase 0 Research: Iteration 1 MVP

Every open technical question in the plan's Technical Context, each resolved with a decision, its
rationale and the alternatives considered. The architecture itself is settled in ADR 0002. This
file covers only the choices below that level.

## R1. Typed interfaces: Pydantic v2 models

- **Decision:**
  - Every interface between components is a Pydantic v2 model, frozen.
  - Input models use `extra="forbid"`.
  - The output models export a JSON Schema into `contracts/`.
- **Rationale:**
  - Validation at the boundary.
  - The forbid on input models is a second labels firewall: if an answer key ever survived
    the loader, validation fails.
  - The JSON Schema export is the L3 seam that ADR 0002 names.
  - mypy strict works with the Pydantic plugin.
- **Alternatives:**
  - Dataclasses: no validation and no schema export.
  - TypedDicts: no runtime checks.

## R2. Money: `Decimal` end to end inside the engine

- **Decision:**
  - The loader parses numbers with `json.loads(..., parse_float=Decimal)`.
  - All conversions and thresholds use `Decimal`.
  - Comparisons follow the policy wording exactly: "above $200" is `>`, and "four or more
    nights" is `>=`.
  - Output amounts are serialised as JSON numbers, quantised to 2 decimals for USD and 4 for
    rates.
  - Confidence stays as the model returned it.
- **Rationale:**
  - Boundary cases such as $189 against $200, or EUR 70 at a receipt rate, must not depend on
    binary floating point.
  - It also helps byte-identical output.
- **Alternatives:** floats with an epsilon. Rejected, because tolerances would become policy.

## R3. Model access: OpenRouter through the `openai` SDK, ported from `explorations/lib/budget.py`

- **Decision:**
  - Use the `openai` client with `base_url=https://openrouter.ai/api/v1`.
  - Model `openai/gpt-oss-120b`, pinned to endpoint `deepinfra/bf16`, with
    `allow_fallbacks: false` and `require_parameters: true`.
  - Temperature 0. Reasoning effort low.
  - Strict `json_schema` response format.
  - Billed cost is read from `usage.cost`, and the request id is kept.
  - A spend cap of USD 1.00 for this iteration, checked before each call against the summed
    reported cost.
- **Ported, not imported:** the pinning, the cap and the cost reading are re-implemented in
  `classification/openrouter.py`, with tests. Explorations stay frozen research.
- **Rationale:**
  - This is the configuration E11 and E13 already exercised (105/109 on the DRAFT dev set,
    PRELIMINARY).
  - The pin keeps provider variance out.
- **Alternatives:**
  - `httpx` by hand: more code.
  - LiteLLM: another dependency and another layer to trace.

## R4. Prompt `cls-v2`

- **Decision:**
  - `cls-v1`'s taxonomy-derived system prompt and its "names lie" rules, extended:
    - when the category is `other`, a closed `subtype` (A6);
    - `recipient_kind` and `recipient_name` (A9).
  - The strict schema has the fields `category`, `confidence`, `subtype`, `recipient_kind` and
    `recipient_name` (nullable), all required, with no additional properties.
  - The user message carries only the cleaned description, the merchant name and the MCC.
  - The prompt is versioned in code and pushed to Langfuse Prompt Management as
    `classify-item-chat` under the label `cls-v2`.
- **Rationale:** one call per item, as A9 decided. The fields are closed, so the engine never
  parses text.
- **Alternatives:**
  - Separate calls for the recipient fields. Rejected in A9.
  - A per-receipt call, classifying all items at once. Deferred: it changes the cache key and
    the failure granularity, and is an iteration 2 experiment if wanted.

## R5. Classification cache, committed

- **Decision:**
  - The cache is `outputs/classifications.jsonl`: one row per cache key, rows sorted by key.
  - The key is the SHA-256 of the canonical JSON of the cleaned description, merchant name,
    MCC, model ID, provider endpoint and prompt version.
  - Each row stores:
    - the parsed fields;
    - the model ID, endpoint and prompt version;
    - the request id;
    - the billed cost and token usage;
    - the reasoning text.
  - Raw response bodies stay local, under gitignored `.cache/raw/`.
- **Rationale:**
  - The panel can re-run the whole pipeline without a key and get byte-identical results.
  - A change of prompt or model is a cache miss, never a wrong hit.
- **Alternatives:**
  - A local-only cache: re-running costs money.
  - Committing raw bodies: noisy, and possibly carrying provider metadata.

## R6. Langfuse: Python SDK v3 API, behind a `Tracer` port that never gates a run

- **Decision:**
  - Use the `langfuse` package (v3 or later API: `get_client`, `start_as_current_observation`,
    `create_trace_id`).
  - The trace ID is `create_trace_id(seed=f"{run_label}:{receipt_id}")`, applied through
    `trace_context`. The Langfuse docs confirm that a seed gives a deterministic ID.
  - `LangfuseTracer` is enabled only when the keys are present and `auth_check()` succeeds
    within a short timeout. Otherwise the tracer is `NoopTracer`, with one warning.
  - Any tracer exception during the run switches to no-op.
  - `flush()` blocks, according to the docs. It runs in a daemon thread joined with a timeout,
    so a dead server can never hang the CLI.
- **Rationale:** CLAUDE.md rule 11 and constitution X: everything is traced, and nothing is
  gated on tracing.
- **Alternatives:**
  - Raw OpenTelemetry: more plumbing for the same result.
  - Logging traces to files only: loses the prompt link and the inspection UI the panel will
    see.
- **Verify at implementation:** the exact installed version and the `auth_check` signature,
  through the Langfuse docs MCP.

## R7. Where evaluation and the viewer live, and the import boundaries

- **Decision:**
  - Three top-level packages:
    - `src/expense_validator/`, the pipeline;
    - `eval/`, the only code that reads answer fields;
    - `viewer/`, Streamlit.
  - They are built as packages from `pyproject.toml`, and mypy covers all three.
  - The architecture test parses imports with `ast`, over `src/expense_validator/` and
    `viewer/`:
    - the pure core (`models`, `normaliser`, `retriever`, `engine`, `reporter`) imports no
      adapter, no `openai`, no `langfuse`, no `httpx` and no `requests`;
    - no module imports `eval`, with one exception: a lazy import inside the `eval` subcommand
      of `cli.py`, which `epv eval` needs to dispatch to the evaluation package;
    - no module other than `loader.py` names `receipts.jsonl`;
    - no module other than `loader.py` contains the string keys `labels` or `notes`.
      `loader.py` must name them to strip them.

    Both exceptions were added after `/speckit-analyze` found the original rule contradicted
    `loader.py` and `cli.py` (analysis I1 and I2).
- **Rationale:** CLAUDE.md rule 1 names `eval/` explicitly. Static checks catch a violation
  before it runs.
- **Alternatives:**
  - `src/expense_validator/eval/`: blurs the firewall path.
  - The import-linter tool: an extra dependency for about 30 lines of `ast`.

## R8. The evidence quote and the rules version

- **Decision:**
  - Each registry entry holds one verbatim sentence from its policy document as `evidence`.
  - A test asserts that the sentence is an exact substring of the file, after collapsing
    whitespace and removing Markdown bold markers.
  - `rules_version` is the first 12 hex characters of a SHA-256 over:
    - the engine package source;
    - `docs/decisions/policy_decisions.yaml`;
    - the nine policy documents, in sorted path order.
- **Rationale:**
  - Evidence is the literal policy text (EXC-04).
  - Any change in rules or decisions changes the version recorded in every result (the L5
    seam).
- **Alternatives:**
  - Parsing rule paragraphs from Markdown at runtime: brittle with these documents.
  - A hand-set semver: easy to forget to bump.

## R9. Determinism of the outputs

- **Decision:**
  - Receipts are processed and written in `receipt_id` order.
  - The JSON is canonical: a fixed field order from the models, a fixed float quantisation,
    `ensure_ascii=False`, and `\n` line endings.
  - Results contain no timestamps or run IDs. Run metadata with a timestamp goes to a separate,
    uncommitted run log.
  - The determinism test runs the pipeline twice, and once on a shuffled batch, and compares
    bytes.
- **Rationale:** constitution II and VII, and spec SC-003.

## R10. Retriever: a trigger map

- **Decision:** a static table maps each in-scope rule to the trigger conditions under which it
  could apply. A rule is selected when any of its triggers matches:
  - categories present;
  - a subtype;
  - the MCC tier or set;
  - the declared type family;
  - currency other than USD;
  - entity;
  - itemized is false;
  - a trip;
  - a recipient kind;
  - always-on rules (DOC-02, DOC-03).

  A test checks, on every fixture and on the full run, that the engine never raises a rule the
  retriever did not select.
- **Rationale:** the `02_retriever_candidates` exploration. It is deterministic and explains
  itself.
- **Alternatives:**
  - Passing every rule: kept as the iteration 2 comparison.
  - Embeddings: no gain at nine documents, and a vector database is forbidden.

## R11. Keyword baselines

- **Decision:**
  - **`keyword-classifier`** implements the `ItemClassifier` port in
    `classification/keyword.py`. Lowercase keyword lists per restricted category, in six
    languages, are written from the taxonomy's examples, never from the receipts' descriptions.
    Anything unmatched is `food_beverage` when the MCC is 5812, 5813 or 7011, and `other`
    otherwise. Confidence is 1.0.
  - **`keyword-flagger`** lives in `eval/baselines.py`: any restricted keyword on any line flags
    the receipt; otherwise it passes.
- **Rationale:** spec FR-032. A fair baseline that shares the engine, plus the legacy strawman,
  both stated honestly.
- **Contamination guard:** a test checks that no keyword list entry equals a real line
  description, mirroring the dev-set contamination check.

## R12. CLI

- **Decision:**
  - One entry point, `epv`, defined in `[project.scripts]` and built with stdlib `argparse`.
  - Subcommands:
    - `epv run [--classifier openrouter|keyword] [--offline]`;
    - `epv eval`;
    - `epv view`, which launches `streamlit run viewer/app.py`.
  - `--offline` forbids model calls. A cache miss then becomes unclassified, then EXC-03.
- **Rationale:** spec FR-035. `argparse` adds no dependency.
- **Alternatives:** Typer or Click: a nicer UX, but another dependency.

## R13. Dependencies

- **Runtime:**
  - `pydantic>=2`;
  - `openai`;
  - `langfuse` (v3 or later API);
  - `python-dotenv`;
  - `pyyaml`;
  - `streamlit` (viewer).
- **Dev additions:** `types-PyYAML`.
- **Rationale:** each one is used in iteration 1. There is no `scipy`: Wilson intervals and the
  confusion matrix are a few lines and are tested.
