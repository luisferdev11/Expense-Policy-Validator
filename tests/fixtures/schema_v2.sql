-- A schema-version-2 database (spec 006's end state), built with the spec 006 code and then
-- given three outbox rows: R-A pending, R-B claimed, R-C done (the highest id). Used by the
-- migration test of spec 007 (tests/unit/test_sqlite_store.py). Synthetic ids only.
BEGIN TRANSACTION;
CREATE TABLE batch_items (
    batch_id TEXT NOT NULL,
    row INTEGER NOT NULL,
    receipt_id TEXT,
    outcome TEXT NOT NULL,
    error TEXT,
    PRIMARY KEY (batch_id, row)
);
CREATE TABLE batches (
    batch_id TEXT PRIMARY KEY,
    total INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE classification_cache (
    cache_key TEXT PRIMARY KEY,
    entry TEXT NOT NULL,
    model_id TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    cost_usd REAL,
    seeded INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE classifications (
    receipt_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (receipt_id, revision)
);
CREATE TABLE evaluations (
    receipt_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    version INTEGER NOT NULL,
    result TEXT NOT NULL,
    result_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (receipt_id, revision, version)
);
CREATE TABLE events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    type TEXT NOT NULL,
    payload TEXT NOT NULL,
    actor TEXT NOT NULL,
    at TEXT NOT NULL
);
CREATE TABLE outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    stage TEXT NOT NULL CHECK (stage IN ('classify', 'evaluate')),
    state TEXT NOT NULL CHECK (state IN ('pending', 'claimed', 'done', 'cancelled', 'failed')),
    lease_until TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL
);
INSERT INTO "outbox" VALUES(1,'R-A',1,'classify','pending',NULL,0,NULL,'2026-10-12T10:00:00.000000+00:00');
INSERT INTO "outbox" VALUES(2,'R-B',1,'classify','claimed','2026-10-12T10:01:00.000000+00:00',1,NULL,'2026-10-12T10:00:01.000000+00:00');
INSERT INTO "outbox" VALUES(3,'R-C',1,'evaluate','done',NULL,1,NULL,'2026-10-12T10:00:02.000000+00:00');
CREATE TABLE receipt_keys (
    receipt_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    key TEXT NOT NULL,
    PRIMARY KEY (receipt_id, revision, key)
);
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
    created_at TEXT NOT NULL DEFAULT '',
    decided_by TEXT,
    decided_at TEXT
);
CREATE TABLE revisions (
    receipt_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    content TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('current', 'superseded')),
    created_at TEXT NOT NULL,
    PRIMARY KEY (receipt_id, revision)
);
CREATE TABLE submissions (
    idempotency_key TEXT PRIMARY KEY,
    receipt_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    batch_id TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX receipt_keys_key ON receipt_keys (key);
CREATE INDEX receipts_state ON receipts (state);
CREATE INDEX receipts_created ON receipts (created_at, receipt_id);
CREATE INDEX receipts_updated ON receipts (updated_at, receipt_id);
CREATE INDEX events_receipt ON events (receipt_id, seq);
CREATE TRIGGER events_no_update BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
CREATE TRIGGER events_no_delete BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
CREATE UNIQUE INDEX outbox_open ON outbox (receipt_id, revision, stage)
    WHERE state = 'pending';
CREATE INDEX classification_cache_model ON classification_cache (model_id, prompt_version);
DELETE FROM "sqlite_sequence";
INSERT INTO "sqlite_sequence" VALUES('outbox',3);
COMMIT;
PRAGMA user_version = 2;
