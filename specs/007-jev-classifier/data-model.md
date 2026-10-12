# Data model: jev classifier, shadow mode and E16

## Schema change: version 3 (after spec 006's version 2)

The step `v2 → v3` is appended to spec 006's ordered migration list in
`adapters/sqlite_store.py`, and `SCHEMA_VERSION` becomes 3. The fresh-database `_SCHEMA` is
updated to the same end state, and a test asserts that a fresh v3 database and a migrated one have
identical `sqlite_master` entries. The whole step runs in one transaction: if any statement fails,
the database stays at v2.

### 3a. Rebuild `outbox` to allow the `shadow` stage

`outbox.stage` has `CHECK (stage IN ('classify', 'evaluate'))` (`sqlite_store.py:114`), and SQLite
cannot alter a CHECK constraint. So the step rebuilds the table, keeping ids, so `AUTOINCREMENT`
continues:

```sql
CREATE TABLE outbox_v3 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    stage TEXT NOT NULL CHECK (stage IN ('classify', 'evaluate', 'shadow')),
    state TEXT NOT NULL CHECK (state IN ('pending', 'claimed', 'done', 'cancelled', 'failed')),
    lease_until TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL
);
INSERT INTO outbox_v3 (id, receipt_id, revision, stage, state, lease_until, attempts, last_error, created_at)
    SELECT id, receipt_id, revision, stage, state, lease_until, attempts, last_error, created_at FROM outbox;
DROP TABLE outbox;                       -- also drops outbox_open
ALTER TABLE outbox_v3 RENAME TO outbox;
CREATE UNIQUE INDEX outbox_open ON outbox (receipt_id, revision, stage) WHERE state = 'pending';
```

**Indexes.** The implementation re-creates every index that `sqlite_master` lists for `outbox` at
v2. `outbox_open` is the only one at v0.4.0; if spec 006 added any, re-create those too. It
asserts that the list is the same before and after.

**Test** (`tests/unit/test_sqlite_store.py`). It migrates a v2 fixture database that holds:

- a `pending` and a `claimed` outbox item;
- a `done` item, whose `id` is the highest.

After the migration:

- the rows are identical;
- `outbox_open` exists and still rejects a second pending item for the same receipt, revision and
  stage;
- a new item gets an `id` above the old maximum;
- the pending item is claimable;
- `user_version` is 3.

### 3b. The shadow table

```sql
CREATE TABLE shadow_classifications (
    receipt_id          TEXT    NOT NULL,
    revision            INTEGER NOT NULL,
    line_id             TEXT    NOT NULL,
    classifier          TEXT    NOT NULL,   -- factory name, e.g. 'jev-hybrid'
    model_id            TEXT    NOT NULL,
    prompt_version      TEXT    NOT NULL,
    status              TEXT    NOT NULL CHECK (status IN ('classified', 'unclassified')),
    payload             TEXT    NOT NULL,   -- the Classification as JSON (model_dump_json)
    created_at          TEXT    NOT NULL,   -- spec 006 format: _ts(), e.g. 2026-10-12T15:04:05.123456+00:00
    PRIMARY KEY (receipt_id, revision, line_id, classifier)
);
CREATE INDEX shadow_by_classifier ON shadow_classifications (classifier, created_at);
```

**What it stores:**

- One row per line, per revision, per shadow classifier.
- It is written with `INSERT OR IGNORE`, so a re-run of the same shadow item stores nothing new.
- The table is never read by the engine or the evaluate stage.

**The outbox stage.** `Stage` in `domain/lifecycle.py:25` gains `"shadow"`; `ports/store.py`
imports it. `ReceiptRecord.failed_stage` keeps the type, but the shadow never sets it, and a test
asserts so.

- A `shadow` row is claimed, leased and retried like `classify` and `evaluate` (`LEASE = 60 s`,
  `MAX_ATTEMPTS = 3`).
- When its attempts run out, the worker writes the lines as `unclassified` with the last
  transient reason and completes the item.
- It never calls `_fail`, so the receipt's state and `failed_stage` are never touched.

## Configuration

| Key | Where | Values | Effect on outputs |
|---|---|---|---|
| `classifier_model` | `config/pipeline.yaml` (existing) | `gpt-oss-120b` (committed), `gpt-oss-20b`, `qwen3.5-9b`, `gemma-3-12b`, `jev-1.13`, `jev-hybrid` | Changes the classifier, and the file's hash in `RunMetadata.pipeline_config_version`. Only changed at migration (US4) |
| shadow classifier | `--shadow` flag or `EPV_SHADOW` | `jev-1.13`, `jev-hybrid` | None. The worker only adds `shadow` work and rows |
| shadow cap | `--shadow-cap-usd` flag, default 0.25 | float | Per-process spend limit of the shadow classifier |

`PipelineConfig` (`adapters/config_files.py`) keeps its fields. `load_pipeline_config` validates
`classifier_model` against the factory's accepted names (FR-024).

## Domain and adapter types

| Type | Module | Fields and notes |
|---|---|---|
| `DecisionAnswer` | `adapters/openrouter/decision_prompt.py` | `category: Category`, `confidence: float`, `confidence_source: Literal["top_probability", "confidence"]`. Built by the strict `parse_decision(content) -> DecisionAnswer` (raises `ParseError`) |
| `DecisionClassifier` | `adapters/openrouter/decision_classifier.py` | `ItemClassifier`, plus counters `calls_made`, `cache_hits`, `run_spend_usd` (same names as `OpenRouterClassifier`) |
| `HybridClassifier` | `adapters/hybrid_classifier.py` | `ItemClassifier`, composed of `category_source` and `detail_source`. Its counters are the sums of both |
| `ShadowRecord` | `ports/store.py` | `receipt_id, revision, line_id, classifier, model_id, prompt_version, classification: Classification, created_at` |
| `ShadowComparison` | `domain/shadow.py` (pure) | `compare(primary: Sequence[Classification], shadow: Sequence[Classification]) -> list[LineComparison]` with `agrees_category` and `agrees_all` |
| `ShadowReport` | `domain/shadow.py` (pure) | The counts of FR-016, each a `{k, n, interval}`, with the interval from `domain/stats.wilson`. `wilson` moves there from `eval/stats.py`, which re-exports it (research R6) |

## Store port additions (`ports/store.py`)

```python
def save_shadow(self, records: Sequence[ShadowRecord]) -> None: ...            # in a transaction
def shadow_for(self, receipt_id: str, revision: int) -> list[ShadowRecord]: ...
def iter_shadow(self, classifier: str | None = None) -> Iterator[ShadowRecord]: ...
```

## Events

No new event type. The receipt's audit trail does not mention the shadow, because the shadow is
not part of the receipt's decision.
