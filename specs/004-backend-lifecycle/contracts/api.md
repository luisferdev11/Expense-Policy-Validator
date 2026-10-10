# HTTP API contract

Base URL `http://localhost:8000`. JSON in and out. The machine-readable document is FastAPI's
`/openapi.json`; the Postman collection in `docs/api/` mirrors this file. Every response that
carries a receipt carries the **stripped** receipt only.

## Error shape

```json
{"error": {"code": "stale_evaluation", "message": "...", "details": {}}}
```

Codes: `invalid_receipt` (422), `idempotency_key_reuse` (422), `not_found` (404),
`action_not_allowed` (409), `stale_evaluation` (409), `reason_required` (422), `unknown_category`
(422).

## Receipts

### `POST /receipts`

Headers: `Idempotency-Key` (optional, at most 255 characters). Body: one receipt (the input
contract of `ReceiptInput`; answer keys are tolerated and discarded).

| Case | Status | Body |
|---|---|---|
| New receipt | 202 | `{"receipt_id", "revision": 1, "outcome": "accepted", "state": "submitted"}` |
| Same key or same content again | 200 | the same, with `"outcome": "existing"` and the current state |
| Same `receipt_id`, different content, no reused key | 202 | `"outcome": "revision"`, `"revision": n+1` |
| Client key reused with a different body | 422 | `idempotency_key_reuse` |
| Invalid body | 422 | `invalid_receipt`, with the offending fields |

### `GET /receipts`

Query: `state`, `disposition`, `batch_id`, `limit` (default 100), `offset`. Returns
`{"items": [ReceiptSummary], "total": n}`.

### `GET /receipts/{receipt_id}`

```json
{
  "receipt_id": "...", "revision": 2, "state": "in_review", "disposition": "flag",
  "evaluation_version": 3, "notice": null, "qa_sample": false,
  "failed": null,
  "receipt": { "...stripped ReceiptInput..." },
  "result": { "...ReceiptResult as in outputs/results.jsonl..." },
  "allowed_actions": ["approve", "reject", "correct-category", "request-info", "escalate"]
}
```

### `GET /receipts/{receipt_id}/events`

`{"items": [{"seq", "revision", "type", "actor", "at", "payload"}]}` in `seq` order.

### `GET /receipts/{receipt_id}/revisions/{n}`

The revision's stripped content, its status and its evaluation versions.

### `POST /receipts/{receipt_id}/retry`

Retries a receipt in `failed` from the failed stage. `202`; `409 action_not_allowed` otherwise.

## Reviewer actions

`POST /receipts/{receipt_id}/actions/{action}`, `action` one of `approve`, `reject`,
`correct-category`, `request-info`, `escalate`. Common body fields: `actor` (required),
`evaluation_version` (required), `note` (optional).

| Action | Extra fields | Result state |
|---|---|---|
| `approve` | `reason_code` (required when overriding a `flag`) | `approved` |
| `reject` | `reason_code` (required when overriding a `pass`) | `rejected` |
| `correct-category` | `line_id`, `category` | `in_review` or `compliance` (new evaluation version) |
| `request-info` | `question` | `needs_info` |
| `escalate` | `reason` | `compliance` |

Response `200`: the updated receipt (as `GET`), plus `"agreement": 0 or 1`. A stale
`evaluation_version` or a state that does not allow the action gives `409`.

## Batches

### `POST /batches`

Body: JSONL (`Content-Type: application/x-ndjson`) or a JSON array (`application/json`). Optional
`Idempotency-Key`. Status `202` when every row was accepted or existed, `207` when some rows were
invalid.

```json
{"batch_id": "bat_ab12cd34", "total": 4,
 "items": [{"row": 1, "receipt_id": "...", "outcome": "accepted"},
           {"row": 3, "receipt_id": null, "outcome": "invalid", "error": "not valid JSON: ..."}]}
```

### `GET /batches/{batch_id}`

`{"batch_id", "total", "counts": {"submitted": 0, "classifying": 1, "in_review": 2, ...},
"items": [...]}`. Items in `failed` can be retried with `POST /receipts/{id}/retry`.

## Operations

`GET /health` returns `{"status": "ok", "schema_version": 1}`.
