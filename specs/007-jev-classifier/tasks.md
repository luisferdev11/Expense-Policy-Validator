# Tasks: jev classifier, shadow mode and experiment E16

**Input**: `specs/007-jev-classifier/` (spec, plan, research, data model, contracts)

**Format**: `- [ ] T### [P?] [US?] Description with file path`. `[P]` means independent of the open
tasks around it. Story labels follow the spec:

- US1: decision adapter and hybrid
- US2: shadow mode
- US3: E16 and the decide-rule fixes
- US4: the switch and the runbook

**Rules for every task:**

- Test first: the failing test goes in the same commit as the code that makes it pass.
- Never read `data/receipts.jsonl` or the dev set's labels outside `eval/`.
- Alert Luis before any change under `src/expense_validator/domain/engine/`.
- Do not change `outputs/`, `config/pipeline.yaml` or `docs/decisions/policy_decisions.yaml`.
- Everything in English.
- ruff, mypy and pytest green before each commit. No `--no-verify`.
- No billed call in any test: use fake transports.

**Prerequisite**: spec 006 Phase 2 and US1 (T006–T024) are merged:

- `ClassificationCachePort` in `ports/classification_cache.py`;
- `SqliteClassificationCache` in `adapters/sqlite_cache.py`;
- ordered schema migrations, `SCHEMA_VERSION = 2`.

Check with `uv run pytest tests/unit/test_sqlite_cache.py` and by reading `adapters/sqlite_store.py`
for the migration list. If they are missing, stop and implement them first.

## Phase 0: Setup

- [x] T001 Create branch `feat/007-jev-classifier` from `main` (with 006 merged). Move `httpx` from the dev group to `dependencies` in `pyproject.toml`. Bump the version to `1.2.0` in all three places: `pyproject.toml`, `frontend/package.json`, and `create_app` in `src/expense_validator/app/api/__init__.py` (the OpenAPI `version`). Regenerate `docs/api/openapi.json`. Run `uv sync`
- [x] T002 Capture the `dec-v1` payload fixture once: write a throwaway script under `explorations/scripts/capture_dec_v1_fixture.py` that imports `explorations/lib/decision_adapters.py` and writes `decision_payload()` for 3 synthetic items (one English food item, one Japanese item, one "Moscow Mule mug" trap; merchants and MCCs invented) into `tests/fixtures/dec_v1_payload.json`. Commit both, so the provenance is visible

## Phase 1: Decide-rule fixes, US3 (slice 1)

**Goal**: guards before superiority, and a superior challenger wins outright. E14's outcome is unchanged.
**Independent test**: synthetic rows; then `uv run python -I eval/experiments/decide.py` leaves `outputs/eval/experiments.json` byte-identical.

- [x] T003 [P] [US3] Write `tests/unit/test_decide_rule_order.py` with synthetic items and rows (no dev labels): (a) a challenger with 130/130 against the reference's 123/130 and 23 A6/A9 items wrong against 2 gets `fails_a6a9_guard` and cannot win; (b) a superior challenger that costs more than the reference wins; (c) two superior challengers: the cheaper one wins; (d) no superior challenger: the cheapest of the reference and the non-inferior ones wins, as before; (e) restricted F1 below the reference's minus 0.01 gives `fails_restricted_guard` for any challenger
- [x] T004 [US3] Fix `eval/experiments/decide.py` `e14()`: evaluate the exclusion, then the A6/A9 guard, then the restricted guard, then superiority, then non-inferiority. Pick the winner among the superior ones first, else among the reference and the non-inferior ones. Add `fails_restricted_guard` to `_loss()`. Keep the E14 result keys unchanged
- [x] T005 [US3] Prove E14 is unchanged (SC-003): run `uv run python -I eval/experiments/decide.py` and `git diff --exit-code outputs/eval/experiments.json` (byte-identical; the existing `tests/integration/test_eval_reproducible.py` must stay green). Then add `eval/experiments/recheck_jev_2026_10_11.py` (committed, under `eval/` because it reads the frozen dev set's labels, principle I), run as `uv run python -I eval/experiments/recheck_jev_2026_10_11.py`. It runs `e14()` over the committed E14 rows plus `frontend/data/jev-1.13-dev.jsonl`, prints each variant's status, and exits non-zero unless jev-1.13 is `fails_a6a9_guard` and the winner is `gpt-oss-120b`. It writes nothing. Record both results in the commit message
- [x] T006 [US3] Verify and commit: `fix(eval): check the A6/A9 guard before superiority and let a superior challenger win (E14 unchanged)`

## Phase 2: Decision adapter, US1 (slice 2)

**Goal**: `DecisionClassifier` behind `ItemClassifier`, cached and traced.
**Independent test**: a fake transport; the first call bills and traces; the replay does neither and is identical.

- [x] T007 [P] [US1] Write `tests/unit/test_decision_prompt.py`: `decision_payload(request)` equals `tests/fixtures/dec_v1_payload.json` for its 3 items; `parse_decision` accepts a valid body and takes the top probability as confidence, falls back to `confidence`, and rejects a choice outside the taxonomy, a confidence outside [0, 1], a missing `answers.category` and non-JSON (each a `ParseError`)
- [x] T008 [US1] Implement `src/expense_validator/adapters/openrouter/decision_prompt.py` (`DECISION_PROMPT_VERSION = "dec-v1"`, `DECISION_PROMPT_NAME = "classify-item-decision"`, `DECISION_INSTRUCTIONS`, criteria built from `domain/taxonomy.py` with the exploration's example text, `decision_payload`, `DecisionAnswer`, `parse_decision`)
- [x] T009 [P] [US1] Write `tests/contract/test_decision_classifier.py` with a fake transport and the 006 cache adapter on `tmp_path`: miss → one transport call, one `classify-item` generation (fields as in `contracts/decision-adapter.md`), entry cached first-write-wins; hit → no call, no generation, identical `Classification` with `cache_hit=True`; transport raises → `gateway_error`, nothing cached; offline miss → `offline_cache_miss`; cap reached → `budget_refused`; a bad choice → `schema_violation` both live and on replay. The cache key differs from `cls-v2`'s for the same request
- [x] T010 [US1] Implement `src/expense_validator/adapters/openrouter/decision_classifier.py` (`DecisionClassifier`, an httpx transport with the retry and backoff of the contract, raw bodies to `RAW_CACHE_DIR`, counters `calls_made`, `cache_hits`, `run_spend_usd`)
- [x] T011 [P] [US1] Add `sync_decision_prompt(tracer)` to `src/expense_validator/adapters/openrouter/prompt_sync.py` (`classify-item-decision`, label `dec-v1`, config `{model, endpoint: "/api/alpha/decisions", kind: "decision"}`), with a new test file `tests/unit/test_prompt_sync.py`: no-op with the no-op tracer, and a client that raises only warns (`TracingWarning`) and returns `None`
- [x] T012 [P] [US1] Add the `dec-v1` entry to `docs/ai/prompt-log.md` (instructions and criteria in English, why it exists, which experiments used it)
- [x] T013 Verify and commit: `feat: jev decision adapter behind the ItemClassifier port, cached and traced`

## Phase 3: Hybrid and factory, US1 + US4 (slice 3)

**Goal**: the hybrid merge and one factory used by every entry point. `gpt-oss-120b` behaves exactly as before.
**Independent test**: the merge table, case by case; the factory builds each name; parity unchanged.

- [ ] T014 [P] [US1] Write `tests/unit/test_hybrid_merge.py`: one test per row of the merge table in `contracts/decision-adapter.md`, including `hybrid_conflict` and `detail_violation` reported to the tracer, composite `ClassificationSource` fields, summed counters and the `cache_hit` rule
- [ ] T015 [US1] Implement `src/expense_validator/adapters/hybrid_classifier.py` (`HybridClassifier`). The `classify-receipt` span output gains `hybrid_conflict` and `detail_violation` only when true: extend the per-line dict in `src/expense_validator/app/pipeline.py:61-73` from optional attributes the hybrid exposes, without changing the output for other classifiers
- [ ] T016 [P] [US4] Write `tests/unit/test_classifier_factory.py`: `build_classifier` returns `OpenRouterClassifier` for each pin (same attributes as today), `DecisionClassifier` for `jev-1.13`, `HybridClassifier` for `jev-hybrid`, and raises `ValueError` listing the names otherwise. Extend `tests/unit/test_pipeline_config.py`: an unknown `classifier_model` is rejected at load
- [ ] T017 [US4] Implement `src/expense_validator/app/classifiers.py` (`build_classifier`, `CLASSIFIER_NAMES`). Make `default_classifier` (`src/expense_validator/app/intake.py:93`), `build_worker` (`src/expense_validator/app/composition.py:76`) and `epv run`'s openrouter path (`src/expense_validator/app/cli.py`) use it. Validate `classifier_model` in `src/expense_validator/adapters/config_files.py`
- [ ] T018 [US4] Run `tests/integration/test_api_parity.py`, `test_determinism.py` and `uv run epv run --offline --no-trace` into a temporary path: `outputs/results.jsonl` is byte-identical (SC-001 with shadow off)
- [ ] T019 Verify and commit: `feat: hybrid classifier (jev category, gpt-oss details) and one classifier factory`

## Phase 4: E16 registration and runner, US3 (slice 4)

**Goal**: E16 registered and runnable, but refused until Luis approves.
**Independent test**: `run_dev.py --experiment E16` raises `RegistrationError` before approval.

- [ ] T020 [US3] Append the E16 entry from `specs/007-jev-classifier/contracts/e16-rule.md` under `iteration_2:` in `explorations/research/experiments_plan.yaml`, with `registered_at` set to the current UTC time and `approved_by: Luis` (his approval of 2026-10-12, recorded in the contract, given before any run)
- [ ] T021 [P] [US3] Write `tests/unit/test_run_dev_e16.py`: `check_registration("E16", ...)` raises without `approved_by` and passes with it (a temporary copy of the plan); `--variant` accepts only `jev-1.13` and `jev-hybrid` for E16; the hybrid's detail side is built on the committed `explorations/results/iter2/cache/gpt-oss-120b.jsonl` (a fake transport proves no gpt-oss call for cached items)
- [ ] T022 [US3] Extend `eval/experiments/run_dev.py`: `--experiment E16`, variants built through `build_classifier` with per-variant caches under `explorations/results/iter2/cache/`, rows with the same fields as E14's plus `top_probability` and `confidence_source`, latency per item recorded, spend capped at USD 0.10 for E16, and an optional `--repeat-subset 20` pass with the cache bypassed (seed 20261012) written to `explorations/results/iter2/E16/repeat.jsonl`
- [ ] T023 [P] [US3] Write `tests/unit/test_decide_e16.py` with synthetic rows: `e16()` applies the rule of `contracts/e16-rule.md` (statuses, winner, why others lost), computes the latency median and p95, reports the repeatability k/20, and calls `e7()`'s threshold procedure for a jev winner with both confidence sources
- [ ] T024 [US3] Implement `e16()` in `eval/experiments/decide.py` and add it to `main()` only when `explorations/results/iter2/E16/` holds both variants' rows (otherwise E16 is listed as "registered, not run"). Write it into `outputs/eval/experiments.json` and `table()`
- [ ] T025 Verify and commit: `feat(eval): register E16 (jev for the category) and let run_dev run it once approved`
- [x] T026 **[GATE] Luis approves E16.** Done on 2026-10-12: Luis approved the rule in conversation, before any run, and the contract records it. Before the first live run, show him the registered entry once more and confirm it matches the contract; any change to the rule text after this point needs a new approval. Phase 5 does not depend on E16's outcome
- [ ] T027 [US3] After T026 only: run `uv run python -I eval/experiments/run_dev.py --experiment E16 --variant jev-1.13`, then `--variant jev-hybrid`, then the repeatability pass; then `uv run python -I eval/experiments/decide.py`. Commit the rows, the caches and `outputs/eval/experiments.json` with `exp: E16 jev for the category on the frozen dev set`. The message states the winner, the N and the spend. Do not change `config/pipeline.yaml` (migration is US4's runbook, a separate decision)

## Phase 5: Shadow storage and stage, US2 (slice 5)

**Goal**: with `--shadow`, every classified revision gets shadow rows; receipts are unaffected.
**Independent test**: parity with shadow on (fake transports); a shadow failure leaves the receipt untouched.

- [ ] T028 [P] [US2] Extend `tests/unit/test_sqlite_store.py` with a new fixture `tests/fixtures/schema_v2.sql`: a v2 database (spec 006's end state) holding a `pending`, a `claimed` and a `done` outbox item. The migration v2→v3:
  - rebuilds `outbox` with the `shadow` stage allowed, keeping every row and id;
  - re-creates `outbox_open`, which still rejects a duplicate pending item;
  - creates `shadow_classifications` and its index;
  - sets `user_version` to 3, and a fresh v3 database has the same `sqlite_master` as a migrated one;
  - a forced failure mid-step leaves the database at v2, unchanged.

  Also test that `save_shadow` is idempotent; `shadow_for` returns the current revision's rows; a `shadow` outbox row is claimed, leased and retried like the others; and `created_at` uses spec 006's `_ts()` format (`+00:00`, 32 characters)
- [ ] T029 [US2] Add `"shadow"` to `Stage` in `src/expense_validator/domain/lifecycle.py:25`. Add `ShadowRecord` and the three methods to `src/expense_validator/ports/store.py`. Implement them, and the v2→v3 migration step of `data-model.md` §3a–3b (outbox rebuild in the migration transaction, then the shadow table; `SCHEMA_VERSION = 3`; fresh `_SCHEMA` updated to match), in `src/expense_validator/adapters/sqlite_store.py`
- [ ] T030 [P] [US2] Write `tests/unit/test_worker_shadow.py` with `tests/fakes.py` doubles: shadow off → no shadow work; shadow on → `_classify` queues `evaluate` and `shadow` in one transaction; the shadow stage stores one row per line; a shadow transport that raises ends after `MAX_ATTEMPTS` with `unclassified` rows and the receipt's state, `failed_stage`, events and evaluations unchanged; a newer revision makes the old shadow item complete without storing anything; the shadow classifier's spend cap is separate from the primary's; `failed_stage` is never `shadow`. Tracing:
  - with `tests/fakes.py`'s recording tracer, the shadow stage opens a top-level span `shadow-classify-receipt` in the revision's trace (`app-r<revision>`, same seed);
  - it emits one `classify-item` generation per billed shadow call and none on a cache hit;
  - no observation name contains a model name.

  Langfuse down: with a tracer that raises on every call (wrapped in `GuardedTracer`, as in `tests/integration/test_langfuse_down.py`), the shadow stage still stores its rows and the receipt is unchanged (SC-007)
- [ ] T031 [US2] Implement the shadow stage in `src/expense_validator/app/worker.py` (`Worker(..., shadow: ItemClassifier | None = None)`, `_shadow(item)`, trace span `shadow-classify-receipt` in the revision's trace `app-r<revision>`) and wire `build_worker(..., shadow=name)` in `src/expense_validator/app/composition.py` through the factory, with its own cache counters and the cap
- [ ] T032 [US2] Add `--shadow {jev-1.13,jev-hybrid}` (default from `EPV_SHADOW`) and `--shadow-cap-usd` to `epv worker` and to `epv serve --with-worker` in `src/expense_validator/app/cli.py`; extend `tests/smoke/test_worker.py`
- [ ] T033 [US2] Write `tests/integration/test_shadow_parity.py`: the 32 receipts through the backend with shadow on (a fake shadow transport, the offline primary) equal `outputs/results.jsonl` byte for byte, with zero billed primary calls and one shadow row per line (78)
- [ ] T034 [P] [US2] Extend `tests/integration/test_crash_resume.py`: a shadow item interrupted mid-receipt resumes after the lease expires, with no duplicate rows
- [ ] T034a [P] [US2] Extend `tests/integration/test_firewall_scan.py` (already extended to the cache table by spec 006 T022): run the 32 receipts with shadow on (fake shadow transport), then scan `shadow_classifications`, the `GET /receipts/{id}/shadow` responses and the recorded shadow trace inputs for the answer keys (`labels`, `notes`). Zero occurrences (FR-028)
- [ ] T035 Verify and commit: `feat: shadow classification stage beside the deciding classifier`

## Phase 6: Shadow read side, US2 (slice 6)

**Goal**: see the shadow for one receipt, and the agreement report over the store.
**Independent test**: the endpoint on a stored receipt; the report on a synthetic store of 20 lines or more.

- [ ] T036 [P] [US2] Move `wilson` from `eval/stats.py` into `src/expense_validator/domain/stats.py` and re-export it from `eval/stats.py`; the existing `tests/unit/test_stats.py` passes unchanged; the architecture test stays green
- [ ] T037 [P] [US2] Write `tests/unit/test_shadow.py`: `compare()` gives `agrees_category` and `agrees_all` (names casefolded and trimmed), skips non-comparable lines from the agreement N but counts them; the report counts category, restricted, subtype and recipient-kind agreement with k/N and Wilson intervals; the confusion table; reviewer-correction matches for each side (from `LineCategoryCorrected` events, k/N)
- [ ] T038 [US2] Implement `src/expense_validator/domain/shadow.py`
- [ ] T039 [P] [US2] Write `tests/contract/test_api_shadow.py`: 200 with the shape of `contracts/api-delta.md`; 404 `not_found`; 404 `no_shadow`; the schemas appear in `openapi.json`
- [ ] T040 [US2] Add `ShadowLine` and `ShadowView` to `src/expense_validator/app/api/schemas.py` and the route to `src/expense_validator/app/api/routes.py`; regenerate `docs/api/openapi.json` with `uv run epv openapi > docs/api/openapi.json`; update the path set in `tests/smoke/test_openapi.py`
- [ ] T041 [US2] Implement `src/expense_validator/app/shadow_report.py` and `epv shadow report [--db] [--json]` in `src/expense_validator/app/cli.py`. The disposition impact re-runs `app/decide.py` over receipts whose every line has a classified shadow answer, with the context built from that set; it reports k/N and makes no call. Smoke test in `tests/smoke/test_shadow_report.py` on a temporary store
- [ ] T042 [P] [US2] Add the `GET /receipts/{id}/shadow` 404 `no_shadow` request to `docs/api/build_collection.py`, regenerate the collection, and run Newman (`specs/004-backend-lifecycle/quickstart.md`)
- [ ] T043 Verify and commit: `feat: shadow comparison endpoint and agreement report`

## Phase 7: Runbook and notes, US4 (slice 7)

- [ ] T044 [US4] Follow `specs/007-jev-classifier/quickstart.md` end to end except the migration itself and E16's live run (if T026 is still open); fix any step that does not work
- [ ] T045 [P] Add AI_NOTES entries for any assistant mistake found in this feature (what, how it was caught, what changed), and update the "Open issues" section if the cache issue is closed by 006
- [ ] T046 [P] Update `docs/roadmap.md` (iteration 6, spec 007 status) and, outside git, mark the jev entry in `../MEJORAS-ITERACION-FINAL.md`
- [ ] T047 Run `/speckit-analyze` on `specs/007-jev-classifier/` and resolve any critical finding
- [ ] T048 Final verification and PR `feat/007-jev-classifier` → `main`; tag `v1.2.0` after Luis merges. Check that the version is `1.2.0` in `pyproject.toml`, `frontend/package.json` and `docs/api/openapi.json`

## Verification commands

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
uv run pytest tests/integration/test_api_parity.py tests/integration/test_shadow_parity.py
uv run python -I eval/experiments/decide.py && git diff --exit-code outputs/eval/experiments.json   # before E16 runs
uv run epv openapi > /tmp/openapi.json && diff -q /tmp/openapi.json docs/api/openapi.json
uv run epv serve --with-worker --offline --no-trace --shadow jev-hybrid --db /tmp/epv-shadow.sqlite3   # submit docs/samples/*, then:
uv run epv shadow report --db /tmp/epv-shadow.sqlite3   # offline: shadow rows are offline_cache_miss, zero billed calls
uv run pre-commit run -a
```

## Dependencies

- Phase 1 is independent and goes first.
- Phase 2 → Phase 3 → Phase 4.
- Phase 5 needs Phase 3 (the factory) and spec 006 Phase 2 and US1 (T006–T024). Phase 6 needs Phase 5.
- T027 needs T026 (Luis). Nothing else waits for it.
