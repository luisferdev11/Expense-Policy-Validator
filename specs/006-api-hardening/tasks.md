# Tasks: API hardening

**Input**: `specs/006-api-hardening/` (spec, plan, research, data model, contracts)

**Format**: `- [ ] T### [P?] [US?] Description with file path`. `[P]` means independent of the open
tasks around it (different files). Story labels follow the spec: US1 shared cache, US2 `created_at`,
US3 decision fields, US4 typed OpenAPI, US5 load test.

**Rules for every task**: test first (the failing test is committed in the same commit as the code
that makes it pass); never read `data/receipts.jsonl` (tests use `load_receipts()`, which strips);
no change under `src/expense_validator/domain/engine/` (if one seems needed, stop and alert Luis);
everything in English; ruff, mypy and pytest green before each commit; no `--no-verify`; never print
or write a key.

Each phase is a vertical slice that ends green and committed. If time runs out, cut from the bottom.

## Phase 1: Setup

- [x] T001 Create branch `feat/006-api-hardening` from `main` (after `docs/specs-final-iteration` is merged); confirm `uv run pytest` is green before any change
- [x] T002 Bump `version` to `1.1.0` in `pyproject.toml`, `frontend/package.json` and `create_app(version=...)` in `src/expense_validator/app/api/__init__.py:41`
- [x] T003 [P] `uv add --dev locust` (pinned 2.46.6, see plan.md); record the resolved version in `specs/006-api-hardening/plan.md` (Technical Context); add `perf` to `[tool.mypy] files` in `pyproject.toml` and, if Locust ships no types, `locust.*` to the `ignore_missing_imports` override
- [x] T004 [P] In `frontend/`, `npm install --save-dev --save-exact openapi-typescript@<7.x at least two weeks old>`; add the script `"gen:api": "openapi-typescript ../docs/api/openapi.json -o src/api/generated.ts"` to `frontend/package.json`; record the version in `plan.md`
- [x] T005 Commit: `chore: version 1.1.0 and dev dependencies for iteration 6`

## Phase 2: Foundational — migration framework (blocks every story)

**Goal**: a database at schema 1 opens at schema 2 without losing anything; a fresh one starts at 2.

- [x] T006 Write `tests/fixtures/schema_v1.sql`: the v1 `_SCHEMA` (copy of `sqlite_store.py:42-136` at v0.4.0) plus `PRAGMA user_version = 1` and five receipts built with v1 semantics and timestamps written by `now.isoformat()` (some without microseconds): R-A one revision `in_review`; R-B two revisions (revision 1 at 10:00, revision 2 at 10:05) `in_review`; R-C `approved` by `alice` (event `ReceiptApproved`); R-D `auto_approved` with one evaluation; R-E `rejected` by `bob` after `auto_approved`. Synthetic ids only; no real receipt content
- [x] T007 Write failing tests in `tests/unit/test_sqlite_store.py`: (a) a fresh file opens at `user_version = 2` with tables `classification_cache` and the new `receipts` columns and indexes; (b) the v1 fixture opens at version 2; (c) a step that raises leaves `user_version = 1` and the data intact (monkeypatch a failing step); (d) version 3 still raises `SchemaTooNewError`; (e) `/health` reports `schema_version: 2` (extend `tests/contract/test_api_receipts.py`)
- [x] T008 Implement in `src/expense_validator/adapters/sqlite_store.py`: `SCHEMA_VERSION = 2`; `_SCHEMA` updated per data-model.md §1; `MIGRATIONS = [(2, _migrate_1_to_2)]`; `_init_schema` applies pending steps in order inside its `BEGIN IMMEDIATE` and sets `user_version` last; `_migrate_1_to_2` with the DDL of data-model.md §3.1–3.2 only (backfills come in US2 and US3)
- [x] T009 Commit: `feat: schema migrations for the store, version 2 (iteration 6)`

## Phase 3: User Story 1 — several workers on one answer cache (P1)

**Goal**: answers stored per row in the database, seeded from and exportable to the committed file.
**Independent test**: SC-001, SC-002, SC-003.

### Tests first

- [x] T010 [P] [US1] Write `tests/unit/test_sqlite_cache.py` as a contract parametrised over both adapters (`ClassificationCache` on a tmp JSONL, `SqliteClassificationCache` on a tmp database): `get` of a missing key is None; `put` returns True then False for the same key and keeps the first entry; `len` counts rows
- [x] T011 [P] [US1] Extend `tests/unit/test_sqlite_cache.py` for the table only: `seed_from(outputs/classifications.jsonl)` inserts 78 rows with `seeded = 1` and returns 78; a second `seed_from` on a non-empty table inserts 0; `export_lines()` joined with newlines equals the committed file byte for byte; two `SqliteClassificationCache` instances on one file see each other's `put` immediately
- [x] T012 [P] [US1] Update `tests/contract/test_openrouter_adapter.py:160-170`: the cap is per instance — an instance with `cap_usd=1.0` bills until its own `run_spend_usd` reaches 1.0, and seeded rows with a total cost above the cap do not trigger `budget_refused`; keep `tests/unit/test_cache.py:62` testing `total_cost_usd()` on the JSONL adapter
- [x] T013 [P] [US1] Write `tests/integration/test_two_workers.py`: two `Worker` instances (`app/worker.py`) on one tmp database with the table cache, (a) offline over the 32 receipts from `load_receipts()` interleaving `process_next()` calls: zero billed calls and every latest result equals `outputs/results.jsonl` (SC-001); (b) two `OpenRouterClassifier` instances over one `SqliteClassificationCache`, each with a fake transport that counts calls (the pattern of `make` in `tests/contract/test_openrouter_adapter.py`; `BillingClassifier` in `tests/fakes.py` keeps its own in-memory cache and does not exercise the table), over 20 synthetic receipts from `tests/factories.py` sharing 10 distinct new lines: exactly 10 transport calls in total and 10 new rows (SC-002)
- [x] T014 [P] [US1] Write `tests/smoke/test_cache_export.py`: `epv cache export --db <fresh tmp>` prints the committed file exactly and the row count on stderr (SC-003)

### Implementation

- [x] T015 [US1] Create `src/expense_validator/ports/classification_cache.py` with `ClassificationCachePort` (data-model.md §5)
- [x] T016 [US1] Make `ClassificationCache.put` return `bool` (True when new) in `src/expense_validator/adapters/classification_cache.py`; no other behaviour change
- [x] T017 [US1] Create `src/expense_validator/adapters/sqlite_cache.py`: `SqliteClassificationCache(path, clock)` with `get`, `put` (`INSERT ... ON CONFLICT (cache_key) DO NOTHING` in its own `BEGIN IMMEDIATE`, connection settings as `SqliteStore._connect`), `__len__`, `seed_from(path) -> int` (no-op when the table has rows), `export_lines() -> Iterator[str]` (sorted by key, `json.dumps(CacheEntry.model_validate_json(entry).model_dump(mode="json"), ensure_ascii=False)`)
- [x] T018 [US1] Change `OpenRouterClassifier` (`src/expense_validator/adapters/openrouter/classifier.py:91-116,196`) to take `cache: ClassificationCachePort` and to refuse with `budget_refused` when `self.run_spend_usd >= self.cap_usd`; after a racing `put` returns False, rebuild the classification from `self.cache.get(key)` so both racers return the stored answer
- [x] T019 [US1] Change `default_classifier` (`src/expense_validator/app/intake.py:93-112`) to accept a `ClassificationCachePort` (uploads keep passing their JSONL cache; the copy at lines 101-103 stays for `UPLOAD_CACHE` only)
- [x] T020 [US1] Rewire `build_worker` (`src/expense_validator/app/composition.py:76-93`): build `SqliteClassificationCache(store.path, utc_now)`, call `seed_from(seed_path)` (default `CLASSIFICATIONS_FILE`), pass it to the classifier, and drop `PersistingClassifier` for the backend (each `put` is already durable); keep `PersistingClassifier` in the tree for the JSONL path and note it in its docstring
- [x] T021 [US1] In `src/expense_validator/app/cli.py`: `--cache` now names the seed file (help text updated, default `outputs/classifications.jsonl`); add `epv cache export [--db] [--out]` (contracts/api-delta.md)
- [x] T022 [US1] Extend `tests/integration/test_firewall_scan.py` to scan the `classification_cache` table for answer keys
- [x] T023 [US1] Update the comment on `APP_CLASSIFICATION_CACHE` in `src/expense_validator/paths.py` (no longer used by the backend); add an amendment to `docs/decisions/0007-backend-design.md` saying amendment 2 ("two workers must not share one cache file") no longer applies to the backend, which now uses the cache table; check `tests/integration/test_crash_resume.py` still proves zero extra billed calls with the table cache
- [x] T024 [US1] Verify (ruff, mypy, pytest, `uv run epv run --offline --no-trace` byte-identical) and commit: `feat: classification cache in a table, shared by workers (iteration 6)`

## Phase 4: User Story 2 — `created_at` and one timestamp format (P1)

**Goal**: every receipt has an immutable `created_at`; all timestamps sort as text.
**Independent test**: submit, revise a minute later, read; list by `created_at`.

### Tests first

- [x] T025 [P] [US2] Write `tests/unit/test_stamp.py`: `stamp()` returns 32 characters with microseconds and `+00:00` for an aware UTC, an aware non-UTC (converted) and a zero-microsecond datetime; a naive datetime is treated as UTC (`stamp(datetime(2026,10,12,15,0))` is `2026-10-12T15:00:00.000000+00:00`, whatever the machine's local zone; set `TZ` to a non-UTC zone in the test); text order equals time order over 100 random instants (seeded)
- [x] T026 [P] [US2] Extend `tests/unit/test_sqlite_store.py`: `put_receipt` inserts `created_at` and an upsert never changes it; `list_receipts(order="created_at"|"updated_at")` orders by time with `receipt_id` as tiebreak; the v1 fixture migrates with `created_at` = earliest revision time for R-A..R-E and every `updated_at` rewritten to 32 characters by the Python step of data-model.md §3.4 (SC-004, part); with R-B's revision 1 row deleted before migrating, R-B gets revision 2's time; a receipt with no revision row at all makes the migration raise and leaves `user_version = 1`
- [x] T027 [P] [US2] Extend `tests/unit/test_service_submit.py` with `StepClock` (`tests/fakes.py:72-85`): revision 1 at t0, revision 2 at t0+60 s; the record's `created_at` is t0, `updated_at` t0+60 s
- [x] T028 [P] [US2] Extend `tests/contract/test_api_receipts.py`: summary and detail include `created_at`; `GET /receipts?order=created_at` and `order=updated_at` sort; `order=bogus` is 422 `invalid_request`; extend `tests/contract/test_api_batches.py`: `created_at` on POST and GET batch responses

### Implementation

- [x] T029 [US2] Add `stamp(moment: datetime) -> str` to `src/expense_validator/ports/store.py`; make `sqlite_store._ts` call it
- [x] T030 [US2] Add `created_at: str` (and, for US3, `decided_by`, `decided_at` defaulting to None) to `ReceiptRecord` in `src/expense_validator/ports/store.py`; add `order` to `StoreTx.list_receipts`
- [x] T031 [US2] In `src/expense_validator/adapters/sqlite_store.py`: `_receipt()` reads the new columns; `put_receipt` inserts `created_at` and leaves it out of `DO UPDATE SET`; `list_receipts` builds `ORDER BY <column>, receipt_id` from a whitelist; add data-model.md §3.3 and §3.4 to `_migrate_1_to_2`
- [x] T032 [US2] Replace every `updated_at=now.isoformat()` with `updated_at=stamp(now)`: `src/expense_validator/app/service.py:140,284`, `src/expense_validator/app/reviewing.py:182`, `src/expense_validator/app/worker.py:141,203,258`, `src/expense_validator/app/evaluation.py:114`; in `ReceiptService._store_revision` (`service.py:272-286`) set `created_at=stamp(now)` for revision 1 and `current.created_at` for a later revision
- [x] T033 [US2] In `src/expense_validator/app/api/schemas.py` and `routes.py`: `created_at` on `ReceiptSummary`; `order: Literal["receipt_id","created_at","updated_at"] = "receipt_id"` on `GET /receipts`, passed through `ReceiptService.list_receipts`; `created_at` on `BatchResponse` (from `BatchView`; add the field to `src/expense_validator/app/batching.py` `BatchView` from `BatchRecord.created_at`)
- [x] T034 [US2] Verify and commit: `feat: created_at on receipts and batches, one timestamp format, list order (iteration 6)`

## Phase 5: User Story 3 — decision fields (P2)

**Goal**: `decided_by` and `decided_at` on summary and detail, set with the state, backfilled.
**Independent test**: SC-005 and the decision part of SC-004.

### Tests first

- [x] T035 [P] [US3] Extend `tests/unit/test_lifecycle.py`: `decision_after` for every row of data-model.md §4 (approve, reject from each of its four states, auto-approve, re-evaluation to `in_review` and `compliance`, request-info, escalate, new revision, failure, retry); reaching `approved` or `rejected` with `by_human_action=False` raises
- [x] T036 [P] [US3] Extend `tests/unit/test_review_actions.py`: approve as `alice` sets both fields in the same transaction as the event (read back inside the action's result); request-info and escalate leave them null; a category correction leaves them null
- [x] T037 [P] [US3] Extend `tests/unit/test_worker.py`: an evaluation to `auto_approved` sets `("system", evaluation time)`; a re-evaluation of an approved receipt that returns it to `in_review` (ADR 0007 D7) clears them; a failed re-evaluation keeps the state and the fields unchanged and does not call `decision_after` (spy on it)
- [x] T038 [P] [US3] Extend `tests/unit/test_service_submit.py`: a new revision of a decided receipt clears them
- [x] T039 [P] [US3] Extend `tests/unit/test_sqlite_store.py`: the v1 fixture migrates with R-C `("alice", approval time)`, R-D `("system", its evaluation time)`, R-E `("bob", rejection time)`, R-A and R-B null (SC-004)
- [x] T040 [P] [US3] Extend `tests/contract/test_api_actions.py`: the eight transitions of SC-005 (including escalate) through the HTTP API, reading `decided_by`/`decided_at` from `GET /receipts` and `GET /receipts/{id}`

### Implementation

- [x] T041 [US3] Add `SYSTEM_ACTOR = "system"` and `decision_after(...)` to `src/expense_validator/domain/lifecycle.py` (pure; data-model.md §4)
- [x] T042 [US3] Apply it in `ReviewService._decide` (`src/expense_validator/app/reviewing.py:176-184`) with the actor and `stamp(now)`
- [x] T043 [US3] Apply it in `record_evaluation` (`src/expense_validator/app/evaluation.py:104-116`) with `by_human_action=False`; this covers first evaluations, re-evaluations and corrections
- [x] T044 [US3] Call `decision_after` in `ReceiptService._store_revision` (`service.py:272-286`), `ReceiptService.retry` (`service.py:132-141`) and `Worker._fail` only when it sets `failed` (`worker.py:251-260`); a failed re-evaluation keeps its state and does not call it
- [x] T045 [US3] Store and read the columns in `src/expense_validator/adapters/sqlite_store.py` (`put_receipt`, `_receipt`); add data-model.md §3.5 and §3.6 to `_migrate_1_to_2`
- [x] T046 [US3] Add `decided_by` and `decided_at` to `ReceiptSummary` in `src/expense_validator/app/api/schemas.py:42-63`
- [x] T047 [US3] Verify and commit: `feat: decided_by and decided_at on receipts (iteration 6)`

## Phase 6: User Story 4 — typed OpenAPI and generated front-end types (P2)

**Goal**: `receipt` and `result` have real schemas; the front end generates its types.
**Independent test**: SC-006; `npm test` fails on a stale `generated.ts`.

### Tests first

- [x] T048 [P] [US4] Extend `tests/contract/test_result_schema.py`: the OpenAPI document's result schema (resolve the `$ref` used by `ReceiptDetail.result`) has the same property names as `specs/001-mvp-end-to-end/contracts/receipt-result.schema.json`, recursively for `line_items`, `exceptions`, `review_signals`, `run`
- [x] T049 [P] [US4] Extend `tests/contract/test_api_receipts.py`: in the document, `ReceiptDetail.receipt`, `RevisionDetail.receipt` refer to the receipt schema and `ReceiptDetail.result`, `EvaluationItem.result` to the result schema; every property of `ReceiptInput`/`ReceiptResult` is present; money fields are `type: string`; the components `ReceiptInput`, `LineItemInput`, `ReceiptResult`, `ReceiptInputRequest` and `LineItemInputRequest` all exist, no component name contains `-Input` or `-Output`, `ReceiptInputRequest != ReceiptInput` and `LineItemInputRequest != LineItemInput` (SC-005a); the `POST /receipts` body is `{"$ref": "#/components/schemas/ReceiptInputRequest"}`; a real `GET /receipts/{id}` response is unchanged byte for byte from the v0.4.0 shape for `DEMO-001` (compare with a fixture captured before the change)
- [x] T050 [P] [US4] Write `frontend/src/api/generated.test.ts`: generate types from `../../docs/api/openapi.json` in memory with the `openapi-typescript` programmatic API and compare with the committed `src/api/generated.ts`; the failure message names `npm run gen:api`
- [x] T051 [P] [US4] Extend `frontend/src/contract.test.ts` `USED_FIELDS`: `ReceiptSummary` and `ReceiptDetail` gain `created_at`, `decided_by`, `decided_at`; `BatchResponse` gains `created_at`; `Health` gains `open_work`; add the schemas `ReceiptInput`, `LineItemInput`, `ReceiptResult`, `ReceiptInputRequest` and `LineItemInputRequest` with the fields the front end reads (spec 008's form reads `ReceiptInputRequest`); the list endpoint's parameters include `order`

### Implementation

- [x] T052 [US4] In `src/expense_validator/app/api/schemas.py`: `ReceiptDetail.receipt: ReceiptInput`, `result: ReceiptResult | None`, `RevisionDetail.receipt: ReceiptInput`, `EvaluationItem.result: ReceiptResult`; constructors pass model instances (no `model_dump`); remove `Any` imports no longer used
- [x] T053 [US4] In `src/expense_validator/app/api/__init__.py` and `routes.py:29-36`: install a custom `app.openapi()` that builds FastAPI's document, then calls `ReceiptInput.model_json_schema(mode="validation", ref_template="#/components/schemas/{model}Request")`, adds the top-level schema as `ReceiptInputRequest` and every `$defs` entry as `<name>Request` (so `LineItemInputRequest`), raising if any `*Request` key already exists; point `_RECEIPT_BODY` at `#/components/schemas/ReceiptInputRequest`; response-side names stay `ReceiptInput`, `LineItemInput`, `ReceiptResult` (research R10)
- [x] T054 [US4] Regenerate `docs/api/openapi.json` with `uv run epv openapi > docs/api/openapi.json`; `tests/smoke/test_openapi.py` passes
- [x] T055 [US4] In `frontend/`: `npm run gen:api` to create `src/api/generated.ts`; change `src/api/types.ts` to export these named aliases from `generated.ts` (research R11) and nothing else from it: `Receipt = components["schemas"]["ReceiptInput"]`, `LineItem = components["schemas"]["LineItemInput"]`, `ReceiptInput = components["schemas"]["ReceiptInputRequest"]` (the shape a client submits), `LineItemInputRequest = components["schemas"]["LineItemInputRequest"]`, `Entity = ReceiptInput["entity"]`, `Language = ReceiptInput["line_items"][number]["language"]`, `Result = components["schemas"]["ReceiptResult"]`, `OutputLine`, `Finding`, `ReviewSignal`, `RunMetadata`; spec 008 imports only these names from `types.ts`; add `created_at`, `decided_by`, `decided_at` to `ReceiptSummary`, `created_at` to `BatchResponse`; fix any type errors (`npm run typecheck`)
- [x] T056 [US4] Update `docs/api/build_collection.py` with assertions on `created_at`, `decided_by`/`decided_at` after approve and reject, `order=created_at`, batch `created_at`; make every receipt the builder generates use an `employee_id` prefixed `TEST-` (so the collection keeps working once roles land, spec 009 and ADR 0010 D6); regenerate `docs/api/epv.postman_collection.json`; run Newman (quickstart §5) and record the request and assertion counts in `quickstart.md`
- [x] T057 [US4] Verify (`uv run pytest`, `npm test`, `npm run e2e`) and commit: `feat: typed receipt and result in OpenAPI, generated front-end types (iteration 6)`

## Phase 7: User Story 5 — load test (P2)

**Goal**: one command per profile, a committed report with every figure's N.
**Independent test**: the `smoke` profile writes a complete report with zero model calls.

### Tests first

- [x] T058 [P] [US5] Write `tests/unit/test_simulated_classifier.py`: `SimulatedClassifier` returns `office_supplies`, 0.99, `source.classifier == "simulated"`, `calls_made == 0`; `LatencyClassifier(inner, ms)` sleeps through an injected `sleep` function (no real sleeping in tests) and returns the inner answer
- [x] T059 [P] [US5] Write `tests/unit/test_perf_report.py`: from a committed fixture (`tests/fixtures/perf/stats.csv`, `stats_history.csv`, `failures.csv`, `stop.json`, a drain record), `perf.report.render(...)` writes a Markdown report with the commit, machine, profile row, a per-endpoint table with N, p50, p95, p99 and failures, drain time and peak backlog, and a "thresholds" section that names each miss
- [x] T060 [P] [US5] Write `tests/smoke/test_locustfile.py`: import the task functions from `perf/locustfile.py` and run each once against a `TestClient` app with the simulated classifier (an adapter object that exposes `.post`/`.get` like Locust's client), asserting 2xx/207 responses; assert `perf/receipts.py` produces unique `receipt_id`s across 1,000 calls and never opens `data/receipts.jsonl` (patch `open` to fail on that path)
- [x] T061 [P] [US5] Extend `tests/contract/test_api_receipts.py`: `GET /health` returns `open_work` equal to pending plus claimed outbox items
- [x] T061a [P] [US5] Write `tests/unit/test_cli_worker_options.py`: `epv serve` and `epv worker` parse `--cap-usd 0.25` into `WorkerOptions.cap_usd` (default 1.00), `build_worker` passes it to `OpenRouterClassifier(cap_usd=...)`, and an `OpenRouterClassifier` built that way refuses with `budget_refused` once its fake transport has billed 0.25; `--cap-usd -1` is rejected by the parser

### Implementation

- [x] T062 [US5] Create `src/expense_validator/adapters/simulated_classifier.py` with `SimulatedClassifier` and `LatencyClassifier` (research R13)
- [x] T063 [US5] In `src/expense_validator/app/cli.py` and `composition.py`: `--classifier {openrouter,keyword,simulated}`, `--simulated-latency-ms` and `--cap-usd` (default 1.00, `CAP_USD`) on `serve` and `worker` (`_add_worker_options`, `WorkerOptions`, `build_worker`); add `open_work` to `Health` (`schemas.py:209-211`, `routes.py:44-46`) from `open_work_count`
- [x] T064 [US5] Create `perf/__init__.py`, `perf/profiles.py` (research R14 table), `perf/receipts.py` (load `docs/samples/receipt-one.json`, set `receipt_id = f"LT-{run_id}-{n:06d}"`, matching `line_id`s, and `employee_id = f"TEST-LT-{run_id}-{n % 50:02d}"`, keep everything else), `perf/locustfile.py` (an `HttpUser` with weighted tasks submit, submit-with-key, batch-100, list-by-updated_at, detail, approve-in-review; a `--profile` custom argument via `events.init_command_line_parser`; a background greenlet that samples `GET /health` `open_work` every 0.5 s into `backlog.csv`; a `test_stop` hook writing `stop.json`), `perf/report.py` (`python -m perf.report --profile P --raw DIR --out FILE [--drain --host URL]`; peak backlog from `backlog.csv`, drain time by polling `/health` until `open_work` is 0; no other endpoint judges the queue). Extend T060 to assert every generated `employee_id` starts with `TEST-`
- [ ] T065 [US5] With `DATE=$(date +%F)` and a fresh `--db var/perf.sqlite3` per run, start `uv run epv serve --with-worker --classifier simulated --no-trace --db var/perf.sqlite3` with `--simulated-latency-ms 0` for `smoke` and `--simulated-latency-ms 1500` for `nominal` and `peak` (quickstart §6); commit `docs/perf/$DATE-{smoke,nominal,peak}.md` and `docs/perf/raw/$DATE-<profile>/`. Do not run `live` unless Luis asks; if run, start the server with `--classifier openrouter --cap-usd 0.25` and say so in the report
- [ ] T066 [US5] Commit: `feat: Locust load test with profiles and committed reports (iteration 6)`

## Phase 8: Polish and cross-cutting

- [ ] T067 [P] Add an `AI_NOTES.md` row for every assistant mistake caught during this feature (what, how it was caught, what changed), and a line under "Open issues" closing AI_NOTES 40's shared-cache issue for the backend (the dev runner still uses JSONL files)
- [ ] T068 [P] Update `docs/roadmap.md` (iteration 6 status) and `README.md` if it lists the API fields or the cache (one line each)
- [ ] T069 [P] Log the important prompts of this session in `docs/ai/prompt-log.md`
- [ ] T070 Run the full verification below and fix what fails; commit `docs: iteration 6 API hardening notes`
- [ ] T071 Open the PR `feat/006-api-hardening` → `main` with the SC table and the load reports linked; after Luis merges, tag `v1.1.0` and create the GitHub release

## Verification (before the PR)

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run epv openapi > /tmp/openapi.json && diff /tmp/openapi.json docs/api/openapi.json
uv run epv run --offline --no-trace && git diff --stat outputs/          # empty
uv run pytest tests/integration/test_api_parity.py tests/integration/test_two_workers.py -q
uv run epv cache export --db "$(mktemp -d)/fresh.sqlite3" | diff - outputs/classifications.jsonl
cd frontend && npm test && npm run typecheck && npm run e2e && cd ..
uv run epv serve --with-worker --offline --no-trace &   # then Newman, see quickstart.md §5
git diff --stat main -- src/expense_validator/domain/engine/             # empty
```

## Dependencies and execution order

- Phase 1 → Phase 2 → US1 → US2 → US3 → US4 → US5 → Polish.
- US2 and US3 both touch `_migrate_1_to_2` and `put_receipt`, so they run in order.
- US4 can start after US3 (the summary fields must exist before the document is regenerated once).
- US5 depends only on Phase 2 and on `--classifier`; it can run in parallel with US4 by another
  session if needed, rebasing `cli.py` and `schemas.py`.
- Within a story, tasks marked `[P]` are tests in different files and can be written together.
