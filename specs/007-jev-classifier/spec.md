# Feature Specification: jev classifier, shadow mode and experiment E16

**Feature Branch**: `feat/007-jev-classifier`

**Created**: 2026-10-12

**Status**: Draft

**Release**: v1.2.0 (final iteration)

**Input**: User description (Luis, 2026-10-12, translated): "Reconsider whether jev is an option:
build one adapter for gpt-oss-120b and another for jev, and run both as part of A/B tests, because
it really does seem to give good results. Shadow mode plus a registered E16, and we must be ready
in case we want to migrate to jev."

**Depends on**: spec 006 (api-hardening), Phase 2 and US1 (T006–T024). This spec needs 006's
`ClassificationCachePort` (`ports/classification_cache.py`), its table adapter
`SqliteClassificationCache` (`adapters/sqlite_cache.py`) and its ordered schema migrations
(`SCHEMA_VERSION = 2`). If they are not merged when this work starts, implement them first. This
spec's migration is schema version 3.

## Context

The pipeline classifies every line item with `openai/gpt-oss-120b` through OpenRouter (prompt
`cls-v2`). That model won experiment E14 on the frozen dev set (N = 130, SHA-256 `5f34f08e…`,
ADR 0005). On 2026-10-11 the front-end session ran TypeSafe's decision model `typesafe/jev-1.13`
on the same 130 items, through OpenRouter's `POST /api/alpha/decisions` endpoint with the E13
payload `dec-v1` (`frontend/scripts/jev_dev_run.py`). The result is in
`frontend/data/classifier-comparison.json`:

| Variant | Category accuracy | Restricted F1 | A6/A9 items wrong | USD per 1,000 items |
|---|---|---|---|---|
| gpt-oss-120b (reference) | 123/130 | 0.9912 | 2/29 | 0.0608 |
| jev-1.13 | 130/130 | 1.000 | 23/29 | 0.0426 |

- **McNemar:** b = 7 items right only for jev, c = 0 right only for the reference, exact p = 0.0156.
- **Paired bootstrap:** 95 % interval of the difference [+0.015, +0.100].
- **Calibration:** jev's top probability has Brier 0.0109 (N = 130). gpt-oss-120b's self-reported
  confidence has Brier 0.0365 (N = 128).
- **Latency (jev):** mean 0.59 s per item, p95 1.06 s.

### Why jev has not been adopted

1. **It answers only the category.** The decision endpoint returns a choice over the 21
   categories, so no subtype (A6) and no recipient (A9). The engine needs both:
   - ENT-01, TECH-03 and HEALTH-01 read the subtype;
   - GIFT-01, GIFT-03 and GIFT-04 read the recipient.

   jev got 23 of the 29 items that exercise A6/A9 wrong, because the script hard-codes `none`.
2. **It was never a registered experiment.** The 2026-10-11 run is evidence, not a decision
   (ADR 0008 §6). The iteration-2 amendment of E14 removed decision models from the candidates
   precisely because `cls-v2` needs subtype and recipient. Constitution principle V requires a
   decision rule written before the run.
3. **Earlier evidence was weak.** In E13, on the 109-item draft set, jev's advantage was not
   significant: b = 4, c = 0, p = 0.125 (`explorations/results/05_results.json`).
4. **It is early access and not deterministic.** Repeated calls can differ (E8, and
   `explorations/research/05_technical_spike.md`), so only a cache makes a run reproducible.
5. **The decision code has a gap.** `eval/experiments/decide.py` tests "superior" before the
   A6/A9 guard (lines 137–146). It therefore labels jev-1.13 "superior" although it fails the
   guard by 21 items. A second gap: the winner is the cheapest of all qualifying models, the old
   reference included (line 153). So a *superior* challenger that costs more than the reference
   would lose on cost, which contradicts E14's text ("a challenger becomes the reference").

None of this rules out a **hybrid**: jev for the category (and its confidence), and gpt-oss-120b
for subtype and recipient. That is what this spec builds, measures (E16) and prepares to adopt.

### Constraints from the constitution

- **Principle I, labels firewall.** No adapter, shadow record, report or trace reads or carries
  `labels`, `line_items[].labels` or `notes`. Only `eval/` reads the dev set's answers.
- **Principle II, deterministic decisions.** The engine, the retriever and the disposition logic
  do not change. A different classifier changes inputs to the engine, never the engine.
- **Principle V, decide on dev, report on test.** jev becomes the classifier only through a
  registered E16 that Luis approves before the run. The 28 in-scope receipts run once per
  finalist, after E16.
- **Principle VII, reproducibility.** Every jev answer is cached literally (spec 006 Phase 2 and US1 (T006–T024)), so a
  re-run is byte-identical with no call.
- **Principle X, observability.** Every billed jev call is one `classify-item` generation, and a
  cache hit produces none. Langfuse never gates a run.

## Clarifications

### Session 2026-10-12

- Q: What does "A/B" mean here: a traffic split, or a comparison that decides nothing? → A:
  **Shadow mode plus a registered E16.** gpt-oss-120b keeps deciding. The jev-based classifier
  runs beside it in the backend, and its answers are stored and compared. E16 on the dev set is
  what can change the classifier. A per-receipt traffic split was rejected, because it would let a
  model that was never validated decide (principle V).
- Q: Must the code be ready to switch to jev? → A: **Yes.** Switching the primary classifier must
  be one configuration change plus the documented runbook (US4), gated by E16 and an ADR. Luis:
  "it is giving very good results".
- Q: Which jev configuration? → A: The **hybrid** (jev category and confidence, gpt-oss-120b
  subtype and recipient). jev alone is kept as a variant in E16 only to show that the A6/A9
  guard works.
- Q: Where does the answer cache live? → A: In spec 006's cache table, behind its port. The same
  table holds both models' answers, under different keys.
- Q: Does shadow mode change any committed output? → A: **No.** It is switched on by a worker flag
  or an environment variable, not by `config/pipeline.yaml`. That file's hash is recorded in
  every result as `pipeline_config_version`, so changing it would change `outputs/results.jsonl`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Classify a line with jev, alone or as a hybrid (Priority: P1)

A maintainer configures the item classifier as `jev-1.13` or `jev-hybrid`. Every line gets a
`Classification` through the same port as today:

- **`jev-1.13`:** category and confidence from jev; subtype `none`, recipient `none`.
- **`jev-hybrid`:** category and confidence from jev; subtype, recipient kind and recipient name
  from gpt-oss-120b.

Answers are cached and traced like the current adapter's.

**Why this priority**: every other story uses this adapter. It moves the jev call out of a
front-end script and into the pipeline, under the same rules as the current classifier.

**Independent Test**: with a fake transport, classify the same request twice. The first call
makes one jev call (and, for the hybrid, one gpt-oss call) and one generation per call. The
second makes no call and no generation, and returns an identical `Classification`.

**Acceptance Scenarios**:

1. **Given** a request whose answer is not cached, **When** the jev adapter classifies it,
   **Then** one decision call is made, the literal response is cached under a key that includes
   the model, `dec-v1` and the payload, and one `classify-item` generation records the payload,
   the answer, usage, cost and request id.
2. **Given** the same request again, **When** it is classified, **Then** no call is made, no
   generation is emitted, and the result equals the first one field for field (with
   `cache_hit = true`).
3. **Given** jev answers a choice outside the 21 categories, **When** the answer is read,
   **Then** the line is `unclassified` with reason `schema_violation`, and it stays so on every
   replay.
4. **Given** the hybrid, jev answers `other`, and gpt-oss-120b answers `other` with subtype
   `event_ticket`, **When** the answers are merged, **Then** the line is `other` / `event_ticket`
   with jev's confidence and gpt-oss's recipient fields.
5. **Given** the hybrid, jev answers `other`, and gpt-oss-120b answers a category other than
   `other`, **When** the answers are merged, **Then** the subtype is `none` and the disagreement
   is recorded in the trace (`hybrid_conflict: true`). Nothing is silently invented.
6. **Given** the hybrid and either side is unavailable (gateway error or budget refused),
   **When** the line is classified, **Then** the line is `unclassified` with that transient
   reason, so the worker fails the stage and retries it, as today (AI_NOTES 51).
7. **Given** the hybrid and gpt-oss-120b's answer is a schema violation while jev's is valid,
   **When** the answers are merged, **Then** the line keeps jev's category and confidence with
   subtype `none` and recipient `none`, and the trace records the violation.

---

### User Story 2 - Run jev in shadow beside the deciding classifier (Priority: P1)

An operator starts the worker with shadow mode on. gpt-oss-120b still classifies and decides
every receipt. In addition, each receipt revision is classified by the shadow classifier, and
both answers are stored per line. Anyone can see them side by side for one receipt, and a report
summarises agreement over the whole store. The shadow never changes a state, a disposition, a
committed output or the time a receipt takes to reach a person.

**Why this priority**: this is the A/B Luis asked for. It measures jev on real traffic without
letting it decide.

**Independent Test**: with shadow on and fake transports, submit two synthetic receipts. Both are
decided exactly as with shadow off (same results, same states). Both have shadow rows per line.
`GET /receipts/{id}/shadow` shows both answers. `epv shadow report` gives agreement with its N.

**Acceptance Scenarios**:

1. **Given** shadow mode is off (the default), **When** receipts are processed, **Then** nothing
   new is stored, called or traced.
2. **Given** shadow mode is on, **When** a revision's classify stage completes, **Then** a
   separate `shadow` work item is queued for that revision. The receipt's `evaluate` work is
   queued as today, so evaluation never waits for the shadow.
3. **Given** a `shadow` work item, **When** the worker runs it, **Then** it stores one shadow row
   per line (the shadow classifier's answer, or its unclassified reason) and changes no receipt
   state, disposition, evaluation or event.
4. **Given** the shadow classifier fails transiently, **When** its attempts run out, **Then** the
   shadow rows record the failure, the receipt is unaffected, and nothing is shown to reviewers.
5. **Given** a receipt with shadow rows, **When** `GET /receipts/{id}/shadow` is called, **Then**
   the response lists, per line of the current revision, the primary answer, the shadow answer,
   and whether category and all fields agree.
6. **Given** a store with shadow rows, **When** `epv shadow report` runs, **Then** it prints:
   - category agreement between the two classifiers, with k, N and a Wilson interval;
   - agreement on the restricted flag, the subtype and the recipient kind;
   - a confusion table of the disagreements;
   - for lines a reviewer corrected (`LineCategoryCorrected`), how often each classifier matched
     the reviewer, with k and N;
   - how many receipts would get a different disposition if the shadow answers had been used
     (computed by the unchanged decision code, no model call).

   It never reads answer labels.
7. **Given** shadow mode is on, **When** the 32-receipt parity test runs, **Then** every result
   still equals `outputs/results.jsonl` byte for byte.

---

### User Story 3 - Decide on jev with a registered experiment (Priority: P1)

Before any jev variant can become the classifier, experiment E16 is registered with its decision
rule, approved by Luis, and run on the frozen dev set. The rule fixes both known gaps of E14's
code. The EXC-03 threshold is re-chosen for the new confidence source.

**Why this priority**: principle V. Without E16, shadow data can describe jev but cannot justify
adopting it.

**Independent Test**: unit tests of the decision function on synthetic rows:

- a category-only model with 130/130 and 23/29 A6/A9 wrong cannot be "superior";
- a superior model that costs more than the reference still wins;
- an unregistered or unapproved E16 is refused by the runner.

**Acceptance Scenarios**:

1. **Given** E16 is not registered or not approved by Luis, **When** `run_dev.py --experiment E16`
   is called, **Then** it refuses before any call (`RegistrationError`).
2. **Given** a challenger that fails the A6/A9 guard, **When** the rule is applied, **Then** its
   status is `fails_a6a9_guard` whatever its accuracy, and it cannot win.
3. **Given** a challenger that is superior and passes the guard, **When** the rule is applied,
   **Then** it wins even if it costs more than the reference. If several are superior, the
   cheapest of them wins.
4. **Given** E16's winner, **When** the confidence-source and threshold step runs, **Then** the
   threshold is chosen with E7's registered procedure on that winner's answers, and the report
   states how many dev items it sends to review (k/N).
5. **Given** E16 has run, **When** `decide.py` writes `outputs/eval/experiments.json`, **Then** E16
   appears with every variant's metrics and N, its winner, and why the others lost. E14's
   committed outcome is unchanged, because E14 is re-scored with its own registered rule.

---

### User Story 4 - Be ready to migrate to jev (Priority: P2)

If E16 selects a jev variant, a maintainer switches the primary classifier by changing
`classifier_model` in `config/pipeline.yaml`. Then they follow a written runbook: an ADR, the
threshold update, regenerated outputs, a once-only report on the 28 in-scope receipts, and
AI_NOTES. No code change is needed at migration time.

**Why this priority**: Luis wants to be ready. The migration itself is not in scope; the switch
and the runbook are.

**Independent Test**: in a test, load a pipeline config with `classifier_model: jev-hybrid` and
check that `default_classifier` and `build_worker` build the hybrid. With `gpt-oss-120b` they
build today's adapter, unchanged.

**Acceptance Scenarios**:

1. **Given** `classifier_model: gpt-oss-120b` (the committed value), **When** anything runs,
   **Then** behaviour and outputs are exactly as before this feature.
2. **Given** `classifier_model: jev-hybrid` or `jev-1.13`, **When** `epv run`, the upload path or
   the worker builds its classifier, **Then** it builds the corresponding adapter, and results
   record the classifier, model ids and prompt versions of that adapter.
3. **Given** an unknown value, **When** the config is loaded, **Then** loading fails with a
   message listing the accepted values.
4. **Given** the runbook in `quickstart.md`, **When** a maintainer follows it, **Then** every step
   is a command or a named document, and nothing in it reads the receipts' answers outside
   `eval/`.

---

### Edge Cases

- **jev returns `probabilities` but no `confidence`.** The confidence used is the configured
  source: `top_probability` by default, falling back to `confidence`. If neither is present, the
  line is `schema_violation`.
- **jev returns a confidence above 1 or below 0.** It is a schema violation, as for gpt-oss.
- **The decisions endpoint returns HTTP 429, 502 or 503.** Retry with backoff inside the
  transport, at most five extra attempts. If they all fail, `gateway_error`.
- **The endpoint changes shape (alpha API).** Parsing is strict, so an unknown shape is a
  `schema_violation` with the response cached. It replays identically, and a fixed parser can
  re-read it without a new call.
- **Shadow is switched on halfway through a batch.** Only revisions classified after the switch
  get shadow rows. The report counts N over rows that exist and never extrapolates.
- **A new revision arrives while its shadow work is pending.** The shadow item for the old
  revision completes without storing anything, as the classify stage does today.
- **The shadow budget runs out.** Shadow rows record `budget_refused`, and the primary path is
  unaffected.
- **Two workers.** Shadow work is claimed through the same leased outbox, so each item is
  processed once. The cache table (spec 006 Phase 2 and US1 (T006–T024)) is safe for concurrent writers.
- **Offline mode** (`--offline`). The shadow classifier only answers from the cache. Misses are
  recorded as `offline_cache_miss`, with no call.

## Requirements *(mandatory)*

### Functional Requirements

**Decision adapter (US1)**

- **FR-001**: The system MUST provide an item classifier for `typesafe/jev-1.13` that implements
  the existing `ItemClassifier` port. It receives only the cleaned description, the merchant name
  and the MCC (FR-007 of spec 001).
- **FR-002**: The jev request MUST be the `dec-v1` payload of `contracts/decision-adapter.md`
  (moved from `explorations/lib/decision_adapters.py` into the package), sent through
  OpenRouter's decisions endpoint with the existing `OPENROUTER_API_KEY`. No new secret.
- **FR-003**: Every jev response MUST be cached literally through spec 006's cache port before it
  is parsed. A cached answer MUST be returned without a call, and without a generation.
- **FR-004**: The cache key for a jev answer MUST be derived from the model id, the endpoint, the
  prompt version `dec-v1` and the payload, so it can never collide with a `cls-v2` key.
- **FR-005**: The system MUST provide a hybrid classifier. It merges jev's category and
  confidence with gpt-oss-120b's subtype, recipient kind and recipient name, following the merge
  table in `contracts/decision-adapter.md`.
- **FR-006**: The hybrid MUST report a transient failure of either side as that transient reason
  (so the worker retries the stage), and a schema violation as defined in the merge table.
- **FR-007**: Every billed jev call MUST be one `classify-item` generation. It records:
  - the model and the payload;
  - the answer, usage, billed cost and request id;
  - `model_parameters.kind = "decision"`;
  - `metadata.prompt_version` and `metadata.cache_key`;
  - the linked Langfuse prompt `classify-item-decision` (label `dec-v1`) when tracing is on.

  A cache hit MUST NOT produce a generation.
- **FR-008**: The decision prompt (instructions and criteria) MUST be registered in Langfuse
  Prompt Management as `classify-item-decision` under label `dec-v1`, by a sync function like
  `prompt_sync.sync_prompt`. It MUST also be logged in `docs/ai/prompt-log.md`.
- **FR-009**: The jev adapter MUST refuse a billed call when its spend in the current process has
  reached its cap. The answer is `budget_refused`. Cached and seeded answers never count. The
  factory sets the cap by role:
  - as the primary classifier: USD 1.00 per process, as today;
  - as the shadow: `--shadow-cap-usd`, default USD 0.25;
  - in E16: what remains of USD 0.10.

  Each side of the hybrid counts separately (`contracts/decision-adapter.md`, "Budget caps").

**Shadow mode (US2)**

- **FR-010**: Shadow mode MUST be off by default. It MUST be switched on only by
  `epv worker --shadow <classifier>`, `epv serve --with-worker --shadow <classifier>`, or the
  environment variable `EPV_SHADOW`. It MUST NOT be a key in `config/pipeline.yaml`.
- **FR-011**: With shadow on, completing a revision's classify stage MUST queue a `shadow` work
  item for that revision in the same transaction. The `evaluate` item MUST be queued exactly as
  today.
- **FR-012**: Processing a `shadow` item MUST store one row per line in `shadow_classifications`,
  and MUST NOT change any receipt state, projection, evaluation, event or committed file.
- **FR-013**: A shadow failure MUST be recorded in the shadow rows (status and reason). It MUST
  never fail, block or delay the receipt.
- **FR-014**: Shadow calls MUST have their own spend cap per process (default USD 0.25), separate
  from the primary classifier's.
- **FR-015**: The API MUST expose `GET /receipts/{receipt_id}/shadow`, as defined in
  `contracts/api-delta.md`. It returns 404 `not_found` for an unknown receipt and 404
  `no_shadow` when the current revision has no shadow rows.
- **FR-016**: `epv shadow report` MUST print the measures of US2 scenario 6, each with its k and
  N, from the store alone, with no model call and no answer labels. `--json` MUST write the same
  content as JSON.
- **FR-017**: The shadow classification of a revision MUST be traced in that revision's trace
  (`app-r<revision>`), under a top-level span `shadow-classify-receipt`, with one `classify-item`
  generation per billed call.

**Experiment E16 (US3)**

- **FR-018**: `eval/experiments/decide.py` MUST apply the A6/A9 guard before the superiority test,
  for E14 as well. A test MUST show that E14's committed winner (`gpt-oss-120b`) is unchanged by
  this fix.
- **FR-019**: The winner selection MUST follow the registered text: a superior challenger that
  passes every guard wins (the cheapest among several superior ones). Only when none is superior
  is the cheapest among the reference and the non-inferior models chosen. A test MUST show that
  E14's committed outcome is unchanged.
- **FR-020**: E16 MUST be registered in `explorations/research/experiments_plan.yaml` under
  `iteration_2` with the text of `contracts/e16-rule.md`, the frozen set's hash and
  `registered_at`, before any E16 run. `approved_by` MUST be set only by Luis.
- **FR-021**: `eval/experiments/run_dev.py` MUST accept `--experiment E16 --variant
  {jev-1.13,jev-hybrid}` and refuse to run unless E16 is registered and approved on the frozen
  set's hash (the existing `check_registration`).
- **FR-022**: E16's threshold step MUST reuse E7's registered procedure (`decide.e7`) on the
  winner's answers, with the confidence sources listed in `contracts/e16-rule.md`, and report the
  number of bins with at least 10 items.
- **FR-023**: E16's outcome MUST be written to `outputs/eval/experiments.json` with every variant's
  N, and the run's spend MUST be reported.

**Switch and runbook (US4)**

- **FR-024**: `classifier_model` in `config/pipeline.yaml` MUST accept `jev-1.13` and `jev-hybrid`
  besides the existing pins, and MUST reject unknown values with the list of accepted ones.
- **FR-025**: `default_classifier` (`app/intake.py`), `build_worker` (`app/composition.py`) and
  `epv run` MUST build the configured classifier through one factory, so the switch is one
  configuration value.
- **FR-026**: The committed value MUST stay `gpt-oss-120b`. This feature MUST NOT change
  `outputs/`, `config/pipeline.yaml` or `docs/decisions/policy_decisions.yaml`.
- **FR-027**: `quickstart.md` MUST contain the migration runbook: E16 approved and run, ADR 0011,
  the config change, the A3 threshold change (Luis is alerted first), regenerated committed
  outputs, one run on the 28 in-scope receipts reported with its N, and AI_NOTES.

**Firewall**

- **FR-028**: No code outside `eval/` added by this feature MUST read `data/receipts.jsonl`'s
  answer fields or the dev set's labels. The shadow report MUST use only the store. The
  existing architecture test MUST stay green.

### Key Entities

- **Decision classifier**: an `ItemClassifier` over OpenRouter's decisions endpoint. Its identity
  is model id `typesafe/jev-1.13` and prompt version `dec-v1`.
- **Hybrid classifier**: an `ItemClassifier` composed of a decision classifier (category,
  confidence) and the existing OpenRouter classifier (subtype, recipient).
- **Shadow classification**: per receipt, revision and line, the shadow classifier's answer or
  its failure, with the classifier's identity and time.
- **E16**: a registered experiment, with variants, reference, data hash, rule, approval and
  outcome.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With shadow off, the 32 receipts through the backend equal `outputs/results.jsonl`
  byte for byte, with zero billed calls (N = 32 receipts, 78 lines). The same holds with shadow
  on and fake shadow transports.
- **SC-002**: Replaying a jev answer from the cache gives an identical `Classification`, and no
  call and no generation are made (N = every line in the adapter tests).
- **SC-003**: The corrected decision function reproduces E14's committed outcome exactly (winner
  `gpt-oss-120b`, N = 130), and classifies the 2026-10-11 jev-1.13 row set as
  `fails_a6a9_guard` (N = 130, 29 A6/A9 items).
- **SC-004**: E16, once approved and run, is reported with every variant's accuracy (k/N, Wilson
  interval), restricted F1, A6/A9 wrong (k/29), McNemar b/c/p, bootstrap interval, cost per
  1,000 items and median latency, and the chosen threshold with the dev items it sends to review
  (k/N).
- **SC-005**: `epv shadow report` on a store where every line has a shadow row reports agreement
  as k/N, and N equals the number of lines with both answers (checked on a synthetic store of at
  least 20 lines).
- **SC-006**: Switching `classifier_model` to `jev-hybrid` needs no code change. A test builds the
  hybrid from config (N = 3 entry points: `epv run`, upload, worker).
- **SC-007**: With Langfuse down, every new path runs to the end with the same outputs (shadow
  stage, decision adapter, report).

## Assumptions

- OpenRouter's alpha decisions endpoint keeps the request and response shape used on 2026-10-11
  (`state`, `questions`, `answers.<id>.{choice, probabilities, confidence}`). If it changes, the
  strict parser turns answers into `schema_violation`, and the adapter is updated against the
  cached raw responses.
- jev's price stays near USD 0.04 per 1,000 items. The hybrid costs about the sum of both models,
  about USD 0.10 per 1,000 items on dev. Caps are per process.
- The frozen dev set (N = 130) is the E16 data unless Luis enlarges it first. A larger set gets
  its new hash written into the registration before any run.
- Shadow verification in this feature uses fake transports and synthetic receipts. The 32 receipts
  are run with a jev variant only once, after E16 names it a finalist (principle V).
- Spec 006 Phase 2 and US1 (T006–T024) (cache port, cache table, migrations) is merged before this work starts.
