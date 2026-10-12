# Tasks: Guided intake form

**Input**: `specs/008-guided-intake/` (spec, plan, research, data model, contracts/form-fields.md)

**Format**: `- [ ] T### [P?] [US?] Description with file path`. `[P]` means independent of the open
tasks around it. Stories: US1 fill and send, US2 validation, US3 draft, US4 revise.

**Rules for every task**: test first (the failing test is committed with the code that makes it
pass); synthetic receipts only, never `data/receipts.jsonl`; no policy rule, threshold or rule ID
in the form; no change under `src/` (backend) except the release version line of T030, and none at
all under `src/expense_validator/domain/engine/`; everything
in English; `npm test` and `npm run typecheck` green before each commit; no `--no-verify`.

**Before starting**: check whether spec 006 user story 4 is merged: `docs/api/openapi.json` has
`components.schemas.ReceiptInputRequest` and `frontend/src/api/types.ts` exports `ReceiptInput`,
`Entity` and `Language` (006 task T055). If yes, import those aliases from `types.ts`; never import
the generated file directly. If not, follow the fallback in research.md R2 and note it in the PR
body.

## Phase 0: Pure core (no UI)

**Goal**: every computation and conversion exists and is tested.
**Independent test**: `npx vitest run src/lib` green.

- [ ] T001 [P] Write `frontend/src/lib/decimal.test.ts`: parse accepts `"12"`, `"12.50"`, `"-3.1"`, `" 7 "` and rejects `"12,5"`, `"abc"`, `""`, `"1e3"`; `mul("8000","0.0067") = "53.6000"` and `roundHalfUp(…, 2) = "53.60"`; `add("0.1","0.2") = "0.3"`; `roundHalfUp("0.125",2) = "0.13"`, `roundHalfUp("-0.125",2) = "-0.13"`; `equals("12.5","12.50")`; large values (`"123456789012.123456"`) stay exact
- [ ] T002 [P] Implement `frontend/src/lib/decimal.ts` (`parseDecimal`, `isDecimal`, `add`, `mul`, `roundHalfUp`, `equals`, `canonical`) on `BigInt` with a scale; no dependency
- [ ] T003 Write `frontend/src/lib/receiptForm.test.ts` part 1, shape and conversion: `emptyForm()` defaults of data-model.md; `formToReceipt(emptyForm())` has exactly the 20 receipt keys in the order of `contracts/form-fields.md` and each line the 7 line keys; empty nullable fields are `null`; money is a string, `mcc`, `attendee_count`, `trip_nights` are numbers; `trip_nights` is `null` when `trip_id` is empty; `vat_number` is `null` unless the entity is EMEA or `vat_visible_on_load`
- [ ] T004 Extend `frontend/src/lib/receiptForm.test.ts` part 2, computation: line amount `2 × 15.00 = 30.00`; USD amount with rate `0.0067` on `8000` is `53.60`; USD receipt uses the amount as USD; totals are sums; a `manual` value is sent as typed; `computed` returns `null` for USD amounts when the currency is not USD and there is no rate
- [ ] T005 Extend `frontend/src/lib/receiptForm.test.ts` part 3, round trip (SC-001): for the N = 5 synthetic receipts `SAMPLE-001` (`JSON.parse(SAMPLE_RECEIPT)`), `SAMPLE-002` (the valid dinner row of `SAMPLE_BATCH` in `frontend/src/samples/samples.ts`), `DEMO-001` (`docs/samples/receipt-one.json`, read with `readFileSync` as `contract.test.ts` reads `openapi.json`), `receipt("E2E-RT")` and `apac("E2E-RT-APAC")` from `frontend/e2e/fixtures.ts`, `canonicalJson(formToReceipt(receiptToForm(r).form)) === canonicalJson(r)`; the test asserts the list has 5 entries; a receipt whose `amount` differs from `quantity × unit_price` loads that line as `manual`; a USD receipt with `fx_rate_to_usd: null` stays `null`
- [ ] T006 Extend `frontend/src/lib/receiptForm.test.ts` part 4, firewall: `receiptToForm` with `labels`, `notes` and `line_items[0].labels` reports them in `dropped` and `formToReceipt` never emits them; an unknown key `"foo"` is dropped and reported
- [ ] T007 Extend `frontend/src/lib/receiptForm.test.ts` part 5, validation (US2): each required field of `contracts/form-fields.md` empty gives an error at its dotted path; `"12,5"` in a money field gives "Enter a number, for example 12.50"; `quantity` `"0"` gives "Must be greater than 0"; `mcc` `"59.4"` gives an integer error; a non-USD receipt with no rate and typed USD amounts gives **no** error (no policy); a non-USD receipt with no rate and an empty USD amount gives "Required" on that amount
- [ ] T008 Extend `frontend/src/lib/receiptForm.test.ts` part 6, helpers: `serverErrors(["mcc","line_items.1.language","line_items","weird"], form)` maps the first three and leaves `"weird"` unmapped; `suggestEntity` for JP, DE, US; `nextLineId` after removing a row does not reuse a number; `renameLines` renames only auto line IDs
- [ ] T009 Implement `frontend/src/lib/receiptForm.ts` (types of data-model.md, `emptyForm`, `computed`, `formToReceipt`, `receiptToForm`, `validateForm`, `serverErrors`, `suggestEntity`, `nextLineId`, `renameLines`, `canonicalJson`, `KNOWN_EXPENSE_TYPES` imported from `frontend/src/samples/expense-types.json` (T013a), `ENTITIES` and `LANGUAGES` typed against `Entity` and `Language` imported from `frontend/src/api/types.ts`)
- [ ] T010 [P] Write `frontend/src/lib/draft.test.ts` with a `localStorage` stub: save then load round-trips; a draft of another version or unparseable JSON loads as `null` and is removed; `saveDraft` and `clearDraft` never throw when `setItem`/`removeItem` throw; an empty draft is not saved
- [ ] T011 [P] Add `removeStore(key)` to `frontend/src/lib/hooks.tsx` with the same guard as `writeStore`
- [ ] T012 Implement `frontend/src/lib/draft.ts` (`loadDraft`, `saveDraft`, `clearDraft`, `isEmptyDraft`, key `epv.intake.draft.v1`)
- [ ] T013 Contract: in `frontend/src/contract.test.ts`, if `components.schemas.ReceiptInputRequest` is in `docs/api/openapi.json`, assert its properties equal the 20 keys the form emits, its line item schema the 7 line keys, and its `entity` and `language` enums equal `ENTITIES` and `LANGUAGES`; otherwise (fallback) assert those lists against the `Literal[...]` lines of `src/expense_validator/domain/models.py`. Also assert `KNOWN_EXPENSE_TYPES` equals `frontend/src/samples/expense-types.json`
- [ ] T013a [P] Write `tests/contract/test_expense_types.py`: it imports `COVERS` from `expense_validator.domain.engine.rules.documentation` and `MEAL_TYPES` from `expense_validator.domain.engine.context` and asserts that `frontend/src/samples/expense-types.json` equals `sorted(set(COVERS) | MEAL_TYPES)`; under `if __name__ == "__main__"` it rewrites the JSON, and the assertion message says `uv run python -m tests.contract.test_expense_types` regenerates it. Create the JSON by running it once (9 types today). The engine is only imported, not changed
- [ ] T014 Verify (`npm test`, `npm run typecheck`) and commit: `feat(frontend): exact decimal helpers and the receipt form model (008)`

## Phase 1: The form, US1 and US2

**Goal**: one receipt can be entered, previewed and sent from a form; errors are shown per field.
**Independent test**: e2e "form: fill and submit" and "form: field errors" pass.

- [ ] T015 [P] [US1] Write the e2e test "form: fill and submit a two-line receipt" in `frontend/e2e/smoke.spec.ts`: choose "One receipt (form)", fill receipt ID `E2E-FORM-1`, employee, country `US`, entity GLOBAL, declared type `Office Supplies`, MCC `5943` and its description, two lines (quantity 2 × 15.00, and 1 × 12.50), check the computed totals `42.50` and USD `42.50`, open "Preview JSON" and check it contains `"line_id": "E2E-FORM-1-L2"`, submit with the keyboard only (SC-002), expect "Accepted" in the region "Submission result"; submit again, expect "Already known"
- [ ] T016 [P] [US2] Write the e2e test "form: errors are shown per field and nothing is sent" in `frontend/e2e/smoke.spec.ts`: with an empty employee ID and quantity `0`, pressing submit shows the error summary (role alert) with two links, both inputs have `aria-invalid="true"`, clicking a link focuses the input, and `page.on("request")` records zero `POST /api/receipts` (SC-003)
- [ ] T017 [US1] Implement `frontend/src/components/LineItemsEditor.tsx`: a `<fieldset>` per row with legend "Line n", inputs of `contracts/form-fields.md` (line table), computed amount and USD amount with "computed" text and "Use computed value", override warnings, "Add line" (focus to the new description) and "Remove line n" (focus management of plan.md), "The charge" label when not itemized
- [ ] T018 [US1] Implement `frontend/src/components/ReceiptForm.tsx`: header inputs with labels, hints and `datalist` suggestions (country, declared type, currency, MCC), entity select prefilled by `suggestEntity` until the person changes it, rate read-only `1` while USD on a new form, `trip_nights` shown only with a trip, `vat_number` only for EMEA (or `vat_visible_on_load`), computed totals with overrides and warnings, "Preview JSON" `<details>`, error summary with links
- [ ] T019 [US1] Edit `frontend/src/pages/IntakePage.tsx`: a third chip "One receipt (form)" in the mode group; in form mode render `ReceiptForm` instead of the drop zone and textarea; the idempotency key field shows in form mode too; submit calls `api.submitReceipt(formToReceipt(form), key)` after `validateForm` returns no error; the `planIntake` auto-switch (lines 67-70) only moves between the two text modes
- [ ] T020 [US2] In `frontend/src/pages/IntakePage.tsx`, on `ApiError` with code `invalid_receipt` in form mode, pass `serverErrors(details.fields, form)` to the form (mapped fields marked "The server refused this value", unmapped listed in the summary); keep the existing callout for the text modes
- [ ] T021 [P] [US1] Add form styles to `frontend/src/styles/app.css` (header grid, line rows, warning and error states) using existing Ledgerline tokens; check light and dark themes
- [ ] T022 Verify (`npm test`, `npm run typecheck`, `npm run e2e`) and commit: `feat(frontend): guided form for one receipt, with per-field errors (008)`

## Phase 2: Draft, US3

**Goal**: leaving the screen keeps the work; success or discard removes it.
**Independent test**: e2e "form: draft restored after reload" passes.

- [ ] T023 [P] [US3] Write the e2e test "form: a draft survives a reload and can be discarded" in `frontend/e2e/smoke.spec.ts`: fill receipt ID `E2E-FORM-DRAFT`, employee, merchant and two lines' descriptions, reload, expect the values and the notice "Draft restored from", click "Discard draft", expect an empty form, reload, expect no notice (SC-004)
- [ ] T024 [US3] Edit `frontend/src/pages/IntakePage.tsx`: on mount (no `?revise`), `loadDraft()` restores mode, form, text and key and shows the notice with "Discard draft"; changes call `saveDraft` debounced at 400 ms; accepted, existing and revision outcomes call `clearDraft()`; failures keep it
- [ ] T025 Verify and commit: `feat(frontend): keep the intake draft in the browser (008)`

## Phase 3: Revise and form ⇄ JSON, US4

**Goal**: a stored receipt opens in the form unchanged; text and form convert both ways.
**Independent test**: e2e "form: revise prefill" passes.

- [ ] T026 [P] [US4] Write the e2e test "form: revise opens the stored receipt in the form" in `frontend/e2e/smoke.spec.ts`: submit `receipt("E2E-FORM-REV")` through the JSON mode, open `/intake?revise=E2E-FORM-REV`, expect form mode with the merchant and line IDs shown, submit unchanged and expect "Already known", change the merchant and expect "New revision"
- [ ] T027 [US4] Edit the revise effect in `frontend/src/pages/IntakePage.tsx` (lines 73-86): `receiptToForm(detail.receipt)` sets the form and selects form mode; the draft is not loaded or overwritten while `?revise` is present until the person edits
- [ ] T028 [US4] Add "Open as JSON" (form → textarea with `JSON.stringify(formToReceipt(form), null, 2)`) and "Edit in the form" (shown when `planIntake` is `single`; uses `receiptToForm` and shows "N keys not shown in the form were dropped" when `dropped` is not empty) to `frontend/src/pages/IntakePage.tsx`
- [ ] T029 Verify and commit: `feat(frontend): revise a receipt in the form, and move between form and JSON (008)`

## Phase 4: Polish

- [ ] T030 [P] Bump the release to `1.3.0` in all three places: `pyproject.toml` `version`, `frontend/package.json` `version`, and the `version` passed to FastAPI in `create_app` (`src/expense_validator/app/api/__init__.py`); regenerate `docs/api/openapi.json` (`uv run epv openapi > docs/api/openapi.json`, only `info.version` changes) so `tests/smoke/test_openapi.py` stays green
- [ ] T031 [P] Close the intake entry in `frontend/FINDINGS.md` (form and draft) with a link to this spec; keep F-06 open (per-field server reasons are a backend change)
- [ ] T032 [P] Add the iteration 6 line for 008 to `docs/roadmap.md` and the assistant mistakes of this feature to `AI_NOTES.md`
- [ ] T033 Run the full verification below, then open the PR `feat(frontend): guided intake form (008)` against `main`; after Luis merges it, tag `v1.3.0` on the merge commit and publish the GitHub release

## Verification

```bash
cd frontend
npm test            # unit + contract (includes decimal, receiptForm, draft, contract.test.ts)
npm run typecheck
npm run build
npm run e2e         # starts its own epv serve --with-worker --offline and Vite
cd ..
git diff --stat main -- src/ tests/ docs/api/
uv run pytest -q    # backend still green, including tests/contract/test_expense_types.py
```

Expected: all green. Outside `frontend/`, `specs/008-guided-intake/`, `docs/roadmap.md` and
`AI_NOTES.md`, the diff has only the version lines (`pyproject.toml`,
`src/expense_validator/app/api/__init__.py`, `info.version` in `docs/api/openapi.json`) and the new
`tests/contract/test_expense_types.py`. Nothing under `src/expense_validator/domain/` changes.

## Dependencies

- Phase 0 blocks everything. Phases 1 → 2 → 3 in order (all edit `IntakePage.tsx`).
- T013 depends on whether spec 006 US4 is merged (see "Before starting").
- Within a phase, `[P]` test tasks can be written in parallel; implementation tasks follow their tests.
