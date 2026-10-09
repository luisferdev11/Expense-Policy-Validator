# ADR 0002: Architecture for iteration 1

- **Status:** accepted
- **Date:** 2026-10-08
- **Decided by:** Luis. The assistant (Claude Code) proposed three options and recommended B.
- **Scope:** iteration 1, the end-to-end MVP (`specs/001-mvp-end-to-end/spec.md`,
  `docs/roadmap.md`). A later iteration that changes the architecture gets its own ADR.

## Context

The spec asks for five separate components (normaliser, item classifier, policy retriever,
policy engine, exception reporter), plus evaluation and a viewer. Every decision must be
deterministic, and only the classifier may call a model. Every model call is traced, but
tracing never gates a run. The roadmap also asks for seams that keep three later changes cheap:
a queue (L1), authentication (L2) and a replacement for the viewer (L3).

Three facts shape the design:

1. **Some rules span receipts.**
   - MEAL-01, REG-02 and REG-03 add up one employee's meal receipts on the same date.
   - HEALTH-01 adds up OTC medication over a whole trip (A4).

   The engine therefore cannot be a function of one receipt alone.
2. **Only one stage is non-deterministic and costs money:** classification. Everything else is
   pure and runs in milliseconds.
3. **The decisions on ambiguous policy text already have a machine-readable home:**
   `docs/decisions/policy_decisions.yaml` (A1–A9).

## Options considered

| | A. Plain package with a batch CLI | **B. Ports and adapters around a pure core** | C. Pipeline of typed stages with a cache per stage |
|---|---|---|---|
| Shape | One module per component, calling each other. The classifier calls the gateway and the tracer directly | A pure core (models, normaliser, retriever, engine, FX, disposition, reporter) with no I/O. A few ports, adapters for the gateway, cache, tracer and files, and one orchestration module | A generic stage abstraction with memoisation. Every stage persists an artifact |
| LLM isolation | By convention only | By structure: the core cannot import adapters or network libraries, and a test enforces it | Inside one stage, but within a generic framework |
| Tracing that never gates a run | `try` blocks scattered through the code | One `Tracer` port with a Langfuse and a no-op implementation | A hook per stage |
| Cost now | Lowest | Low to medium | High. The stage framework is the kind of speculative abstraction principle XI forbids |
| Adding a queue (L1) | Medium to high: batch and receipt logic have to be separated afterwards | Low: a worker calls the same `validate(receipt, context)` | Low to medium, but the cross-receipt rules break a per-item stage model |
| Adding auth (L2) | Low | Low | Low |
| Swapping the viewer (L3) | Medium, if the viewer imports internals | Low: the viewer reads only through `results.py` and the schema | Low |
| Main risk | I/O leaking into the engine, which is what the panel will ask about most | More files | Not reaching the MVP |

## Decision

**Option B**, with one element borrowed from C: the classification artifact is committed.

### Module boundaries

```
src/expense_validator/
  models.py         # Pydantic models: the typed interfaces between components
  loader.py         # the only reader of data/receipts.jsonl; strips answer fields
  normaliser.py     # pure
  classification/
    port.py         # ItemClassifier protocol
    prompt.py       # versioned prompt cls-v2 and its strict output schema
    openrouter.py   # gateway adapter (pinned model and provider, temperature 0)
    keyword.py      # keyword-classifier baseline (same port)
    cache.py        # classification cache, keyed on normalised input + MCC + model + prompt version
  retriever.py      # pure trigger map
  engine/
    registry.py     # per rule: rule_id, policy_doc, severity, decision IDs, literal evidence quote
    rules/          # one module per policy document, pure functions
    fx.py           # FX component with date_basis and rate_kind settings (A1)
    context.py      # build_context(batch): per employee per date, and per trip
    disposition.py  # EXC-01
    settings.py     # reads docs/decisions/policy_decisions.yaml
  reporter.py       # pure template, with the arithmetic behind each finding
  tracing.py        # Tracer protocol, LangfuseTracer, NoopTracer
  pipeline.py       # orchestration (see "Flow")
  results.py        # read-only access to committed outputs
  cli.py            # run, eval, view
eval/               # the only code that reads answer fields; keyword-flagger baseline lives here
viewer/app.py       # Streamlit; reads through results.py and eval outputs only
outputs/            # committed: results.jsonl, classifications.jsonl, eval/
```

The `models.py` names below are indicative. The plan fixes the exact fields.
- **Typed interfaces between components.**
  - `ReceiptInput` goes to `normalise`, which returns `NormalisedReceipt`.
  - `ItemClassifier.classify(NormalisedItem)` returns `Classification`. That holds the category,
    the restricted flag, the confidence, the subtype (A6), `recipient_kind` and `recipient_name`
    (A9), or an unclassified reason.
  - `retrieve(ClassifiedReceipt)` returns the `RuleSet`.
  - `evaluate(ClassifiedReceipt, CrossReceiptContext, RuleSet, Settings)` returns the
    `EngineFindings`, which `report(...)` turns into a `ReceiptResult`.
- **Ports.** There are two, because each has at least two implementations today:
  - `ItemClassifier`: the OpenRouter adapter, the keyword classifier, and a fake for tests;
  - `Tracer`: Langfuse and no-op.

  The cache and the results reader are plain modules, not ports.

### Flow

1. `load` returns the receipts, without answer fields.
2. Each receipt is normalised.
3. Every item is classified. The cache is checked first, and a miss calls the gateway.
4. `build_context(all classified receipts)` computes the cross-receipt aggregates.
5. For each receipt, in a fixed order: `retrieve`, `evaluate`, `report`.
6. The results are written in a canonical order and serialisation.

Step 4 is a pure function. The result never depends on the order of receipts.

### Where things live

- **Cache.**
  - `outputs/classifications.jsonl` is committed. It holds parsed classifications with the model
    ID, provider, prompt version, OpenRouter request id and billed cost, but not the raw response
    bodies. Those stay local and gitignored.
  - With this file, anyone can re-run the whole pipeline without a key and get byte-identical
    results.
- **FX component.**
  - `engine/fx.py` is pure. Its settings come from A1. Its data (the ISO 4217
    country-to-currency table for A8, and the euro rate table for A1) lives as versioned files
    under `config/`, each recording its source.
  - A missing rate yields review, never pass.
- **Decision IDs.**
  - Each rule's registry entry lists the decisions it follows (A1–A9) and its literal evidence
    quote.
  - A test checks that every quote is an exact substring of its policy document.
  - Settings such as `exc03.threshold` (0.5, provisional) and the reference prefix table (A5)
    are read from `policy_decisions.yaml`, the single source.
  - Each result records `rules_version`, a hash of the registry and settings.
- **LLM isolation.**
  - Only `classification/openrouter.py` talks to a model.
  - `engine/`, `retriever.py`, `normaliser.py`, `reporter.py`, `models.py` and `context.py`
    import no adapter and no network or SDK module, and an architecture test enforces this.
  - The classifier's request never contains the declared expense type or the attendee count,
    and a contract test enforces this too.

### Observability (CLAUDE.md rule 11)

- **One trace per receipt.**
  - Its ID is derived deterministically from the run and the receipt ID. The ID is not written
    into results, so the results stay byte-identical across runs.
  - It has one span per component, with stable verb-first names: `normalise-receipt`,
    `classify-receipt`, `retrieve-rules`, `apply-rules`, `report-exceptions`.
- **One generation per model call**, named `classify-item`. It records:
  - the model and the exact messages;
  - the output and the reasoning;
  - usage and billed cost;
  - the linked prompt version;
  - the OpenRouter request id.

  A cache hit is not a model call. It produces no generation, and the span marks the item
  `cache_hit` with the original request id.
- **Langfuse never gates a run.** `LangfuseTracer` is built only when keys are present and a
  health check passes within a short timeout. Any error during the run switches it to
  `NoopTracer` with one warning. The final flush has a timeout too. Outputs never depend on
  tracing.
- **Labels firewall.** Pipeline traces contain inputs and outputs only. `eval/` attaches
  results as scores on the same trace IDs.

### Test strategy

- **Test-first** is mandatory for the deterministic components:
  - the loader and the labels firewall;
  - the normaliser;
  - `fx.py`;
  - the retriever;
  - the engine rules;
  - `context.py`;
  - disposition;
  - the reporter.

  This settles the constitution's TODO(TEST_FIRST), which v1.1.0 amends.
- **Fixtures:**
  - The brief's five cases, using real receipt inputs through the loader. Their classifications
    are written by hand from the descriptions, never from labels.
  - The 13 DRAFT synthetic engine cases, which Luis reviews before "MVP done".
- **Determinism:** the full pipeline runs twice from the committed cache, and the outputs must be
  byte-identical. The engine also runs on a shuffled batch and must give the same results.
- **Classifier contracts:**
  - the schema is checked against recorded responses;
  - a gateway failure and invalid JSON each become an unclassified item, then EXC-03, then a
    disposition that is not pass;
  - a test checks the request payload never carries the declared type or the attendee count.
- **Architecture:**
  - the pure core imports no adapter;
  - no module outside `eval/` references the answer fields;
  - every evidence quote is verbatim.
- **Retriever:** on every fixture, the selected rules include every rule the engine raises.
- **CLI and viewer:** smoke tests only.

## Built now and only made room for

| Item | Built in iteration 1 | Only a seam (deferred to) |
|---|---|---|
| `validate(receipt, context)` with the context as an explicit input | Yes | A queue worker and a context store (L1). Timing rules use the same context (L6) |
| `results.py` as the only way to read outputs | Yes | An API, auth in front of it, and a new UI (L2, L3) |
| Pydantic models that export a JSON Schema | Yes | API contracts (L3) |
| `rules_version` in every result | Yes | Versioned policy deployment (L5) |
| One span per component | Yes | Observability of the parts that call no model (L7) |
| A worker, queue, auth, API, database or server | No | L1–L4 |

## Consequences

- **The engine can be explained and tested with no model**, which is what the panel will probe.
- **More files than option A**, about two ports. The architecture test is what keeps the
  boundary honest.
- **The committed classification file** makes reproducibility cheap. It must be regenerated
  whenever the prompt or the model changes. Its key includes both, so a stale entry is a miss,
  never a wrong hit.
