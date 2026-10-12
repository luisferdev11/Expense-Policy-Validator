# ADR 0007: Backend design for iteration 3

- **Status:** proposed, implemented in iteration 3, pending Luis's review in the pull request
- **Date:** 2026-10-10
- **Decided by:** Claude (proposal). Luis has not yet decided these. The technical choices follow
  from ADR 0006 and the architecture. The **product decisions** below are Claude's proposals and
  need Luis's confirmation: reopening a closed receipt when a new revision arrives (D5), the notice
  rules (D7), the allowed actions and reason codes (D8), the agreement table (D10) and the
  quality-review sample of one in ten (D12).
- **Builds on:** ADR 0003 (layers), ADR 0006 (intake, idempotency and lifecycle)

## Context

ADR 0006 fixes what the backend does. It leaves open how: the storage shape, the API, what an
idempotency key means when the body differs, what a revision does to a receipt that is already
under review or closed, what counts as a changed result, how a human category enters the engine,
and where an agreement score attaches. This ADR closes those questions before any code is written.
Nothing here changes a policy decision or the engine.

## Decisions

### D1. Storage: stdlib `sqlite3`, no ORM

- One file, `var/epv.sqlite3` (override with `EPV_DB`), under a gitignored `var/`.
- WAL mode, `busy_timeout`, `foreign_keys=ON`, and `PRAGMA user_version` as the schema version. A
  newer schema than the code knows is refused at start.
- **One transaction per command.** The event, the projection update and the outbox row commit
  together or not at all. That is what makes the outbox an outbox.
- The work queue is claimed with `UPDATE ... RETURNING` (SQLite 3.35 or later, checked at start),
  so two workers never hold the same row. A claim sets `lease_until`; an expired lease makes the
  row claimable again.
- The clock is injected, so lease expiry is tested without sleeping.
- Tables: `submissions` (idempotency key to receipt and revision), `receipts` (projection),
  `revisions` (immutable stripped content), `events` (append-only, the source of truth),
  `evaluations` (versioned findings), `outbox`, `batches` and `batch_items`.
- A `ReceiptStore` port in `ports/` describes the operations the use cases need; the SQLite
  implementation lives in `adapters/`. Only one implementation exists. The port is the seam to
  DynamoDB and SQS on AWS, not a speculative abstraction (constitution XI).

### D2. Layering of the new code (ADR 0003)

| Layer | New modules |
|---|---|
| `domain/` (pure) | `lifecycle.py` (states, transitions, allowed actions), `idempotency.py` (key and canonical hash), `events.py` (typed events), `cascade.py` (affected set), `review.py` (reason codes, agreement rule, human classification) |
| `ports/` | `store.py` (`ReceiptStore`), `Tracer` gains `score` |
| `adapters/` | `sqlite_store.py` |
| `app/` | `service.py` (submit, batch, actions), `worker.py` (stages), `decide.py` (the decision step shared with `epv run`), `api/` (FastAPI routes and schemas) |

The HTTP routes call the use-case services, and adapters may not import `app/` (architecture
test), so they live in `app/api/`, like the CLI.

`app/decide.py` extracts the loop body of `run_pipeline` (retrieve, apply, report). `epv run` and
the worker both call it, so the two cannot diverge. `outputs/results.jsonl` stays byte-identical.

### D3. API

| Method and path | Purpose |
|---|---|
| `POST /receipts` | Submit one receipt. Optional `Idempotency-Key` header. |
| `POST /batches` | Submit JSONL or a JSON array. Per-row outcome. |
| `GET /batches/{id}` | Counts per state and the item list. |
| `GET /receipts` | List, filter by `state`, `disposition` or `batch`. |
| `GET /receipts/{id}` | Current state, current revision, latest evaluation. |
| `GET /receipts/{id}/events` | The full event trail. |
| `GET /receipts/{id}/revisions/{n}` | One revision and its evaluation versions. |
| `POST /receipts/{id}/retry` | Retry a `failed` receipt from the failed stage. |
| `POST /receipts/{id}/actions/{action}` | `approve`, `reject`, `correct-category`, `request-info`, `escalate`. |
| `GET /health` | Liveness and schema version. |

Status codes: `202` accepted (new receipt or new revision), `200` existing (repeat), `207` for a
batch with mixed outcomes, `409` stale action or action not allowed in the current state, `422`
invalid body or idempotency key reuse with a different body. Every response carries the stripped
receipt only (rule 1). Errors use one shape: `{"error": {"code", "message", "details"}}`.

### D4. Idempotency key reuse with a different body: 422

A client key that was used before with different content is rejected with `422` and changes
nothing. This follows the IETF idempotency-key draft. It differs from the case with no client
key: the same `receipt_id` with different content is a **new revision** (ADR 0006, decision 3),
because that is how an employee corrects a receipt. The hash is computed on the stripped
canonical form, so the same receipt with or without answer keys is the same receipt.

### D5. A revision arriving while the receipt is in some state

A new revision always becomes the current one and always restarts the lifecycle at `submitted`.
The previous revision stays in the trail with its decisions, marked `superseded`.

| State of the previous revision | What happens |
|---|---|
| `submitted`, `classifying` | Pending work for the old revision is cancelled; the new revision is queued. |
| `evaluated`, `auto_approved`, `in_review`, `compliance` | Superseded; the new revision is evaluated from scratch. |
| `needs_info` | The expected path: the resubmission is the answer. |
| `approved`, `rejected` | Superseded and reopened: a decision about different content cannot stand. The earlier decision stays visible in the trail. |

If the revision changes the employee, date or trip, both the old and the new group are
re-evaluated (D6).

### D6. Cascade and the affected set

`build_context` is used unchanged, over the latest classified revision of every receipt in the
store. When a receipt finishes classification (or is corrected), the worker enqueues an
`evaluate` for it and for every other receipt that shares a key with it, where the keys are the
employee-date (MEAL-01, REG-02, REG-03) and the trip (HEALTH-01). For a revision, the keys are
the union of the old and the new revision's keys. Each `evaluate` rebuilds the context from the
store when it runs, so the result at rest does not depend on arrival order. A receipt evaluated
before its partner was classified is evaluated again when the partner lands. The pure function
`affected_receipts(store_view, receipt)` lives in `domain/cascade.py` and is tested on its own.

If implementing this needs a change to `domain/engine/context.py`, that is an engine change and
Luis is alerted first.

### D7. What counts as a changed result

An evaluation is compared with the previous one for the same revision by the canonical JSON of
`(disposition, exceptions, review_signals)`. Equal: nothing is recorded. Different: a new
evaluation version is stored and the earlier one stays. The receipt then behaves as follows.

| Receipt before | After a changed result |
|---|---|
| Untouched in the queue (`evaluated`, `in_review`, `compliance`) | The proposal is updated silently; the trail shows both versions. |
| `auto_approved` (an engine proposal) | Follows the new disposition: `pass` stays approved; `review` or `flag` moves to `in_review`, with a notice. |
| Acted on by a human (`approved`, `rejected`, `needs_info`, or any receipt with a reviewer action) | Returns to `in_review` with a notice "result changed after your decision". The decision stays in the trail. |

The notice is a flag on the projection, cleared by the next reviewer action. Notification delivery
is out of scope.

### D8. Reviewer actions

- **Stale actions.** Every action carries the `evaluation_version` the reviewer saw. A different
  current version gives `409` with the current one.
- **Reason codes** (a closed list): `policy_exception_granted`, `engine_false_positive`,
  `engine_missed_issue`, `documentation_provided`, `other` (a note is then required). Required
  when the decision overrides the proposal: approving a `flag`, or rejecting a `pass`.
- **Allowed actions by state.** Approve, reject, correct a category, request information and
  escalate need `in_review` or `compliance`, except that escalate needs `in_review`, and reject
  is also allowed from `needs_info` (a request that is never answered). A receipt in
  `auto_approved` may be rejected (an override, so a reason code is required) or sampled for
  quality review. Anything else gives `409`.
- **Actor.** Free text recorded in the event; there is no authentication in this iteration.

### D9. A human category is an ordinary classification

`correct-category` stores an event, then the next `evaluate` builds the line's `Classification` as:
`status=classified`, the human `category`, `restricted` from the taxonomy, `confidence=1.0`,
`subtype` and recipient fields kept from the model's classification when the category is still
`other` and reset to `none` otherwise, and a `ClassificationSource` with `classifier="auditor"`,
`model_id="human"`, `prompt_version="n/a"` and a cache key of the form
`auditor:<receipt_id>:<revision>:<line_id>:<n>`. The engine reads only these fields, so it does
not change and the result is deterministic. The correction applies to that revision in every
later evaluation, including cascades. The line is recorded as a dev-set candidate
(`DevCandidateMarked`: receipt, line, original category, human category). That is an output of
the product, not a read of the answer keys.

### D10. Agreement score

One Langfuse score named `auditor_agreement` (numeric, 0 or 1) per reviewer action, on the decision
trace of the evaluation version the action was based on, with the action and reason code in the
comment. It never contains labels or free text from the receipt.

| Action | 1 when | 0 when |
|---|---|---|
| Approve | proposal was `pass` or `review` | proposal was `flag` |
| Reject | proposal was `flag` or `review` | proposal was `pass` |
| Correct a category | never | always (the reviewer disagreed with the classifier) |
| Request information, escalate | proposal was `review` or `flag` | proposal was `pass` |

Scores are best effort: a Langfuse failure never fails the action. The score is also kept in the
event payload, so the committed side does not depend on Langfuse.

### D11. Trace identity

**One receipt revision is one trace** (constitution X). The trace id is
`trace_id_for(run_label, receipt_id)` with `run_label = "app-r<revision>"`. The classification of
the revision is its `validate-receipt` observation, and every stored evaluation version is a
`decide-receipt` observation in the same trace, with `metadata.evaluation_version` telling them
apart, as the batch run does with its two top-level observations. A new revision is a new trace.
The `Tracer` port gains `score(trace_label, receipt_id, name, value, comment)`, guarded like the
other methods. (The first implementation used `app-r<revision>-c` and `app-r<revision>-v<n>`, which
made two traces per revision against the constitution; amendment 8 records the change.)

### D12. Quality-review sample

A receipt in `auto_approved` is flagged `qa_sample` when `sha256(receipt_id:revision)` modulo 10
is 0: deterministic, about 10%, reproducible, no randomness. The sampling rate is a named
setting, not a policy decision. The quality-review screen belongs to iteration 4.

### D13. Processes

- `epv serve` runs the API. `epv serve --with-worker` also runs a worker thread, for demos.
- `epv worker` polls the outbox. `epv worker --once` drains it and exits, which tests and CI use.
- The worker is built with an injected classifier, tracer, clock and store, so the contract tests
  use a counting fake classifier and a classifier that raises after N lines to simulate a crash.
  No test spawns a subprocess.
- The worker classifier uses the gitignored cache seeded from the committed one (as in 2.1).

### D14. Labels firewall in the backend

The only entry to the store is `parse_receipt_line` (or its dict equivalent). The stored
`revisions.content` is the stripped receipt; the idempotency hash is computed on it. A test
submits the 32 receipts through the API using the same stripping path as `epv run`, then scans
the database, every endpoint's response and the trace inputs for the answer keys.

## Amendments made during implementation (2026-10-10)

Each one refines a decision above after the code or a test showed a gap. None changes the engine.

1. **D1, the outbox index covers only `pending` items.** With `pending` and `claimed` covered, a
   cascade that queued an `evaluate` while that receipt's evaluation was running would have been
   dropped as a duplicate, and the running evaluation might have read the state before the
   change (a lost update). A new item may now be queued while one runs. The evaluate stage is one
   transaction, so its read and its write cannot be separated by another writer.
2. **D1, every billed classification is saved at once.** The answer cache is written after each
   billed call (`PersistingClassifier`) and replaced atomically, because a worker can be killed at
   any line of a receipt. Two workers must not share one cache file (the AWS design replaces the
   file with a table).
3. **D6, the cascade has two triggers**: a receipt finishing classification, and a reviewer's
   category correction. Both queue an `evaluate` for every classified receipt that shares a key.
4. **D7, the "changed result" signature also covers how each line was classified.** The
   disposition, exceptions and review signals alone would let a category correction that happens to
   leave the findings equal produce no new version, but FR-023 asks for one. The notice text says
   "after your decision" when a reviewer had acted on the receipt, and "after a re-evaluation"
   otherwise.
5. **D8, a category correction re-runs the engine inside the action's own transaction**, not
   through the outbox. The response already carries the new evaluation version, and no "result
   changed" notice is raised for a change the reviewer caused. After a correction the receipt
   stays with a human (`in_review`, or `compliance` if a critical finding remains) even if it
   would now pass. The re-run reuses the run metadata of the receipt's latest evaluation.
6. **D9, the ordinal in the human classification's cache key is the event's sequence number.**
7. **D10, `request-info` and `escalate` are scored like the other actions**: 1 when the proposal was
   `review` or `flag`, 0 when it was `pass`.
8. **D11, one trace per receipt revision, decided with Luis's go-ahead on 2026-10-11.** Only a
   stored evaluation version gets a `decide-receipt` observation, because an evaluation that leaves
   the result unchanged records nothing, so it has nothing to observe. The label is
   `app-r<revision>` for the classification and for every decision, so the trace of a revision
   gathers all of them. The `auditor_agreement` score is attached to that trace and names the
   evaluation version it was based on in its comment (`evaluation_version=<n>`).
9. **D3, batches have no key of their own.** Each valid row follows the receipt rules, so
   resubmitting a batch is idempotent per receipt, and each submission is a new batch record. A
   batch has at most 1000 rows. A row that is valid JSON but not an object is an invalid row.
10. **D13, `epv serve` runs the API; `--with-worker` also runs a worker thread.** Both accept
    `--offline`, `--no-trace` and `--cache`. `epv openapi` prints the API's OpenAPI document, which
    is committed as `docs/api/openapi.json` with a test against drift.
11. **A classifier outage is a failure, not a result.** The OpenRouter adapter reports an outage
    or a spent budget as an unclassified line (`gateway_error`, `budget_refused`) instead of
    raising. The classify stage fails when a line comes back like that, before anything is saved,
    so the receipt is `failed` at `classify` and a retry asks again (the answered lines are in the
    cache and cost nothing). `schema_violation` and `offline_cache_miss` are final results: EXC-03
    asks for a review.
12. **A failed re-evaluation keeps the receipt's state.** A receipt that already has an evaluation
    keeps its state (a decision does not disappear) and shows the failure; a retry runs the stage
    again and changes no state by itself, and a later successful evaluation clears the failure.
    Only a receipt that was never evaluated is `failed`.
13. **Failure reasons are scrubbed.** A stage failure stores the exception type and a message with
    key-like tokens redacted and the length bounded, so a provider's error text cannot put a key
    in the store.
14. **CORS for a browser front end.** The API answers cross-origin calls only from a list of
    origins: the Vite dev server by default, else `--cors-origin` (repeatable) or
    `EPV_CORS_ORIGINS`. Methods are `GET` and `POST`; the headers are `Content-Type` and
    `Idempotency-Key`. No origin outside the list gets any CORS header.

## Consequences

- The engine, retriever and disposition logic are untouched; `outputs/results.jsonl` is unchanged
  by this iteration.
- The cascade can produce interim evaluation versions while a batch is still classifying. The
  final version is what the parity test compares; interim versions on untouched receipts raise no
  notice (D7).
- A closed receipt can be reopened by a new revision. That is deliberate and visible in the trail.
- Not covered: authentication, notification delivery, multi-node deployment, a real queue.
