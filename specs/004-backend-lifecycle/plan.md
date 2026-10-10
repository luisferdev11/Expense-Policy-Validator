# Implementation Plan: Intake and lifecycle backend

**Branch**: `feat/004-backend-lifecycle` | **Date**: 2026-10-10 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/004-backend-lifecycle/spec.md`. The technical decisions
are in `docs/decisions/0007-backend-design.md` (D1 to D14) and `0006`; this plan follows them.

## Summary

Add a persist-first backend around the existing pipeline: an append-only event store with
projections and an outbox in SQLite; a FastAPI service (`epv serve`) and a separate worker
(`epv worker`); idempotent single and batch intake with revisions; stage-by-stage resume under
leased claims; cascade re-evaluation through the unchanged `build_context`; the lifecycle state
machine; four reviewer actions with `auditor_agreement` scores; and a Postman collection. The
engine, retriever, reporter and `epv run` do not change. The decision step of `run_pipeline` is
extracted into one function that both `epv run` and the worker call, so parity is by construction
(FR-016) and is proven by a test (SC-001).

## Technical Context

**Language/Version**: Python 3.12, managed with uv

**Primary Dependencies**: pydantic 2 (existing), FastAPI and uvicorn (new), stdlib `sqlite3`
(SQLite 3.53 in the project environment; 3.35 or later is required for `RETURNING`), langfuse
(existing, through the `Tracer` port); `httpx` in the dev group for FastAPI's `TestClient`

**Storage**: one SQLite file, `var/epv.sqlite3` (gitignored), WAL mode, schema version in
`PRAGMA user_version`

**Testing**: pytest. Test-first for every deterministic component (lifecycle, idempotency,
cascade, review rules, the store and the outbox against a temporary file, the service). Contract
tests for the HTTP API through `TestClient`. A crash is simulated in process with a classifier
that raises after N lines; a counting fake proves zero extra billed calls. No test spawns a
process. Smoke tests for `epv serve` and `epv worker --once`.

**Target Platform**: Linux, macOS; a single machine (the AWS mapping is documented in iteration 5)

**Project Type**: web service plus worker inside the existing layered package (ADR 0003)

**Performance Goals**: none stated beyond correctness. 32 receipts end to end in seconds with a
warm cache; the receipt count of the brief is the scale.

**Constraints**: the labels firewall; deterministic output identical to `epv run`; Langfuse never
gates a run; no change to engine decisions (alert Luis first); everything in English

**Scale/Scope**: tens to thousands of receipts on one SQLite file. The cascade loads only the
receipts that share a key with the one evaluated, so evaluation cost does not grow with the whole
store.

## Constitution Check

*GATE: passed before Phase 0 and re-checked after Phase 1.*

| Principle | Status | How |
|---|---|---|
| I. Labels are evaluation-only | Pass | Single entry through `parse_receipt_line`; hash and store on the stripped form; a test scans the database, responses and trace inputs (FR-009, FR-010). No code outside `eval/` names the answer keys; the architecture test stays green. |
| II. Deterministic decisions | Pass | The engine is untouched. A human category is a `Classification` with source `auditor`. Same input gives byte-identical output (parity test, SC-001, SC-008). |
| III. Policy text is the source of truth | Pass | No rule is added or changed; no receipt ID in code. |
| IV. Evidence or nothing | Pass | Exceptions come from the unchanged engine and reporter. |
| V. Decide on dev, report on test | Pass | No variant is compared in this iteration. |
| VI. Honest measurement | Pass | Every success criterion carries its N. |
| VII. Reproducibility | Pass | Worker classification goes through the existing cached OpenRouter adapter; results carry model, provider and prompt version as before. |
| VIII. Separation of components | Pass | New code follows the layers: pure `domain/`, `ports/`, `adapters/`, `app/`. The classifier input is unchanged. |
| IX. Secrets stay out | Pass | Keys stay in `.env`; the API never echoes configuration. |
| X. Observability | Pass | Every model call is traced through the existing adapter; one trace per receipt revision and evaluation version (D11); scores best effort. |
| XI. Iterative delivery | Pass | The store port is the seam to AWS and has one implementation; vertical slices, each green. |

No violations, so no Complexity Tracking entries.

**Deviation recorded after implementation (Principle X).** The constitution says one receipt is
one trace. The backend produces two traces per receipt revision, because classification and
decision happen at different times and in different processes: `app-r<revision>-c` for the
classification (the only one with model calls) and `app-r<revision>-v<version>` for each stored
evaluation version. Observation names are unchanged and verb-first, every model call is still a
`classify-item` generation, and Langfuse still never gates a run (tested: SC-006). The split is
what lets a re-evaluation or a reviewer's correction have its own trace without merging into the
first. If Luis prefers one trace per revision, the trace id seed is the only thing to change.

**Correction to ADR 0007 D2**: `adapters/` may not import `app/` (architecture test). The FastAPI
routes call the use-case services, so they live in `app/api/`, as the CLI does. ADR 0007 is
amended accordingly in the same change.

## Project Structure

### Documentation (this feature)

```text
specs/004-backend-lifecycle/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── api.md
├── checklists/requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
src/expense_validator/
├── domain/
│   ├── lifecycle.py        # states, transitions, allowed actions
│   ├── idempotency.py      # canonical form, content hash, default key
│   ├── events.py           # typed events
│   ├── cascade.py          # sharing keys, affected receipts
│   └── review.py           # reason codes, agreement, human classification
├── ports/
│   ├── store.py            # ReceiptStore and its transaction
│   └── tracer.py           # + score
├── adapters/
│   ├── sqlite_store.py     # schema, transactions, claims
│   └── tracing.py          # + score on the Langfuse and no-op tracers
└── app/
    ├── decide.py           # the decision step shared by epv run and the worker
    ├── service.py          # submit, batch, actions, retry
    ├── worker.py           # stages, claim loop, resume
    ├── api/                # FastAPI application, routes, schemas, errors
    └── cli.py              # + serve, worker

tests/
├── unit/                   # lifecycle, idempotency, cascade, review, store, service
├── contract/               # HTTP API
├── integration/            # parity, order independence, crash-resume, firewall scan
└── smoke/                  # serve and worker --once

docs/api/                   # Postman collection and environment
var/                        # SQLite file, gitignored
```

**Structure Decision**: extend the existing single package in its four layers. No new package and
no front end here (iteration 4).

## Delivery order (vertical slices)

Each slice ends with ruff, mypy and pytest green and a commit. If time runs out the product
stays coherent from the top of the list, so cut from the bottom.

0. **Refactor and housekeeping.** `app/decide.py` extracted; `outputs/results.jsonl` byte
   identical; dependencies added; `pyproject` bumped to 0.3.0.
1. **Intake.** Domain events, lifecycle, idempotency; the store; persist-first `POST /receipts`;
   `GET` endpoints. Postman requests for these.
2. **Worker and resume.** Outbox, leased claims, classify and evaluate stages, `failed` and retry,
   `epv worker`.
3. **Cascade and parity.** Affected set, context from the store, changed-result rule, the
   32-receipt parity test in several orders (the strongest demo).
4. **Revisions.** New revision rules (D5), old-and-new group re-evaluation.
5. **Reviewer actions.** Approve, reject, correct category, request information, escalate;
   stale-version check; `auditor_agreement`; dev-set candidate event.
6. **Batches.** `POST /batches`, per-row outcomes, summary, retry of failed items.
7. **Postman and polish.** Collection and environment, quickstart verified, README pointer, notes.

## Risks

- **Interim evaluation versions** in a batch, because a receipt can be evaluated before its
  partner is classified. Mitigated by D7 (no notice on untouched receipts) and by comparing only
  the final version in the parity test.
- **SQLite writer contention** between API and worker. Mitigated by WAL, `busy_timeout`, short
  transactions and `BEGIN IMMEDIATE` for every write.
- **Engine change creeping in.** Rule: if the cascade needs a change to `domain/engine/`, stop and
  alert Luis.
