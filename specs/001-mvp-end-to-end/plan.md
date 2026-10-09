# Implementation Plan: Iteration 1, an End-to-End MVP

**Branch**: `chore/spec-kit-init` | **Date**: 2026-10-08 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-mvp-end-to-end/spec.md`; architecture from
`docs/decisions/0002-architecture.md`; scope from `docs/roadmap.md` (iteration 1 only).

## Summary

Build the brief's whole pipeline once, thin and correct:
- a label-stripping loader;
- a deterministic normaliser;
- one model-backed item classifier, `openai/gpt-oss-120b` on OpenRouter with prompt `cls-v2`
  (category, restricted, confidence, the subtype from A6, the recipient fields from A9);
- a trigger-map retriever;
- a pure engine over all 37 in-scope rules, with the cross-receipt context explicit;
- a template reporter;
- committed JSONL outputs;
- an `eval/` package that alone reads the answers;
- a Streamlit viewer.

**Architecture**, from ADR 0002 option B:
- ports and adapters around a pure core, with two ports (`ItemClassifier`, `Tracer`);
- a committed classification cache, so anyone can re-run the pipeline byte for byte without a
  key;
- Langfuse tracing that falls back to no-op and never gates a run.

**Tests.** The deterministic core is built test-first (constitution v1.1.0).

## Technical Context

**Language/Version**: Python 3.12, managed with uv

**Primary Dependencies**: `pydantic>=2`, `openai` (OpenRouter-compatible client), `langfuse`
(v3 or later API), `python-dotenv`, `pyyaml`, `streamlit`. Dev: `pytest`, `ruff`, `mypy`,
`pre-commit`, `types-PyYAML`. See research R13.

**Storage**: Local files only.
- Inputs: `data/`, `config/` and `docs/decisions/policy_decisions.yaml`.
- Committed outputs: `outputs/`.
- Raw response bodies: gitignored `.cache/raw/`.

**Testing**: pytest. Test-first for the deterministic core. Contract tests for the classifier
adapters. Smoke tests for the CLI and viewer. Architecture, determinism and firewall tests.

**Target Platform**: Local Linux or macOS, with a batch CLI

**Project Type**: CLI pipeline with a Python library core, an evaluation package and a
Streamlit viewer

**Performance Goals**: Not a constraint at 32 receipts.
- A warm-cache run takes well under 10 s.
- A cold run is bounded by 79 classification calls.

**Constraints**:
- Byte-identical outputs.
- No model call in the engine.
- No paid call on a warm cache.
- Model spend under USD 1.00 for this iteration, within the brief's USD 5.
- Langfuse never gates a run.
- No vector database.
- Labels are read only under `eval/`.

**Scale/Scope**: 32 receipts and 79 line items, 28 receipts and 65 items scored, 37 rules, 21
categories, 6 languages

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How this plan complies | Pre | Post |
|---|---|---|---|
| I. Labels evaluation-only | The loader strips the fields, and input models forbid extra keys (R1). `eval/` is the only reader (R7). Architecture tests forbid answer keys and `receipts.jsonl` access elsewhere. Traces carry no answers, and eval writes scores. The viewer reads answers only from `comparison.jsonl` | ✅ | ✅ |
| II. Deterministic decisions | The engine, retriever, context and disposition are pure. An architecture test bans network and SDK imports in the core. A determinism test runs the pipeline twice and on a shuffled batch (R9) | ✅ | ✅ |
| III. Policy text is the source of truth | The registry holds one verbatim sentence per rule, checked by a test (R8). Each rule cites its A-IDs. No receipt ID appears in pipeline code, and the out-of-scope list lives in `eval/` | ✅ | ✅ |
| IV. Evidence or nothing | `ExceptionFinding` requires `rule_id`, `policy_doc`, `line_ids` and `evidence`. Invariant tests check them (`contracts/receipt-result.md`) | ✅ | ✅ |
| V. Decide on dev, report on test | Iteration 1 chooses no variant. The model and the EXC-03 threshold of 0.5 are provisional and declared in every result. Choosing them is iteration 2 work | ✅ | ✅ |
| VI. Honest measurement | Every metric is `{value, n, interval?}`. The base-rate table is in the report. `epv eval` reproduces everything without a model call | ✅ | ✅ |
| VII. Reproducibility | Temperature 0 and a pinned endpoint (R3). Prompt `cls-v2` is versioned in code and in Langfuse (R4). The committed cache is keyed on input, model, endpoint and prompt (R5). `run` metadata is in every result | ✅ | ✅ |
| VIII. Separation of components | Five components, plus `eval/` and `viewer/`, each a module behind Pydantic interfaces. `ClassifierRequest` carries only description, merchant and MCC, which a contract test checks | ✅ | ✅ |
| IX. Secrets stay out | Keys only in `.env`. The stderr summary and traces never print a key. The pre-commit hook is unchanged. Committed cache rows hold no auth data | ✅ | ✅ |
| X. Observability | The trace shape is in `contracts/tracing.md`: one trace per receipt, a span per component, a generation per billed call. `NoopTracer` is the fallback, and flush is bounded (R6) | ✅ | ✅ |
| XI. Iterative delivery | Only the seams named in ADR 0002 are built. No queue, auth, API, worker or database. The tasks put a thin end-to-end path first, with an "MVP done" checkpoint | ✅ | ✅ |
| Test-first | The tasks order each deterministic module's test before its code (constitution v1.1.0) | ✅ | ✅ |
| Language | Every artifact here is in English | ✅ | ✅ |

**Gate result:** pass, with no violations. Complexity Tracking stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/001-mvp-end-to-end/
├── spec.md
├── plan.md              # this file
├── research.md          # Phase 0: R1–R13
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1: validation scenarios, "MVP done"
├── contracts/
│   ├── cli.md
│   ├── classifier-output-cls-v2.schema.json
│   ├── receipt-result.md
│   └── tracing.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
src/expense_validator/
├── __init__.py
├── models.py              # Pydantic interfaces (data-model.md)
├── loader.py              # only reader of data/receipts.jsonl; strips answers
├── normaliser.py          # pure
├── classification/
│   ├── port.py            # ItemClassifier protocol, ClassifierRequest
│   ├── prompt.py          # cls-v2 system prompt + strict schema (ported from explorations/lib)
│   ├── taxonomy.py        # 21 categories + restricted flags from data/category-taxonomy.md
│   ├── cache.py           # committed cache: outputs/classifications.jsonl
│   ├── openrouter.py      # adapter: pin, cap, cost, request id, generation tracing
│   ├── prompt_sync.py     # pushes cls-v2 to Langfuse Prompt Management before the first billed call
│   └── keyword.py         # keyword-classifier baseline (same port)
├── retriever.py           # pure trigger map
├── engine/
│   ├── registry.py        # RuleSpec per rule: doc, severity, scope, A-IDs, verbatim evidence
│   ├── settings.py        # policy_decisions.yaml + config tables
│   ├── fx.py              # A1 settings; USD and EUR conversion; missing rate → review
│   ├── context.py         # CrossReceiptContext (meal days, trip OTC), order-independent
│   ├── rules/
│   │   ├── meals.py       # MEAL-01/02, ALC-01/02/03, ENT-01/02
│   │   ├── technology.py  # TECH-01..04
│   │   ├── gifts.py       # GIFT-01..04
│   │   ├── non_reimbursable.py  # PERS-01..03, HOUSE-01, HEALTH-01, LAUNDRY-01
│   │   ├── merchant.py    # MCC-01/02/03
│   │   ├── documentation.py     # DOC-01..04
│   │   └── regional.py    # REG-01..05 (overrides)
│   ├── uncertainty.py     # EXC-03 exclusion and signals
│   ├── disposition.py     # EXC-01
│   └── evaluate.py        # evaluate(receipt, context, ruleset, settings) -> EngineFindings
├── reporter.py            # pure templates with arithmetic
├── tracing.py             # Tracer, LangfuseTracer, NoopTracer
├── pipeline.py            # load → normalise → classify → context → retrieve/evaluate/report
├── results.py             # read-only access to outputs (viewer/API seam)
└── cli.py                 # epv run | eval | view

eval/
├── __init__.py
├── answers.py             # the only reader of answer fields
├── scope.py               # the four out-of-scope receipt IDs (eval config, not pipeline)
├── compare.py             # matching rules from data/README.md
├── metrics.py             # macro F1, restricted F1, confusion, FP/9, missed/16, per-rule, evidence, Wilson
├── baselines.py           # keyword-flagger
├── base_rate.py           # flags per 10,000 at 1/3/5 % prevalence
├── report.py              # metrics.json → report.md
└── scores.py              # Langfuse scores (optional, non-gating)

viewer/
└── app.py                 # Streamlit: list, detail, metrics

config/
├── iso4217_country_currency.csv   # A8, with source
└── eur_rates.csv                  # A1 fallback table, with source (empty rows allowed)

outputs/                   # committed
├── results.jsonl
├── classifications.jsonl
├── baselines/keyword_classifier/results.jsonl
├── baselines/keyword_flagger/results.jsonl
└── eval/{comparison.jsonl, metrics.json, report.md}

tests/
├── unit/                  # test-first: loader, normaliser, fx, context, retriever, each rule module, disposition, reporter, eval metrics
├── engine_cases/          # brief's five cases + 13 DRAFT synthetic cases (fixtures)
├── contract/              # classifier request/response, schema export drift, tracer fallback
├── architecture/          # import bans, answer-key ban, verbatim evidence
├── integration/           # determinism (twice + shuffled), offline run, eval reproducibility
└── smoke/                 # CLI and viewer start
```

**Structure decision**: a single project with three packages: the pipeline, `eval` and
`viewer`. All three are built from `pyproject.toml` and checked by mypy (R7). `explorations/`
stays frozen research. Code from it is ported into `src/`, never imported.

## Delivery order (input to `/speckit-tasks`)

1. **Setup.** Dependencies, packages, the `epv` entry point, and `pyproject` mypy paths.
2. **Thin path.** Pull one receipt through every component:
   - the loader and firewall, test-first;
   - the models;
   - the normaliser;
   - the classifier port with a fake, then the OpenRouter adapter and cache;
   - a retriever with two rules;
   - an engine with EXC-01, MCC-02 and TECH-02;
   - the reporter;
   - results writing;
   - a minimal `eval` with the disposition matrix;
   - a viewer list view.

   The tracer is wired in here too. It is the earliest point where `epv run`, `epv eval` and
   `epv view` all work.
3. **Widen the engine**, rule module by rule module, test-first, against the five brief cases and
   the 13 DRAFT cases. Cross-receipt context, FX and regional overrides go last.
4. **Widen the evaluation** to every FR-030 and FR-031 item and both baselines.
5. **Widen the viewer** to the detail and metrics views.
6. **Cold run, once.** Generate the committed cache and outputs, and commit.
7. **"MVP done" checkpoint.** Every quickstart scenario passes, and Luis has reviewed the 13
   engine cases.

## Complexity Tracking

No violations. The two ports each have two or more implementations today, as constitution XI
requires.
