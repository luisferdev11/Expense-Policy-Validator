# Contract: API and CLI changes

Everything else in `specs/004-backend-lifecycle/contracts/api.md` (as amended by spec 006) is
unchanged. Errors use the existing shape: `{"error": {"code", "message", "details"}}`.

## `GET /receipts/{receipt_id}/shadow`

Returns the shadow comparison for the receipt's **current** revision.

**200**:

```json
{
  "receipt_id": "RCP-X",
  "revision": 1,
  "primary": {"classifier": "openrouter", "model_id": "openai/gpt-oss-120b", "prompt_version": "cls-v2"},
  "shadow": {"classifier": "hybrid", "model_id": "typesafe/jev-1.13+openai/gpt-oss-120b", "prompt_version": "hyb-v1(dec-v1+cls-v2)"},
  "lines": [
    {
      "line_id": "RCP-X-L1",
      "primary": {"status": "classified", "category": "alcohol", "confidence": 0.98,
                  "subtype": "none", "recipient_kind": "none", "recipient_name": null,
                  "unclassified_reason": null},
      "shadow":  {"status": "classified", "category": "food_beverage", "confidence": 0.97,
                  "subtype": "none", "recipient_kind": "none", "recipient_name": null,
                  "unclassified_reason": null},
      "agrees_category": false,
      "agrees_all": false
    }
  ],
  "summary": {"lines": 1, "comparable": 1, "agree_category": 0, "agree_all": 0},
  "created_at": "2026-10-12T18:00:00.000000+00:00"
}
```

- **`comparable`** counts the lines where both sides are `classified`.
- **`agrees_all`** compares category, subtype, `recipient_kind` and `recipient_name`. Names are
  compared after `casefold()` and whitespace trimming.
- **`primary`** is the stored classification of that revision. The shadow never changes it.
- **Typed schemas.** `ShadowLine` and `ShadowView` are declared in `app/api/schemas.py`, so they
  appear in `openapi.json`.
- **As built.** `shadow.classifier` is the factory name the rows were stored under (`jev-hybrid`,
  the value of `--shadow`), not the composite source's `hybrid` of the example; `primary` comes
  from the stored classification's source. A line the shadow has no row for is left out of `lines`
  and of the summary. `created_at` is the latest shadow row's. `/health` now reports
  `schema_version: 3`.

**404 `not_found`**: there is no such receipt.

**404 `no_shadow`**: the current revision has no shadow rows, either because shadow mode was off
or its work is still pending.

## CLI

| Command | Change |
|---|---|
| `epv worker --shadow {jev-1.13,jev-hybrid}` | New flag. Default none. `EPV_SHADOW` sets it when the flag is absent |
| `epv serve --with-worker --shadow ...` | The same flag, passed to the in-process worker |
| `epv shadow report [--db PATH] [--json]` | New command: the agreement report of FR-016, from the store only; no model call |
| `epv run` | Unchanged flags. The classifier comes from `config/pipeline.yaml` through the factory |

`epv openapi` regenerates `docs/api/openapi.json` with the new path and schemas. The drift test
(`tests/smoke/test_openapi.py`) and its path set are updated, and so is the Postman collection
(`docs/api/build_collection.py`, one request asserting the 404 `no_shadow` case offline).
