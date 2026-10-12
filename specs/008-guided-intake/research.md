# Research: Guided intake form

Resolved before design. Each entry records the decision, why, and what was rejected.

## R1. Where the form lives: a third mode on the intake screen

- **Decision**: a third mode on `IntakePage`, "One receipt (form)", beside "One receipt (JSON)" and
  "A batch". The form is its own component (`components/ReceiptForm.tsx`); the page keeps the
  result panel, the error callout, the idempotency key and the submit flow it already has.
- **Rationale**: one place to send receipts, one result panel, one submit path
  (`api.submitReceipt`). The JSON mode stays for developers and for pasting.
- **Alternatives**: a new route `/intake/form` (two places to keep in step, and the "revise" link
  would need to choose); replacing the textarea (loses batch upload and paste).

## R2. Where enum values and the receipt type come from

- **Decision**: after spec 006 user story 4, import the named aliases that `frontend/src/api/types.ts`
  exports (006 task T055): `ReceiptInput` (the request shape, OpenAPI component
  `ReceiptInputRequest`, validation mode), `Receipt` and `Result` (the stored shapes, components
  `ReceiptInput` and `ReceiptResult`), `Entity`, `Language` and the line item types. The form
  imports **only from `types.ts`**, never from the generated file, so the generator's naming can
  change without touching the form. The form module derives its select options from those types (a
  `satisfies` check makes a missing or extra option a type error).
- **How to tell 006 is merged**: `docs/api/openapi.json` has `components.schemas.ReceiptInputRequest`
  and `types.ts` exports `ReceiptInput`.
- **Fallback when 006 is not merged**: use `Receipt` and `LineItem` from the hand-written
  `frontend/src/api/types.ts` (they already match `models.py`), keep `ENTITIES` and `LANGUAGES` in
  `frontend/src/lib/receiptForm.ts`, and assert those lists against the `models.py` text (a small
  regex over `Language = Literal[...]` and `Entity = Literal[...]`) in `frontend/src/contract.test.ts`.
  This is acceptable for one release and is replaced by the OpenAPI check when 006 lands.
- **Known declared types**: `KNOWN_EXPENSE_TYPES` in `receiptForm.ts` is a suggestion list, so it
  must not drift from the engine. The list lives in `frontend/src/samples/expense-types.json` (a
  sorted JSON array), which `receiptForm.ts` imports as `KNOWN_EXPENSE_TYPES`.
  `tests/contract/test_expense_types.py` asserts that the committed JSON equals the sorted union of
  the `COVERS` keys (`domain/engine/rules/documentation.py`) and `MEAL_TYPES`
  (`domain/engine/context.py`); run as a script
  (`uv run python -m tests.contract.test_expense_types`) it rewrites the JSON, and its failure
  message says so. No CLI command is added, and the engine is only imported, never changed.
- **Rationale**: the front end today copies the 21 categories by hand with no drift test (FINDINGS
  F-05); the form must not add another hand copy.
- **Alternatives**: a `GET /schema` endpoint (backend change, out of scope); hard-coding (drift).

## R3. Decimal arithmetic without a dependency

- **Decision**: a small module `frontend/src/lib/decimal.ts` that parses a decimal string into a
  `BigInt` and a scale, and offers `add`, `mul`, `roundHalfUp(scale)`, `equals`, `toString`. Inputs
  are validated by one regular expression (`^-?\d+(\.\d+)?$` after trimming; a comma is an error,
  not a decimal separator).
- **Rationale**: the backend is exact (`Decimal`, `parse_float=Decimal`); computing USD amounts with
  binary floats in the browser would propose `53.599999…`. The operations needed are four; a library
  (decimal.js, big.js) adds a dependency for 60 lines of code.
- **Alternatives**: `Number` with `toFixed` (wrong for long rates and large JPY amounts); decimal.js
  (a dependency for little).

## R4. What the form validates

- **Decision**: only what the API refuses: required keys of `ReceiptInput` and `LineItemInput`,
  parseable numbers, integers for `mcc`, `attendee_count`, `trip_nights`, `quantity > 0`, and enum
  membership. Nothing from `data/policy-docs/`.
- **Rationale**: Principle II. The engine decides; a form that refuses a receipt with no conversion
  rate would hide DOC-04 from the auditor. A missing rate only changes how USD amounts are filled
  (they must be typed, because `amount_usd` is required).
- **Alternatives**: mirror some policy checks as warnings (rejected: a second, divergent copy of the
  rules).

## R5. Server errors

- **Decision**: map `details.fields` (dotted pydantic paths, `app/service.py:84`) to inputs as in
  `contracts/form-fields.md`; message "The server refused this value".
- **Rationale**: the API gives names, not reasons (FINDINGS F-06). A per-field reason needs a backend
  change (`details.errors`), which is a separate improvement and not in this spec.

## R6. Draft storage

- **Decision**: one `localStorage` key, `epv.intake.draft.v1`, holding
  `{version: 1, mode, form, text, idempotencyKey, savedAt}`, written through the existing
  `readStore` / `writeStore` (`frontend/src/lib/hooks.tsx:8-22`, which already swallow storage
  errors), debounced at 400 ms. A draft with another version is ignored and deleted.
- **Rationale**: matches how `epv.actor` and `epv.theme` are kept; the version guards against a
  shape change in a later release.
- **Privacy**: the draft holds an employee ID and amounts, on the person's own browser only. It is
  deleted on a successful submit and on "Discard draft". Results are never stored.
- **Alternatives**: `sessionStorage` (lost when the tab closes, which is the case the finding
  describes); IndexedDB (more code for one object); server-side drafts (backend change).

## R7. Revise: preserving the stored receipt

- **Decision**: each derived value in the form state carries `mode: "auto" | "manual"`. `receiptToForm`
  sets `manual` whenever the stored value differs from the computation (or when the computation is
  not possible), so a stored receipt is reproduced exactly. Line IDs are kept. A stored USD receipt
  whose `fx_rate_to_usd` is `null` keeps `null` (the "1 while USD" default applies only to a new
  form).
- **Rationale**: FR-016. Sending a revision without changes must be "Already known", or the form
  would create spurious revisions.
- **Alternatives**: recompute everything on load (silently changes stored receipts).

## R8. Testing

- **Decision**: Vitest for the pure modules (`decimal.ts`, `receiptForm.ts`, `draft.ts`), test first;
  Playwright for the flows, added to `frontend/e2e/smoke.spec.ts`, which already runs against a real
  `epv serve --with-worker --offline` (`frontend/playwright.config.ts:19-30`). New receipts use IDs
  `E2E-FORM-*` because the suite is serial and shares one database.
- **Note**: the e2e backend runs `--offline`, so lines not in the committed cache are unclassified
  and the receipt goes to review; the tests assert the submission outcome, not a disposition.
