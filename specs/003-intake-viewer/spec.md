# Iteration 2.1: intake in the viewer

**Release:** v0.2.1 · **Plan:** `docs/plans/2026-10-10-product-plan.md` · **Decisions:** ADR 0006

A small iteration, so spec, plan and tasks share this file.

## Goal

A person can load new receipts into the existing viewer and see them validated by the same
pipeline, before the backend of iteration 3 exists.

## Requirements

- **FR-1.** The Upload view accepts one receipt (a JSON object), a JSON array, or JSONL, as a
  file or pasted text.
- **FR-2.** Every row passes through `parse_receipt_line`, so answer keys are stripped as for
  the dataset (rule 1).
- **FR-3.** A bad row (invalid JSON, invalid receipt, duplicate `receipt_id` within the upload)
  is reported with its row number; the other rows still run.
- **FR-4.** The uploaded batch is the cross-receipt context (meal days, trips).
- **FR-5.** The run id is a hash of the receipts: the same upload gives the same id and output
  file, and no new billed calls (classification cache).
- **FR-6.** The cache for uploads is gitignored and seeded from the committed cache, so uploads
  never change committed outputs.
- **FR-7.** Every model call is traced in Langfuse; Langfuse never gates the run.

## Tasks

- [x] Tests first: `tests/unit/test_intake.py` (formats, partial success, stripping, duplicates,
  stable run id).
- [x] `src/expense_validator/app/intake.py`: `parse_upload`, `run_id`, `default_classifier`,
  `run_upload`.
- [x] Parity: `tests/integration/test_intake_parity.py`, uploading the 32 receipts reproduces
  `outputs/results.jsonl` byte for byte, with 0 calls.
- [x] Upload view in `viewer/app.py`; smoke test extended.
- [x] Demo file `docs/samples/upload-demo.jsonl`: two meals for one employee-day (MEAL-01 across
  receipts), a gift to an official (GIFT-04), one invalid row.
- [x] Live check: 4 new calls, USD 0.00028, traced.

## Out of scope

Persistence of uploads beyond a gitignored file, idempotency keys, revisions, reviewer actions:
iteration 3 (ADR 0006).
