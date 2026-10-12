# Quickstart: validating API hardening end to end

Prerequisites: `uv sync`, and `npm install` in `frontend/`. No key and no model call are needed for
any section except §6 `live`. Details: [contracts/api-delta.md](contracts/api-delta.md),
[data-model.md](data-model.md).

## 1. Automated checks

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run mypy
cd frontend && npm test && npm run typecheck && cd ..
```

Expected: green. The integration tests prove SC-001 (two workers, parity), SC-002 (no double
billing), SC-003 (export), SC-004 (migration) and SC-009 (`epv run` unchanged).

## 2. Migrate an existing database

A database written by v0.3.0 or v0.4.0 (schema 1) is migrated the first time v1.1.0 opens it:

```bash
cp var/epv.sqlite3 var/epv.backup.sqlite3          # optional: keep the v1 file
uv run epv serve --offline --no-trace               # opening the file migrates it
curl -s localhost:8000/health                       # {"status":"ok","schema_version":2,"open_work":0}
curl -s 'localhost:8000/receipts?order=created_at&limit=5'
```

Every receipt now shows `created_at` (from its first revision) and, when decided, `decided_by` and
`decided_at`. A failed migration leaves the file at schema 1 and prints the error.

## 3. The shared cache

```bash
rm -f var/two.sqlite3
uv run epv worker --db var/two.sqlite3 --offline --no-trace &   # worker 1
uv run epv worker --db var/two.sqlite3 --offline --no-trace &   # worker 2, same database
uv run epv serve  --db var/two.sqlite3 --no-trace &
# submit the 32 receipts (the parity test does this in process; by hand, use Postman's batch request)
uv run epv cache export --db var/two.sqlite3 | diff - outputs/classifications.jsonl   # empty: nothing billed
```

The table was seeded from `outputs/classifications.jsonl` when the first process opened the file.
`--cache PATH` on `serve` or `worker` names a different seed file. The budget cap (`--cap-usd`,
default USD 1.00) applies to what each process bills; seeded and cached answers never count.

## 4. Decisions on the list

```bash
curl -s -X POST localhost:8000/receipts -H 'Content-Type: application/json' \
  --data @docs/samples/receipt-one.json
curl -s localhost:8000/receipts/DEMO-001 | jq '{state, created_at, decided_by, decided_at}'
# auto_approved: decided_by "system"
curl -s -X POST localhost:8000/receipts/DEMO-001/actions/reject -H 'Content-Type: application/json' \
  --data '{"actor":"alice","evaluation_version":1,"reason_code":"engine_missed_issue"}'
curl -s 'localhost:8000/receipts?order=updated_at' | jq '.items[] | {receipt_id, decided_by, decided_at}'
# DEMO-001: decided_by "alice"
```

## 5. Contract, OpenAPI, Postman

```bash
uv run epv openapi > docs/api/openapi.json && git diff --stat docs/api/openapi.json   # empty when committed
cd frontend && npm run gen:api && git diff --stat src/api/generated.ts && cd ..       # empty
uv run python docs/api/build_collection.py
uv run epv serve --with-worker --offline --no-trace &
npx --yes newman run docs/api/epv.postman_collection.json -e docs/api/epv.local.postman_environment.json
```

Expected: no diff; Newman passes every assertion. v0.4.0 had 51 requests and 99 assertions; after
T056 there are 53 requests and 108 assertions, all passing on a fresh instance (run on 2026-10-12;
the counts are updated again when the `/health` `open_work` assertion is added).

## 6. Load test

Start a fresh database with the simulated classifier, then run a profile:

```bash
rm -f var/perf.sqlite3
uv run epv serve --with-worker --classifier simulated --simulated-latency-ms 0 \
  --no-trace --db var/perf.sqlite3 &                       # smoke: no latency
DATE=$(date +%F)
uv run locust -f perf/locustfile.py --headless --host http://127.0.0.1:8000 \
  --profile smoke --csv docs/perf/raw/$DATE-smoke/locust
uv run python -m perf.report --profile smoke --raw docs/perf/raw/$DATE-smoke \
  --out docs/perf/$DATE-smoke.md --drain --host http://127.0.0.1:8000
```

| Profile | Start the server with | Rate | Duration |
|---|---|---|---|
| `smoke` | `--classifier simulated --simulated-latency-ms 0` | about 1 receipt a second | 30 s |
| `nominal` | `--classifier simulated --simulated-latency-ms 1500` | 1.2 a second (100,000 a day) | 5 min |
| `peak` | `--classifier simulated --simulated-latency-ms 1500` | 12 a second (10× peak) | 5 min |
| `live` | `--classifier openrouter --cap-usd 0.25` (key in `.env`) | 0.2 a second | 2 min |

Use a fresh `--db` per run. The report states the machine and commit, p50/p95/p99 per endpoint with
N, throughput, failures, drain time and peak backlog, and compares with `docs/aws.md`. The queue is
read only from `GET /health` (`open_work`): sampled every 0.5 s during the run for the peak backlog,
and polled after the run until it is 0 for the drain time. To rebuild a report from committed raw
data without load: run only the `perf.report` line without `--drain`.

The receipts are generated from `docs/samples/receipt-one.json` with ids `LT-<run>-<n>` and employee
ids prefixed `TEST-`; nothing
reads `data/receipts.jsonl`. The simulated classifier answers every line the same way, so the
results say nothing about policy; only timings matter.

## 7. Invariants

```bash
uv run epv run --offline --no-trace && git diff --stat outputs/             # empty
uv run pytest tests/integration/test_api_parity.py -q                        # 32 receipts, 5 orders
uv run pytest tests/integration/test_firewall_scan.py -q                     # includes the cache table
git diff --stat main -- src/expense_validator/domain/engine/                 # empty
```
