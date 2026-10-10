# Plan: from batch pipeline to a product (iterations 2.1–5)

Approved by Luis on 2026-10-10. Decisions are recorded in ADR 0006; the order of work in `docs/roadmap.md`.

## Context

Iterations 1–2 deliver a batch pipeline (`epv run` over `data/receipts.jsonl`), committed outputs,
an evaluation, and a read-only Streamlit viewer. v0.2.0 scores 28/28 dispositions.

Luis wants, before delivery (Saturday 2026-10-10, night):
- a real application (FastAPI + React/Vite, Ledgerline design, mockups in
  https://claude.ai/artifact/EMAPwShVsAojUGiPCHtzqZ as a starting point, not the last word);
- loading new receipts, one at a time and in batches, robust to interruptions (the "an order was
  saved but the user got an error: do we create another one?" problem);
- a defined lifecycle after classification: what a reviewer can do, what happens after a review;
- a demonstrative comparison of three models (gpt-oss-120b reference, gpt-oss-20b best LLM
  challenger, jev-1.13 best decision model).

This session only defines the design. A later session implements it with Spec Kit
(specify → plan → tasks), one iteration per release.

## What exists and is reused

- `app/pipeline.py`: `classify_receipt` (per receipt) and `run_pipeline` (batch; the cross-receipt
  context needs every receipt of the batch).
- `domain/engine/context.py` `build_context`: meal days per employee-date and OTC per trip.
- `domain/engine/evaluate.py` `evaluate`, `domain/retriever.py` `retrieve`, `domain/reporter.py`.
- `adapters/classification_cache.py`: answers keyed by request content, model, endpoint and
  prompt. A retried classification is free and identical.
- `adapters/receipts_file.py` `parse_receipt_line` (strips answer keys), `domain/models.py`
  `ReceiptInput` (the intake contract).
- `adapters/tracing.py`: one trace per receipt, deterministic trace IDs.
- `explorations/lib/decision_adapters.py`: decision-model (jev) scaffolding from E13.
- `docs/design/ledgerline.css` + tokens; mockups: workbench, compliance case, insights, boundary.

## Design

### 1. Receipt lifecycle (state machine)

```
submitted → classifying → evaluated ─┬─ pass   → auto_approved (a sample goes to QA)
                                      ├─ review → in_review ─┬→ approved
                                      ├─ flag   → in_review ─┼→ rejected
                                      └─ critical → compliance┘└→ needs_info → (employee) → resubmitted
any stage → failed(stage, reason) → retried from that stage
```

Every transition is an event appended to an event log. The current state is a projection.

### 2. Intake and idempotency

- `POST /receipts` (one) and `POST /batches` (JSONL or JSON array). The client may send an
  `Idempotency-Key`; without one, the key is `receipt_id` + SHA-256 of the canonical receipt.
- Same key, same content → 200 with the existing receipt and its current state (no new work).
- Same `receipt_id`, different content → a new revision (Q-A).
- The receipt is persisted (event `ReceiptSubmitted`) before any work and before the response,
  so a dropped connection never loses it and a retry finds it.
- Processing is asynchronous: an outbox row per submitted receipt; a worker claims rows
  (lease with timeout), runs stage by stage, and writes one event per completed stage. A crash
  resumes at the first incomplete stage; classification hits the cache, so redoing it costs
  nothing and gives the same answer.
- A batch is a parent with per-receipt children: partial success is normal; the batch view shows
  counts per state and lets failed items be retried.

### 3. Cross-receipt re-evaluation

MEAL-01/REG-02/REG-03 (employee-day) and HEALTH-01 (trip) depend on other receipts. When a
receipt lands, the worker rebuilds the context for its keys and re-evaluates every receipt that
shares them → decision Q-B. A re-evaluation is a new evaluation version; the old one stays
in the trail.

### 4. Reviewer actions (after classification)

Decision Q-C, all four actions:
- Approve / Reject the receipt (closes it; reason code required when it overrides the proposal).
- Correct a line's category → the engine re-runs deterministically with the human category
  (source `auditor`), the new findings replace the proposal, and the item becomes a dev-set
  candidate.
- Request information from the employee → `needs_info`; a resubmission creates a revision.
- Escalate to Compliance (critical findings go there directly).
- Every decision is an event and a Langfuse score `auditor_agreement` on the receipt's trace.

### 5. Storage and processes (local, mirrors the AWS page)

- SQLite: `events` (append-only), `receipts` projection, `outbox`. One file under `var/`,
  gitignored. AWS mapping: SQS + DynamoDB + S3 (Option B of the mockups).
- `epv serve` (FastAPI) and `epv worker` (separate process, or in-process for demos).
- Committed outputs and `epv run` stay as they are: evaluation reproducibility does not depend on
  the app.

### 6. Screens (React + Vite, Ledgerline)

From the mockups, kept: review queue + workbench, compliance case, insights, theme toggle.
Added:
- **Intake**: upload one receipt (form or JSON) or a batch file; live per-receipt state.
- **Receipt timeline**: the event trail (submitted, classified, evaluated vN, decided).
- **Evaluation** (developer/lead area, outside the auditor view, per the "who sees what" board):
  metrics with N, experiments table, the three-model comparison.
Improvements over the mockups: show "checked and passed" rules, the arithmetic, and the
confidence as Certain/Likely/Uncertain (already there); add retry and failed states.

### 7. Three-model comparison (demonstrative)

On the frozen dev set: 120b and 20b from E14 (already committed); jev-1.13 through
the decision API, category only (it returns no subtype or recipient), traced in Langfuse.
Shown in the Evaluation screen; decides nothing.

## Decisions taken with Luis (2026-10-10)

- **Q-A, same `receipt_id` with different content → a new revision.** Revision n+1 is stored,
  re-evaluated, and revision n stays in the trail. Luis asked for this to be recorded: first task
  of iteration 3 is ADR 0006 (intake, idempotency and revisions), before any code.
- **Q-B, cross-receipt changes → re-evaluate the affected receipts and notify.** A changed
  disposition is a new evaluation version and returns to the queue.
- **Q-C, reviewer actions: all four.** Approve/reject (reason code when overriding), correct a
  line's category (deterministic re-run, line becomes a dev-set candidate), request information
  (`needs_info` → resubmission = revision), escalate to Compliance.
- **Q-D, order of work:** Streamlit intake first, as an update of the last release; then the
  backend with Postman collections for Luis to check it; then the front; then delivery.

## Iterations

| Iteration | Release | Content |
|---|---|---|
| 2.1 · intake in the viewer | v0.2.1 | Streamlit page to upload one receipt (JSON) or a batch (JSONL), run the existing pipeline on it (traced, cached, through `parse_receipt_line`, so answer keys are stripped), and show results in the existing views. Context = the uploaded batch. No persistence beyond an output file per upload. Smoke test |
| 3 · intake and lifecycle backend | v0.3.0 | ADR 0006; SQLite event store + projections + outbox; FastAPI `epv serve` and `epv worker`; idempotent single and batch intake with revisions; stage-by-stage resume; cascade re-evaluation; review actions API; Langfuse `auditor_agreement` scores. Postman collection + environment under `docs/api/` covering every endpoint and the edge cases (repeat POST, revision, batch with a bad row, cascade, each review action). Tests: idempotency, crash-resume, cascade, parity with `epv run` |
| 4 · application | v0.4.0 | React + Vite on the API, Ledgerline tokens: intake, queue + workbench, compliance, receipt timeline, insights, evaluation with the 3 models (jev-1.13 run on the dev set, traced) |
| 5 · delivery | v1.0.0 | README, AWS page (incl. Q3), failure cases (CoreWeave → RCP-012), base rate, AI_NOTES closed, engine adjustments from Luis's review session |

Each iteration: branch, Spec Kit cycle sized to it, PR, tag + GitHub release.

## Verification

- Idempotency: the same POST twice → one receipt, one processing; same id, other content → per Q-A.
- Crash-resume: kill the worker mid-batch → restart → every receipt reaches `evaluated`, zero
  extra billed calls (cache), identical results.
- Cascade: two meal receipts for one employee-day submitted apart → the first is re-evaluated and
  MEAL-01 appears on both, as in the batch run.
- Parity: submitting the 32 receipts through the API gives results identical to `epv run`.
- Review: correct a category → new evaluation version; decision events appear as Langfuse scores.
- Front: smoke tests per screen; manual walk-through of upload → review → decision.
