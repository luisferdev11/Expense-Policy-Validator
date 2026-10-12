# Data model: Guided intake form

Front end only; nothing is stored on the server that is not stored today. Types are TypeScript in
`frontend/src/lib/receiptForm.ts` and `frontend/src/lib/draft.ts`. `ReceiptInput`, `Entity` and
`Language` below are the aliases exported by `frontend/src/api/types.ts` (spec 006 task T055;
`ReceiptInput` is the request shape, OpenAPI component `ReceiptInputRequest`), or the hand-written
`Receipt` in the same file in the fallback (research.md R2). Nothing imports the generated file
directly.

## Derived value

```ts
/** A value the form can compute. "auto" follows the computation; "manual" keeps what was typed. */
type Derived = { mode: "auto" | "manual"; value: string };
```

- In `auto` mode the stored `value` is ignored and the computed one is shown and sent.
- Typing into the field switches it to `manual`. A "Use computed value" button switches it back.
- A `manual` value that differs from the computation shows the warning of
  `contracts/form-fields.md`.

## Form state

```ts
interface LineRow {
  key: string;               // React key, stable for the row's life; never sent
  line_id: string;
  line_id_auto: boolean;     // true while line_id follows `${receipt_id}-L${n}`
  description_raw: string;
  language: Language;        // "en" | "es" | "fr" | "de" | "pt" | "ja"
  quantity: string;          // decimal text
  unit_price: string;        // decimal text
  amount: Derived;           // quantity × unit_price
  amount_usd: Derived;       // amount × rate, half up to 2 dp
}

interface ReceiptFormState {
  receipt_id: string;
  employee_id: string;
  employee_country: string;
  entity: Entity | "";       // "" until chosen; suggested from the country
  submitted_expense_type: string;
  merchant_name: string;     // "" ⇒ null
  mcc: string;               // integer text
  mcc_description: string;
  transaction_datetime: string; // "YYYY-MM-DDTHH:MM:SS" or "" ⇒ null
  currency: string;          // "" ⇒ null
  fx_rate_to_usd: Derived;   // auto = "1" while currency is "USD" on a new form; manual otherwise
  total_amount: Derived;     // Σ line amount
  total_amount_usd: Derived; // total × rate, or Σ line amount_usd without a rate
  attendee_count: string;    // integer text, "" ⇒ null
  trip_id: string;           // "" ⇒ null
  trip_nights: string;       // integer text, "" ⇒ null; sent as null when trip_id is ""
  pre_approval_ref: string;  // "" ⇒ null
  itemized: boolean;
  vat_number: string;        // "" ⇒ null; sent as null unless visible (contracts/form-fields.md row 19)
  vat_visible_on_load: boolean; // a revised receipt that had a VAT number keeps the field visible
  lines: LineRow[];          // at least one
}
```

Empty text means `null` for every nullable field. Whitespace is trimmed before that test.

## Field error

```ts
type FieldPath = string;   // "employee_id", "line_items.0.amount": the server's dotted loc
interface FieldError { path: FieldPath; message: string; source: "client" | "server" }
```

## Pure functions (all in `frontend/src/lib/receiptForm.ts`, test first)

| Function | Signature | Contract |
|---|---|---|
| `emptyForm` | `() => ReceiptFormState` | one empty line, currency `USD`, rate auto `1`, itemized true, language `en`, quantity `1` |
| `computed` | `(s: ReceiptFormState) => Computed` | every derived value from the current inputs; `null` where it cannot be computed (no rate and not USD, an unparseable input) |
| `formToReceipt` | `(s: ReceiptFormState) => ReceiptInputJson` | the exact body: every receipt key in the order of `contracts/form-fields.md`, money as strings, integers as numbers, `null` for empty nullable fields; derived values from `computed` when `auto` |
| `receiptToForm` | `(json: Record<string, unknown>) => { form: ReceiptFormState; dropped: string[] }` | inverse of `formToReceipt`; unknown keys reported in `dropped` (answer keys included); derived values set to `manual` when they differ from the computation; line IDs kept |
| `validateForm` | `(s: ReceiptFormState) => FieldError[]` | only the API's own constraints (research.md R4); paths in the server's dotted form |
| `serverErrors` | `(fields: string[], s: ReceiptFormState) => { mapped: FieldError[]; unmapped: string[] }` | mapping of `contracts/form-fields.md` "Mapping server errors" |
| `suggestEntity` | `(country: string) => Entity` | IN, JP, SG → APAC; GB, DE, FR, NL, IE, PT, ES → EMEA; otherwise GLOBAL (data/README) |
| `nextLineId` | `(receiptId: string, rows: LineRow[]) => string` | `${receiptId}-L${n}`, `n` one more than the highest used |
| `renameLines` | `(rows: LineRow[], oldId: string, newId: string) => LineRow[]` | renames only rows with `line_id_auto` |

`ReceiptInputJson` is the request shape (`ReceiptInput` from `types.ts`, OpenAPI component
`ReceiptInputRequest`, validation mode) narrowed so that every `Decimal` field is a `string`. The
validation-mode schema accepts a number or a string for a decimal; the form always sends the
string form.

### Properties the tests assert

1. **Round trip**: for every valid sample receipt `r`,
   `normalise(formToReceipt(receiptToForm(r).form))` equals `normalise(r)`, where `normalise`
   rewrites every decimal as its canonical string (`"12.5"` and `12.50` compare equal), the same
   normalisation as the backend content hash (`src/expense_validator/domain/idempotency.py`).
2. **Shape**: `Object.keys(formToReceipt(emptyForm()))` equals the 20 `ReceiptInput` keys, and each
   line has the 7 `LineItemInput` keys.
3. **No answer keys**: `receiptToForm({..., labels: {...}, notes: "..."})` drops them and reports
   them; `formToReceipt` never emits them.
4. **Exactness**: `8000 × 0.0067 = "53.60"`; `3 × 0.1 = "0.3"`; rounding is half up (`0.125 → 0.13`).
5. **No policy**: `validateForm` of a non-USD receipt with no rate and typed USD amounts returns no
   error.

## Draft (in `frontend/src/lib/draft.ts`)

```ts
interface IntakeDraft {
  version: 1;
  mode: "form" | "single" | "batch";
  form: ReceiptFormState;
  text: string;            // the textarea
  idempotencyKey: string;
  savedAt: string;         // ISO time, for the "Draft restored from …" notice
}
```

| Function | Contract |
|---|---|
| `loadDraft(): IntakeDraft \| null` | reads `epv.intake.draft.v1`; returns `null` on missing, unparseable or other version (and removes the bad entry) |
| `saveDraft(d)` | writes it; never throws |
| `clearDraft()` | removes it; never throws |
| `isEmptyDraft(d)` | true when the form equals `emptyForm()` and the text and key are empty; an empty draft is not saved |

Storage goes through `readStore` / `writeStore` in `frontend/src/lib/hooks.tsx`; a `removeStore`
helper with the same guard is added there.

## State transitions on the intake screen

```text
open ──(?revise=id)──▶ form prefilled from GET /receipts/{id}   (draft untouched)
open ──(draft found)──▶ restore mode, form, text, key; show notice
open ──(nothing)─────▶ default mode (batch, as today)

form ⇄ JSON         : formToReceipt ↔ receiptToForm (dropped keys reported)
submit ok           : accepted | existing | revision ⇒ clearDraft()
submit failed       : 422 / network ⇒ keep draft, show errors
Discard draft       : clearDraft(), emptyForm(), empty text
```
