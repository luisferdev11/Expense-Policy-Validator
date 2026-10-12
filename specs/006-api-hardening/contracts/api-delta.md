# Contract delta: API hardening

Changes to `specs/004-backend-lifecycle/contracts/api.md`. Everything not listed is unchanged. All new
fields are additions, so existing clients keep working. The committed `docs/api/openapi.json` is
regenerated from the code (`uv run epv openapi > docs/api/openapi.json`) and is the authority.

## Timestamps

Every timestamp is a string: UTC, ISO 8601 with microseconds and an explicit offset, 32 characters,
for example `2026-10-12T15:04:05.123456+00:00`. Text order equals time order.

## `ReceiptSummary` (list items, retry response, and the base of the detail)

| Field | Type | New | Meaning |
|---|---|---|---|
| `receipt_id` | string | | |
| `revision` | integer | | current revision |
| `state` | string | | |
| `disposition` | string or null | | |
| `evaluation_version` | integer or null | | |
| `notice` | string or null | | |
| `qa_sample` | boolean | | |
| `updated_at` | string | | last change; now always in the format above |
| `created_at` | string | yes | when revision 1 was stored; never changes |
| `decided_by` | string or null | yes | reviewer's actor for `approved`/`rejected`; `"system"` for `auto_approved`; otherwise null |
| `decided_at` | string or null | yes | time of that decision; null when `decided_by` is null |

Example (a receipt approved by a reviewer after a correction by the employee):

```json
{
  "receipt_id": "DEMO-001",
  "revision": 2,
  "state": "approved",
  "disposition": "review",
  "evaluation_version": 1,
  "notice": null,
  "qa_sample": false,
  "updated_at": "2026-10-12T15:10:00.000000+00:00",
  "created_at": "2026-10-12T15:00:00.000000+00:00",
  "decided_by": "alice",
  "decided_at": "2026-10-12T15:10:00.000000+00:00"
}
```

## `ReceiptDetail`, `ActionResponse`

Inherit the summary fields. Two fields gain a schema:

| Field | Before | After |
|---|---|---|
| `receipt` | object (any keys) | `ReceiptInput` (`$ref`) |
| `result` | object or null (any keys) | `ReceiptResult` (`$ref`) or null |

`ReceiptInput` and `ReceiptResult` are the domain models (`src/expense_validator/domain/models.py:44,232`)
in serialization mode: money fields (`fx_rate_to_usd`, `total_amount`, `total_amount_usd`,
`quantity`, `unit_price`, `amount`, `amount_usd`) are strings; `transaction_datetime` is a string or
null; `category` is an enum of the 21 taxonomy categories; nested schemas `LineItemInput`,
`OutputLineItem`, `ExceptionFinding`, `ReviewSignal`, `RunMetadata` are named components.

The JSON on the wire does not change: it was already `model_dump(mode="json")` of these models.

### Component names (fixed)

| Component | Mode | Referenced by |
|---|---|---|
| `ReceiptInput` | serialization (money as string) | `ReceiptDetail.receipt`, `ActionResponse.receipt`, `RevisionDetail.receipt` |
| `LineItemInput` | serialization | `ReceiptInput.line_items` |
| `ReceiptResult` | serialization | `ReceiptDetail.result`, `ActionResponse.result`, `EvaluationItem.result` |
| `OutputLineItem`, `ExceptionFinding`, `ReviewSignal`, `RunMetadata` | serialization | `ReceiptResult` |
| `ReceiptInputRequest` | validation (money as number or string) | `POST /receipts` request body |
| `LineItemInputRequest` | validation | `ReceiptInputRequest.line_items` |

No `-Input`/`-Output` suffixes appear. The `*Request` schemas are added by a custom `app.openapi()`
with `ref_template="#/components/schemas/{model}Request"` and every `$defs` key renamed with the same
suffix (research R10), so they cannot collide with the response schemas. A contract test asserts that
`ReceiptInput`, `LineItemInput`, `ReceiptInputRequest` and `LineItemInputRequest` exist and that each
`*Request` schema differs from its response counterpart.

## `RevisionDetail`, `EvaluationItem`

| Model | Field | Before | After |
|---|---|---|---|
| `RevisionDetail` | `receipt` | object | `ReceiptInput` |
| `EvaluationItem` | `result` | object | `ReceiptResult` |

## `POST /receipts` request body

The endpoint still reads the raw body (money keeps its written precision). The document's request
body changes from `{"type": "object"}` to `{"$ref": "#/components/schemas/ReceiptInputRequest"}`,
the validation-mode receipt schema. Answer keys
(`labels`, `notes`, `line_items[].labels`) are still accepted and stripped, as documented in
contracts/api.md; the schema does not list them.

## `GET /receipts`

New query parameter:

| Parameter | Values | Default | Meaning |
|---|---|---|---|
| `order` | `receipt_id`, `created_at`, `updated_at` | `receipt_id` | ascending sort; ties broken by `receipt_id` |

An unknown value is a 422 with the standard error shape (`code: "invalid_request"`, as for other
query validation errors).

## `BatchResponse` (`POST /batches`, `GET /batches/{batch_id}`)

| Field | Type | New |
|---|---|---|
| `created_at` | string | yes: when the batch was received |

## `Health` (`GET /health`)

| Field | Type | New | Meaning |
|---|---|---|---|
| `status` | string | | `"ok"` |
| `schema_version` | integer | | now 2 |
| `open_work` | integer | yes | outbox items pending or claimed (`open_work_count`, `sqlite_store.py:484-486`) |

## CLI

### `epv cache export`

```text
epv cache export [--db PATH] [--out PATH]
```

Writes the database's classification cache as JSONL sorted by `cache_key`, one `CacheEntry` per line,
the same bytes `ClassificationCache.save` writes. Default `--db` follows `db_path` (flag, `$EPV_DB`,
`var/epv.sqlite3`); default `--out` is stdout. Exit 0; prints the row count to stderr.

```bash
uv run epv cache export --db var/epv.sqlite3 > /tmp/cache.jsonl
diff /tmp/cache.jsonl outputs/classifications.jsonl    # empty on a freshly seeded database
```

### `epv serve` and `epv worker`: new options

| Option | Values | Default | Meaning |
|---|---|---|---|
| `--classifier` | `openrouter`, `keyword`, `simulated` | `openrouter` | which classifier the worker uses |
| `--simulated-latency-ms` | integer ≥ 0 | 0 | sleep per line before answering, any classifier |
| `--cache` | path | `outputs/classifications.jsonl` | the JSONL file that seeds an empty cache table (was: the cache file itself) |
| `--cap-usd` | decimal ≥ 0 | 1.00 | most this process may bill to OpenRouter; seeded and cached answers never count; the `live` load profile uses 0.25 |

`simulated` answers every line `office_supplies`, confidence 0.99, `source.classifier = "simulated"`,
with no model call and no trace generation. `keyword` is the existing keyword baseline. `--offline`
keeps its meaning for `openrouter`.

### Load test

```text
DATE=$(date +%F)
uv run locust -f perf/locustfile.py --headless --host http://127.0.0.1:8000 \
    --profile smoke --csv docs/perf/raw/$DATE-smoke/locust
uv run python -m perf.report --profile smoke --raw docs/perf/raw/$DATE-smoke \
    --out docs/perf/$DATE-smoke.md --drain --host http://127.0.0.1:8000
```

`--profile` is a custom Locust argument read by `perf/locustfile.py`; it sets the user count, spawn
rate, run time and task weights from `perf/profiles.py` (research R14). The queue is judged only
through `GET /health`: during the run a background greenlet samples `open_work` every 0.5 s (peak
backlog, written to `backlog.csv`), the `test_stop` hook records the moment the load stopped in
`stop.json`, and `perf.report --drain` polls `/health` until `open_work` is 0 (drain time). Generated
receipts use `employee_id` values prefixed `TEST-` (research R14).
