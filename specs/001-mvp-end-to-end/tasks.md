---

description: "Task list for iteration 1, the end-to-end MVP"
---

# Tasks: Iteration 1, an End-to-End MVP

**Input**: Design documents from `specs/001-mvp-end-to-end/`: plan.md, spec.md,
research.md, data-model.md, contracts/ and quickstart.md.

**Prerequisites**: ADR 0002 (architecture) and ADR 0001 (decisions A1–A9). The constitution is
v1.1.0, which makes test-first mandatory for every deterministic component.

**Tests**: Requested. The constitution and ADR 0002 make them mandatory: test-first for the
loader, normaliser, FX, context, retriever, rules, disposition, reporter and eval metrics.
Contract tests cover the classifier adapters and the tracer, and smoke tests cover the CLI and
viewer. Every test task comes before the implementation task it covers, and must fail first.

**Organization**:
- **Phase 3** is a thin end-to-end path through all four stories.
- **Phases 4–7** widen one story each.
- **Phase 8** is the single cold run and the "MVP done" checkpoint.

**Standing rules for every task**:
- **Labels firewall.** Never read `labels`, `line_items[].labels` or `notes` outside `eval/`.
- **No receipt IDs in pipeline code.** Tests MAY use receipt IDs.
- **Commits.** Make small Conventional Commits.
- **Language.** Everything written is in English.
- **AI_NOTES.** Every assistant mistake caught along the way gets an `AI_NOTES.md` entry in the
  same commit as its fix.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1 validate end to end, US2 trust the engine, US3 measure honestly, US4 viewer

## Path Conventions

- **Packages:** `src/expense_validator/` (pipeline), `eval/`, `viewer/`.
- **Tests:** `tests/{unit,engine_cases,contract,architecture,integration,smoke}/`.
- **Data and outputs:** `config/` (data tables), `outputs/` (committed results).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: dependencies, packages and the entry point.

- [X] T001 Add the runtime dependencies `pydantic>=2`, `openai`, `langfuse`, `python-dotenv`, `pyyaml` and `streamlit`, and the dev dependency `types-PyYAML`, with `uv add`. Commit `pyproject.toml` and `uv.lock`
- [X] T002 Configure the build in `pyproject.toml`:
  - build `src/expense_validator`, `eval` and `viewer` as packages;
  - add `[project.scripts] epv = "expense_validator.cli:main"`;
  - set mypy `files = ["src", "eval", "viewer"]` with the pydantic plugin;
  - set pytest `testpaths = ["tests"]`.
- [X] T003 [P] Create the package skeletons, each with a docstring stating its role and firewall status: `src/expense_validator/__init__.py`, `eval/__init__.py`, `viewer/__init__.py`, and the empty `tests/` subfolders with `__init__.py`
- [X] T004 [P] Add `.cache/` (raw response bodies) and `outputs/dev/` (`--only` runs) to `.gitignore`. Create `outputs/.gitkeep` and `config/.gitkeep`
- [X] T005 Run `uv sync` and `uv run pre-commit run -a`, and confirm ruff, mypy and pytest pass with zero tests collected

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: the typed interfaces, the firewall, the rule registry and the tracer port.
Everything after this depends on them. Each test task comes first and fails first.

- [X] T006 [P] Write `tests/unit/test_models.py`. It asserts that:
  - `ReceiptInput` and `LineItemInput` reject unknown keys (`extra="forbid"`), and a `labels` or `notes` key in particular;
  - money fields are `Decimal`;
  - `Classification` enforces `subtype == "none"` unless `category == "other"`;
  - `Classification` allows a null `category` only when `status == "unclassified"`;
  - `ExceptionFinding.severity` accepts only `critical`, `high`, `medium` and `low`.
- [X] T007 Implement every model in `data-model.md` in `src/expense_validator/models.py`, frozen and in Pydantic v2: `LineItemInput`, `ReceiptInput` (with `vat_number: str | None = None`, A2), `NormalisedItem`, `ClassifierRequest` (only `description_clean`, `merchant_name` and `mcc`), `Classification`, `ClassificationSource`, `CacheEntry`, `ClassifiedReceipt`, `CrossReceiptContext`, `RuleSet`, `ExceptionFinding`, `ReviewSignal`, `EngineFindings`, `OutputLineItem`, `RunMetadata` and `ReceiptResult` [FR-003, FR-005]
- [X] T008 [P] Write `tests/unit/test_loader.py`. It asserts that: [FR-001, FR-002]
  - loading `data/receipts.jsonl` returns 32 `ReceiptInput` objects and 79 line items;
  - no `labels` key survives at any level, and no `notes` key either;
  - amounts parse as `Decimal`;
  - a hand-written JSONL with an extra answer key, in `tests/fixtures/`, raises a validation error.

  The test must never print or assert any answer value.
- [X] T009 Implement `src/expense_validator/loader.py`, ported from `explorations/lib/receipts_safe.py`. It strips `labels` and `notes` at the receipt level and `labels` at the line level immediately after `json.loads(..., parse_float=Decimal)`, then validates into `ReceiptInput`. It is the only module that opens `receipts.jsonl` [FR-001]
- [X] T010 [P] Write `tests/architecture/test_boundaries.py`, using `ast` (FR-002, constitution I and II), to fail when:
  - `models`, `normaliser`, `retriever`, `engine/*` or `reporter` import `openai`, `langfuse`, `httpx`, `requests`, `expense_validator.classification.openrouter` or `expense_validator.tracing`;
  - any module in `src/expense_validator/` or `viewer/` imports `eval`. There is one allowed exception: a lazy import inside the `eval` subcommand function of `src/expense_validator/cli.py`, and the test asserts it stays inside that function (analysis I2);
  - any module in `src/expense_validator/` or `viewer/` other than `loader.py` contains the string `receipts.jsonl`;
  - any module in `src/expense_validator/` or `viewer/` other than `loader.py` contains the string literals `"labels"` or `"notes"`. `loader.py` is exempt because it must name those keys to strip them (analysis I1).

  The scan covers `src/expense_validator/` and `viewer/` only. `tests/` and `eval/` are out of its scope.
- [X] T011 [P] Write `tests/unit/test_taxonomy.py`. It asserts that the parsed taxonomy has exactly 21 categories, with the restricted flags of `data/category-taxonomy.md`, and that `restricted_for(category)` is derived from the taxonomy, never from model output
- [X] T012 Implement `src/expense_validator/classification/taxonomy.py`, parsing `data/category-taxonomy.md` as `explorations/lib/classifier_prompt.py` does, and exposing a `Category` enum and `restricted_for()`
- [X] T013 [P] Write `tests/unit/test_settings.py`. It asserts that `engine/settings.py` reads these values from `docs/decisions/policy_decisions.yaml`: [FR-017]
  - `fx.date_basis == "transaction"`, `fx.rate_kind == "recorded"` and `fx.missing_rate_disposition == "review"`;
  - `exc03.threshold == Decimal("0.5")`;
  - `reference_prefixes == {"PA-": "pre_approval"}`;
  - decisions A1–A9 all present.
- [X] T014 Implement `src/expense_validator/engine/settings.py`, and add `config/iso4217_country_currency.csv` and `config/eur_rates.csv`. Each file has a header comment line with its source and fetch date, and the euro table may have no rows
- [X] T015 [P] Write `tests/architecture/test_evidence_verbatim.py`. For every `RuleSpec` in the registry, `evidence` must be an exact substring of `data/policy-docs/<policy_doc>` after whitespace is collapsed and `**` markers are removed. The registry must contain exactly the 37 in-scope rule IDs and no TIME rule [FR-018, SC-005]
- [X] T016 Implement `src/expense_validator/engine/registry.py` with all 37 `RuleSpec` entries, taken from the spec's Rule Catalogue: `rule_id`, `policy_doc`, severity or effect, scope, the decision A-IDs, and one verbatim evidence sentence. Add `rules_version()`, a 12-hex SHA-256 over the engine package source, `policy_decisions.yaml` and the policy docs in sorted order (research R8) [FR-012, FR-018, FR-024]
- [X] T017 [P] Write `tests/contract/test_tracer.py`. It asserts that: [FR-026, FR-028]
  - `NoopTracer` satisfies the `Tracer` protocol;
  - `make_tracer()` returns `NoopTracer` with one warning when the keys are missing;
  - a tracer whose methods raise is swapped for `NoopTracer` mid-run, with one warning;
  - `flush` returns within its timeout even when the exporter blocks, using a fake blocking exporter.
- [X] T018 Implement `src/expense_validator/tracing.py` as research R6 and `contracts/tracing.md` describe: [FR-026, FR-028]
  - the `Tracer` protocol: `receipt_trace`, `span`, `generation` and `flush`;
  - `NoopTracer`;
  - `LangfuseTracer`, with `create_trace_id(seed=f"{run_label}:{receipt_id}")` applied through `trace_context`, `auth_check()` with a short timeout, and swap-to-noop on error;
  - `flush` in a daemon thread joined with a timeout.

  Before coding, confirm the installed `langfuse` API through the Langfuse docs MCP.

**Checkpoint**: interfaces, firewall, registry and tracer are in place. `uv run pytest` is green.

---

## Phase 3: Thin End-to-End Path (all stories, minimal depth)

**Goal**: one receipt goes through every component, and `epv run`, `epv eval` and `epv view` all
work. The engine knows only EXC-01, MCC-02 and TECH-02 here.

**Independent test**: on the committed cache, `uv run epv run --offline`, then
`uv run epv eval`, then `uv run epv view` all succeed. The TECH-02 brief cases (RCP-006 and
RCP-026) pass as engine tests.

- [X] T019 [P] [US1] Write `tests/unit/test_normaliser.py`. It asserts: [FR-004]
  - NFKC normalisation and collapsed whitespace;
  - `description_raw` unchanged;
  - `language` preserved;
  - the same output for the same input;
  - full-width Japanese and accented Latin text survive.
- [X] T020 [US1] Implement `src/expense_validator/normaliser.py`: a pure `normalise(receipt) -> list[NormalisedItem]`, with no translation (spec FR-004)
- [X] T021 [P] [US1] Write `tests/contract/test_classifier_request.py`. It asserts that `ClassifierRequest` built from any receipt carries only `description_clean`, `merchant_name` and `mcc`, never `submitted_expense_type` or `attendee_count` (FR-007), and that the user message built by `prompt.py` contains no other receipt field [FR-007]
- [X] T022 [US1] Implement the `ItemClassifier` protocol and `ClassifierRequest` construction in `src/expense_validator/classification/port.py`, and a `FakeClassifier` in `tests/fakes.py`, a mapping from description to `Classification`
- [X] T023 [P] [US1] Write `tests/contract/test_prompt_schema.py`. It asserts that: [FR-005, FR-006, FR-009]
  - the `cls-v2` strict schema equals `specs/001-mvp-end-to-end/contracts/classifier-output-cls-v2.schema.json`;
  - `parse()` accepts a valid answer;
  - `parse()` turns invalid JSON, an unknown category, a confidence outside [0, 1], a subtype other than `none` on a non-`other` category, and extra keys each into `unclassified` with reason `schema_violation`.
- [X] T024 [US1] Implement `src/expense_validator/classification/prompt.py`: `PROMPT_VERSION = "cls-v2"`, ported from `explorations/lib/classifier_prompt.py`. Extend the system prompt with the closed subtype (A6) and the recipient fields (A9), and add `RESPONSE_FORMAT_STRICT` and `parse()` [FR-005, FR-006]
- [X] T025 [P] [US1] Write `tests/unit/test_cache.py`. It asserts that: [FR-008]
  - the cache key is the SHA-256 of the canonical JSON of the cleaned text, merchant, MCC, model ID, endpoint and prompt version;
  - a change in any of those is a miss;
  - rows are written sorted by key with a trailing newline;
  - writing and reading round-trips byte for byte.
- [X] T026 [US1] Implement `src/expense_validator/classification/cache.py` over `outputs/classifications.jsonl`, plus raw bodies under `.cache/raw/` [FR-008]
- [X] T027 [P] [US1] Write `tests/contract/test_openrouter_adapter.py` with a fake HTTP transport. It asserts that: [FR-009, FR-025, FR-026]
  - the request uses model `openai/gpt-oss-120b`, provider order `["deepinfra/bf16"]` with `allow_fallbacks: false` and `require_parameters: true`, temperature 0 and the strict response format;
  - `usage.cost` and the request id are recorded;
  - a transport error gives `unclassified/gateway_error`;
  - the cap (USD 1.00) refuses the call with `unclassified/budget_refused`;
  - `--offline` never calls the transport;
  - one `classify-item` generation is emitted per billed call, and none on a cache hit.
- [X] T028 [US1] Implement `src/expense_validator/classification/openrouter.py`, porting the pinning, cap and cost reading from `explorations/lib/budget.py` (FR-025, FR-026). It uses `.env` through `python-dotenv`, never logs the key, and emits the generation fields in `contracts/tracing.md`, including the link to the Langfuse prompt `classify-item-chat` at label `cls-v2`. Add `src/expense_validator/classification/prompt_sync.py` with `sync_prompt(tracer)`. It creates `classify-item-chat` in Langfuse Prompt Management with the label `cls-v2`, only when the stored text or config differs (ported from `explorations/scripts/langfuse_log_e13.py`). It is a no-op with `NoopTracer`. The pipeline calls it once before the first billed call of a run (analysis C1)
- [X] T029 [P] [US2] Write `tests/unit/test_disposition.py` for EXC-01: [FR-016]
  - any critical, high or medium exception gives `flag`;
  - otherwise, any low exception or any review signal gives `review`;
  - otherwise `pass`;
  - the result is the same for any order of findings.
- [X] T030 [US2] Implement `src/expense_validator/engine/disposition.py` [FR-016]
- [X] T031 [P] [US2] Write `tests/engine_cases/test_brief_thin.py`, with the brief's threshold boundary. RCP-006 and RCP-026 are loaded through the loader, with `Classification`s written by hand from their descriptions, never from labels. RCP-006 has a $189 accessory and raises no TECH-02. RCP-026 has a $329 monitor without pre-approval and raises TECH-02 at medium, citing the monitor line. Also test MCC-02 alone (RCP-028): no exceptions, one MCC-02 review signal, disposition `review`
- [X] T032 [US2] Implement `src/expense_validator/engine/rules/technology.py` (TECH-02 only, judged on unit price in USD, `>` $200, with the `PA-` reference satisfying it per A5), `src/expense_validator/engine/rules/merchant.py` (MCC-02 only), and `src/expense_validator/engine/evaluate.py` with `evaluate(receipt, context, ruleset, settings) -> EngineFindings` and the one-per-rule merge
- [X] T033 [P] [US1] Write `tests/unit/test_retriever.py` for the thin path. TECH-02 is selected when a `computer_accessory` is present. MCC-02 is selected for a medium-tier MCC. The output is a sorted tuple [FR-010]
- [X] T034 [US1] Implement `src/expense_validator/retriever.py` with the trigger-map structure (research R10), holding only these two triggers for now
- [X] T035 [P] [US1] Write `tests/unit/test_reporter.py`. A TECH-02 finding gets an explanation naming the rule, the line and `unit_price_usd` against `cap_usd`. The reporter adds no claim missing from `computed` [FR-022]
- [X] T036 [US1] Implement `src/expense_validator/reporter.py`: pure templates keyed by `rule_id`, filling `explanation` and building `ReceiptResult` with `RunMetadata`, where `exc03_threshold_status` is `"provisional"` [FR-022, FR-024]
- [ ] T037 [US1] Implement `src/expense_validator/pipeline.py`: load, normalise, classify (cache first), `build_context` (an empty stub for now), then retrieve, evaluate and report for each receipt in `receipt_id` order, then write canonical `outputs/results.jsonl` (research R9). Wrap every stage in the tracer spans named in `contracts/tracing.md` [FR-023, FR-026]
- [ ] T038 [US1] Implement `src/expense_validator/results.py` (read-only `load_results(path)` and `load_comparison(path)`) and `src/expense_validator/cli.py` (FR-035), as `contracts/cli.md` describes:
  - `epv run [--classifier] [--offline] [--no-trace] [--only RECEIPT_ID ...]`;
  - `epv eval`, which imports `eval` lazily inside its subcommand function only (analysis I2);
  - `epv view`.

  `--only` is a development option. With it, `epv run` writes to `outputs/dev/results.jsonl`, never to `outputs/results.jsonl`, and still writes cache rows. The stderr summary shows receipts, calls, cache hits, billed USD and tracer state
- [ ] T039 [US1] Thin-path cold run, with Langfuse up: `uv run epv run --only RCP-006 RCP-026` (the development option in `contracts/cli.md`, analysis U1). First confirm that `sync_prompt` pushed `classify-item-chat`/`cls-v2`. Then confirm that every `classify-item` generation of this run links that prompt (constitution X, analysis C1). Commit the resulting cache rows. Record the spend in the commit message
- [ ] T040 [P] [US3] Write `tests/unit/test_eval_compare_thin.py` with synthetic predictions and answers built in the test, never read from the data. It checks the 3×3 disposition matrix and the exclusion of the four out-of-scope receipts listed in `eval/scope.py`
- [ ] T041 [US3] Implement `eval/answers.py` (the only reader of answer fields), `eval/scope.py`, `eval/compare.py` (disposition only for now), and `eval/report.py`, which writes `outputs/eval/comparison.jsonl`, `outputs/eval/metrics.json` (`{value, n}`) and `outputs/eval/report.md` [FR-029]
- [ ] T042 [US4] Implement the list view of `viewer/app.py`: each receipt's predicted against answer disposition, with mismatches highlighted. It reads through `expense_validator.results` only [FR-034]
- [ ] T043 [P] [US4] Write `tests/smoke/test_viewer.py` with Streamlit's `AppTest`: the app loads offline from the committed outputs without errors
- [ ] T044 [US1] Write `tests/integration/test_thin_path.py`. It runs `epv run --offline`, then `epv eval`, on the committed cache, checks that the output exists and that a second run is byte-identical, and confirms the tracer falls back to no-op without keys [SC-003, SC-007]

**Checkpoint (thin path)**: run, eval and view work end to end. Commit and push. The pipeline
now has its full shape; every phase after this only widens it.

---

## Phase 4: User Story 2, Trust the Engine (Priority: P1)

**Goal**: all 37 in-scope rules, built test-first, module by module.

**Independent test**: `uv run pytest tests/unit tests/engine_cases` passes with no key and no
network.

- [ ] T045 [US2] Convert `explorations/dev_set/engine_cases_draft.jsonl` into `tests/engine_cases/fixtures/engine_cases.jsonl`, marked `status: DRAFT`:
  - add `subtype: "none"`, `recipient_kind` and `recipient_name` to every item, derived from the case's own line text and `why`;
  - list every added value in `tests/engine_cases/fixtures/CONVERSION_NOTES.md`, for Luis's review (SC-010);
  - add a loader and a parametrised runner in `tests/engine_cases/test_synthetic_cases.py`. Cases whose rules are not implemented yet are marked `xfail(strict=True)` with the reason.
- [ ] T046 [P] [US2] Write `tests/unit/test_fx.py`: [FR-013]
  - USD amounts are unchanged;
  - foreign amounts × `fx_rate_to_usd` give USD in `Decimal`;
  - the EUR 70 and EUR 50 thresholds use the receipt's own rate for a EUR receipt;
  - a non-EUR receipt with no table rate returns a `MissingRate` outcome, and the engine then sends the receipt to review (A1);
  - `date_basis` and `rate_kind` default to `transaction` and `recorded`.
- [ ] T047 [US2] Implement `src/expense_validator/engine/fx.py`
- [ ] T048 [P] [US2] Write `tests/unit/test_documentation_rules.py`: [FR-012]
  - DOC-01: non-itemized above $75 gives medium;
  - DOC-02: a missing merchant, date or total gives medium;
  - DOC-03: no line in the categories covered by the declared type gives medium, with service fee, gratuity and `other` ignored, and no exception when no lines remain;
  - DOC-04: a non-USD receipt missing its currency or rate gives medium.

  All of them cite empty `line_ids`.
- [ ] T049 [US2] Implement `src/expense_validator/engine/rules/documentation.py` with the DOC-03 table from `receipt-documentation-requirements.md`
- [ ] T050 [P] [US2] Write `tests/unit/test_merchant_rules.py`. MCC-01 is high, with empty `line_ids`, for 5921, 5993, 7995, 7297 and 5944. MCC-02 is always its own signal, even alongside an exception. An MCC not in the table is low tier. MCC-03 treats 5813 as on-premises [FR-020]
- [ ] T051 [US2] Complete `src/expense_validator/engine/rules/merchant.py` (MCC-01, MCC-02 and MCC-03, with the tier table)
- [ ] T052 [P] [US2] Write `tests/unit/test_technology_rules.py`: [FR-013, FR-014]
  - TECH-01: personal electronics give high;
  - TECH-02: a unit price above $200 without a `PA-` reference gives medium, and $200.00 exactly does not;
  - TECH-03: `other` with `subtype=mobile_handset` gives high;
  - TECH-04: a software subscription gives low, and a `PA-` reference does not satisfy it (A5).
- [ ] T053 [US2] Complete `src/expense_validator/engine/rules/technology.py`
- [ ] T054 [P] [US2] Write `tests/unit/test_non_reimbursable_rules.py`: [FR-014]
  - PERS-01 and PERS-02 give medium, and the baggage carve-out never applies with a `PA-` reference (A5);
  - PERS-03 gives high;
  - HOUSE-01 gives medium;
  - LAUNDRY-01 gives low for fewer than 4 nights or no trip, and nothing at 4 nights or more;
  - HEALTH-01 gives low for OTC with no trip, medium for `subtype=prescription_medication`;
  - A4: when a trip's OTC total across receipts is above $25, HEALTH-01 is raised as low on **every** receipt of that trip with OTC lines, each citing only its own medication lines. A trip total of exactly $25.00 raises nothing (analysis G2).
- [ ] T055 [US2] Implement `src/expense_validator/engine/rules/non_reimbursable.py` (the HEALTH-01 trip total is read from the context; see T057)
- [ ] T056 [P] [US2] Write `tests/unit/test_context.py`: [FR-021]
  - meal spend uses `food_beverage`, `alcohol` and `service_fee` lines, or the total when non-itemized;
  - per person divides by the attendee count, or by 1 when it is null;
  - one employee's meal receipts on the same calendar date are added up;
  - international means the receipt currency differs from the home currency (A8, the config table);
  - a mixed day uses the higher cap;
  - the trip OTC total adds `health_otc` lines over the trip;
  - uncertain items are excluded;
  - a shuffled input gives an identical context.
- [ ] T057 [US2] Implement `src/expense_validator/engine/context.py` with `build_context(classified_receipts) -> CrossReceiptContext`
- [ ] T058 [P] [US2] Write `tests/unit/test_meals_rules.py`: [FR-014]
  - MEAL-01 gives medium on every contributing receipt of a breached day, at $75 domestic and $100 international, with empty `line_ids`;
  - MEAL-02 gives low when the meal receipt total is above $150 and the attendee count is null;
  - ALC-01 gives high unless the receipt is Client Entertainment with 2 or more attendees, at MCC 5812, 5813 or 7011;
  - ALC-02 gives medium above $30 per attendee;
  - ALC-03 gives high for alcohol at any other MCC;
  - ENT-01 gives medium for `subtype=event_ticket` without a VP reference;
  - ENT-02 gives high.

  Gratuity lines are never in `line_ids`.
- [ ] T059 [US2] Implement `src/expense_validator/engine/rules/meals.py`
- [ ] T060 [P] [US2] Write `tests/unit/test_gifts_rules.py`: [FR-006]
  - GIFT-01 applies only when the receipt is declared Client Gifts or `recipient_name` is set (A7). It caps $50 per `recipient_name` per receipt, requires a name for any gift of $10 or more, and raises one exception citing every line;
  - GIFT-02 gives high for `gift_card`, and those lines are not tested under GIFT-01;
  - GIFT-03 gives medium for `recipient_kind=employee`;
  - GIFT-04 gives critical for `recipient_kind=government_official`. It covers meal lines but not gratuities, and replaces GIFT-01 for those lines, while the meal cap still applies.
- [ ] T061 [US2] Implement `src/expense_validator/engine/rules/gifts.py`
- [ ] T062 [P] [US2] Write `tests/unit/test_regional_rules.py`: [FR-015]
  - REG-01: APAC alcohol gives high and replaces ALC-01, ALC-02 and ALC-03, while MCC-01 still applies;
  - REG-02: the APAC $60 per person per day cap gives medium and replaces MEAL-01;
  - REG-03: the EMEA EUR 70 cap, converted at the transaction-date euro rate, gives medium and replaces MEAL-01;
  - REG-04: an EMEA receipt above EUR 50 with `vat_number` None gives low (A2);
  - REG-05 raises nothing.
- [ ] T063 [US2] Implement `src/expense_validator/engine/rules/regional.py`, with the overrides applied in `evaluate.py`
- [ ] T064 [P] [US2] Write `tests/unit/test_uncertainty.py`: [FR-017, SC-006]
  - confidence below 0.5 gives one EXC-03 signal citing the line;
  - an `unclassified` item gives EXC-03 with its reason;
  - an uncertain item is excluded from every rule's input, meal spend, DOC-03 and the gift caps;
  - a non-itemized `other` raises no EXC-03;
  - a receipt with EXC-03 is never `pass`.
- [ ] T065 [US2] Implement `src/expense_validator/engine/uncertainty.py` and wire it into `evaluate.py`, before the rules run
- [ ] T066 [P] [US2] Write `tests/engine_cases/test_brief_cases.py` with all five brief cases. Their classifications are written by hand from the descriptions, never from labels. The expected behaviour comes from the brief text only: [SC-002]
  - RCP-027 raises PERS-02;
  - RCP-016 raises REG-01 and no ALC rule;
  - RCP-006 and RCP-026 behave as in T031;
  - RCP-031: a single low exception gives `review`;
  - RCP-028: an MCC-02 signal alone gives `review`.
- [ ] T067 [US2] Complete the retriever's trigger map in `src/expense_validator/retriever.py` for all 37 rules (research R10). Add `tests/unit/test_retriever_superset.py`: on every engine fixture, `set(raised rule_ids)` must be a subset of the retrieved set [FR-010, FR-011]
- [ ] T068 [US2] Extend the reporter templates in `src/expense_validator/reporter.py` to every exception and signal rule. Each one states the lines and the `computed` arithmetic: per-person against the cap, unit price against $200, the EUR conversion. Extend `tests/unit/test_reporter.py` to cover one template per rule [FR-022]
- [ ] T069 [US2] Remove every `xfail` from `tests/engine_cases/test_synthetic_cases.py`. A remaining failure is resolved against the policy text and recorded in `CONVERSION_NOTES.md`, never by editing the expected value to match the code [SC-002]
- [ ] T070 [US2] Write `tests/integration/test_determinism.py`: [SC-003]
  - the pipeline runs twice from the committed cache with `NoopTracer` and gives byte-identical output;
  - the receipts are shuffled and the output is identical;
  - a fake recording tracer gives output identical to `NoopTracer` (FR-028);
  - every payload the recording tracer captured is free of answer data (FR-027, analysis G1). It checks two things:
    - none of the answer-only keys `labels`, `notes` and `expected_exceptions` appears;
    - no answer-only text appears: each receipt's `notes` text and every answer `reason` string, loaded through `eval/answers.py` inside the test.

    It does not check keys such as `disposition` or `review_signals`, because the pipeline's own outputs legitimately contain them.

**Checkpoint**: all 37 rules are tested, the brief and synthetic cases pass, and the run is
deterministic.

---

## Phase 5: User Story 1, Validate End to End (Priority: P1)

**Goal**: the full pipeline is hardened: the keyword-classifier, the schema export, offline
safety and the trace shape.

**Independent test**: quickstart scenarios 2–6.

- [ ] T071 [P] [US1] Write `tests/unit/test_keyword_classifier.py`:
  - it implements `ItemClassifier`;
  - lowercase keyword lists for the six languages are written from the taxonomy's examples;
  - unmatched items are `food_beverage` at MCC 5812, 5813 or 7011, and `other` otherwise;
  - confidence is 1.0;
  - a contamination guard checks that no keyword entry equals any real `description_raw`, loaded through the loader.
- [ ] T072 [US1] Implement `src/expense_validator/classification/keyword.py`, and route `epv run --classifier keyword` to `outputs/baselines/keyword_classifier/results.jsonl` [FR-032]
- [ ] T073 [P] [US1] Write `tests/contract/test_result_schema.py`. The `ReceiptResult` JSON Schema export must equal the committed `specs/001-mvp-end-to-end/contracts/receipt-result.schema.json`. Every invariant in `contracts/receipt-result.md` must hold on `outputs/results.jsonl` [FR-018, FR-019, FR-023, SC-005]
- [ ] T074 [US1] Export and commit `specs/001-mvp-end-to-end/contracts/receipt-result.schema.json` from `ReceiptResult`
- [ ] T075 [P] [US1] Write `tests/integration/test_offline_fallback.py`. Running with an empty cache and `--offline` makes every line `unclassified/offline_cache_miss` and no receipt `pass` (SC-006) [FR-009, SC-006]
- [ ] T076 [US1] Verify the trace shape against a running local Langfuse, following quickstart scenario 6 and `docs/ai/langfuse-guide.md`. Re-classify one item on a cold cache in a scratch copy, then confirm the `classify-item` generation fields and the prompt link `classify-item-chat`/`cls-v2`. Push prompt `cls-v2` to Langfuse Prompt Management. Update `docs/ai/langfuse-guide.md` with the pipeline trace shape [FR-026, SC-007]

**Checkpoint**: US1 is complete except for the full cold run (Phase 8).

---

## Phase 6: User Story 3, Measure Honestly (Priority: P2)

**Goal**: every FR-030 and FR-031 item, for the pipeline and both baselines, each with its N.

**Independent test**: quickstart scenarios 7–8.

- [ ] T077 [P] [US3] Write `tests/unit/test_eval_metrics.py` with hand-computed toy data built in the test: [FR-030]
  - macro F1 over the categories present in the answers, where a never-predicted category counts as zero precision;
  - restricted F1 with true as the positive class;
  - false positives out of 9 and missed violations out of 16;
  - Wilson 95 % intervals;
  - every metric returns `{value, n, interval?}`.
- [ ] T078 [US3] Implement `eval/metrics.py`
- [ ] T079 [P] [US3] Write `tests/unit/test_eval_compare.py`: [FR-031]
  - an exception matches on (receipt, `rule_id`);
  - `evidence_exact` means the `line_ids` are equal, and both are empty for whole-receipt rules;
  - signals match on (receipt, `rule_id`);
  - per-rule recall is 0 for a rule never raised, with precision n/a;
  - EXC-03 signals are counted as unmatched, along with the dispositions they changed;
  - the count of REG-04 exceptions coming only from an absent `vat_number` is reported (A2).
- [ ] T080 [US3] Complete `eval/compare.py` and the per-rule and evidence sections of `eval/report.py`
- [ ] T081 [P] [US3] Write `tests/unit/test_keyword_flagger.py`. Any restricted keyword on a line gives `flag`, otherwise `pass`. It reuses the keyword lists from `classification/keyword.py`. Macro F1 is reported as `n/a`
- [ ] T082 [US3] Implement `eval/baselines.py` (`keyword-flagger`, writing `outputs/baselines/keyword_flagger/results.jsonl`), and make `epv eval` score all three systems [FR-032]
- [ ] T083 [P] [US3] Write `tests/unit/test_base_rate.py`. From the measured false-positive and missed-violation rates, it computes true and false flags per 10,000 receipts at 1 %, 3 % and 5 % prevalence. It checks the result against hand arithmetic, and passes the Ns through
- [ ] T084 [US3] Implement `eval/base_rate.py`. Add to `eval/report.py` the base-rate table and two marked slots, `Failure case 1` and `Failure case 2`, each with "stage: TBD in iteration 3" [FR-033]
- [ ] T085 [US3] Implement `eval/scores.py`. When Langfuse is reachable, it posts `disposition_correct`, `category_correct_rate`, `exceptions_matched` and `exceptions_extra` on the deterministic trace IDs. Otherwise it warns and skips. Add a test that it is a no-op without keys [FR-027]
- [ ] T086 [US3] Write `tests/integration/test_eval_reproducible.py`. `epv eval` run twice gives byte-identical `outputs/eval/*`, makes no model call, and needs no key [FR-029, SC-004]

**Checkpoint**: the evaluation report is complete and reproducible.

---

## Phase 7: User Story 4, Browse Results (Priority: P3)

**Goal**: the three viewer views the brief asks for.

**Independent test**: quickstart scenario 9.

- [ ] T087 [US4] Add the receipt detail view to `viewer/app.py`: [FR-034, SC-009]
  - line items with category, confidence, subtype and recipient fields;
  - exceptions with `rule_id`, `policy_doc`, `line_ids`, the literal `evidence`, the `explanation` and the `computed` values;
  - review signals;
  - the answer alongside, from `outputs/eval/comparison.jsonl` only (FR-034).
- [ ] T088 [US4] Add the metrics view to `viewer/app.py`. It renders `outputs/eval/metrics.json` for the three systems, every value with its N, the confusion matrix and the base-rate table [FR-034]
- [ ] T089 [US4] Extend `tests/smoke/test_viewer.py`. All three views render offline, and a receipt's detail matches its line in `outputs/results.jsonl` [SC-009]

**Checkpoint**: the viewer can be used for the demo.

---

## Phase 8: Cold Run and "MVP done" Checkpoint

- [ ] T090 Run the full cold classification once, with `uv run epv run`, Langfuse up and the `.env` key. Then run `uv run epv run --classifier keyword` and `uv run epv eval`. Commit `outputs/` with an `exp:` commit stating the model, endpoint, prompt version, billed USD from the stderr summary, and the cache hit count [SC-001, SC-008]
- [ ] T091 Re-run `uv run epv run --offline` and `uv run epv eval`. Confirm `git diff --exit-code outputs/` is clean (SC-003, SC-004) [SC-003, SC-004]
- [ ] T092 Ask Luis to review the 13 converted engine cases and `tests/engine_cases/fixtures/CONVERSION_NOTES.md` against the policy text. Record the outcome per case in `tests/engine_cases/fixtures/REVIEW.md` (who, date, changes and reasons), and flip `status` to `REVIEWED` (SC-010). Add the checked items to the "Checked by hand" section of `AI_NOTES.md` [SC-010]
- [ ] T093 **MVP done.** Run every scenario in `specs/001-mvp-end-to-end/quickstart.md` on a clean checkout, and tick each roadmap iteration 1 exit criterion in `docs/roadmap.md`. Record in the PR description a scenario-by-scenario pass list, with the spend against the USD 1.00 cap (SC-008)

**Checkpoint**: the MVP is done. Iteration 1 is shippable.

---

## Phase 9: Polish and Cross-Cutting Concerns

- [ ] T094 [P] Update `AI_NOTES.md` with every assistant mistake caught during iteration 1: what happened, how it was caught and what changed. Update the "Assistants and what they did" table
- [ ] T095 [P] Update `docs/ai/prompt-log.md` with this session's outcome, and the implementation session's important prompts, translated into English, with their outcomes
- [ ] T096 [P] Update `explorations/INDEX.md` to say which `explorations/lib` modules were ported into `src/`, and that explorations stay frozen
- [ ] T097 Run `uv run pre-commit run -a` and `uv run pytest`. Open the iteration 1 PR and merge it after review

---

## Dependencies & Execution Order

- **Setup (Phase 1)**, then **Foundational (Phase 2)**, then the **Thin path (Phase 3)**. These
  run strictly in order, because each one blocks the next.
- **Phase 4 (US2)** depends on Phase 3. **Phase 5 (US1)** depends on Phase 3 and can run
  alongside Phase 4. T072 must finish before T082.
- **Phase 6 (US3)** depends on Phase 3. Its full numbers need Phase 4, because the dispositions
  need every rule.
- **Phase 7 (US4)** depends on the Phase 6 outputs.
- **Phase 8** depends on Phases 4–7. **Phase 9** comes last.
- **Inside every phase:** the test task comes before its implementation task and must fail
  first (constitution v1.1.0).

## Parallel Opportunities

- **Phase 2:** T006, T008, T010, T011, T013, T015 and T017 are independent test files.
- **Phase 4:** the rule-module test tasks (T046, T048, T050, T052, T054, T056, T058, T060, T062,
  T064) are independent files. Each implementation follows its own test.
- **Phase 6:** T077, T079, T081 and T083 are independent test files.

```text
Example, Phase 4:
  Task: "Write tests/unit/test_documentation_rules.py (T048)"
  Task: "Write tests/unit/test_technology_rules.py (T052)"
  Task: "Write tests/unit/test_gifts_rules.py (T060)"
```

## Implementation Strategy

1. **Thin path first** (Phases 1–3). As soon as one receipt runs through `run`, `eval` and
   `view`, the shape of the whole system is real and can be demonstrated.
2. **Widen in this order:**
   1. the engine (US2), which is what the panel probes most;
   2. pipeline hardening (US1);
   3. the evaluation (US3);
   4. the viewer (US4).
3. **One cold run**, then **"MVP done"** (T093).
4. **Out of scope** (`docs/roadmap.md`). No task here builds:
   - a queue, worker, auth, API, database or new UI (L1–L4);
   - policy deployment (L5);
   - TIME rules (L6);
   - non-model observability (L7);
   - any iteration 2 experiment (E5, E7, E14, retriever or reporter variants, oracle ablation);
   - any iteration 3 deliverable (README, AWS page, failure-case write-ups).
