# Quickstart: validating the backend end to end

Prerequisites: `uv sync`; the committed classification cache is enough, no key is needed for the
offline scenarios. Details of the API are in [contracts/api.md](contracts/api.md) and the tables
in [data-model.md](data-model.md).

## 1. Run the automated checks

```bash
uv run pytest            # includes parity, order independence, crash-resume, firewall scan
uv run ruff check . && uv run ruff format --check . && uv run mypy
```

Expected: green. The integration tests prove SC-001 to SC-004, SC-007 and SC-008.

## 2. Start the processes

```bash
uv run epv serve --port 8000          # API
uv run epv worker                     # a second terminal; use --once to drain and exit
```

`uv run epv serve --with-worker` runs both in one process for a demo.

## 3. Submit and repeat

```bash
curl -s -X POST localhost:8000/receipts -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: demo-1' --data @docs/samples/receipt-one.json
# 202 accepted; repeat the exact command: 200 existing, no second processing
curl -s localhost:8000/receipts/<receipt_id>/events
```

## 4. Postman

Import `docs/api/epv.postman_collection.json` and `docs/api/epv.local.postman_environment.json`,
select the environment and run the collection in order. Every request carries assertions; the
collection covers each endpoint, a repeated POST, a revision, a batch with a bad row, a cascade and
each reviewer action.

## 5. Parity and crash drills

```bash
uv run pytest tests/integration/test_api_parity.py -q
uv run pytest tests/integration/test_crash_resume.py -q
```

Expected: the 32 receipts submitted in several orders equal `outputs/results.jsonl`; a worker that
dies mid-batch is resumed with zero additional billed calls.
