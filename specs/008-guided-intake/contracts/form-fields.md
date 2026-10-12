# Contract: form fields

Every field of `ReceiptInput` and `LineItemInput` (`src/expense_validator/domain/models.py:34-64`),
checked against the model on 2026-10-12, with what the form shows and what it sends. Meanings come
from `data/README.md`. The form emits **every** receipt key below, in this order, with `null` for an
empty nullable field. `vat_number` is the only key with a default in the model; the form emits it
anyway (as `null`) so the preview always shows the full shape.

Legend for **Required**:

- **API**: the model has no default and does not allow `null`; the API refuses the receipt without
  it. The form blocks sending.
- **Nullable**: the key must be present but may be `null`. The form sends `null` when empty and
  never blocks.

Money and rates are `Decimal` in the model. The form keeps them as typed strings, does exact decimal
arithmetic on them (research.md R3), and sends them as **JSON strings** (`"12.50"`). Integers are
sent as JSON numbers.

## Receipt header

| # | Field | Label | Control | Required | Values / source | Default | JSON | Visibility |
|---|---|---|---|---|---|---|---|---|
| 1 | `receipt_id` | Receipt ID | text | API | free text | empty | string | always |
| 2 | `employee_id` | Employee ID | text | API | free text | empty | string | always |
| 3 | `employee_country` | Employee's home country | text with suggestions (`datalist`) | API | ISO 3166 alpha-2, uppercased on blur; suggestions: the countries named in `data/README.md` plus US | empty | string | always |
| 4 | `entity` | Regional entity | select | API | enum `GLOBAL`, `APAC`, `EMEA` from the API types (`Entity`) | suggested from the country (IN, JP, SG → APAC; GB, DE, FR, NL, IE, PT, ES → EMEA; else GLOBAL), the person confirms | string | always |
| 5 | `submitted_expense_type` | Declared expense type | text with suggestions | API | free `str` in the API; suggestions are the declared types the engine knows, today `Client Entertainment`, `Client Gifts`, `Computer Equipment`, `Lodging`, `Meals - Individual`, `Meals - Team`, `Office Supplies`, `Software`, `Travel - Other`, read from `frontend/src/samples/expense-types.json`, which a contract test keeps equal to `COVERS` (`domain/engine/rules/documentation.py`) ∪ `MEAL_TYPES` (`domain/engine/context.py`) | empty | string | always |
| 6 | `merchant_name` | Merchant | text | Nullable | free text; whitespace-only becomes `null` | empty | string or `null` | always |
| 7 | `mcc` | MCC | number (integer) | API | 4-digit integer; suggestions from the MCC table in `data/policy-docs/merchant-category-risk.md` | empty | number | always |
| 8 | `mcc_description` | MCC description | text | API | free text; filled from the suggestion when a known MCC is picked, editable | empty | string | always |
| 9 | `transaction_datetime` | Date and time (local, at the merchant) | `datetime-local` with seconds | Nullable | no time zone (data/README) | empty | `"YYYY-MM-DDTHH:MM:SS"` or `null` | always |
| 10 | `currency` | Currency | text with suggestions | Nullable | 3 uppercase letters; suggestions USD, EUR, GBP, INR, JPY, SGD | `USD` | string or `null` | always |
| 11 | `fx_rate_to_usd` | Rate to USD on the transaction date | decimal text | Nullable | > 0 when given | `1` when currency is USD (read-only while USD), empty otherwise | string or `null` | always; read-only when currency is `USD` |
| 12 | `total_amount` | Total (receipt currency) | decimal text, computed | Nullable | computed: sum of line `amount`; overridable, warning when it differs | computed | string or `null` | always |
| 13 | `total_amount_usd` | Total in USD | decimal text, computed | Nullable | computed: `total_amount × rate`, rounded half up to 2 decimals; when there is no rate and the currency is not USD, the sum of line `amount_usd`; overridable | computed | string or `null` | always |
| 14 | `attendee_count` | People covered (including the employee) | number (integer) | Nullable | integer; no minimum enforced beyond integer (the engine judges) | empty | number or `null` | always |
| 15 | `trip_id` | Trip ID | text | Nullable | free text | empty | string or `null` | always |
| 16 | `trip_nights` | Trip length (nights) | number (integer) | Nullable | integer ≥ 0 | empty | number or `null` | only when `trip_id` is set; otherwise sent as `null` |
| 17 | `pre_approval_ref` | Approval or exception reference | text | Nullable | free text (for example `PA-2026-0042`) | empty | string or `null` | always |
| 18 | `itemized` | The receipt lists its items | checkbox | API | boolean | checked | boolean | always |
| 19 | `vat_number` | Merchant VAT number | text | Nullable, has default | free text | empty | string or `null` | only when `entity` is `EMEA`, or when a revised receipt already has one |
| 20 | `line_items` | Items | repeatable rows (below) | API | at least one row in the form (the API accepts an empty list; see spec Edge Cases) | one empty row | array | always; when `itemized` is unchecked the single row is labelled "The charge" |

## Line item row

| # | Field | Label | Control | Required | Values / source | Default | JSON |
|---|---|---|---|---|---|---|---|
| 1 | `line_id` | Line ID | text, prefilled | API | `<receipt_id>-L<n>`, `n` = the next unused number; renamed with the receipt ID only while it still follows that pattern | generated | string |
| 2 | `description_raw` | Description (as printed) | text | API | free text, in its original language | empty | string |
| 3 | `language` | Language of the description | select | API | enum `en`, `es`, `fr`, `de`, `pt`, `ja` from the API types (`Language`) | `en` | string |
| 4 | `quantity` | Quantity | decimal text | API | > 0 (the model has `gt=0`) | `1` | string |
| 5 | `unit_price` | Unit price | decimal text | API | any decimal | empty | string |
| 6 | `amount` | Amount | decimal text, computed | API | computed `quantity × unit_price`; overridable, warning when it differs | computed | string |
| 7 | `amount_usd` | Amount in USD | decimal text, computed | API | computed `amount × rate` rounded half up to 2 decimals (`amount` itself when the currency is USD and no rate is given); when the currency is not USD and there is no rate, an editable required input with the hint "No rate on this receipt: type the USD amount" | computed | string |

## What the form computes and what it leaves to the person

| Value | Computed by the form | Person can override | Warning on override |
|---|---|---|---|
| line `amount` | `quantity × unit_price`, exact | yes | "Differs from quantity × unit price (<value>)" |
| line `amount_usd` | `amount × fx_rate_to_usd`, half up to 2 dp; `amount` when USD | yes; required input when no rate and not USD | "Differs from amount × rate (<value>)" |
| `total_amount` | Σ line `amount` | yes (taxes, tips on the total) | "Differs from the sum of the lines (<value>)" |
| `total_amount_usd` | `total_amount × rate`, half up to 2 dp; Σ line `amount_usd` when no rate | yes | "Differs from the total × rate (<value>)" |
| `fx_rate_to_usd` | `1` while the currency is `USD` | no while USD | none |
| `entity` | suggested from the country | yes (it is a select) | none |
| `mcc_description` | filled from a picked known MCC | yes | none |

None of these warnings blocks sending, and none of them names a policy rule.

## Mapping server errors to inputs

`422 invalid_receipt` carries `details.fields`: dotted paths from pydantic's `loc`
(`src/expense_validator/app/service.py:84`). The form maps:

| Server path | Input |
|---|---|
| `<field>` (header) | the header input of that name |
| `line_items` | the line list (summary message) |
| `line_items.<i>` | row `i` (0-based) as a whole |
| `line_items.<i>.<field>` | that field in row `i` |
| anything else | listed as text in the error summary |

The message for a mapped server error is "The server refused this value". The server does not give
a per-field reason today (FINDINGS F-06).

## Opening JSON in the form

`receiptToForm` accepts any JSON object. Known keys fill the form; unknown keys (including `labels`,
`notes` and `line_items[].labels`) are dropped and counted ("2 keys not shown in the form were
dropped"). Values are kept as strings exactly as given (a JSON number `12.5` becomes `"12.5"`), and a
derived value that differs from its computation is loaded as an override, so a stored receipt round-
trips.
