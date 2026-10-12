# Data model: API hardening

Delta over `specs/004-backend-lifecycle/data-model.md` and `_SCHEMA` in
`src/expense_validator/adapters/sqlite_store.py:42-136`. Schema version 1 → 2.

## 1. Schema version 2

`SCHEMA_VERSION = 2` (`sqlite_store.py:38`). A fresh database runs `_SCHEMA` as below and sets
`user_version = 2`. A version-1 database runs the migration step of section 3.

### 1.1 `receipts` (projection): three new columns, two new indexes

```sql
CREATE TABLE receipts (
    receipt_id TEXT PRIMARY KEY,
    current_revision INTEGER NOT NULL,
    state TEXT NOT NULL,
    disposition TEXT,
    evaluation_version INTEGER,
    human_acted INTEGER NOT NULL DEFAULT 0,
    notice TEXT,
    qa_sample INTEGER NOT NULL DEFAULT 0,
    failed_stage TEXT,
    failed_reason TEXT,
    updated_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT '',   -- new: revision 1's time, written once
    decided_by TEXT,                       -- new: actor of the current decision, or 'system'
    decided_at TEXT                        -- new: time of the current decision
);
CREATE INDEX receipts_state ON receipts (state);
CREATE INDEX receipts_created ON receipts (created_at, receipt_id);   -- new
CREATE INDEX receipts_updated ON receipts (updated_at, receipt_id);   -- new
```

`created_at` is declared `NOT NULL DEFAULT ''` in both the fresh schema and the migration, because
SQLite's `ALTER TABLE ... ADD COLUMN` cannot add a `NOT NULL` column without a default; the two
schemas are therefore identical, and a test asserts that no row keeps the empty string after a write
or a migration.

### 1.2 `classification_cache`: new table

```sql
CREATE TABLE classification_cache (
    cache_key TEXT PRIMARY KEY,
    entry TEXT NOT NULL,          -- CacheEntry.model_dump_json(); the exported row
    model_id TEXT NOT NULL,       -- copied from the entry, for queries and reports
    prompt_version TEXT NOT NULL,
    cost_usd REAL,
    seeded INTEGER NOT NULL DEFAULT 0,   -- 1 when imported from the committed file
    created_at TEXT NOT NULL
);
CREATE INDEX classification_cache_model ON classification_cache (model_id, prompt_version);
```

The full `CacheEntry` (`src/expense_validator/domain/models.py:128-142`) is kept as one JSON text so
the export is the same serialisation the JSONL adapter writes (`classification_cache.py:66-69`); the
other columns are copies for querying. Writes are `INSERT ... ON CONFLICT (cache_key) DO NOTHING`.

### 1.3 Unchanged tables

`revisions`, `receipt_keys`, `submissions`, `classifications`, `evaluations`, `events` (and its two
append-only triggers), `outbox`, `batches`, `batch_items`. `batches.created_at` already exists and is
now returned by the API.

## 2. Timestamp format

Every timestamp the store holds is `_ts(moment)`: UTC, ISO 8601, microseconds, explicit offset:
`2026-10-12T15:04:05.123456+00:00` (32 characters). Text order equals time order. A helper
`stamp(moment: datetime) -> str` in `src/expense_validator/ports/store.py` returns the same string and
is used by the services wherever they build a `ReceiptRecord`; `sqlite_store._ts` calls it. A naive
`datetime` (no `tzinfo`) is treated as UTC: `stamp` attaches `UTC` and does not convert it from local
time. An aware value in another zone is converted to UTC.

## 3. Migration step 1 → 2

One function, `_migrate_1_to_2(conn)`, run inside the `BEGIN IMMEDIATE` of `_init_schema`. Order:

```sql
-- 3.1 new columns and indexes
ALTER TABLE receipts ADD COLUMN created_at TEXT NOT NULL DEFAULT '';
ALTER TABLE receipts ADD COLUMN decided_by TEXT;
ALTER TABLE receipts ADD COLUMN decided_at TEXT;
CREATE INDEX receipts_created ON receipts (created_at, receipt_id);
CREATE INDEX receipts_updated ON receipts (updated_at, receipt_id);

-- 3.2 cache table (section 1.2, verbatim)

-- 3.3 created_at from the earliest revision
UPDATE receipts SET created_at = (
    SELECT MIN(v.created_at) FROM revisions v WHERE v.receipt_id = receipts.receipt_id
);

-- 3.5 decisions by a reviewer (approve or reject on the current revision, latest one)
UPDATE receipts SET decided_by = d.actor, decided_at = d.at
FROM (
    SELECT receipt_id, revision, actor, at,
           ROW_NUMBER() OVER (PARTITION BY receipt_id, revision ORDER BY seq DESC) AS rn
    FROM events
    WHERE type IN ('ReceiptApproved', 'ReceiptRejected')
) AS d
WHERE d.receipt_id = receipts.receipt_id
  AND d.revision = receipts.current_revision
  AND d.rn = 1
  AND receipts.state IN ('approved', 'rejected');

-- 3.6 decisions by the system
UPDATE receipts SET decided_by = 'system', decided_at = (
    SELECT MAX(e.created_at) FROM evaluations e
    WHERE e.receipt_id = receipts.receipt_id AND e.revision = receipts.current_revision
)
WHERE state = 'auto_approved';
```

**3.4, in Python between 3.3 and 3.5**: normalise `updated_at`. Read `receipt_id, updated_at` for every
row, parse with `datetime.fromisoformat`, rewrite with `stamp(...)` when the text differs. Done in
Python because SQLite's `strftime` cannot keep the offset and microseconds together reliably.
`created_at` values copied from `revisions` are already in the `_ts` form.

`UPDATE ... FROM` and window functions need SQLite 3.33 and 3.25; the store already requires 3.35
(`MIN_SQLITE`, `sqlite_store.py:39`).

A receipt in any other state keeps `decided_by` and `decided_at` null.

**One rule for `created_at`**: it is the `created_at` of the receipt's earliest revision present
(`MIN(revisions.created_at)`). Normally that is revision 1; if revision 1's row is missing (a hand
edit), the earliest remaining revision is used, and the migration logs the receipt id. A receipt with
no revision row at all cannot exist (the revision and the projection are written in one transaction,
`app/service.py:263-286`); if one is found, the step raises and the database stays at schema 1. A
test removes revision 1 of fixture R-B and checks that R-B gets revision 2's time.

## 4. Decision rule (pure)

`src/expense_validator/domain/lifecycle.py` gains:

```python
SYSTEM_ACTOR = "system"


def decision_after(
    new_state: State,
    *,
    actor: str | None,
    at: str,
    by_human_action: bool,
) -> tuple[str | None, str | None]:
    """(decided_by, decided_at) for a receipt that has just moved to `new_state`."""
```

| Transition | `decided_by` | `decided_at` |
|---|---|---|
| reviewer approve → `approved` | the reviewer's actor | the action's time |
| reviewer reject → `rejected` (from `in_review`, `compliance`, `auto_approved`, `needs_info`) | the reviewer's actor | the action's time |
| evaluation → `auto_approved` | `"system"` | the evaluation's time |
| evaluation → `in_review`, `compliance` (first evaluation, re-evaluation, correction) | null | null |
| request-info → `needs_info`, escalate → `compliance` | null | null |
| new revision → `submitted` | null | null |
| failure before any evaluation → `failed`, retry → `submitted`/`classifying` | null | null |
| failure of a re-evaluation (state kept, `app/worker.py:251-255`) | unchanged: `decision_after` is not called | unchanged |

`decision_after` is called only where the state changes: `ReviewService._decide`,
`record_evaluation`, `ReceiptService._store_revision`, `ReceiptService.retry`, and `Worker._fail` when
it sets `failed`.

`by_human_action` distinguishes a reviewer's `approved`/`rejected` (actor kept) from any other path;
`approved` and `rejected` are reached only by actions today, and the function raises if they are
reached otherwise, so a future path cannot silently attribute a decision.

## 5. Port and records

`src/expense_validator/ports/store.py`:

- `ReceiptRecord` gains `created_at: str`, `decided_by: str | None = None`,
  `decided_at: str | None = None` (defaults keep call sites that build a record from scratch short;
  `_store_revision` sets `created_at` explicitly).
- `StoreTx.list_receipts(..., order: Literal["receipt_id", "created_at", "updated_at"] = "receipt_id")`.
- `BatchRecord.created_at` already exists (line 105).
- `stamp(moment: datetime) -> str` (section 2).

`src/expense_validator/ports/classification_cache.py` (new):

```python
class ClassificationCachePort(Protocol):
    def get(self, key: str) -> CacheEntry | None: ...
    def put(self, entry: CacheEntry) -> bool: ...  # True if this call stored the row
    def __len__(self) -> int: ...
```

`ClassificationCache` (JSONL) already satisfies `get` and `__len__`; its `put` returns True when the
key was new. `SqliteClassificationCache(path, clock)` implements the port plus `seed_from(path) -> int`
and `export_lines() -> Iterator[str]`.

## 6. API models (`src/expense_validator/app/api/schemas.py`)

| Model | Field | Before | After |
|---|---|---|---|
| `ReceiptSummary` | `created_at` | absent | `str` |
| `ReceiptSummary` | `decided_by` | absent | `str \| None` |
| `ReceiptSummary` | `decided_at` | absent | `str \| None` |
| `ReceiptDetail` | `receipt` | `dict[str, Any]` | `ReceiptInput` |
| `ReceiptDetail` | `result` | `dict[str, Any] \| None` | `ReceiptResult \| None` |
| `ActionResponse` | (inherits `ReceiptDetail`) | | typed |
| `RevisionDetail` | `receipt` | `dict[str, Any]` | `ReceiptInput` |
| `EvaluationItem` | `result` | `dict[str, Any]` | `ReceiptResult` |
| `BatchResponse` | `created_at` | absent | `str` |
| `Health` | `open_work` | absent | `int` |

`EventItem.payload` stays `dict[str, Any]` (out of scope). The `from_view` constructors pass the
model instances instead of `model_dump(mode="json")`; FastAPI serialises them in JSON mode, so the
wire format is unchanged (money stays a string). The parity and firewall tests prove it.
