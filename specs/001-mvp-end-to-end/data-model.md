# Data Model: Iteration 1 MVP

All models live in `src/expense_validator/models.py`, except where noted. They are Pydantic v2
models, frozen; see research R1. Money is `Decimal` (R2). Field names follow `data/README.md` and
the brief's output shape. Exact Python types are settled in implementation. The constraints below
are the contract.

## Inputs (produced by `loader.py`, firewall applied)

### `LineItemInput`

| Field | Type | Constraint |
|---|---|---|
| `line_id` | str | e.g. `RCP-014-L4` |
| `description_raw` | str | Unchanged from the file |
| `language` | Literal `en` `es` `fr` `de` `pt` `ja` | |
| `quantity` | Decimal | > 0 |
| `unit_price` | Decimal | In the receipt's currency |
| `amount` | Decimal | `quantity × unit_price` |
| `amount_usd` | Decimal | |

`extra="forbid"`: a surviving `labels` key fails validation.

### `ReceiptInput`

| Field | Type | Constraint |
|---|---|---|
| `receipt_id`, `employee_id` | str | |
| `employee_country` | str | ISO 3166 alpha-2 |
| `entity` | Literal `GLOBAL` `APAC` `EMEA` | |
| `submitted_expense_type` | str | One of the DOC-03 table's types |
| `merchant_name` | str or null | DOC-02 checks presence |
| `mcc` | int | |
| `mcc_description` | str | |
| `transaction_datetime` | naive datetime or null | Local time at the merchant |
| `currency` | str or null | DOC-04 checks presence |
| `fx_rate_to_usd` | Decimal or null | DOC-04 checks presence (REG-05) |
| `total_amount`, `total_amount_usd` | Decimal or null | DOC-02 checks presence |
| `attendee_count` | int or null | Includes the employee |
| `trip_id` | str or null | |
| `trip_nights` | int or null | |
| `pre_approval_ref` | str or null | The kind comes from the prefix table (A5) |
| `itemized` | bool | |
| `vat_number` | str or null | Optional, absent in this dataset (A2) |
| `line_items` | list of `LineItemInput` | |

`extra="forbid"`: a surviving `labels` or `notes` key fails validation.

## Pipeline intermediates

### `NormalisedItem`

`line_id`, `description_raw`, `description_clean` (NFKC, whitespace collapsed, case folded for
matching only), `language`. It never carries the declared type or the attendee count.

### `ClassifierRequest`

What the classifier port receives:
- `description_clean`;
- `merchant_name`;
- `mcc`.

No other field. A contract test enforces this (FR-007).

### `Classification`

| Field | Type | Constraint |
|---|---|---|
| `line_id` | str | |
| `status` | Literal `classified` `unclassified` | |
| `category` | Category enum of 21, or null | Null only when unclassified |
| `restricted` | bool or null | Derived from the taxonomy, never from the model |
| `confidence` | float in [0, 1], or null | |
| `subtype` | Literal `event_ticket` `mobile_handset` `prescription_medication` `none` | `none` unless the category is `other` (A6) |
| `recipient_kind` | Literal `none` `client_or_prospect` `employee` `government_official` | A9 |
| `recipient_name` | str or null | Normalised. Equal names mean one recipient (A9) |
| `unclassified_reason` | str or null | e.g. `gateway_error`, `schema_violation`, `budget_refused`, `offline_cache_miss` |
| `source` | `ClassificationSource` | See below |

**State transitions.**
- A cache hit, or a valid model answer, gives `classified`.
- A gateway error, a schema violation, a budget refusal or an offline miss gives `unclassified`.

The engine treats an `unclassified` item as uncertain:
- it raises EXC-03 with the reason;
- the item is excluded from every other rule's calculation;
- the receipt can never be `pass` (FR-009).

### `ClassificationSource`

`classifier` (`openrouter` or `keyword`), `model_id`, `provider_endpoint`, `prompt_version`,
`cache_key`, `request_id`, `cost_usd`, `prompt_tokens`, `completion_tokens`, `cache_hit`.

### `CacheEntry` (one row of `outputs/classifications.jsonl`, the literal model answer)

Each row holds:
- the `cache_key`;
- the model's literal answer `content`;
- the `reasoning` text;
- the model ID, provider endpoint and prompt version;
- the request id, billed cost and token counts.

The answer is parsed on every read. A parser change therefore never needs a new paid call, and
a schema violation replays identically offline. This changed during implementation: the first
version stored parsed fields and dropped failed answers, which broke offline replay (AI_NOTES).

A key collides only when the cleaned text, merchant, MCC, model, endpoint and prompt version are
all identical.

### `ClassifiedReceipt`

The `ReceiptInput`, plus one `Classification` per line, aligned by `line_id`.

### `CrossReceiptContext` (built by `engine/context.py`)

- **`meal_days`**: a map from (`employee_id`, calendar date) to a list of `MealContribution`.
  Each contribution holds `receipt_id`, `per_person_usd`, `international: bool`, and the
  entity's cap basis.
- **`trip_otc`**: a map from `trip_id` to the total OTC medication spend in USD, over classified
  `health_otc` lines.

It is built from all classified receipts, with uncertain items excluded. The result does not
depend on the order of receipts.

### `RuleSet`

The rule IDs the retriever selected for one receipt, held in a sorted tuple.

### `Settings` (from `docs/decisions/policy_decisions.yaml` via `engine/settings.py`)

- `fx.date_basis`, `fx.rate_kind`, `fx.missing_rate_disposition` (A1);
- `exc03.threshold`, provisionally 0.5 (A3);
- `reference_prefixes` (A5).

The country-to-currency table (A8) and the euro rate table (A1) come from `config/`.

## Engine output

### `RuleSpec` (registry entry in `engine/registry.py`)

`rule_id`, `policy_doc`, `severity` (Literal `critical` `high` `medium` `low`, a `review_signal`
marker, or `modifier`), `scope` (`items` or `receipt`), `decisions` (a tuple of A-IDs), and
`evidence`, a verbatim sentence checked by a test.

### `ExceptionFinding`

| Field | Type | Constraint |
|---|---|---|
| `rule_id` | str | In the registry |
| `policy_doc` | str | File name in `data/policy-docs/` |
| `severity` | Literal `critical` `high` `medium` `low` | |
| `line_ids` | sorted list of str | Empty for whole-receipt rules. Never a `service_fee` line (EXC-04) |
| `evidence` | str | The literal policy sentence |
| `explanation` | str | Filled by the reporter |
| `decisions` | list of str | The A-IDs applied (an additional field, allowed by the brief) |
| `computed` | map of str to str | The values behind a threshold, e.g. `per_person_usd`, `cap_usd` (additional) |

At most one finding per `rule_id` per receipt (FR-019).

### `ReviewSignal`

`rule_id` (`MCC-02` or `EXC-03`), `policy_doc`, `reason`, and `line_ids` (additional, for
EXC-03).

### `EngineFindings`

The exceptions and review signals, both sorted by `rule_id`, and the disposition from EXC-01.

## Output (one line per receipt in `outputs/results.jsonl`)

### `OutputLineItem`

Brief fields: `line_id`, `description_raw`, `category`, `restricted`, `confidence`.

Additional fields: `subtype`, `recipient_kind`, `recipient_name`, `status`,
`unclassified_reason`.

### `ReceiptResult`

Brief fields: `receipt_id`, `disposition` (`flag`, `review` or `pass`), `line_items`,
`exceptions`, `review_signals`.

Additional field: `run`, a `RunMetadata`.

### `RunMetadata`

`classifier`, `model_id`, `provider_endpoint`, `prompt_version`, `rules_version`,
`exc03_threshold`, `exc03_threshold_status` (`provisional`).

It holds no timestamp and no run ID (R9).

## Evaluation outputs (`eval/`, the only reader of answers)

- **`outputs/eval/comparison.jsonl`**, one line per receipt:
  - `receipt_id` and `scored` (false for the four out-of-scope receipts);
  - the predicted and answer dispositions;
  - per line, the predicted and answer category and restricted flag;
  - matched, missed and extra exceptions, with an `evidence_exact` flag;
  - matched, missed and extra review signals;
  - the answer's exceptions and signals, with their reasons, for the viewer.

  The list of out-of-scope receipts lives in `eval/` configuration, never in pipeline code.
- **`outputs/eval/metrics.json`**: every FR-030 and FR-031 metric, each as
  `{value, n, interval?}`, for three systems: the pipeline, `keyword-classifier` and
  `keyword-flagger`.
- **`outputs/eval/report.md`**: generated from `metrics.json`, with the two failure-case slots
  and the base-rate table.
- **Baseline results**: `outputs/baselines/keyword_classifier/results.jsonl` and
  `outputs/baselines/keyword_flagger/results.jsonl`.
