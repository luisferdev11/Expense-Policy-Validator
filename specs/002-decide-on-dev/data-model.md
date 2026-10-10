# Data Model: Iteration 2

Iteration 1's models are unchanged (`src/expense_validator/domain/models.py`). This iteration
adds experiment records outside the domain, plus two small settings changes.

## Frozen dev item (`explorations/dev_set/dev_set_v2.jsonl`)

| Field | Type | Constraint |
|---|---|---|
| `item_id` | str | `DEV-001` … `DEV-130` |
| `description`, `language`, `merchant_name`, `mcc` | as in the draft | Inputs to the classifier |
| `category`, `restricted` | Category, bool | Luis's reviewed label; restricted comes from the taxonomy |
| `subtype` | Subtype | Reviewed where proposed, else `none` |
| `recipient_kind`, `recipient_name` | RecipientKind, str or null | Reviewed where proposed, else `none` and null |
| `review` | `confirmed`, `changed` or `debatable-confirmed` | From `label_reviews.jsonl` |
| `trap` | str or null | Kept from the draft |

`FROZEN.md` records the SHA-256 of the file, the item count and the date.

## Experiment registration (`experiments_plan.yaml` entry)

`id`, `factor`, `variants[]`, `held_fixed`, `data` (the frozen set's hash), `metrics[]`,
`decision_rule`, `approved_by`, `registered_at`, `amendments[]` (date and reason).

## Prediction row (`explorations/results/iter2/<experiment>/<variant>.jsonl`)

`item_id`, `variant`, `model_id`, `prompt_version`, `status`, `category`, `restricted`,
`confidence`, `subtype`, `recipient_kind`, `recipient_name`, `raw_content`, `request_id`,
`cost_usd`, `cache_hit`. For E5 only: `translation`.

## Experiment outcome (`outputs/eval/experiments.json`)

For each experiment:
- **Description:** `id`, `factor`, `rule`, `n`.
- **`variants[]`:** each with its metrics, every metric as `{value, n, interval?}`, plus `cost_usd`
  and `failures`.
- **The decision:** `winner`, `margin` (the statistic, its value and its interval) and
  `why_others_lost[]`.

Iteration totals: `spend_usd` and `calls`.

## Oracle ablation (in `outputs/eval/metrics.json`, under `oracle`)

- **Accuracy:** `disposition_accuracy` as `{value, n, interval}`.
- **`rows[]`:** each with `receipt_id`, `pipeline`, `oracle`, `answer` and `stage`.
  - `stage` is one of: `classification`, `rule_logic_or_convention`,
    `right_for_wrong_reason`, `none`.
- **`limitation`:** the answers carry no subtype or recipient labels.

## Settings changes

- **`config/pipeline.yaml`** (new), read by `adapters/config_files.py`:
  - `classifier_model`, a pin name;
  - `confidence_source`, `self_reported` or `agreement`;
  - `translate`, a bool;
  - `null_subtype_as_none`, a bool.
- **`RunMetadata.exc03_threshold_status`** becomes `chosen_on_dev` once E7 decides.
  `RunMetadata` gains `confidence_source` and `pipeline_config_version`, the hash of
  `config/pipeline.yaml`.
