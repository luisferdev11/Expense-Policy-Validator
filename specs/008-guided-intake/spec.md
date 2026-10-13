# Feature Specification: Guided intake form for a single receipt

**Feature Branch**: `feat/008-guided-intake`

**Created**: 2026-10-12

**Status**: Draft

**Release**: v1.3.0 (iteration 6)

**Input**: User description: "A guided form for a single receipt, so nobody has to paste JSON. Today
the intake screen is a JSON textarea; going back loses the text and the result. Add a field-by-field
form with repeatable line items, keep a draft in the browser, and prefill the form when a receipt is
revised." Source: `MEJORAS-ITERACION-FINAL.md`, Frontend, "Formulario guiado para un solo recibo"
(2026-10-11, front-end session), chosen by Luis on 2026-10-12.

## Context

The intake screen (`frontend/src/pages/IntakePage.tsx`) accepts one receipt or a batch as raw JSON:
a textarea, a file picker and two sample buttons. A person who is not a developer cannot write a
valid `ReceiptInput` by hand, and the screen keeps nothing when they navigate away. This feature
adds a third way to send **one** receipt: a form that builds the same JSON the textarea sends, to
the same endpoint, `POST /receipts`. The backend does not change.

Three constitution principles frame it:

- **Deterministic decisions (Principle II).** The form decides nothing about policy. It never warns
  that a rule will fire, never blocks a receipt the API would accept, and never copies a threshold
  from `data/policy-docs/`. Missing fields that the API accepts as `null` (a missing date, a missing
  conversion rate) are the engine's to judge (DOC-02, DOC-04).
- **Labels firewall (Principle I).** The form has no field for `labels`, `line_items[].labels` or
  `notes`. A pasted receipt that carries them loses them when it is opened in the form, and the API
  strips them anyway.
- **Iterative delivery (Principle XI).** The batch path and the JSON textarea stay as they are.

**Dependency.** The preferred order is after spec 006, user story 4 (`receipt` and `result` typed in
OpenAPI). Spec 006 publishes the submitted shape as the OpenAPI component `ReceiptInputRequest`
(validation mode, what a client sends) and the stored shapes as `ReceiptInput` and `ReceiptResult`;
its task T055 makes `frontend/src/api/types.ts` export named aliases (`ReceiptInput` for the request
shape, `Receipt`, `Result`, `Entity`, `Language` and the line item types) on top of the generated
file. The form imports **only from `types.ts`**, never from the generated file directly. If 006 is
not merged when this starts, the fallback is the hand-written `Receipt` in `types.ts`, with every
enum list kept in one module and a drift test (see research.md R2).

## Clarifications

### Session 2026-10-12

- Q: Batches too, or a single receipt? → A: A single receipt only. Batches stay JSON Lines or a
  JSON array, pasted or uploaded.
- Q: Where does the draft live? → A: In the browser only (`localStorage`). Nothing is sent to the
  server until the person submits.
- Q: Does the form check policy (for example, require a conversion rate for a non-USD receipt)?
  → A (**pending Luis's confirmation**): No. It enforces only what the API itself rejects. A non-USD
  receipt with no rate is sent; the engine raises DOC-04, which is the engine's call. The form makes
  the person type the USD amounts in that case, because `amount_usd` is required by the API and
  cannot be computed without a rate. This departs from the approved plan, which said "fx required
  when the currency is not USD"; if Luis prefers the plan's wording, US2 scenario 4, FR-010 and
  research R4 change to a blocking check and nothing else moves.
- Q: Who computes derived amounts? → A: The form proposes them (line amount, USD amounts, totals)
  and the person can override each one; an override that disagrees with the computation shows a
  warning but is sent as typed.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Send one receipt by filling in a form (Priority: P1)

An auditor or an employee has a paper receipt in front of them. They open Intake, choose "One
receipt (form)", fill in the header (who, where, when, how much), add one row per item, see the
totals add up in the receipt currency and in USD, look at the JSON that will be sent, and submit. The
result panel is the one the JSON path already shows: accepted, already known, or new revision, with
the receipt's live state.

**Why this priority**: it is the feature. Without it the only way in is hand-written JSON.

**Independent Test**: on an empty intake screen, fill the form for a two-line USD receipt and submit;
the receipt is accepted, appears in the queue, and its stored `receipt` equals the previewed JSON.

**Acceptance Scenarios**:

1. **Given** the intake screen, **When** the person chooses "One receipt (form)", **Then** the form
   shows the header fields, one empty line item, the computed totals and a submit button, and the
   textarea is hidden.
2. **Given** a line with quantity `2` and unit price `15.00`, **When** the unit price is entered,
   **Then** the line amount proposes `30.00`; **When** the person overrides it with `29.00`, **Then**
   the field shows a non-blocking warning that it differs from quantity × unit price, and `29.00` is
   sent.
3. **Given** currency `JPY` and conversion rate `0.0067`, **When** a line amount is `8000`, **Then**
   its USD amount proposes `53.60` and the receipt total in USD is the sum of the lines unless the
   person overrides the total.
4. **Given** the person clicks "Add line", **Then** a new row appears with its line ID
   `<receipt_id>-L<n>` and keyboard focus moves to its description; **When** they remove a row,
   **Then** the other rows keep their line IDs.
5. **Given** a filled form, **When** the person opens "Preview JSON", **Then** they see exactly the
   body that will be sent, with every field of `ReceiptInput` present (`null` where empty) and money
   as strings.
6. **Given** a valid form and an optional idempotency key, **When** the person submits, **Then** the
   request is `POST /receipts` with that key, and the result panel shows the outcome as it does for
   pasted JSON.
7. **Given** the same form is submitted twice, **Then** the second answer is "Already known", as on
   the JSON path.

---

### User Story 2 - See what is wrong before and after sending (Priority: P1)

The person makes mistakes: an empty required field, a letter in a number, a quantity of zero. The
form tells them which field and why before anything is sent. If the API still refuses the receipt,
the form marks the fields the API named.

**Why this priority**: a form that sends invalid receipts and shows a list of field names is no
better than the textarea (FINDINGS F-06).

**Independent Test**: submit a form with an empty employee ID and a quantity of `0`; nothing is
sent, both fields are marked with a reason, and an error summary links to each.

**Acceptance Scenarios**:

1. **Given** a required field is empty (receipt ID, employee ID, employee country, entity, declared
   type, MCC, MCC description, and for each line its description, language, quantity, unit price,
   amount and USD amount), **When** the person submits, **Then** nothing is sent, each such field is
   marked with "Required", and an error summary at the top lists them as links that move focus to the
   field.
2. **Given** a money field contains `12,5` or `abc`, **Then** the field is marked "Enter a number,
   for example 12.50" and nothing is sent.
3. **Given** a quantity of `0` or less, **Then** it is marked "Must be greater than 0" (the API
   requires `quantity > 0`).
4. **Given** a non-USD currency and no conversion rate, **When** the person fills the lines,
   **Then** the USD amounts are editable and required, the form explains that they cannot be computed
   without a rate, and the receipt is sent without a rate if the person chooses so.
5. **Given** the API answers `422 invalid_receipt` with `details.fields` such as
   `["line_items.1.language", "mcc"]`, **When** the answer arrives, **Then** those inputs are marked
   "The server refused this value", the summary lists them, and any field name that does not map to
   an input is listed as text.
6. **Given** any rule in `data/policy-docs/`, **Then** the form never shows a message about it; the
   result panel and the review screen are where findings appear.

---

### User Story 3 - Do not lose work when leaving the screen (Priority: P2)

The person fills half a receipt, opens the queue to check something, and comes back. The form, the
pasted text and the chosen mode are still there. After a successful submission, or when they choose
"Discard draft", the draft is gone.

**Why this priority**: the intake finding said "going back loses the text and the result"; it is the
second half of the same request, but the form is usable without it.

**Independent Test**: fill three fields, reload the page; the three fields are restored and a notice
says a draft was restored, with a "Discard draft" button.

**Acceptance Scenarios**:

1. **Given** a partly filled form, **When** the page is reloaded or the person navigates away and
   back, **Then** the form is restored with the same values and line items, and a notice says
   "Draft restored from <time>".
2. **Given** a restored draft, **When** the person clicks "Discard draft", **Then** the form is empty,
   the stored draft is deleted, and nothing is sent.
3. **Given** a submission is accepted, already known or a new revision, **Then** the draft is
   deleted.
4. **Given** a submission fails (validation or network), **Then** the draft is kept.
5. **Given** the browser refuses storage (private mode, quota), **Then** the form still works and no
   error is shown.
6. **Given** the JSON textarea mode, **Then** its text is kept in the draft as well.

---

### User Story 4 - Revise a stored receipt in the form (Priority: P2)

From a receipt's detail, "Submit a corrected revision" opens Intake with `?revise=<id>`. Today that
fills the textarea. With this feature it opens the form, prefilled with the stored receipt, so the
person changes one field and sends a new revision.

**Why this priority**: revising is the most common reason a non-developer would touch a receipt's
content; it depends on US1.

**Independent Test**: open `/intake?revise=<id>` for a stored receipt; the form shows every stored
value, including line IDs and any amounts that do not match the computation; changing the merchant
and submitting gives "New revision".

**Acceptance Scenarios**:

1. **Given** a stored receipt, **When** `/intake?revise=<id>` opens, **Then** the form mode is
   selected and every field shows the stored value; line IDs are kept; derived amounts that differ
   from the computation are shown as overrides, so sending without changes reproduces the stored
   receipt (the API answers "Already known").
2. **Given** a revise link and an existing draft, **Then** the revise prefill wins, and the draft is
   left in storage untouched until the person submits or discards.
3. **Given** the person prefers JSON, **When** they switch to "One receipt (JSON)", **Then** the
   textarea holds the JSON of the current form (and the reverse: a valid single receipt in the
   textarea can be opened in the form).

---

### Edge Cases

- A pasted receipt with extra keys (answer keys, unknown fields): "Edit in the form" drops them and
  says how many keys were dropped; the API would strip the answer keys and reject unknown ones.
- A non-itemized receipt (`itemized = false`): the form keeps one line, labelled "The charge", and the
  person enters its amount; the form does not hide the line, because the API requires the line list.
- A receipt with zero lines: allowed by the API type (an empty list). The form requires at least one
  line for an itemized receipt and keeps one for a non-itemized one; a stored receipt with zero lines
  opens in the form with one empty line and a notice.
- Currencies with no minor unit (JPY): money fields accept integers; USD amounts round half up to 2
  decimals.
- A receipt ID is changed after lines exist: line IDs that still follow `<old_id>-L<n>` are renamed
  to the new ID; line IDs typed by hand are kept.
- `vat_number` is shown only when the entity is EMEA; switching to another entity clears it and sends
  `null`. Exception: a receipt opened for revision that already has a VAT number keeps the field
  visible whatever the entity, so nothing is dropped silently.
- `trip_nights` is shown only when a trip ID is set; clearing the trip ID sends `trip_nights: null`.
- A very large number or more than 10 decimals in a rate: kept as typed; the arithmetic is exact on
  strings, never on binary floats.
- The API is unreachable: the error says so; the draft is kept.

## Requirements *(mandatory)*

### Functional Requirements

**Form and mode**

- **FR-001**: The intake screen MUST offer three modes: "One receipt (form)", "One receipt (JSON)"
  and "A batch". The JSON and batch modes MUST behave as today.
- **FR-002**: The form MUST cover every field of `ReceiptInput` and `LineItemInput`
  (`src/expense_validator/domain/models.py`), as listed in `contracts/form-fields.md`, and MUST emit
  every key of `ReceiptInput`, with `null` for an empty nullable field.
- **FR-003**: The form MUST NOT contain or emit `labels`, `line_items[].labels` or `notes`.
- **FR-004**: Line items MUST be repeatable (add, remove), each with a stable line ID that defaults
  to `<receipt_id>-L<n>` and can be edited.
- **FR-005**: The form MUST propose derived values (line amount = quantity × unit price; USD amount =
  amount × rate, or the amount itself when the currency is USD; receipt totals = sum of lines) and
  MUST let the person override each; an override that differs from the computation MUST show a
  non-blocking warning.
- **FR-006**: All money arithmetic MUST be exact decimal arithmetic on the typed strings; USD amounts
  MUST round half up to 2 decimals; money MUST be sent as JSON strings.
- **FR-007**: The person MUST be able to preview the exact JSON body before sending it.
- **FR-008**: Submission MUST use the existing `api.submitReceipt` with the optional idempotency key,
  and MUST show the same result panel as the JSON path.
- **FR-009**: Enumerated values (`entity`, line `language`) MUST come from the API types exported by
  `frontend/src/api/types.ts` (aliases over the generated file after spec 006, or one module checked
  by a drift test in the fallback). Free-text fields with known values (declared expense type,
  currency, country, MCC) MUST accept any value and MAY suggest known ones; the suggested declared
  types MUST be kept equal to the engine's known types by a test.

**Validation**

- **FR-010**: Before sending, the form MUST check only what the API rejects: required fields
  present, numbers parseable, integers where the type is an integer, quantity greater than 0, enum
  values in their set. It MUST NOT check any policy rule.
- **FR-011**: Each invalid field MUST show its reason next to it, be marked `aria-invalid`, and be
  linked to its message with `aria-describedby`; an error summary MUST list every invalid field as a
  link that moves focus to it.
- **FR-012**: A `422 invalid_receipt` answer MUST be mapped back to inputs through `details.fields`
  (dotted paths such as `line_items.1.amount`); unmatched names MUST be listed as text.

**Draft**

- **FR-013**: The form state, the textarea text and the chosen mode MUST be saved in the browser
  while the person types, and restored when the screen opens again, with a notice and a "Discard
  draft" control.
- **FR-014**: The draft MUST be deleted after an accepted, existing or revision outcome, and kept
  after any failure.
- **FR-015**: Storage failures MUST be silent and MUST NOT break the form.

**Revision**

- **FR-016**: `/intake?revise=<id>` MUST open the form prefilled from the stored receipt, preserving
  line IDs and every stored value, so that sending it unchanged is recognised as the same receipt.
- **FR-017**: The person MUST be able to move a single receipt between the form and the JSON
  textarea in both directions without losing values (except keys the form does not have, which are
  reported).

**Decision reasons** (added 2026-10-12, approved by Luis; the same front-end release, outside the
intake form)

- **FR-019**: In the Approve and Reject dialogs (`ActionDialog`) each action MUST offer only the
  reasons that can describe it. Approve: `policy_exception_granted`, `engine_false_positive`,
  `documentation_provided`, `other`. Reject: `engine_missed_issue`, `other`. The existing rule stays:
  a reason is required only when the decision overrides the engine's proposal (ADR 0007 D8:
  approving a `flag`, rejecting a `pass`), and `other` requires a note.
- **FR-020**: When Reject agrees with the proposal (the engine proposed `flag` or `review`, so it is
  not an override), the dialog MUST NOT show the reason list, only the optional note, and MUST NOT
  send a `reason_code`.
  - *Note.* This is a front-end change only. The API still accepts any reason code with any
    decision; a dedicated "confirmed violation" code was deliberately **not** added, and Luis may
    decide on it later. No ADR is needed for this.

**Boundaries**

- **FR-018**: The backend behaviour, the API contract and the policy engine MUST NOT change in this
  feature (FR-019 and FR-020 are front end only). The only backend edits allowed are the release version (`pyproject.toml` and the
  `version` passed in `create_app`, `src/expense_validator/app/api/__init__.py`) and the new
  contract test of FR-009.

### Key Entities

- **Receipt form state**: the header values, the list of line rows, and for each derived value
  whether it is computed or overridden. Converts to and from `ReceiptInput` JSON.
- **Draft**: a versioned snapshot of the intake screen (mode, form state, textarea text, idempotency
  key, saved time) kept in the browser.
- **Field error**: a path (`employee_id`, `line_items.0.amount`) and a message, from the client
  check or from the API.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For every valid single receipt in the repository's synthetic samples (N = 5:
  `SAMPLE-001` and `SAMPLE-002` from `frontend/src/samples/samples.ts`, `DEMO-001` from
  `docs/samples/receipt-one.json`, and one each from `receipt()` and `apac()` in
  `frontend/e2e/fixtures.ts`), converting the receipt to the form and back gives a body equal to the
  original after decimal normalisation, so the API treats it as the same receipt (a second submit
  answers "Already known"). The test asserts N = 5.
- **SC-002**: A two-line USD receipt can be entered and submitted with the keyboard only, from the
  first field to the result panel (one end-to-end test).
- **SC-003**: Every required-field and number error in US2 is caught before sending: in the
  end-to-end test, the network log shows zero `POST /receipts` while the form is invalid.
- **SC-004**: A reload restores a partly filled form with all values (one end-to-end test, 3
  fields and 2 lines checked).
- **SC-005**: The pure conversion and validation functions have unit tests covering every field in
  `contracts/form-fields.md` (N = 20 receipt fields + 7 line fields).
- **SC-006**: `npm test`, `npm run e2e` and `npm run build` pass; the backend test suite is green,
  with one new test (the declared-type list equals the engine's, N = 9 types today) and no other
  change.

## Assumptions

- The API keeps accepting money as JSON strings (pydantic lax `Decimal`), and the content hash
  normalises `12.5` and `"12.50"` to the same value (`domain/idempotency.py`), so a revision sent
  unchanged from the form is recognised as the same receipt.
- `submitted_expense_type`, `employee_country`, `currency` and `mcc` are free values in the API
  (`str` and `int`), so the form suggests but does not restrict them.
- The `details.fields` list of `invalid_receipt` stays as it is (names only, FINDINGS F-06). A
  per-field reason from the server is a separate backend improvement and is not required here.
- The Ledgerline classes already used on the intake screen (`ll-field`, `ll-input`, `ll-label`,
  `ll-btn`, `callout`) are enough; no new design-system component is needed.
- No role or authentication exists (spec 009 is design only), so anyone who can open Intake can use
  the form.
