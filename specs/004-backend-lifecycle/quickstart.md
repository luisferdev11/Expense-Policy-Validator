# Quickstart: validating the backend end to end

Prerequisites: `uv sync`. The committed classification cache is enough: no key and no model call
are needed for any scenario below. Details of the API are in [contracts/api.md](contracts/api.md)
and the tables in [data-model.md](data-model.md).

## 1. Run the automated checks

```bash
uv run pytest            # includes parity, order independence, crash-resume, firewall scan
uv run ruff check . && uv run ruff format --check . && uv run mypy
```

Expected: green. The integration tests prove SC-001 to SC-004, SC-007 and SC-008.

## 2. Start the processes

Two processes share one SQLite file (`var/epv.sqlite3`, or `--db`, or `$EPV_DB`):

```bash
uv run epv serve --port 8000 --no-trace            # the API
uv run epv worker --offline --no-trace             # a second terminal; add --once to drain and exit
```

For a demo, one command runs both: `uv run epv serve --with-worker --offline --no-trace`.
`--offline` never calls a model. Without it, the worker classifies unknown lines through
OpenRouter (the key is read from `.env`), and every call is traced in Langfuse when it is up.

## 3. Submit and repeat

```bash
curl -s -X POST localhost:8000/receipts -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: demo-1' --data @docs/samples/receipt-one.json
# 202 accepted. Repeat the exact command: 200 existing, no second processing.
curl -s localhost:8000/receipts/DEMO-001               # state, result, allowed actions
curl -s localhost:8000/receipts/DEMO-001/events        # the trail
```

The sample's lines are in the committed cache, so it ends `auto_approved` with disposition `pass`.

## 4. Review it

```bash
curl -s -X POST localhost:8000/receipts/DEMO-001/actions/reject \
  -H 'Content-Type: application/json' \
  --data '{"actor": "alice", "evaluation_version": 1}'
# 422 reason_required: rejecting what the engine passed overrides it.
curl -s -X POST localhost:8000/receipts/DEMO-001/actions/reject \
  -H 'Content-Type: application/json' \
  --data '{"actor": "alice", "evaluation_version": 1, "reason_code": "engine_missed_issue"}'
# 200, state rejected, "agreement": 0
```

## 5. Postman or Newman

Start `uv run epv serve --with-worker --offline --no-trace`, then import
`docs/api/epv.postman_collection.json` and `docs/api/epv.local.postman_environment.json` and run the
collection in order, or from the command line:

```bash
npx --yes newman run docs/api/epv.postman_collection.json \
  -e docs/api/epv.local.postman_environment.json
```

Expected: 51 requests, 99 assertions, 0 failed, in about 20 seconds. It covers every endpoint, a
repeated POST, a revision, a batch with a bad row, a cascade, each reviewer action, a decision that
returns to review, and a critical finding. Each run uses its own id, so it can be run again on the
same database. `docs/api/build_collection.py` generates the files; `uv run epv openapi` prints the
OpenAPI document that is committed as `docs/api/openapi.json`.

## 6. Parity and crash drills

```bash
uv run pytest tests/integration/test_api_parity.py -q      # 32 receipts, 5 orders, 2 modes
uv run pytest tests/integration/test_crash_resume.py -q    # a worker killed mid-batch
uv run pytest tests/integration/test_firewall_scan.py -q   # no answer key in the store, responses or traces
uv run epv run --offline --no-trace && git diff --stat outputs/   # empty: epv run is unchanged
```

Expected: the 32 receipts submitted in shuffled orders, together or one by one, equal
`outputs/results.jsonl` byte for byte with zero model calls; a worker that dies mid-batch is
resumed with identical results and no extra billed call; no answer key anywhere; `epv run` still
writes the committed outputs.
