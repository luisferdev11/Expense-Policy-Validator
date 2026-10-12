# Implementation Plan: jev classifier, shadow mode and experiment E16

**Branch**: `feat/007-jev-classifier` | **Date**: 2026-10-12 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/007-jev-classifier/spec.md`. Contracts:
`contracts/decision-adapter.md`, `contracts/e16-rule.md`, `contracts/api-delta.md`. Decisions:
`research.md` R1–R10.

**Prerequisite**: spec 006 Phase 2 and US1 (T006–T024) merged. They provide:

- `ClassificationCachePort` (`ports/classification_cache.py`);
- the table adapter `SqliteClassificationCache` (`adapters/sqlite_cache.py`);
- the ordered schema migrations in `adapters/sqlite_store.py` (version 2).

`ClassificationCache` is the JSONL adapter and stays for `epv run` and `run_dev.py`. If any of
these is missing, stop and implement it first.

## Summary

The jev call moves from a front-end script into the package, as a `DecisionClassifier` behind the
existing `ItemClassifier` port. Next to it goes a `HybridClassifier` (jev category and
confidence, gpt-oss-120b subtype and recipient), and both are built by one factory chosen by
`classifier_model`.

A `shadow` outbox stage stores a second classifier's answers per line without touching receipts.
It is exposed through `GET /receipts/{id}/shadow` and `epv shadow report`.

Two gaps in `eval/experiments/decide.py` are fixed (guard order, superior-wins), test-first, with
E14's committed outcome unchanged. E16 is registered (`contracts/e16-rule.md`), with a hard stop
for Luis's approval before any run.

The committed configuration stays `gpt-oss-120b`. Outputs, the engine and the policy decisions do
not change.

## Technical Context

- **Language/Version:** Python 3.12, managed with uv.
- **Primary Dependencies:** existing ones (pydantic 2, FastAPI, openai SDK, langfuse through the
  `Tracer` port). `httpx` moves from the dev group into `dependencies`; the decision transport uses
  it, because the OpenAI SDK has no decisions endpoint.
- **Storage:** the SQLite store, plus one table (`shadow_classifications`) in the next schema
  schema version 3 (after spec 006's version 2).
- **Testing:** pytest, test-first for every deterministic piece: payload, parser, merge, factory,
  shadow comparison and report, decide-rule fixes, migration. Contract tests for both adapters
  with fake transports, for the shadow endpoint, and for the tracer (no generation on a cache
  hit). Integration: parity with shadow on (fake transports); crash and resume of a `shadow` item.
  A smoke test for `epv shadow report`.
- **Target Platform:** Linux and macOS, one machine.
- **Project Type:** the existing layered package (ADR 0003).
- **Performance Goals:** the shadow adds no latency to the primary path (a separate stage). jev's
  measured latency is 0.59 s per item on average (N = 130).
- **Constraints:** labels firewall; engine untouched (alert Luis before any change under
  `domain/engine/`); no change to `outputs/`, `config/pipeline.yaml` or `policy_decisions.yaml`;
  Langfuse never gates; no new secret; spend caps of USD 0.25 per process for the shadow and the
  jev adapter, and USD 0.10 for E16.
- **Scale/Scope:** tens to thousands of receipts. E16 has 130 items.

## Constitution Check

*GATE: checked before Phase 0 and again after Phase 1.*

| Principle | Status | How |
|---|---|---|
| I. Labels are evaluation-only | Pass | The adapters see only `ClassifierRequest`. The shadow report reads the store only. E16 reads dev labels inside `eval/` only. The architecture test stays green, and the new `domain/stats.py` imports nothing from `eval/` |
| II. Deterministic decisions | Pass | `domain/engine/` is untouched. The shadow never feeds the engine. The disposition-impact figure re-runs the unchanged decision code over stored answers, with no call |
| III. Policy text is the source of truth | Pass | No rule changes. Migration would change the A3 threshold only through E16 and an ADR, after alerting Luis |
| IV. Evidence or nothing | Pass | Findings still come from the unchanged engine |
| V. Decide on dev, report on test | Pass | E16 is registered and approved before any run. The shadow decides nothing. The 28 receipts run with jev only once, as a finalist |
| VI. Honest measurement | Pass | Every shadow and E16 figure carries k and N, with Wilson intervals for proportions. The repeatability measure is reported |
| VII. Reproducibility | Pass | Literal responses are cached before parsing. The model id, prompt version (`dec-v1`, `hyb-v1(...)`) and serving provider are recorded. Replays make no call |
| VIII. Separation of components | Pass | New adapters sit behind the existing port; the factory is in `app/`; comparison and statistics are pure in `domain/`. The classifier still never sees the declared type or the attendees |
| IX. Secrets stay out | Pass | It reuses `OPENROUTER_API_KEY` from the environment; the transport never logs headers |
| X. Observability | Pass | One `classify-item` generation per billed call, none on a hit. The decision prompt `classify-item-decision`/`dec-v1` is synced. Shadow calls are traced in the revision's trace under `shadow-classify-receipt` |
| XI. Iterative delivery | Pass | The vertical slices below each end green |

No violations, so no Complexity Tracking entries.

## Project Structure

### Documentation (this feature)

```text
specs/007-jev-classifier/
├── spec.md
├── research.md
├── data-model.md
├── plan.md
├── tasks.md
├── quickstart.md
├── contracts/
│   ├── decision-adapter.md
│   ├── e16-rule.md
│   └── api-delta.md
└── checklists/requirements.md
```

### Source Code (repository root)

```text
src/expense_validator/
├── domain/
│   ├── lifecycle.py                  # Stage gains "shadow"
│   ├── shadow.py                     # compare(), report counts (pure)
│   └── stats.py                      # wilson(), moved from eval/stats.py (pure)
├── ports/
│   └── store.py                      # + ShadowRecord, save_shadow/shadow_for/iter_shadow
├── adapters/
│   ├── openrouter/
│   │   ├── decision_prompt.py        # DECISION_INSTRUCTIONS, decision_payload, parse_decision
│   │   ├── decision_classifier.py    # DecisionClassifier (+ httpx transport with retries)
│   │   └── prompt_sync.py            # + sync_decision_prompt (classify-item-decision / dec-v1)
│   ├── hybrid_classifier.py          # HybridClassifier and the merge table
│   ├── config_files.py               # validate classifier_model against the factory names
│   └── sqlite_store.py               # + migration v2→v3: rebuild outbox (stage CHECK), shadow_classifications; shadow methods
└── app/
    ├── classifiers.py                # build_classifier() factory
    ├── intake.py                     # default_classifier() uses the factory
    ├── composition.py                # build_worker(shadow=...) uses the factory
    ├── worker.py                     # queue and process "shadow" items
    ├── shadow_report.py              # the epv shadow report content
    ├── api/routes.py, api/schemas.py # GET /receipts/{id}/shadow
    └── cli.py                        # --shadow, --shadow-cap-usd, epv shadow report

eval/
├── stats.py                          # re-exports wilson from domain/stats.py
└── experiments/
    ├── decide.py                     # guard order + superior-wins fix; e16()
    └── run_dev.py                    # --experiment E16 --variant {jev-1.13,jev-hybrid}

explorations/research/experiments_plan.yaml   # E16 registration (text from contracts/e16-rule.md)

tests/
├── fixtures/dec_v1_payload.json      # captured once from explorations/lib/decision_adapters.py
├── unit/                             # decision prompt, parser, merge, factory, shadow, stats, decide fixes
├── contract/                         # decision adapter, hybrid, shadow endpoint, tracer
├── integration/                      # parity with shadow on; shadow resume
└── smoke/                            # epv shadow report

docs/ai/prompt-log.md                 # dec-v1 entry
docs/api/openapi.json                 # regenerated
docs/api/build_collection.py          # + shadow 404 request
```

**Structure Decision**: extend the four layers. `frontend/scripts/jev_dev_run.py` stays as the
historical record of the 2026-10-11 run and is not rewired.

## Delivery order (vertical slices)

Each slice ends with ruff, mypy and pytest green and a commit. If time runs out, cut from the
bottom.

1. **Decide-rule fixes.** Guard order and superior-wins in `decide.py`, test-first. E14's outcome
   is unchanged and `outputs/eval/experiments.json` is byte-identical. This is the cheapest and
   most important correctness fix.
2. **Decision adapter.** The prompt is moved (fixture-pinned), plus the strict parser, the
   transport, the cache and the tracing. Contract tests with a fake transport.
3. **Hybrid and factory.** The merge table, the factory, and `classifier_model` validation. All
   three entry points use the factory. Parity is byte-identical with `gpt-oss-120b`.
4. **E16 registration and runner.** The registration text goes in `experiments_plan.yaml` without
   `approved_by`; `run_dev.py` gets E16; `decide.e16()`. **STOP: Luis approves the rule.** Only
   then run E16 live (cap USD 0.10) and commit its outcome.
5. **Shadow storage and stage.** The migration step, the store methods, the worker stage, the CLI
   flag, and parity with shadow on.
6. **Shadow read side.** `GET /receipts/{id}/shadow`, `epv shadow report` (with disposition
   impact), the OpenAPI regeneration and Postman.
7. **Runbook and notes.** quickstart verified, the prompt-log entry, AI_NOTES, and the
   MEJORAS-ITERACION-FINAL.md checkbox (outside git).

## Risks

- **The alpha endpoint changes or is withdrawn.** Mitigated by the strict parser, literal
  caching, and the factory keeping gpt-oss-120b one config value away.
- **jev answers differently on E16 than on 2026-10-11.** That is expected (non-deterministic). E16
  is the record; the 2026-10-11 numbers are only context.
- **The hybrid costs about USD 0.10 per 1,000 items, against USD 0.06.** Under the rule it wins
  only if superior. That is stated before running (`contracts/e16-rule.md`).
- **Shadow rows grow without limit.** Acceptable at this scale. Retention is out of scope and is
  noted for the AWS design.
- **Engine change creeping in.** If anything seems to need `domain/engine/`, stop and alert Luis.
