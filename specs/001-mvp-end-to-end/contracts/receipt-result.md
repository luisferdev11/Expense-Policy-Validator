# Contract: one line of `outputs/results.jsonl`

This is the brief's shape. Fields may be added; none of the brief's fields may be removed or
renamed. The authoritative JSON Schema is exported from `ReceiptResult` (see `data-model.md`) to
`contracts/receipt-result.schema.json` during implementation. A test fails if the export drifts.

```json
{
  "receipt_id": "RCP-0XX",
  "disposition": "flag | review | pass",
  "line_items": [
    { "line_id": "RCP-0XX-L1", "description_raw": "<as printed>",
      "category": "<one of 21>", "restricted": true, "confidence": 0.93,
      "subtype": "none", "recipient_kind": "none", "recipient_name": null,
      "status": "classified", "unclassified_reason": null }
  ],
  "exceptions": [
    { "rule_id": "TECH-02", "policy_doc": "technology-and-equipment-policy.md",
      "severity": "medium", "line_ids": ["RCP-0XX-L1"],
      "evidence": "<verbatim policy sentence>",
      "explanation": "<template: rule, lines, arithmetic>",
      "decisions": ["A5"], "computed": {"unit_price_usd": "329.00", "cap_usd": "200.00"} }
  ],
  "review_signals": [
    { "rule_id": "MCC-02", "policy_doc": "merchant-category-risk.md",
      "reason": "<template>", "line_ids": [] }
  ],
  "run": { "classifier": "openrouter", "model_id": "openai/gpt-oss-120b",
           "provider_endpoint": "deepinfra/bf16", "prompt_version": "cls-v2",
           "rules_version": "<12 hex>", "exc03_threshold": 0.5,
           "exc03_threshold_status": "provisional" }
}
```

The example uses placeholder IDs and invented values. It is a shape, not an answer.

**Invariants.** Tests check each of these.
- **Disposition.** `disposition` follows EXC-01 from `exceptions` and `review_signals`.
- **One finding per rule.** No two exceptions on a receipt share a `rule_id`.
- **Whole-receipt rules** cite empty `line_ids`. These are MCC-01, MEAL-01, MEAL-02, DOC-01 to
  DOC-04 and REG-02 to REG-04.
- **No fee lines.** No `line_ids` entry refers to a line whose category is `service_fee`.
- **Verbatim evidence.** Every `evidence` is verbatim from its `policy_doc`.
- **Never pass with an unclassified or uncertain line.** Such a line implies an `EXC-03` review
  signal, so the disposition is never `pass`.
- **Canonical serialisation.** Field order follows the models, receipts are sorted by
  `receipt_id`, and the file ends with a newline. There is no timestamp.
