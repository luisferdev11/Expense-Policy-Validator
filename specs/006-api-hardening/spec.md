# Feature Specification: API hardening

**Feature Branch**: `feat/006-api-hardening`

**Created**: 2026-10-12

**Status**: Draft

**Release**: v1.1.0 (iteration 6)

**Input**: Luis's list for the last iteration (translated): "good cache handling, think about how to
do it properly; a load test, run it and keep it ready to run whenever we want; implement
`created_at`; type `receipt` and `result` in OpenAPI; `decided_by` and `decided_at`, the same as
`created_at`." Chosen from `MEJORAS-ITERACION-FINAL.md`.

## Context

Iteration 3 (v0.3.0) built the intake and lifecycle backend and iteration 4 (v0.4.0) a front end on
top of it. Working against it showed five gaps:

- **The answer cache is a file rewritten whole on every billed call.** Two processes that share it
  lose each other's entries (AI_NOTES 40, ADR 0007 amendment 2), so only one worker can run per
  cache file, and the budget guard counts everything ever cached instead of what this process spent.
- **A receipt has no creation time**, only `updated_at`, and `updated_at` is written in a different
  text format from every other timestamp in the store, so sorting across columns is unsafe.
- **Who decided a receipt, and when, is only in the event trail.** The queue would have to read every
  receipt's events to show it (the N+1 the front end reported as F-09).
- **`receipt` and `result` are untyped objects in OpenAPI**, so the front end writes their types by
  hand from the Python models and nothing checks that they agree.
- **Performance was never measured.** `docs/aws.md` sizes the service for 100,000 receipts a day
  (1.2 a second on average, about 12 at a 10× peak) by arithmetic only.

The constitution frames the work:

- **Deterministic decisions (Principle II).** The policy engine, the retriever and the disposition
  logic do not change. The 32 receipts through the backend still equal `epv run` byte for byte.
- **Honest measurement (Principle VI).** Every load-test figure is reported with its N, the machine
  and the commit, and is reproducible with one command.
- **Reproducibility (Principle VII).** The committed `outputs/classifications.jsonl` stays the way to
  re-run everything with no key and no model call; the cache table is seeded from it and can export it
  back byte for byte.
- **Separation of components (Principle VIII).** The cache gets a port; the SQLite table and the
  committed file are two adapters behind it. Domain code stays pure.
- **Observability (Principle X).** No model call becomes invisible; a load test that uses the real
  model is traced like any other run; a simulated classifier makes no model call.
- **Iterative delivery (Principle XI).** Five independent slices, each green and committed.

## Clarifications

### Session 2026-10-12

- Q: How should the classification cache be stored? → A: A table in the store's own database
  (`classification_cache`), behind a port. The committed `outputs/classifications.jsonl` stays as
  the seed and as an export: `epv cache export` regenerates it byte for byte. The budget counts what
  a process spent, not the whole history.
- Q: What does `created_at` of a receipt mean? → A: When revision 1 was received. It never changes.
  Each revision keeps its own `created_at`; `updated_at` stays the time of the last change. Existing
  receipts get it from their first revision, and `updated_at` is normalised at the same time.
- Q: What counts as a decision for `decided_by` and `decided_at`? → A: The latest human approve or
  reject on the current revision, and only while the state is `approved` or `rejected`. An
  `auto_approved` receipt shows `decided_by: "system"` with the time of that evaluation. Any reopening
  (a new revision, or a re-evaluation that returns the receipt to review) sets both to null.
- Q: Which load-testing tool? → A: Locust, as a dev dependency, against the API and the worker with a
  simulated classifier by default; an optional live profile with a spending cap.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run several workers on one answer cache (Priority: P1)

An operator runs two or more workers against the same database to drain a large batch faster. Every
billed answer is kept, no worker overwrites another's, and a line answered once is never paid for
again by any worker. The committed classification file still lets anyone re-run everything offline.

**Why this priority**: it removes the one-worker-per-file limit that blocks scaling (AI_NOTES 40)
and is the base the jev adapter (spec 007) and the load test build on.

**Independent Test**: start two workers on one fresh database with a counting fake classifier;
submit receipts whose lines overlap; verify every line's answer is stored once, the total number of
billed calls equals the number of distinct lines, and `epv cache export` of the seeded database
equals `outputs/classifications.jsonl` byte for byte.

**Acceptance Scenarios**:

1. **Given** a database with an empty cache table, **When** the API or a worker opens it, **Then**
   the table is seeded once from `outputs/classifications.jsonl` and the 32 receipts can be processed
   offline with zero billed calls.
2. **Given** two workers that classify the same new line at the same time, **When** both store an
   answer, **Then** exactly one row exists for that key, the first stored answer is kept, and both
   receipts use the same answer on any later replay.
3. **Given** a worker killed right after a billed call, **When** the work resumes, **Then** the answer
   is already in the table and no second billed call is made.
4. **Given** a seeded database, **When** `epv cache export` runs, **Then** its output is a JSONL
   sorted by key that equals the committed file when no new answer was added.
5. **Given** a process whose billed spend reaches the cap, **When** it meets an uncached line, **Then**
   that line is refused with `budget_refused`, while answers already cached, including those seeded
   from the committed file, never count against the cap.

---

### User Story 2 - Know when a receipt arrived (Priority: P1)

An auditor sorts the queue by age to work the oldest cases first. Every receipt shows when it was
first received, which does not move when the employee sends a correction, and all timestamps sort
correctly.

**Why this priority**: the queue's first useful order, asked for by Luis and by the front end
(F-01); cheap once the migration exists.

**Independent Test**: submit `R`, then a revision of `R` a minute later (injected clock); verify
`created_at` equals the first submission's time on both reads, `updated_at` moved, and
`GET /receipts?order=created_at` returns receipts oldest first.

**Acceptance Scenarios**:

1. **Given** a new receipt, **When** it is submitted, **Then** its summary and detail show
   `created_at` equal to revision 1's `created_at`.
2. **Given** revision 2 of `R` arrives later, **When** `R` is read, **Then** `created_at` is still
   revision 1's time, the revision detail of revision 2 shows its own time, and `updated_at` is
   revision 2's time.
3. **Given** a database created by v0.3.0 or v0.4.0, **When** the new version opens it, **Then** every
   receipt gets `created_at` from its first revision and every `updated_at` is rewritten in the store's
   single timestamp format.
4. **Given** receipts created at different times, **When** the list is requested with
   `order=created_at` or `order=updated_at`, **Then** it is ordered by that time, ties broken by
   `receipt_id`; without `order` the existing order by `receipt_id` is kept.
5. **Given** a batch, **When** it is read, **Then** it shows the time it was received.

---

### User Story 3 - See who decided a receipt, and when (Priority: P2)

A reviewer looking at the queue or at a receipt sees who approved or rejected it and when, without
opening its history. If the receipt reopens, the old decision disappears from the summary and stays
in the trail.

**Why this priority**: the front end needs it to show closed work without one request per row
(F-09); it depends on the migration of Story 2.

**Independent Test**: approve a receipt in review as `alice`; verify `decided_by` and `decided_at` on
the summary and detail; submit a revision; verify both are null and the approval is still in the
events.

**Acceptance Scenarios**:

1. **Given** a receipt in `in_review` or `compliance`, **When** a reviewer approves or rejects it,
   **Then** `decided_by` is the reviewer's actor and `decided_at` the action's time, on the summary,
   the detail and the list.
2. **Given** an evaluation that leaves a receipt `auto_approved`, **When** it is read, **Then**
   `decided_by` is `"system"` and `decided_at` is that evaluation's time.
3. **Given** an `auto_approved` receipt that a reviewer rejects, **When** it is read, **Then**
   `decided_by` is the reviewer and `decided_at` the time of the rejection.
4. **Given** a decided receipt, **When** a new revision arrives, or a re-evaluation returns it to
   review, or a reviewer requests information or escalates, **Then** `decided_by` and `decided_at`
   are null and the earlier decision is still in the events.
5. **Given** a database from v0.4.0 with decided receipts, **When** it is migrated, **Then** each
   receipt in `approved` or `rejected` gets its decision from its latest approve or reject event on
   the current revision, each `auto_approved` one gets `"system"` and its latest evaluation's time,
   and every other receipt gets null.

---

### User Story 4 - Generate the front end's types from the API (Priority: P2)

A front-end developer regenerates the TypeScript types from `docs/api/openapi.json` and gets the
real shape of `receipt` and `result`, instead of writing it by hand. A backend change that drops or
renames a nested field breaks the front end's check before a screen breaks.

**Why this priority**: removes a hand-maintained copy of two models; the guided intake form
(spec 008) builds on the generated types.

**Independent Test**: regenerate the OpenAPI document and the TypeScript types; verify the
document's `ReceiptDetail.receipt` refers to a `ReceiptInput` schema and `result` to a
`ReceiptResult` schema with every field of the Python models, and that `npm test` fails when the
generated file is stale.

**Acceptance Scenarios**:

1. **Given** the OpenAPI document, **When** it is read, **Then** `receipt` in the detail, the action
   response and the revision detail, and `result` in the detail, the action response and each
   evaluation item, refer to named schemas whose properties match the Python models field for field.
2. **Given** money fields, **When** they appear in a response schema, **Then** they are strings, as
   they are on the wire.
3. **Given** `POST /receipts`, **When** its request body is read in the document, **Then** it refers
   to the receipt input schema, and the endpoint still reads the raw body so no precision is lost.
4. **Given** the generated TypeScript file, **When** the OpenAPI document changes and the file is not
   regenerated, **Then** the front end's tests fail with a message naming the command to run.
5. **Given** the committed `specs/001-mvp-end-to-end/contracts/receipt-result.schema.json`, **When**
   the API's `ReceiptResult` schema is compared with it, **Then** they have the same property names.

---

### User Story 5 - Measure the service under load, on demand (Priority: P2)

Luis or the panel runs one command and gets a report of how the API and the worker behave at the
average and peak rates of the AWS design: latency percentiles per endpoint, throughput, errors and
how long the worker takes to drain the queue, each with its N. The run costs nothing unless the live
profile is chosen.

**Why this priority**: the only performance figures today are derived on paper; the report backs or
corrects them. It depends on nothing else and can be cut first.

**Independent Test**: run the `smoke` profile against a fresh database with the simulated classifier;
verify the report is written with every section filled and that no model call was made.

**Acceptance Scenarios**:

1. **Given** the API and a worker started with the simulated classifier, **When** the `smoke` profile
   runs, **Then** a report is written under `docs/perf/` with p50, p95 and p99 latency per endpoint,
   requests per second, error counts, the queue drain time and the N of every figure.
2. **Given** the `nominal` profile (1.2 receipts a second) and the `peak` profile (12 receipts a
   second), **When** each runs, **Then** each report states whether the worker kept up, and the
   largest backlog seen.
3. **Given** the load test, **When** it generates receipts, **Then** they come from the committed
   sample template with unique identifiers per run, and `data/receipts.jsonl` is never read.
4. **Given** the `live` profile, **When** it runs, **Then** it calls the real model, stops at its
   spending cap, and every call is traced.
5. **Given** any profile, **When** a threshold is exceeded, **Then** the report says so, and the run
   does not fail a build: the figures are information.

---

### Edge Cases

- A database created by v0.3.0 or v0.4.0 (schema 1) is opened: it is migrated to schema 2 in one
  transaction; a failure leaves schema 1 untouched. A database newer than the code is still refused.
- A receipt whose revision 1 row is missing (impossible by construction, but a hand edit): its
  `created_at` is the earliest revision present, and the migration reports the receipt in its log.
  A receipt with no revision at all stops the migration, and the database stays at schema 1.
- Two workers race on the same cache key: the first insert wins; the second's answer is not stored,
  and the second worker returns the stored answer for its line, so both receipts see the same one.
- A naive time value reaches the timestamp helper: it is treated as UTC.
- A cached answer from the committed file has a cost: it does not count towards the process budget.
- In `--offline` mode a line missing from the table is still `offline_cache_miss` and never billed.
- An `updated_at` written by v0.4.0 has no microseconds (`2026-10-11T10:00:00+00:00`): the migration
  rewrites it to the fixed-width form (`2026-10-11T10:00:00.000000+00:00`).
- An `auto_approved` receipt rejected by a reviewer and then re-evaluated with a changed result: it
  returns to review (ADR 0007 D7) and its decision fields become null.
- `decided_by` for a receipt approved by a reviewer whose actor text looks like `system`: it is shown
  as written; the system decision is recognised by the state, not by the text.
- Decimal fields in a response schema: shown as strings, never as numbers.
- The load test runs against a database that already holds receipts: generated identifiers carry a
  run id, so nothing collides and an earlier run's receipts are left alone.
- The simulated classifier answers every line with a fixed category and confidence: results are
  meaningless for policy and are not compared with any answer; the load test only measures timing.

## Requirements *(mandatory)*

### Functional Requirements

**Schema migration**

- **FR-001**: The store MUST migrate a database from any older schema version to the current one by
  applying ordered steps in one transaction, and MUST record the new version only when every step
  succeeded.
- **FR-002**: A fresh database MUST be created at the current schema version directly, and a database
  newer than the code MUST still be refused with a clear message.
- **FR-003**: `GET /health` MUST report the schema version after migration and the number of open
  work items (pending or claimed), so a load test can tell when the worker has drained the queue.

**Classification cache**

- **FR-004**: The application MUST store classification answers behind a cache port with two
  adapters: a table in the store's database, used by the API and the worker, and the committed JSONL
  file, used by `epv run`, uploads and the dev runner.
- **FR-005**: Storing an answer MUST be idempotent and first-writer-wins for a key, and MUST write only
  that row, never rewrite the cache.
- **FR-006**: A database whose cache table is empty MUST be seeded from `outputs/classifications.jsonl`
  when it is opened by the API or a worker, once.
- **FR-007**: `epv cache export` MUST write the table as JSONL sorted by key, byte-identical to the
  committed file when the table holds only the seeded rows.
- **FR-008**: The budget guard MUST compare the cap with what the current process has billed, and MUST
  NOT count answers that were already cached or seeded.
- **FR-009**: The cache key MUST keep its current composition, so every committed answer stays a hit.
- **FR-010**: Several workers on one database MUST be able to classify at the same time without losing
  an answer and without paying twice for a line already stored.

**Receipt creation time**

- **FR-011**: Every receipt summary and detail MUST include `created_at`, the time revision 1 was
  stored, which MUST NOT change afterwards.
- **FR-012**: Every timestamp the store writes, `updated_at` included, MUST use one fixed-width UTC
  text format, and the migration MUST rewrite existing values to it.
- **FR-013**: `GET /receipts` MUST accept `order` with the values `receipt_id` (the default),
  `created_at` and `updated_at`, ascending, ties broken by `receipt_id`.
- **FR-014**: A batch response MUST include the time the batch was received.

**Decision attribution**

- **FR-015**: Every receipt summary and detail MUST include `decided_by` and `decided_at`.
- **FR-016**: An approve or reject action MUST set them to the actor and the time of the action, in the
  same transaction as the action's event.
- **FR-017**: An evaluation that moves a receipt to `auto_approved` MUST set them to `"system"` and the
  evaluation's time.
- **FR-018**: Any change that leaves a receipt outside `approved`, `rejected` and `auto_approved` (a new
  revision, a re-evaluation into review, a correction, a request for information, an escalation, a
  failure before evaluation) MUST set them to null. The events MUST keep every earlier decision.
- **FR-019**: The rule that maps a state change to the decision fields MUST be a pure domain function
  with its own tests.
- **FR-020**: The migration MUST backfill the decision fields of existing receipts from their events,
  following FR-016 to FR-018.

**Typed API contract**

- **FR-021**: The OpenAPI document MUST describe `receipt` and `result` (in the detail, the action
  response, the revision detail and the evaluation items) with named schemas generated from the domain
  models, in serialization mode, so money is a string.
- **FR-022**: The OpenAPI document MUST describe the `POST /receipts` body with the receipt input
  schema, while the endpoint keeps reading the raw body.
- **FR-023**: The front end MUST generate its TypeScript types from the committed OpenAPI document with
  a pinned generator, and MUST fail its tests when the generated file is stale.
- **FR-024**: A test MUST compare the API's result schema with the committed result schema of spec 001
  property by property.
- **FR-025**: The committed OpenAPI document and the Postman collection MUST be regenerated and MUST
  cover the new fields.

**Load test**

- **FR-026**: A load test MUST exercise submit (with and without an idempotency key), batch submit,
  queue listing ordered by `updated_at`, receipt detail and an approve action, and MUST measure the
  worker's queue drain time.
- **FR-027**: The API and the worker MUST accept a choice of classifier (`openrouter`, the default;
  `keyword`; `simulated`, a fixed answer), an optional simulated latency per line, and a spending cap
  in USD for the process (`--cap-usd`, default 1.00), so a run measures the system without billed
  calls, or with a bounded bill.
- **FR-028**: The load test MUST offer the profiles `smoke` (no simulated latency), `nominal`
  (1.2 receipts a second), `peak` (12 receipts a second) and `live` (real model, started with
  `--cap-usd 0.25`).
- **FR-029**: One command MUST turn a run's raw output into a report under `docs/perf/` with latency
  percentiles per endpoint, throughput, errors, drain time, the largest backlog, the machine, the
  commit and the N of each figure. The raw output MUST be committed with the report.
- **FR-030**: The load test MUST generate receipts from `docs/samples/receipt-one.json` with unique
  identifiers per run and employee identifiers prefixed `TEST-`, and MUST NOT read
  `data/receipts.jsonl`.
- **FR-030a**: The load test MUST judge the queue only through `GET /health` (`open_work`): the peak
  backlog is the largest value sampled during the run and the drain time is the time from the end of
  the load until it reaches 0.

**Invariants**

- **FR-031**: The policy engine's decisions MUST NOT change. The 32 receipts through the backend MUST
  still equal `epv run`, and `epv run --offline` MUST still regenerate `outputs/results.jsonl` byte
  for byte. Any proposed engine change MUST be raised with Luis first.
- **FR-032**: Answer keys MUST NOT reach the cache table, the load-test data, a report or a trace.
- **FR-033**: Langfuse MUST NOT gate any run, including a load test.

### Key Entities

- **Cache entry**: one model answer kept literally, identified by a key over the cleaned description,
  merchant, MCC, model, endpoint and prompt version; first written wins.
- **Receipt (projection)**: gains `created_at`, `decided_by` and `decided_at`.
- **Schema version**: the integer that says which migration steps a database has had.
- **Load profile**: a named rate, duration and user count, with its classifier mode.
- **Load report**: the figures of one run with their N, the machine and the commit.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Two workers draining the 32 receipts on one fresh database, offline, make zero billed
  calls and produce results equal to `outputs/results.jsonl` for 32 of 32 receipts (N = 32).
- **SC-002**: With a counting fake classifier, two workers on 20 receipts sharing 10 distinct new
  lines make exactly 10 billed calls and store exactly 10 new cache rows (N = 20 receipts, 10 lines).
- **SC-003**: `epv cache export` of a freshly seeded database equals the committed
  `outputs/classifications.jsonl` byte for byte (N = 78 rows).
- **SC-004**: A schema-1 database fixture with 5 receipts (R-A in review; R-B revised, in review;
  R-C approved by a reviewer; R-D auto-approved; R-E auto-approved and then rejected by a reviewer)
  migrates to schema 2 with the expected `created_at`, `updated_at` format and decision fields on 5 of
  5 receipts.
- **SC-005**: For each of the 8 transitions of User Story 3 (approve, reject, auto-approve, reject
  after auto-approve, new revision, re-evaluation into review, request-info, escalate), the decision
  fields match the rule (N = 8 cases).
- **SC-005a**: OpenAPI exposes the components `ReceiptInput`, `LineItemInput`, `ReceiptResult`,
  `ReceiptInputRequest` and `LineItemInputRequest`, and each `*Request` schema differs from its
  response counterpart (N = 5 names, 2 pairs).
- **SC-006**: The API's `ReceiptInput` and `ReceiptResult` schemas have 100% of the Python models'
  fields, and the result schema equals the spec 001 contract's property names (N = every field).
- **SC-007**: The Newman run of the regenerated Postman collection passes every assertion on a fresh
  instance (N = every request).
- **SC-008**: The `smoke` profile produces a complete report in under 2 minutes with zero model calls;
  the `nominal` and `peak` reports are committed with their N.
- **SC-009**: `epv run --offline` regenerates `outputs/results.jsonl` byte-identical, and the
  32-receipt parity test passes in every order (N = 32 receipts × 5 orders).
- **SC-010**: The test suite, ruff and mypy pass before every commit; no file under
  `src/expense_validator/domain/engine/` changes.

## Assumptions

- The database stays SQLite in this iteration; the migration steps are written so the PostgreSQL
  adapter of ADR 0009 can apply the same logical changes later.
- `"system"` is already the actor the service writes for its own events (`app/service.py:43`), so
  `decided_by: "system"` uses an existing name. The worker writes its events as `"worker"`; the
  decision field says `"system"` because the decision belongs to the system, not to one process.
- The load test runs on one developer machine; its figures describe that machine with SQLite, not
  the AWS design, and the report says so.
- The simulated classifier is a test double exposed through the CLI; it never runs in a deployment.
- The front end consumes the generated types in this iteration only where it already used the
  hand-written `Receipt` and `Result`; other screens keep their types.

## Out of scope

- The translator's cache (experiment E5 lost; nothing reads it in the product).
- Typing event payloads in OpenAPI (`EventItem.payload` stays an object).
- Authentication and roles (spec 009, ADR 0010).
- The PostgreSQL adapter (ADR 0009 says it comes with the AWS work).
- Adding the reasoning effort, temperature or schema to the cache key (research R2).
- The jev adapter and shadow mode (spec 007), which reuse the cache port built here.
