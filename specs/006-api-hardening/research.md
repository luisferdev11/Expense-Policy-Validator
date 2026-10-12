# Research: API hardening

Resolved before design. Luis's choices of 2026-10-12 are in the spec's Clarifications; this file
records the reasoning and the alternatives for each technical decision.

## R1. Schema migration: ordered steps on `PRAGMA user_version`

- **Decision**: replace "create only when the version is 0" in `SqliteStore._init_schema`
  (`src/expense_validator/adapters/sqlite_store.py:554-572`) with a list of migration steps,
  `MIGRATIONS: list[tuple[int, Callable[[sqlite3.Connection], None]]]`. On open, inside the existing
  `BEGIN IMMEDIATE`: version 0 runs the full current schema and sets `SCHEMA_VERSION`; version `n`
  with `0 < n < SCHEMA_VERSION` runs every step whose target is greater than `n`, in order, then sets
  the version; a version above `SCHEMA_VERSION` still raises `SchemaTooNewError`. `SCHEMA_VERSION`
  becomes 2.
- **Rationale**: SQLite runs DDL inside a transaction, so a failed step rolls back everything and the
  file stays at schema 1. Keeping `_SCHEMA` as "the current schema" makes a fresh database one script,
  and the step list is the only history. It is the smallest mechanism that makes a real upgrade
  possible, and the same steps translate to the PostgreSQL adapter of ADR 0009.
- **Alternatives**: Alembic (a dependency and an ORM-shaped tool for a stdlib store); dropping and
  recreating the database (loses the trail of every demo database); a separate "migrations" table
  (`user_version` already holds the one number needed).

## R2. The cache key stays as it is

- **Decision**: keep `cache_key` (`src/expense_validator/adapters/classification_cache.py:18-32`):
  SHA-256 over canonical JSON of the cleaned description, merchant, MCC, model id, provider endpoint
  and prompt version.
- **Rationale**: every committed answer in `outputs/classifications.jsonl` (78 rows) is keyed this
  way; changing the key turns all of them into misses and breaks the offline re-run that ADR 0002 and
  spec 001 FR-008 promise. The key already changes when the prompt version changes, which is how the
  project versions any change to the request it sends.
- **Known gap, recorded and not fixed**: the reasoning effort, temperature, `max_tokens` and the
  response schema are not in the key. They are fixed per pin and per prompt version today, so no wrong
  hit is possible now; a future pin that varies one of them without a new prompt version would need
  them in the key. That is a decision for the iteration that adds such a pin.
- **Alternatives**: add the full payload hash (invalidates the committed cache); add the pin name
  (same effect).

## R3. A cache port with two adapters

- **Decision**: a `ClassificationCachePort` Protocol in `src/expense_validator/ports/classification_cache.py`
  with `get(key) -> CacheEntry | None`, `put(entry) -> bool` (True when this call stored the row) and
  `__len__`. Adapters: the existing `ClassificationCache` (JSONL, kept for `epv run`, uploads and the
  dev runner, unchanged behaviour) and a new `SqliteClassificationCache`
  (`src/expense_validator/adapters/sqlite_cache.py`) over the store's database file. The OpenRouter
  classifier depends on the port, not on the JSONL class.
- **Rationale**: `epv run` must keep writing the committed file (that is how it is regenerated), while
  the backend needs per-row writes. A port lets both live behind the same classifier code.
- **Write semantics**: `INSERT ... ON CONFLICT (cache_key) DO NOTHING`, one short `BEGIN IMMEDIATE`
  transaction per answer. The first writer wins; a racing second answer for the same key is dropped,
  and its classification is rebuilt from the stored row so both receipts see the same answer.
- **Alternatives**: a file lock around the JSONL (still rewrites the whole file, still one machine);
  a separate SQLite file for the cache (one more file to ship and back up, and nothing gained: the
  store's file already has WAL and a busy timeout); Redis (a service for a demo).

## R4. Seeding instead of copying a file

- **Decision**: when the API or a worker opens a database whose `classification_cache` table is empty,
  it inserts every row of `outputs/classifications.jsonl` (or the file named by `--cache`) in one
  transaction, with `seeded = 1`. This replaces the copy of the committed file to
  `.cache/app_classifications.jsonl` done by `default_classifier` (`src/expense_validator/app/intake.py:101-103`)
  for the backend; uploads through the viewer keep their own gitignored copy (`UPLOAD_CACHE`).
- **Rationale**: one source of answers per database, no stray file per process, and the seed runs once
  because the table is no longer empty afterwards. `--cache` keeps its meaning for the operator ("the
  answers to start from"), now as the seed file.
- **Alternatives**: seed on every start with `INSERT OR IGNORE` (harmless but rereads 78 rows on each
  start for nothing); seed in the migration (ties the schema step to a data file outside the store).

## R5. Export for reproducibility

- **Decision**: `epv cache export [--db PATH] [--out PATH]` writes the table as JSONL sorted by key,
  each row `json.dumps(entry.model_dump(mode="json"), ensure_ascii=False)` exactly as
  `ClassificationCache.save` does (`classification_cache.py:64-75`). Default output is stdout. The
  `seeded` and `created_at` columns are not part of the exported row.
- **Rationale**: the committed file stays the reproducibility artifact. A test seeds a fresh database
  and checks that the export equals the committed file byte for byte; answers billed by the backend
  can be exported and committed deliberately, never by accident.
- **Alternatives**: the backend writes the committed file itself (it must never change committed
  outputs, ADR 0007 D1).

## R6. Budget per process, not per history

- **Decision**: `OpenRouterClassifier.classify` compares `self.run_spend_usd` (already accumulated in
  `_call`, `src/expense_validator/adapters/openrouter/classifier.py:116,231`) with `cap_usd` instead of
  `self.cache.total_cost_usd()` (line 196). The JSONL class keeps `total_cost_usd()` for reports.
- **Rationale**: the old guard summed the cost of every row ever stored, seeded ones included, so a
  database that grew past USD 1.00 of history would refuse every new line forever. A per-process cap is
  what "cap" means for an operator, and the load test's live profile sets its own (USD 0.25).
- **Consequence**: `tests/contract/test_openrouter_adapter.py:165-169` and `tests/unit/test_cache.py:62`
  are updated: the first to bill past the cap within one instance, the second keeps testing
  `total_cost_usd()` on the JSONL adapter.
- **Alternatives**: a per-day cap stored in the table (needs a clock and a reset policy nobody asked
  for); no cap in the backend (a runaway loop could bill without limit).

## R7. One timestamp format

- **Decision**: every timestamp the store writes uses `_ts()` (`sqlite_store.py:147-149`):
  `moment.astimezone(UTC).isoformat(timespec="microseconds")`, e.g.
  `2026-10-12T15:04:05.123456+00:00`. The services keep passing `datetime` values; `ReceiptRecord`
  gains a typed path: the seven call sites that write `updated_at=now.isoformat()`
  (`app/service.py:140,284`, `app/reviewing.py:182`, `app/worker.py:141,203,258`,
  `app/evaluation.py:114`) call a shared `stamp(now)` helper in `ports/store.py` that applies the same
  format, so the adapter and the services agree. `stamp` treats a naive `datetime` as UTC (it
  attaches `UTC` before converting) rather than rejecting it, because the injected clocks are aware
  and a naive value can only come from a test or a parsed legacy string; a test covers it. The
  migration rewrites existing `updated_at` values **in Python**: it reads each value, parses it with
  `datetime.fromisoformat`, and writes `stamp(...)` back when the text differs (data-model.md §3.4).
  SQLite's `strftime` is not used, because it cannot keep microseconds and the offset together
  reliably.
- **Rationale**: `datetime.isoformat()` drops the fractional part when it is zero, so two values of the
  same instant can differ in length and text order no longer equals time order. The store already
  relies on text order for leases (`claim_work`, line 454-471).
- **Alternatives**: store epoch integers (a larger change to every reader and the API); leave
  `updated_at` alone and sort by `created_at` only (the queue needs both).

## R8. Decision fields live in the projection

- **Decision**: three new columns on `receipts`: `created_at`, `decided_by`, `decided_at`. A pure
  function `decision_after(new_state, *, actor, at, by_human_action)` in
  `src/expense_validator/domain/lifecycle.py` (signature in data-model.md §4) returns the pair for a
  new state: `approved`/`rejected` from a human action take the actor and time; `auto_approved` from
  an evaluation takes `("system", at)`; every other state gives `(None, None)`. It is called in the
  same transaction that writes a **new state**: `ReviewService._decide` (`app/reviewing.py:147-184`),
  `record_evaluation` (`app/evaluation.py:91-129`), `ReceiptService._store_revision` and
  `ReceiptService.retry` (`app/service.py`), and `Worker._fail` only when it moves the receipt to
  `failed`. A failed re-evaluation keeps the receipt's state (`app/worker.py:251-255`), so it does
  **not** call `decision_after` and the fields stay as they were.
- **Rationale**: reading them from events per row is the N+1 the front end reported (F-09); writing
  them with the state keeps them consistent by construction, and the events remain the source of
  truth for the backfill.
- **Alternatives**: a SQL view joining the latest decision event (correct, but a correlated subquery
  per row on every list and harder to port); computing in the API from `list_events`
  (`sqlite_store.py:420`, loads every event of the receipt).

## R9. `created_at` is written once

- **Decision**: `put_receipt` inserts `created_at` and never updates it (`ON CONFLICT ... DO UPDATE`
  leaves it out). `ReceiptService._store_revision` (`app/service.py:239-290`) passes the current
  record's `created_at` for a revision and `stamp(now)` for revision 1. The migration fills it with
  `MIN(revisions.created_at)` per receipt.
- **Rationale**: "when did this case arrive" must not move when the employee corrects it; the revision
  detail already exposes each revision's own time.
- **Alternatives**: compute it from `revisions` on every read (a join per list row).

## R10. Typed OpenAPI with serialization-mode schemas

- **Decision**: `ReceiptDetail.receipt: ReceiptInput`, `ReceiptDetail.result: ReceiptResult | None`,
  `RevisionDetail.receipt: ReceiptInput`, `EvaluationItem.result: ReceiptResult`
  (`src/expense_validator/app/api/schemas.py:68-69,145,153`). FastAPI generates response schemas in
  serialization mode, where pydantic shows `Decimal` as a string, which is what the API sends.
  `ReceiptInput` is never a FastAPI request model (the body is read raw), so FastAPI emits it once,
  under its own name, with no `-Input`/`-Output` suffix.
- **Component names, fixed now**:

  | Component | Mode | Used by |
  |---|---|---|
  | `ReceiptInput` | serialization | `ReceiptDetail.receipt`, `ActionResponse.receipt`, `RevisionDetail.receipt` |
  | `LineItemInput` | serialization | `ReceiptInput.line_items` |
  | `ReceiptResult` | serialization | `ReceiptDetail.result`, `ActionResponse.result`, `EvaluationItem.result` |
  | `OutputLineItem`, `ExceptionFinding`, `ReviewSignal`, `RunMetadata` | serialization | inside `ReceiptResult` |
  | `ReceiptInputRequest` | validation | `POST /receipts` request body |
  | `LineItemInputRequest` | validation | `ReceiptInputRequest.line_items` |

- **How the request names are made without collisions**: `create_app` installs a custom
  `app.openapi()` that first builds FastAPI's document, then calls
  `ReceiptInput.model_json_schema(mode="validation", ref_template="#/components/schemas/{model}Request")`,
  renames the top-level schema to `ReceiptInputRequest` and every key of its `$defs` to
  `<name>Request`, and adds them to `components.schemas`. Because every validation-mode name ends in
  `Request` and every reference was generated with the same suffix, no request schema can overwrite a
  response schema. The hook raises if a `<name>Request` key already exists. `_RECEIPT_BODY`
  (`routes.py:29-36`) refers to `#/components/schemas/ReceiptInputRequest`. The models are frozen with
  `extra="forbid"`; the response models reuse them as they are.
- **Test**: `tests/contract/test_api_receipts.py` asserts that `ReceiptInput`, `ReceiptInputRequest`,
  `LineItemInput` and `LineItemInputRequest` all exist, that each request schema differs from its
  response schema (money is `string` in the response, `number` or `string` in the request), and that
  the request body refers to `ReceiptInputRequest`.
- **Rationale**: the domain models are already the contract (`tests/contract/test_result_schema.py`
  checks `ReceiptResult` against `specs/001-mvp-end-to-end/contracts/receipt-result.schema.json`).
  Reusing them removes the hand-written copy in `frontend/src/api/types.ts:27-110` and gives the
  front end real types.
- **Alternatives**: hand-written `TypedDict`s in `schemas.py` (a third copy of the same models);
  `response_model_exclude` tricks (no gain).

## R11. Generated TypeScript, pinned

- **Decision**: `openapi-typescript` pinned to an exact version in `frontend/package.json`
  devDependencies (the latest 7.x release that is at least two weeks old on the day of
  implementation; record it in `plan.md`). Script `"gen:api": "openapi-typescript
  ../docs/api/openapi.json -o src/api/generated.ts"`. `frontend/src/api/types.ts` keeps its unions
  (`State`, `Action`, `ReasonCode`) and exports named aliases from `generated.ts`:

  ```ts
  type S = components["schemas"];
  export type Receipt = S["ReceiptInput"];             // what the API returns
  export type LineItem = S["LineItemInput"];
  export type ReceiptInput = S["ReceiptInputRequest"]; // what a client submits
  export type LineItemInputRequest = S["LineItemInputRequest"];
  export type Entity = ReceiptInput["entity"];
  export type Language = ReceiptInput["line_items"][number]["language"];
  export type Result = S["ReceiptResult"];
  export type OutputLine = S["OutputLineItem"];
  export type Finding = S["ExceptionFinding"];
  export type ReviewSignal = S["ReviewSignal"];
  export type RunMetadata = S["RunMetadata"];
  ```

  Spec 008 (guided intake) imports only these names from `types.ts`, never `generated.ts` directly. A
  vitest case regenerates into memory (the library's programmatic API) and compares with the
  committed file.
- **Rationale**: one generator, no runtime dependency, types only; the staleness test turns drift
  into a test failure like the backend's `tests/smoke/test_openapi.py:31-35`.
- **Alternatives**: `openapi-generator` (Java, generates a client the front end does not need);
  `orval` (React Query hooks, more than needed); keep the hand-written types and extend
  `contract.test.ts` to nested fields (still a copy).

## R12. Locust for the load test

- **Decision**: Locust as a dev dependency (`uv add --dev locust`), scenarios in `perf/locustfile.py`,
  profiles in `perf/profiles.py`, report in `perf/report.py` exposed as `uv run python -m perf.report`.
  Locust runs headless with `--csv` to write `stats.csv`, `stats_history.csv` and `failures.csv`.
- **Rationale**: Python like the rest of the project, installs with uv, scenarios are code, a web UI
  for exploration, CSV output that can be committed and turned into a report (Luis's choice).
- **Alternatives**: k6 (a separate binary, scenarios in JavaScript); a hand-written `httpx` script
  (reinvents percentiles, ramp-up and reporting).

## R13. A classifier for load testing

- **Decision**: `epv serve` and `epv worker` gain `--classifier {openrouter,keyword,simulated}`
  (default `openrouter`, today's behaviour) and `--simulated-latency-ms N` (default 0). `keyword` is
  the existing `KeywordClassifier` (`src/expense_validator/adapters/keyword_classifier.py`).
  `simulated` is a new `SimulatedClassifier` in `src/expense_validator/adapters/simulated_classifier.py`
  that answers every line `office_supplies` with confidence 0.99 and `source.classifier = "simulated"`.
  `--simulated-latency-ms` wraps whichever classifier is chosen with a sleep per line, through a
  `LatencyClassifier` wrapper. Neither makes a model call.
- **Rationale**: the committed cache holds only the 78 lines of the 32 receipts, so generated receipts
  would be `offline_cache_miss` (EXC-03 review) or billed. A fixed classifier measures the API, the
  store and the worker; the sleep reproduces the model's latency (1 to 4 seconds per call per
  `docs/aws.md:25-26`, 0.59 s per item measured for jev) without paying for it.
- **Alternatives**: seed the cache with synthetic answers (pollutes the cache table); mock at the HTTP
  layer (needs a fake OpenRouter server).

## R14. Load profiles from `docs/aws.md`

- **Decision**: rates in receipts submitted per second:

  | Profile | Rate | Duration | Users | Classifier | Purpose |
  |---|---|---|---|---|---|
  | `smoke` | about 1 a second | 30 s | 5 | simulated, 0 ms | the setup works; under 2 minutes |
  | `nominal` | 1.2 a second | 5 min | 10 | simulated, 1500 ms | 100,000 a day on average (`docs/aws.md:4`) |
  | `peak` | 12 a second | 5 min | 60 | simulated, 1500 ms | 10× peak (`docs/aws.md:5`) |
  | `live` | 0.2 a second | 2 min | 2 | openrouter, `--cap-usd 0.25` | real latency and rate limits |

  Generated receipts use `receipt_id = LT-<run>-<n>` and `employee_id = TEST-LT-<run>-<n % 50>`. The
  `TEST-` prefix marks synthetic employees, so the load test keeps working once roles land (spec 009,
  ADR 0010 D6).

  Each simulated user mixes tasks by weight: submit 5, submit with key 1, batch of 100 rows 0.1,
  list by `updated_at` 3, detail 3, approve 0.5. The 1500 ms latency is the midpoint of the 1 to 4
  second model call quoted in `docs/aws.md:25-26`, per line; a receipt averages 2.47 lines
  (`docs/aws.md:59`).
- **Drain time**: measured **only** through `GET /health`. After the load stops, `perf/report.py`
  polls `/health` every 0.5 s until `open_work` is 0 and records the elapsed time; the peak backlog is
  the largest `open_work` it saw, sampled every 0.5 s during the run by the locustfile's background
  greenlet (also from `/health`). No other endpoint is used to judge the queue.
- **Spending cap**: `epv serve` and `epv worker` gain `--cap-usd X` (default 1.00, today's
  `CAP_USD`, `classifier.py:41`), passed to `OpenRouterClassifier(cap_usd=...)`. The `live` profile is
  started with `--cap-usd 0.25`; the other profiles do not bill, so the cap does not apply.
- **Rationale**: the AWS page's numbers become testable claims on a laptop, with the caveat that SQLite
  serialises writes (`BEGIN IMMEDIATE`, `sqlite_store.py:578`) and one worker processes one item at a
  time (`app/worker.py:90-107`).
- **Thresholds, reported not enforced**: p95 under 300 ms for reads and under 500 ms for submits at
  `nominal`; the worker keeps up at `nominal` with the simulated latency. A miss is written in the
  report's summary.

## R15. Report format

- **Decision**: `docs/perf/<YYYY-MM-DD>-<profile>.md` plus the raw CSVs in
  `docs/perf/raw/<YYYY-MM-DD>-<profile>/`. The report states: commit hash, Python and SQLite
  versions, CPU model and core count, the command line, the profile table row, then per endpoint the
  request count (N), failures, p50/p95/p99, requests a second; then drain time, peak backlog, and
  receipts evaluated (N). One paragraph compares with `docs/aws.md` and says what SQLite limits.
- **Rationale**: Principle VI: every figure has its N, and the raw data is committed so the report can
  be rebuilt with one command and no load run.
