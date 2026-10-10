# Research: Intake and lifecycle backend

Resolved before design. ADR 0007 holds the decisions; this file records the reasoning and the
alternatives.

## R1. Persistence: stdlib `sqlite3`, explicit transactions

- **Decision**: stdlib `sqlite3`, one connection per operation scope, `BEGIN IMMEDIATE` for every
  write, WAL, `busy_timeout`, `foreign_keys=ON`.
- **Rationale**: the data model is small and the invariants (event plus projection plus outbox in
  one commit) are easier to see in SQL than behind an ORM. `BEGIN IMMEDIATE` takes the write lock up
  front, so a read-modify-write (decide the next state from the current one) cannot interleave with
  another writer.
- **Alternatives**: SQLAlchemy (more dependency and indirection for ten tables); a JSONL event log
  (no atomic multi-record commit, no claim semantics); Postgres (a service to run, not needed to
  show the design).

## R2. Work queue: an outbox table with leases

- **Decision**: `outbox(stage, state, lease_until, attempts)`; a claim is
  `UPDATE ... SET state='claimed', lease_until=? WHERE id=(SELECT ... LIMIT 1) RETURNING *`. An
  expired lease is claimable again. Stages are `classify` and `evaluate`.
- **Rationale**: the same row that is written in the submit transaction is the work item, so there
  is no window in which a receipt is stored but not queued. The lease is the crash recovery.
- **Alternatives**: an in-process queue (lost on a crash); a message broker (a service for a demo);
  polling the `receipts` projection for unfinished states (works, but mixes read model and queue
  and makes contention harder to reason about).

## R3. Resume: an event per stage, classification from the cache

- **Decision**: the classify stage stores the receipt's `Classification` list (one row per
  revision) and emits `ReceiptClassified` in the same transaction that marks the work done. The
  model call itself is idempotent through the existing cache keyed by request, model, endpoint and
  prompt.
- **Rationale**: a crash between a billed call and the commit repeats the call, which the cache
  answers for free; a crash after the commit never repeats it. Zero extra billed calls follow from
  the cache, not from fragile bookkeeping.
- **Note**: the cache file is written by the classifier when dirty; the worker saves it after each
  receipt, so a billed answer is not lost on a crash after the call.

## R4. Cascade: sharing keys, group-limited context

- **Decision**: a receipt's sharing keys are `day:<employee_id>|<date>` (built with the engine's own
  `day_key`) and `trip:<trip_id>`. They are stored per revision in `receipt_keys`. When classification
  completes, the worker enqueues `evaluate` for the receipt and for every receipt whose current
  revision shares a key (the union of old and new keys for a revision). `evaluate` loads the
  classified receipts that share a key with the one being evaluated and calls `build_context` on that
  set.
- **Rationale**: the context entries the rules read for a receipt are exactly those under that
  receipt's own keys, so a group-limited context gives the same result as a global one and the
  parity test proves it. The keys are a superset of what the context actually uses (a receipt that is
  not a meal still shares a day key); a superset is safe because an unchanged result records nothing
  (D7).
- **Alternative**: rebuild the context over the whole store on every evaluation. Simpler, obviously
  correct, but quadratic; rejected once the key table was needed anyway for the affected set.

## R5. Changed-result comparison

- **Decision**: canonical JSON (sorted keys) of `disposition`, `exceptions` and `review_signals`,
  hashed and stored on each evaluation row. A new evaluation is compared with the latest one for the
  same revision.
- **Rationale**: a cheap, exact comparison with no float or ordering ambiguity, because the engine
  output is already deterministic and ordered.

## R6. Canonical form for the idempotency hash

- **Decision**: the stripped `ReceiptInput` dumped in JSON mode, with Decimals normalised
  (`1.0` and `1.00` are the same number) and keys sorted, then SHA-256.
- **Rationale**: the same business content must hash the same however the client formatted it. The
  existing `run_id` hash (iteration 2.1) is a different concern (a file name) and is left alone.

## R7. HTTP framework

- **Decision**: FastAPI with Pydantic models for requests and responses, served by uvicorn.
  Dependencies (store, clock, service) are injected through FastAPI's dependency system so tests
  override them.
- **Rationale**: Pydantic is already the model layer; FastAPI gives validation, error shaping and an
  OpenAPI document for free, which feeds the Postman collection and iteration 4's front end.
- **Alternatives**: Flask (no native Pydantic validation), a bare ASGI app (reinvents validation).

## R8. Clock and ids

- **Decision**: a `Clock` callable injected everywhere time matters (leases, events, `created_at`).
  Batch ids are `bat_` plus a short hash of the batch's canonical content and submission time; event
  order is the `events.seq` autoincrement, never a timestamp.
- **Rationale**: tests control time; ordering never depends on clock resolution.

## R9. Scores

- **Decision**: add `score(trace_label, receipt_id, name, value, comment)` to the `Tracer` port, with
  the Langfuse implementation creating a score on the deterministic trace id, and the no-op and
  guarded tracers inheriting the no-op behaviour. The score is also stored in the action's event.
- **Rationale**: Langfuse never gates; the committed side keeps the fact either way.

## R10. Not resolved here on purpose

- Authentication and notification delivery (spec Assumptions).
- AWS mapping and failure cases (iteration 5).
