# Implementation Plan: Guided intake form

**Branch**: `feat/008-guided-intake` | **Date**: 2026-10-12 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/008-guided-intake/spec.md`; decisions in
[research.md](research.md); types and functions in [data-model.md](data-model.md); every field in
[contracts/form-fields.md](contracts/form-fields.md).

## Summary

Add a third intake mode, "One receipt (form)", to `frontend/src/pages/IntakePage.tsx`: a form for
every `ReceiptInput` field with repeatable line items, exact decimal computation of line amounts,
USD amounts and totals (each overridable), a JSON preview, client validation limited to what the API
refuses, server field errors mapped back onto inputs, a draft kept in `localStorage`, and the
`?revise=<id>` prefill. All logic is in pure, tested modules (`decimal.ts`, `receiptForm.ts`,
`draft.ts`); the component only renders and wires them. The backend does not change.

## Technical Context

**Language/Version**: TypeScript 5.6, React 18.3, Vite 5.4 (`frontend/package.json`)

**Primary Dependencies**: none new. Decimal arithmetic is a small `BigInt` module (research R3).
Types are imported only from `frontend/src/api/types.ts`: after spec 006 its named aliases
(`ReceiptInput` = request shape, OpenAPI `ReceiptInputRequest`; `Receipt`; `Result`; `Entity`;
`Language`; line item types, 006 task T055) over the generated file; before it, the hand-written
types (research R2). The form never imports the generated file directly.

**Storage**: browser `localStorage`, key `epv.intake.draft.v1`

**Testing**: Vitest 2 for the pure modules (test first); Playwright 1.58 end-to-end in
`frontend/e2e/smoke.spec.ts` against `epv serve --with-worker --offline --no-trace`
(`frontend/playwright.config.ts`)

**Target Platform**: evergreen browsers; keyboard and screen-reader usable

**Project Type**: front end of the existing web application (`frontend/`)

**Performance Goals**: none beyond responsiveness; a receipt has tens of lines at most

**Constraints**: no policy logic in the browser; no answer keys; English UI; Ledgerline styles;
backend and engine untouched

**Scale/Scope**: one receipt at a time

## Constitution Check

*GATE: passed before Phase 0; re-check after Phase 1.*

| Principle | Status | How |
|---|---|---|
| I. Labels are evaluation-only | Pass | No field for `labels`, `line_items[].labels` or `notes`; `receiptToForm` drops and reports them; `formToReceipt` never emits them (data-model property 3). Tests use synthetic receipts only; nothing reads `data/receipts.jsonl`. |
| II. Deterministic decisions | Pass | The form validates only the API's own constraints (research R4); no rule from `data/policy-docs/` is copied; decisions stay in the engine. |
| III. Policy text is the source of truth | Pass | No policy text or threshold in the front end. Suggestions for declared types cite the engine module they come from. |
| IV. Evidence or nothing | Pass | Findings still come only from the result panel and the review screens. |
| V. Decide on dev, report on test | Pass | No variant is compared. |
| VI. Honest measurement | Pass | Every success criterion states its N. |
| VII. Reproducibility | Pass | The form produces the same JSON a person could paste; the content hash is unchanged; a revision sent unchanged is "Already known" (SC-001). |
| VIII. Separation of components | Pass | Pure logic in `lib/`, rendering in `components/`, the page composes. No backend change. |
| IX. Secrets stay out | Pass | No key is involved; the draft holds receipt data only. |
| X. Observability | Pass | No model call is added. |
| XI. Iterative delivery | Pass | Three independent slices (form, draft, revise); the JSON and batch modes are untouched. |

No violations; no Complexity Tracking entries.

## Project Structure

### Documentation (this feature)

```text
specs/008-guided-intake/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── form-fields.md
├── checklists/requirements.md
└── tasks.md
```

### Source Code

```text
frontend/
├── src/
│   ├── lib/
│   │   ├── decimal.ts            # NEW  exact decimal strings on BigInt (parse, add, mul, roundHalfUp, equals)
│   │   ├── decimal.test.ts       # NEW
│   │   ├── receiptForm.ts        # NEW  form state, computed, formToReceipt, receiptToForm, validateForm, serverErrors, suggestions
│   │   ├── receiptForm.test.ts   # NEW
│   │   ├── draft.ts              # NEW  load/save/clear the versioned draft
│   │   ├── draft.test.ts         # NEW
│   │   └── hooks.tsx             # EDIT add removeStore (same guard as readStore/writeStore)
│   ├── components/
│   │   ├── ReceiptForm.tsx       # NEW  header fields, computed totals, preview, error summary
│   │   └── LineItemsEditor.tsx   # NEW  repeatable rows, add/remove, focus management
│   ├── pages/
│   │   └── IntakePage.tsx        # EDIT third mode, draft restore/discard, revise into the form, form ⇄ JSON
│   ├── samples/expense-types.json # NEW  declared types the engine knows, kept in sync by tests/contract/test_expense_types.py
│   ├── styles/app.css            # EDIT form grid, row layout, warning and error styles with Ledgerline tokens
│   └── contract.test.ts          # EDIT ReceiptInputRequest fields and enums (after 006) or enum drift test (fallback); KNOWN_EXPENSE_TYPES
├── e2e/
│   ├── smoke.spec.ts             # EDIT four form scenarios
│   └── fixtures.ts               # (reuse receipt(), apac())
└── package.json                  # EDIT version 1.3.0

tests/contract/test_expense_types.py   # NEW  expense-types.json == COVERS ∪ MEAL_TYPES (engine only imported)
pyproject.toml                         # EDIT version 1.3.0
src/expense_validator/app/api/__init__.py  # EDIT version 1.3.0 in create_app (no behaviour change)
docs/api/openapi.json                  # REGENERATED: info.version only
```

**Structure Decision**: the existing `frontend/` layout: pure logic in `src/lib` beside
`intake.ts`, components in `src/components`, the page wires them. No new route.

## Design notes

- **Accessibility**: every input has a visible `<label htmlFor>`; hints and errors have ids
  referenced by `aria-describedby`; invalid inputs get `aria-invalid="true"`; the error summary is a
  `role="alert"` list of links that focus the input; each line is a `<fieldset>` with a `<legend>`
  "Line 2"; "Remove line 2" is the remove button's accessible name; after "Add line" focus moves to
  the new row's description; after removing, focus moves to the previous row's remove button or
  "Add line". Computed fields announce their value with the visible text "computed" and the
  "Use computed value" button.
- **Styles**: reuse `ll-field`, `ll-input`, `ll-label`, `hint`, `ll-btn--primary|secondary|ghost`,
  `callout callout--error|--accent` as `IntakePage.tsx` does; warnings use the low-severity token,
  errors the critical one (`docs/design/tokens.json`); numbers use `ll-num` (tabular figures).
- **Mode toggle**: the existing `chip` group gains a third chip. The auto-switch of
  `planIntake` (`IntakePage.tsx:67-70`) applies only between the two text modes; it never leaves the
  form mode on its own.
- **Revise**: the effect at `IntakePage.tsx:73-86` sets the form (via `receiptToForm`) and selects
  the form mode instead of filling the textarea.
- **Preview**: a `<details>` "Preview JSON" with a read-only `<pre>` of
  `JSON.stringify(formToReceipt(form), null, 2)`.

## Delivery order (vertical slices)

Each slice ends with `npm test`, `npm run typecheck` and the e2e suite green, and a commit.

0. **Pure core.** `decimal.ts`, `receiptForm.ts`, `draft.ts` with their tests (no UI).
1. **Form, US1 and US2.** `ReceiptForm`, `LineItemsEditor`, the third mode, preview, client
   validation, server error mapping; e2e "fill and submit" and "field error".
2. **Draft, US3.** Save, restore, discard, clear on success; e2e "draft restored after reload".
3. **Revise and form ⇄ JSON, US4.** e2e "revise prefill".
4. **Polish.** Version 1.3.0 in `pyproject.toml`, `frontend/package.json` and `create_app`;
   `AI_NOTES.md` entries; `frontend/FINDINGS.md` closes the intake note,
   `docs/roadmap.md` line.

## Risks

- **Spec 006 not merged.** Use the fallback of research R2; the enum test reads `models.py` until
  `openapi.json` has the schemas.
- **Spurious revisions.** A form that recomputes stored values would create a revision on an
  unchanged send. Mitigated by the `manual` mode on load and the round-trip test (SC-001).
- **Policy creeping into the form.** Reviewers reject any message that names a rule; the "no
  policy" unit test (data-model property 5) guards the obvious case.
- **Serial e2e suite.** New tests use unique IDs `E2E-FORM-*` and do not depend on earlier tests.
