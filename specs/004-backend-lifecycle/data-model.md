# Data model: Intake and lifecycle backend

Schema version 1 (`PRAGMA user_version = 1`). Timestamps are ISO 8601 UTC text from the injected
clock. `events.seq` is the only ordering. Every write happens in one `BEGIN IMMEDIATE`
transaction per command.

## Tables

### `revisions` (immutable)

| Column | Type | Notes |
|---|---|---|
| `receipt_id` | TEXT | part of the key |
| `revision` | INTEGER | 1, 2, ...; part of the key |
| `content_hash` | TEXT | SHA-256 of the canonical stripped receipt |
| `content` | TEXT | the stripped `ReceiptInput` as JSON. Never the raw request body (FR-009). |
| `status` | TEXT | `current` or `superseded` |
| `created_at` | TEXT | |

### `receipt_keys`

`(receipt_id, revision, key)`; the sharing keys of a revision, `day:<employee_id>|<date>` and
`trip:<trip_id>`, indexed on `key`. Written with the revision.

### `submissions` (idempotency)

| Column | Notes |
|---|---|
| `idempotency_key` | primary key. The client header, or `<receipt_id>:<content_hash>` |
| `receipt_id`, `revision` | what the key resolved to |
| `content_hash` | to detect a reused client key with a different body (`422`) |
| `batch_id` | nullable |
| `created_at` | |

### `receipts` (projection of the current revision)

| Column | Notes |
|---|---|
| `receipt_id` | primary key |
| `current_revision` | |
| `state` | see lifecycle |
| `disposition` | latest evaluation's disposition, nullable until evaluated |
| `evaluation_version` | latest, nullable until evaluated |
| `human_acted` | 0 or 1: a reviewer acted on the current revision |
| `notice` | nullable text, cleared by the next reviewer action |
| `qa_sample` | 0 or 1 (D12) |
| `failed_stage`, `failed_reason` | nullable, set in state `failed` |
| `updated_at` | |

### `classifications`

`(receipt_id, revision, payload)`; the model's `Classification` list for the revision as JSON,
written by the classify stage. Human corrections are not written here; they are events (D9), applied
when an evaluation is built.

### `evaluations`

`(receipt_id, revision, version, result, result_hash, created_at)`; `result` is the
`ReceiptResult` JSON the batch run would write; `result_hash` is the hash of what a reviewer sees: the
disposition, exceptions, review signals and how each line was classified (R5, ADR 0007 amendment 4);
the run metadata is not part of it. Versions count from 1 per revision.

### `events` (append-only, source of truth)

| Column | Notes |
|---|---|
| `seq` | `INTEGER PRIMARY KEY AUTOINCREMENT` |
| `receipt_id`, `revision` | |
| `type` | see events |
| `payload` | JSON, typed per event |
| `actor` | free text for reviewer actions, `system` otherwise |
| `at` | |

### `outbox`

| Column | Notes |
|---|---|
| `id` | autoincrement |
| `receipt_id`, `revision` | |
| `stage` | `classify` or `evaluate` |
| `state` | `pending`, `claimed`, `done`, `cancelled`, `failed` |
| `lease_until` | nullable; set on claim |
| `attempts` | incremented on claim |
| `last_error` | nullable |
| `created_at` | |

A partial unique index on `(receipt_id, revision, stage) WHERE state = 'pending'`
keeps at most one waiting item per stage. A new one may be queued while one runs, so a change that
lands during an evaluation is never lost (ADR 0007 amendment 1).

### `batches` and `batch_items`

`batches(batch_id, created_at, total)`; `batch_items(batch_id, row, receipt_id, outcome, error)`
with `outcome` one of `accepted`, `existing`, `revision`, `invalid`, `duplicate_in_batch`. The
batch summary counts accepted rows by the state of their receipt, and the other rows under their
outcome, so no receipt is counted twice.

## Lifecycle

```
submitted ──► classifying ──► (evaluated) ─┬─ pass ───────────► auto_approved
    ▲                                       ├─ review / flag ──► in_review
    │                                       └─ critical ───────► compliance
    │                                                          │
  new revision                  in_review ─ approve ─► approved
                                          ─ reject ──► rejected  (also from needs_info and auto_approved)
                                          ─ request-info ─► needs_info ──(revision)──► submitted
                                          ─ escalate ──► compliance
                                compliance ─ approve / reject / request-info
any stage ──► failed(stage, reason) ──(retry)──► that stage
```

`evaluated` is an event, not a resting state: an evaluation moves the receipt straight to its
disposition state. A critical exception means any exception whose severity is `critical`.

Allowed actions by state: see ADR 0007 D8. `reject` is also allowed from `needs_info` (a reviewer
may close a request that is never answered).

## Events

| Type | Payload (besides `receipt_id`, `revision`) |
|---|---|
| `ReceiptSubmitted` | `content_hash`, `batch_id`, `idempotency_key` |
| `RevisionSuperseded` | `superseded_revision`, `by_revision` |
| `ReceiptClassified` | `lines`, `cache_hits`, `calls_made` |
| `ReceiptEvaluated` | `version`, `disposition`, `changed`, `result_hash` |
| `NoticeRaised` | `text` |
| `StageFailed` | `stage`, `reason` |
| `StageRetried` | `stage` |
| `ReceiptApproved`, `ReceiptRejected` | `based_on_version`, `reason_code`, `note`, `agreement` |
| `LineCategoryCorrected` | `line_id`, `from_category`, `to_category`, `based_on_version`, `agreement` |
| `InformationRequested` | `based_on_version`, `question`, `agreement` |
| `EscalatedToCompliance` | `based_on_version`, `reason`, `agreement` |
| `DevCandidateMarked` | `line_id`, `from_category`, `to_category` |

## Validation rules

- A receipt enters only through the stripped parser; the model forbids extra keys, which is a second
  firewall.
- `receipt_id` is non-empty; the idempotency key is at most 255 characters.
- An action's `evaluation_version` must equal the receipt's current one (else `409`).
- A reason code is required when the decision overrides the proposal; `other` requires a note.
- A corrected category is one of the 21 taxonomy categories.
