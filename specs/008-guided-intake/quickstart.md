# Quickstart: validating the guided intake form

Prerequisites: `uv sync` at the repository root and `npm ci` in `frontend/`. No key and no model
call are needed: the backend runs `--offline`.

## 1. Automated checks

```bash
cd frontend
npm test && npm run typecheck && npm run build
npm run e2e        # starts epv serve --with-worker --offline --no-trace and Vite by itself
```

Expected: green. The unit tests prove SC-001 (round trip, the test prints its N) and SC-005; the
end-to-end tests prove SC-002, SC-003 and SC-004.

## 2. Try it by hand

```bash
uv run epv serve --with-worker --offline --no-trace     # terminal 1, API on :8000
cd frontend && npm run dev                              # terminal 2, app on :5173
```

Open `http://localhost:5173/intake` and:

1. Choose **One receipt (form)**. Fill receipt ID `HAND-1`, employee `E-1`, country `US` (entity
   becomes GLOBAL), declared type `Office Supplies`, MCC `5943`, description "Office supply stores".
2. Line 1: "Legal pads 3-pack", quantity `1`, unit price `12.50`. Add a line: "Ballpoint pens box of
   12", quantity `2`, unit price `15`. Totals show `42.50` and USD `42.50`.
3. Override line 2's amount with `29.00`: a warning appears, nothing blocks.
4. Open **Preview JSON**: every field is present, money as strings, `vat_number` is `null`.
5. Submit: "Accepted". Submit again: "Already known".
6. Change the currency to `JPY` and clear the rate: the USD amounts become required inputs with
   "No rate on this receipt: type the USD amount". Type them and submit: the API accepts it, and the
   review screen shows the engine's DOC-04. The form never mentioned DOC-04.
7. Fill half a new receipt, open the queue, come back: "Draft restored from …". Click
   **Discard draft**.
8. From a receipt's detail, "Submit a corrected revision": the form opens with the stored values.
   Submit unchanged: "Already known". Change the merchant: "New revision".

## 3. Check the boundaries

```bash
git diff --stat main -- src/ tests/ docs/api/
uv run pytest tests/contract/test_expense_types.py   # suggestions equal the engine's declared types
```

Expected diff outside the front end: the 1.3.0 version lines (`src/expense_validator/app/api/__init__.py`,
`info.version` in `docs/api/openapi.json`) and the new `tests/contract/test_expense_types.py`;
nothing under `src/expense_validator/domain/`.

Paste a receipt that contains `labels` and `notes` into **One receipt (JSON)** and click **Edit in
the form**: the notice says the keys were dropped, and the preview has neither.
