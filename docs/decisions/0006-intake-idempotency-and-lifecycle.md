# ADR 0006: Receipt intake, idempotency, revisions and the review lifecycle

- **Status:** accepted (design); implemented in iteration 3
- **Date:** 2026-10-10
- **Decided by:** Luis, while planning iterations 2.1 to 5.

## Context

Until v0.2.0 the pipeline runs as one batch over a file. The product needs to take new receipts,
one at a time or in batches, and survive interruptions. A receipt can be saved while the client
gets an error. When the client retries, the system must not create a second receipt, must show
the one it has, and must know where processing stopped. After classification the product also
needs a defined path: what a reviewer can do, and what happens after a review.

## Decisions

1. **Persist first, then work.** A submitted receipt is written to an append-only event log
   (`ReceiptSubmitted`) before any processing and before the response. Processing is
   asynchronous: a worker claims an outbox row with a lease and records one event per completed
   stage (classified, evaluated). After a crash it resumes at the first incomplete stage. A
   redone classification hits the cache, so it costs nothing and returns the same answer.
2. **Idempotency.** The idempotency key is the client's `Idempotency-Key` header, or else the
   `receipt_id` plus the SHA-256 of the canonical receipt. The same key with the same content
   returns the existing receipt and its current state, and starts no new work.
3. **Same `receipt_id`, different content: a new revision.** Revision n+1 is stored and
   evaluated; revision n stays in the trail. This is how an employee corrects a receipt, and how
   a reply to "request information" comes back.
4. **Cross-receipt changes re-evaluate the affected receipts.** MEAL-01, REG-02 and REG-03
   (employee and day) and HEALTH-01 (trip) depend on other receipts. When a receipt lands, the
   context for its keys is rebuilt and every receipt that shares them is evaluated again. A
   changed result is a new evaluation version and returns to the queue with a notice, so the
   outcome does not depend on arrival order and matches the batch run.
5. **Lifecycle.** `submitted → classifying → evaluated`, then `pass → auto_approved` (a sample
   goes to quality review), `review` or `flag → in_review`, a critical finding `→ compliance`.
   Any stage can end in `failed(stage, reason)`, which is retried from that stage.
6. **Reviewer actions.**
   - Approve or reject the receipt. A reason code is required when the decision overrides the
     engine's proposal.
   - Correct a line's category. The engine runs again, deterministically, with the human category
     (source `auditor`); the new findings replace the proposal, and the line becomes a dev-set
     candidate.
   - Request information from the employee: the receipt waits in `needs_info`, and the
     resubmission is a new revision (decision 3).
   - Escalate to Compliance. Critical findings already go there directly.
   Every action is an event, and a Langfuse score `auditor_agreement` on the receipt's trace.
7. **Storage.** SQLite locally (events, projections, outbox), mirroring the AWS design (SQS,
   DynamoDB, S3). The committed outputs and `epv run` stay unchanged, so the evaluation never
   depends on the application.

## Consequences

- The engine stays pure: re-evaluation passes it a rebuilt context, and a human category is
  an ordinary classification with a different source.
- Parity check: submitting the 32 receipts through the API must give results identical to
  `epv run`.
- Not covered here: authentication (candidate L2) and notification delivery to employees.
