# Tasks: Intake and lifecycle backend

**Input**: `specs/004-backend-lifecycle/` (spec, plan, research, data model, contracts)

**Format**: `- [ ] T### [P?] [US?] Description with file path`. `[P]` means independent of the open
tasks around it. Story labels follow the spec: US1 idempotent intake, US2 parity and order
independence, US3 crash and resume, US4 reviewer actions, US5 revisions, US6 batches, US7 Postman.

**Rules for every task**: test first (the failing test is committed in the same commit as the code
that makes it pass); never read `data/receipts.jsonl` (use `load_receipts()` in tests, which
strips); alert Luis before any change under `src/expense_validator/domain/engine/`; everything in
English; ruff, mypy and pytest green before each commit; no `--no-verify`.

Each phase is a vertical slice that ends green and committed. If time runs out, cut from the
bottom; the product stays coherent.

## Phase 0: Refactor and housekeeping (slice 0)

- [ ] T001 Add `fastapi` and `uvicorn` to `dependencies` and `httpx` to the dev group in `pyproject.toml`; bump `version` to `0.3.0`; run `uv sync`
- [ ] T002 [P] Write `tests/unit/test_decide.py`: `decide_receipt(classified, context, meta, settings, tracer, run_label)` returns the same `ReceiptResult` as the loop body of `run_pipeline` for a one-receipt fixture, and emits the spans `retrieve-rules`, `apply-rules`, `report-exceptions`
- [ ] T003 Extract the decision step (retrieve, evaluate, report, with its trace spans) from `run_pipeline` into `src/expense_validator/app/decide.py`; make `run_pipeline` call it
- [ ] T004 Run `uv run epv run --offline --no-trace` into a temporary path and confirm `outputs/results.jsonl` is byte-identical; run the existing parity, determinism and architecture tests
- [ ] T005 Add `var/` handling: confirm `.gitignore` has `var/`; add `VAR_DIR` and `DB_FILE` (overridable with `EPV_DB`) to `src/expense_validator/paths.py`
- [ ] T006 Verify (ruff, mypy, pytest) and commit: `refactor: extract the decision step shared by epv run and the worker`

## Phase 1: Idempotent persist-first intake, US1 (slice 1)

**Goal**: submit a receipt, repeat it, read it back; nothing is processed yet.
**Independent test**: POST twice, one stored receipt; reused key with another body gives 422.

- [ ] T007 [P] [US1] Write `tests/unit/test_idempotency.py`: canonical form is key-sorted with Decimals normalised (`1.0` equals `1.00`); the hash is the same with and without answer keys (use `tests/fixtures/receipt_with_answers.json`); the default key is `<receipt_id>:<content_hash>`; keys over 255 characters are refused
- [ ] T008 [P] [US1] Write `tests/unit/test_lifecycle.py`: the transitions of data-model.md (including critical goes to `compliance`, `pass` to `auto_approved`, `review` and `flag` to `in_review`); `allowed_actions(state)` per ADR 0007 D8; an illegal transition raises
- [ ] T009 [P] [US1] Write `tests/unit/test_events.py`: every event type round-trips through JSON, unknown types are rejected, payload models forbid extra keys
- [ ] T010 [US1] Implement `src/expense_validator/domain/idempotency.py` (`canonical_receipt`, `content_hash`, `default_key`)
- [ ] T011 [US1] Implement `src/expense_validator/domain/lifecycle.py` (`State`, `Action` literals, `next_state_after_evaluation`, `allowed_actions`, `apply_action_state`)
- [ ] T012 [US1] Implement `src/expense_validator/domain/events.py` (typed events with a discriminated union)
- [ ] T013 [US1] Write `tests/unit/test_sqlite_store.py` against `tmp_path`: schema created and `user_version` set; a newer `user_version` is refused; WAL on; `record_submission` writes revision, keys, submission, event, projection and outbox row in one transaction (a forced error rolls all back); a repeated key returns `existing`; a reused client key with another body returns `conflict`
- [ ] T014 [US1] Define the `ReceiptStore` port and its transaction protocol in `src/expense_validator/ports/store.py`
- [ ] T015 [US1] Implement `src/expense_validator/adapters/sqlite_store.py` (schema, `BEGIN IMMEDIATE` transactions, injected clock, `record_submission`, reads)
- [ ] T016 [P] [US1] Write `tests/unit/test_service_submit.py`: `submit` strips answer keys before storing, returns `accepted` then `existing`, discards labels, rejects malformed input with the offending fields and stores nothing
- [ ] T017 [US1] Implement `src/expense_validator/app/service.py` `submit` (parse through `parse_receipt_line`, hash, persist-first)
- [ ] T018 [P] [US1] Write `tests/contract/test_api_receipts.py` with FastAPI `TestClient` on a temporary database: `POST /receipts` 202 then 200, 422 on key reuse and on an invalid body, `GET /receipts/{id}`, `GET /receipts/{id}/events`, `GET /receipts`, `GET /health`, error shape of contracts/api.md
- [ ] T019 [US1] Implement `src/expense_validator/app/api/` (application factory with dependency injection, routes, schemas, error handlers) for the endpoints of T018
- [ ] T020 [US1] Add `epv serve` (`--host`, `--port`, `--db`) to `src/expense_validator/app/cli.py`; smoke test in `tests/smoke/test_serve.py` that the app starts and `/health` answers
- [ ] T021 [P] [US1] Start `docs/api/epv.postman_collection.json` and `docs/api/epv.local.postman_environment.json` with the intake requests and their assertions
- [ ] T022 Verify (ruff, mypy, pytest) and commit: `feat: persist-first idempotent intake and read endpoints (iteration 3)`

## Phase 2: Worker, stages and resume, US3 (slice 2)

**Goal**: submitted receipts are classified and evaluated by a separate worker; a crash resumes.
**Independent test**: a classifier that raises after N lines, then a second `run_once`, ends with
every receipt evaluated and zero extra billed calls.

- [ ] T023 [P] [US3] Extend `tests/unit/test_sqlite_store.py`: `claim_work` returns one row and sets a lease; a second claim returns another or none; an expired lease (injected clock) makes the row claimable again; two connections never claim the same row; attempts increase
- [ ] T024 [US3] Implement claims, `complete_stage`, `record_failure` and `retry` in `src/expense_validator/adapters/sqlite_store.py`
- [ ] T025 [P] [US3] Write `tests/unit/test_worker.py` with `tests/fakes.py` doubles: the classify stage stores classifications and emits `ReceiptClassified`; the evaluate stage stores an evaluation and moves the state; a stage error sets `failed(stage, reason)`; `retry` resumes at that stage
- [ ] T026 [US3] Implement `src/expense_validator/app/worker.py` (`run_once`, `run_forever`, stage handlers using `app/decide.py`, trace label `app-r<revision>-v<version>`)
- [ ] T027 [P] [US3] Add a counting fake classifier and a `RaisesAfter(n)` classifier to `tests/fakes.py`
- [ ] T028 [US3] Write `tests/integration/test_crash_resume.py`: crash after N lines, rerun, all evaluated, results equal an uninterrupted run, billed calls equal an uninterrupted run, and the cache serves the repeated lines (SC-003 for 3 stop points)
- [ ] T029 [US3] Add `Tracer.score` to `src/expense_validator/ports/tracer.py`, the Langfuse tracer, the no-op and guarded tracers in `src/expense_validator/adapters/tracing.py`, and `RecordingTracer.score` in `tests/fakes.py`; contract test in `tests/contract/test_tracer.py` (never raises when Langfuse is down)
- [ ] T030 [US3] Add `epv worker` (`--once`, `--poll-seconds`, `--db`) and `epv serve --with-worker` to `src/expense_validator/app/cli.py`; smoke test `tests/smoke/test_worker.py` with `--once`
- [ ] T031 [US3] Add `POST /receipts/{id}/retry` to `src/expense_validator/app/api/` with contract tests (409 when not `failed`)
- [ ] T032 [P] [US3] Add worker, retry and state-polling requests to the Postman collection
- [ ] T033 Verify (ruff, mypy, pytest) and commit: `feat: leased outbox, worker stages and resume after a crash (iteration 3)`

## Phase 3: Cascade and parity, US2 (slice 3)

**Goal**: results do not depend on arrival order and equal `epv run`.
**Independent test**: the 32 receipts submitted in 5 random orders equal `outputs/results.jsonl`.

- [ ] T034 [P] [US2] Write `tests/unit/test_cascade.py`: sharing keys use the engine's `day_key` and `trip:<trip_id>`; `affected_receipts` returns receipts sharing a day or a trip; a receipt with no date or trip shares nothing; the old and the new keys are unioned for a revision
- [ ] T035 [US2] Implement `src/expense_validator/domain/cascade.py` (`sharing_keys`, `affected_receipts`) without touching `domain/engine/`
- [ ] T036 [P] [US2] Write `tests/unit/test_changed_result.py`: equal findings give no new version; different findings give a new version; the notice rules of ADR 0007 D7 for untouched, `auto_approved` and human-acted receipts
- [ ] T037 [US2] Implement the changed-result comparison and notice rules in `src/expense_validator/domain/lifecycle.py` and `src/expense_validator/domain/review.py` (result hash from R5)
- [ ] T038 [US2] Extend the store and `src/expense_validator/app/worker.py`: after classification enqueue `evaluate` for the receipt and every affected receipt; `evaluate` loads the group's classified receipts, calls `build_context` unchanged, evaluates, stores a new version only when the result changed
- [ ] T039 [P] [US2] Write `tests/integration/test_cascade_order.py`: two meal receipts for one employee-day submitted apart show MEAL-01 on both in either order, and the first gains a new evaluation version (use factories from `tests/factories.py`)
- [ ] T040 [US2] Write `tests/integration/test_api_parity.py`: submit the 32 receipts (through the stripping path of `parse_receipt_line`) in 5 shuffled orders, drain with the offline cached classifier, compare every latest result with `outputs/results.jsonl` line by line, assert zero model calls (SC-001)
- [ ] T041 [P] [US2] Write `tests/integration/test_firewall_scan.py`: after the 32-receipt run, scan the database, every API response and the recorded trace inputs for the answer keys; zero occurrences (SC-007)
- [ ] T042 [P] [US2] Add the cascade scenario to the Postman collection (two meals, one employee-day)
- [ ] T043 Verify (ruff, mypy, pytest) and commit: `feat: cascade re-evaluation and parity with epv run (iteration 3)`. If any engine change was needed, stop and alert Luis first.

## Phase 4: Revisions, US5 (slice 4)

**Goal**: a changed receipt is a new revision; the old one stays in the trail.
**Independent test**: submit `R`, then `R` changed; revision 2 evaluated, revision 1 readable.

- [ ] T044 [P] [US5] Write `tests/unit/test_revisions.py` for each row of the ADR 0007 D5 table: pending work of the old revision cancelled; superseded revision kept; closed receipts reopen; a revision that changes employee, date or trip enqueues both groups
- [ ] T045 [US5] Implement revision handling in `src/expense_validator/adapters/sqlite_store.py` (`RevisionSuperseded`, outbox cancel, key union) and `src/expense_validator/app/service.py`
- [ ] T046 [US5] Add `GET /receipts/{id}/revisions/{n}` and revision responses to `src/expense_validator/app/api/` with contract tests
- [ ] T047 [P] [US5] Add the revision scenario to the Postman collection
- [ ] T048 Verify (ruff, mypy, pytest) and commit: `feat: receipt revisions (iteration 3)`

## Phase 5: Reviewer actions and agreement scores, US4 (slice 5)

**Goal**: the four actions, correct-category re-evaluation, scores.
**Independent test**: each action through the API; state, trail and score as specified.

- [ ] T049 [P] [US4] Write `tests/unit/test_review.py`: reason code required exactly when approving a `flag` or rejecting a `pass`, `other` needs a note; the agreement table of ADR 0007 D10 for every action and proposal; `human_classification` builds a `Classification` with `confidence=1.0`, `classifier="auditor"`, `restricted` from the taxonomy, subtype and recipient kept only while the category is `other`; unknown categories are refused
- [ ] T050 [US4] Implement `src/expense_validator/domain/review.py` (`ReasonCode`, `requires_reason`, `agreement`, `human_classification`)
- [ ] T051 [P] [US4] Write `tests/unit/test_service_actions.py`: each action's state change and event; a stale `evaluation_version` gives a conflict; a disallowed state gives a conflict; `correct-category` stores a `DevCandidateMarked` event and the next evaluation uses the human category (assert through the real engine, no mock); `request-info` then a revision returns to `submitted`; the `auditor_agreement` score reaches a recording tracer and a tracer that raises does not fail the action
- [ ] T052 [US4] Implement the actions in `src/expense_validator/app/service.py` and the store (`apply_action` in one transaction with its event and outbox row for the re-evaluation)
- [ ] T053 [US4] Add `POST /receipts/{id}/actions/{action}` and `allowed_actions` in the receipt response to `src/expense_validator/app/api/` with contract tests for all five actions and every error code
- [ ] T054 [US4] Verify the audit trail and the notice rules end to end in `tests/integration/test_review_lifecycle.py` (a human-approved receipt returns to `in_review` with a notice when a later cascade changes its result)
- [ ] T055 [P] [US4] Add the five actions, a stale action and a not-allowed action to the Postman collection
- [ ] T056 Verify (ruff, mypy, pytest) and commit: `feat: reviewer actions and auditor_agreement scores (iteration 3)`

## Phase 6: Batches, US6 (slice 6)

**Goal**: bulk intake with partial success and a summary.
**Independent test**: a batch with an invalid row and a duplicate.

- [ ] T057 [P] [US6] Write `tests/unit/test_service_batch.py`: JSONL and JSON array input, per-row outcomes (`accepted`, `existing`, `revision`, `invalid`, `duplicate_in_batch`), valid rows proceed, resubmitting the batch creates nothing new; reuse the row parsing of `src/expense_validator/app/intake.py`
- [ ] T058 [US6] Implement `submit_batch` in `src/expense_validator/app/service.py` and `batches`/`batch_items` in the store
- [ ] T059 [US6] Add `POST /batches` (202 or 207) and `GET /batches/{id}` (counts per state) to `src/expense_validator/app/api/` with contract tests
- [ ] T060 [P] [US6] Add the batch scenarios to the Postman collection (good batch, batch with a bad row, repeated batch)
- [ ] T061 Verify (ruff, mypy, pytest) and commit: `feat: batch intake with partial success (iteration 3)`

## Phase 7: Postman, documentation and polish, US7 (slice 7)

- [ ] T062 [US7] Complete `docs/api/epv.postman_collection.json` so every endpoint and edge case of User Story 7 runs in order against a fresh instance, with a test script per request; add a short `docs/api/README.md` on importing and running it
- [ ] T063 [US7] Run the collection with the Postman CLI or Newman against a live `epv serve --with-worker` on a fresh database and record the outcome (use `npx newman` if available, otherwise run the same requests by script and say so)
- [ ] T064 [P] Add `docs/samples/receipt-one.json` (a synthetic receipt, no answer keys) used by the quickstart
- [ ] T065 [P] Run the quickstart of `specs/004-backend-lifecycle/quickstart.md` end to end and fix any divergence
- [ ] T066 [P] Add `docs/ai/prompt-log.md` entries for this iteration (translated to English) and `AI_NOTES.md` entries for every assistant mistake caught, with how it was caught and what changed
- [ ] T067 [P] Update `docs/roadmap.md` (iteration 3 status) and the `CLAUDE.md` module map if it lists the layout; keep the constitution unchanged unless a principle was touched
- [ ] T068 Confirm SC-008: `uv run epv run --offline --no-trace` into a temporary path is byte-identical to `outputs/results.jsonl`; confirm `git diff main -- src/expense_validator/domain/engine/` is empty
- [ ] T069 Full verification (`uv run pre-commit run -a`, pytest, ruff, mypy), push, open the pull request for Luis to merge; after the merge, tag `v0.3.0` and create the GitHub release

## Dependencies and order

- Phase 0 blocks everything. Phase 1 blocks 2 to 6. Phase 2 blocks 3 and 5 (the worker runs the stages). Phase 3 blocks 4 and 5 (the cascade and changed-result rules are used by both). Phase 6 depends only on Phase 1 and 2. Phase 7 is last.
- Within a phase, a test task comes before the code task it covers; tasks marked `[P]` touch different files and can run in parallel.
- MVP: phases 0 to 3 (intake, worker, cascade, parity). Phases 4 to 7 add revisions, review, batches and the Postman deliverable.
