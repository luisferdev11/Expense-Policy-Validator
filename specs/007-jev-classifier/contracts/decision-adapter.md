# Contract: decision adapter (jev) and hybrid classifier

Both classes implement `ItemClassifier` (`src/expense_validator/ports/classifier.py`):
`name`, `model_id`, `provider_endpoint`, `prompt_version` and
`classify(line_id, ClassifierRequest) -> Classification`. They receive only
`description_clean`, `merchant_name` and `mcc`.

## 1. `DecisionClassifier` (module `adapters/openrouter/decision_classifier.py`)

| Attribute | Value |
|---|---|
| `name` | `openrouter-decision` |
| `model_id` | `typesafe/jev-1.13` |
| `provider_endpoint` | `openrouter` (the routed endpoint, as in `ModelPin.endpoint`) |
| `prompt_version` | `dec-v1` |
| URL | `https://openrouter.ai/api/alpha/decisions` |
| Auth | `Authorization: Bearer $OPENROUTER_API_KEY` (read from the environment, never logged) |
| Cap | Constructor argument `cap_usd`: the spend this process billed. The factory sets it per role (see "Budget caps") |

### Request body (`dec-v1`)

The payload is moved verbatim from `explorations/lib/decision_adapters.py`
(`DECISION_INSTRUCTIONS`, `decision_payload`) into
`adapters/openrouter/decision_prompt.py`. The criteria come from the package taxonomy
(`domain/taxonomy.py`) with the same example text as `explorations/lib/classifier_prompt.py`'s
`TAXONOMY`. A test checks that the moved payload equals the exploration's for 3 sample items, so
the dev-set evidence stays valid.

```json
{
  "model": "typesafe/jev-1.13",
  "state": {"item": "<description_clean>", "merchant": "<merchant_name>", "mcc": "<mcc as string>"},
  "questions": {
    "category": {
      "type": "choice",
      "instructions": "<DECISION_INSTRUCTIONS>",
      "criteria": {"alcohol": "<examples>", "...": "...", "other": "<examples>"}
    }
  }
}
```

### Transport

- Use `httpx`, with timeout 120 s.
- Retry on HTTP 429, 502 and 503 with backoff `min(30, 2**attempt)` seconds, up to 6 attempts in
  total (as in `frontend/scripts/jev_dev_run.py:108-139`).
- Any other status of 400 or above, a timeout, or a connection error raises inside the transport.
- The transport is injectable (a `Callable[[dict], tuple[dict, str]]`, like `Transport` in
  `openrouter/classifier.py`), so tests never touch the network.

### Response mapping

| Response | `Classification` |
|---|---|
| `answers.category.choice` in the 21 categories, a usable confidence | `classified`, `category = choice`, `restricted = restricted_for(choice)`, `confidence` per the next row, `subtype = "none"`, `recipient_kind = "none"`, `recipient_name = None` |
| Confidence source | `probabilities[choice]` (top probability) when present and in [0, 1]; else `answers.category.confidence` when in [0, 1]. The source used is recorded in the cache entry's `reasoning` field as `confidence_source=<top_probability|confidence>` |
| `choice` missing or outside the taxonomy, no usable confidence, or the body unparseable | `unclassified`, `schema_violation` (stays one on every replay) |
| Transport raised | `unclassified`, `gateway_error` (not cached) |
| Cache miss in offline mode | `unclassified`, `offline_cache_miss` |
| Spend cap reached | `unclassified`, `budget_refused` |

### Cache

- **Key:**
  `sha256(canonical_json({"description_clean", "merchant_name", "mcc", "model_id", "provider_endpoint", "prompt_version": "dec-v1", "payload_digest": sha256(canonical payload)}))`.
  It is the same function family as `classification_cache.cache_key`, extended with the payload
  digest because the decision payload carries the instructions and criteria.
- **Entry:** a `CacheEntry` with `content` set to the literal response body (JSON text), `model_id`,
  `provider_endpoint`, `prompt_version = "dec-v1"`, `request_id` (`body.id`, else
  `noid-<key[:16]>`), `cost_usd = usage.cost`, `prompt_tokens = usage.input_tokens` (or
  `prompt_tokens`), `completion_tokens = usage.output_tokens` (or `completion_tokens`),
  `reasoning` as above, and `served_by = body.provider`.
- **Store:** through spec 006's `ClassificationCachePort`. The worker and API use the
  `SqliteClassificationCache` table adapter; `epv run` and `run_dev.py` use the JSONL
  `ClassificationCache` adapter. `put` is first-write-wins on both.

### Budget caps (who sets them)

The factory (`build_classifier`) takes a `cap_usd` per role, and each adapter counts only what it
bills itself (spec 006 FR-008: cached and seeded answers never count).

| Role | `DecisionClassifier` | gpt-oss side of the hybrid | Source of the cap |
|---|---|---|---|
| Primary (`classifier_model: jev-1.13` or `jev-hybrid`) | USD 1.00 per process | USD 1.00 per process | `CAP_USD` of `openrouter/classifier.py`, the same as today's primary |
| Shadow (`--shadow`) | `--shadow-cap-usd`, default USD 0.25 per process | Same value, counted separately | The shadow flag |
| E16 (`run_dev.py`) | The USD 0.10 that remains of E16's budget | Not billed: the committed E14 answers (rebuilt from `E14/gpt-oss-120b.jsonl`; the cache directory is gitignored) | The registration |

For a hybrid, each side has its own counter, and a line is refused (`budget_refused`) when the
side that would bill has reached its cap.
- **Raw bodies:** also written to `.cache/raw/<request_id>.json`, as the current adapter does.

### Tracing

One `classify-item` generation per **billed** call; a cache hit produces none.

- Fields at start:
  - `model = typesafe/jev-1.13`;
  - `input` = the payload;
  - `model_parameters = {"endpoint": "/api/alpha/decisions", "kind": "decision", "provider_endpoint": "openrouter"}`;
  - `prompt` = the linked `classify-item-decision` prompt;
  - `metadata = {"prompt_version": "dec-v1", "cache_key": key}`.
- After the call: `output = answers.category`, `usage_details = {input, output}`,
  `cost_details = {total}` and `metadata = {request_id, served_by, confidence_source}`.
- On error: `level = "ERROR"` with `status_message` set to the exception type name.
- On a schema violation: `level = "WARNING"`.

## 2. `HybridClassifier` (module `adapters/hybrid_classifier.py`)

| Attribute | Value |
|---|---|
| `name` | `hybrid` |
| `model_id` | `typesafe/jev-1.13+openai/gpt-oss-120b` (category model first) |
| `provider_endpoint` | `openrouter` |
| `prompt_version` | `hyb-v1(dec-v1+cls-v2)` |

It holds a `DecisionClassifier` (`category_source`) and an `OpenRouterClassifier` with the
`gpt-oss-120b` pin (`detail_source`). Each keeps its own cache entries under its own keys. It
calls both, the category side first.

### Merge table

| jev (category side) | gpt-oss (detail side) | Result |
|---|---|---|
| classified `c` ≠ `other` | classified, any category | `c`, jev confidence, subtype `none`, gpt-oss `recipient_kind` and `recipient_name` |
| classified `other` | classified `other`, subtype `s` | `other`, jev confidence, subtype `s`, gpt-oss recipient fields |
| classified `other` | classified ≠ `other` | `other`, jev confidence, subtype `none`, gpt-oss recipient fields; trace `hybrid_conflict = true` |
| classified | `schema_violation` | jev category and confidence, subtype `none`, recipient `none` / `None`; trace `detail_violation = true` |
| `schema_violation` | any | `unclassified`, `schema_violation` |
| `gateway_error` or `budget_refused` | any | `unclassified` with jev's reason (transient: the worker retries) |
| classified | `gateway_error` or `budget_refused` | `unclassified` with gpt-oss's reason (transient) |
| either `offline_cache_miss` | – | `unclassified`, `offline_cache_miss` |

### Source of a merged answer (`ClassificationSource`)

The schema is unchanged. The fields are composite, joined with `+` in the order category side,
detail side:

- `classifier = "hybrid"`;
- `model_id`, `prompt_version` and `served_by` as composites (for example `deepinfra+groq`);
- `cache_key` = sha256 of the two keys joined with `+`;
- `request_id` = the two ids joined with `+`;
- `cost_usd` and tokens are sums, with `None` when both are `None`;
- `cache_hit` is `true` only if both sides hit.

`calls_made`, `cache_hits` and `run_spend_usd` are the sums of both sides, so `ReceiptClassified`
keeps counting billed calls correctly.

### Tracing

Each side emits its own `classify-item` generations, so a fully billed line produces two. The
`classify-receipt` span output gains `hybrid_conflict` and `detail_violation` per line, only when
true. No observation name contains a model name.

## 3. Factory (`app/classifiers.py`)

`build_classifier(name, tracer, cache, *, offline, prompt_links, null_subtype_as_none) -> ItemClassifier`
does the following:

- A name in `PINS`: today's `OpenRouterClassifier`, byte-identical behaviour.
- `jev-1.13`: `DecisionClassifier`.
- `jev-hybrid`: `HybridClassifier(DecisionClassifier, OpenRouterClassifier(PINS["gpt-oss-120b"]))`.
- Any other name raises `ValueError`, listing the accepted names.

`default_classifier` (`app/intake.py:93`), `build_worker` (`app/composition.py:76`), the shadow
stage and `epv run` call only this factory.

As built (phase 3): `prompt_links` is a mapping with the keys `chat` and `decision`, and
`app/classifiers.py` also provides `sync_prompt_links(name, tracer, offline)`, which syncs only the
prompts the named classifier needs (a pin: `cls-v2`; `jev-1.13`: `dec-v1`; the hybrid: both).
`default_classifier(tracer, cache_path, offline, prompt_links)` returns an `ItemClassifier` and its
callers read `calls_made` and `run_spend_usd` with `getattr`. `CLASSIFIER_NAMES` lives in
`adapters/openrouter/models.py`, so `load_pipeline_config` (an adapter) can validate against it,
and `app/classifiers.py` re-exports it. The hybrid exposes `last_flags`, `last_keys` and
`last_latency_s` after every call (the span output, the E16 runner), and the merged source's
`prompt_version` is the hybrid's own, `hyb-v1(dec-v1+cls-v2)`.
