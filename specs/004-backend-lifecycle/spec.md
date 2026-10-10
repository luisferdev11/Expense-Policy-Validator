# Feature Specification: Intake and lifecycle backend

**Feature Branch**: `feat/004-backend-lifecycle`

**Created**: 2026-10-10

**Status**: Draft

**Release**: v0.3.0 (iteration 3)

**Input**: User description: "Iteration 3: the intake and lifecycle backend. Persist-first idempotent
intake of single receipts and batches; revisions; resume after a crash; re-evaluation when other
receipts change the outcome; a review lifecycle with four reviewer actions; auditor-agreement
scores; a Postman collection to exercise it. Built from ADR 0006 and the product plan."

## Context

Until v0.2.1 the validator runs as a batch (`epv run`) or as an upload into a viewer that keeps
nothing. A product needs to accept receipts over time, survive interruptions, and give an auditor a
defined path after the classification. This iteration adds that backend. The decisions are recorded
in `docs/decisions/0006-intake-idempotency-and-lifecycle.md`; the questions ADR 0006 leaves open are
closed in ADR 0007 before any code is written.

Three constraints from the constitution frame everything below:

- **Labels firewall (Principle I).** The backend never sees, stores, returns or traces the answer
  keys of `data/receipts.jsonl` (`labels`, `line_items[].labels`, `notes`). Everything it handles is
  the stripped receipt. No part of this iteration reads that file except evaluation code.
- **Deterministic decisions (Principle II).** The policy engine, the retriever and the disposition
  logic do not change. A human correction is an ordinary classification with a different source; the
  engine runs again over it.
- **Langfuse never gates a run (Principle X).** Tracing and scoring are best effort.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Submit a receipt without fear of duplicates (Priority: P1)

An employee or an upstream system submits a receipt. The connection drops after the receipt was
saved and the caller sees an error. The caller retries. The system must show the receipt it
already has, in its current state, and must not create or process a second one.

**Why this priority**: it is the central robustness requirement of the brief extension ("an order
was saved but the user got an error: do we create another one?"), and every other story builds on a
receipt being stored safely first.

**Independent Test**: submit the same receipt twice, with and without a client-supplied key;
verify one stored receipt, one processing run, and the same answer both times.

**Acceptance Scenarios**:

1. **Given** no receipt `R`, **When** `R` is submitted, **Then** it is stored before any
   processing and before the response, and the response reports its identity and state.
2. **Given** `R` is stored, **When** the identical `R` is submitted again, **Then** the response is
   the existing receipt in its current state and no new work starts.
3. **Given** a client-supplied idempotency key was used for `R`, **When** the same key arrives with
   a different body, **Then** the request is rejected as a conflict and nothing changes.
4. **Given** a submission contains answer keys, **When** it is stored, **Then** the stored and
   returned receipt contains none of them, and the same receipt with and without them is treated
   as the same receipt.

---

### User Story 2 - Get the same decision as the batch run, in any order (Priority: P1)

A receipt is processed through its stages and receives findings and a disposition. Rules that depend
on other receipts (several meals on one employee-day, a trip's over-the-counter total) give the same
answer whatever order the receipts arrive in, and the same answer as the batch run.

**Why this priority**: without parity with `epv run` the product cannot be trusted against the
evaluation; it is the strongest demonstration that the application did not fork the logic.

**Independent Test**: submit the 32 receipts one by one in shuffled order; after processing, the
results equal `outputs/results.jsonl` produced by `epv run`, byte for byte per receipt.

**Acceptance Scenarios**:

1. **Given** the 32 receipts submitted in any order, **When** processing completes, **Then** every
   result is identical to the batch run's, and no billed model call is made when the
   classification cache already holds the answers.
2. **Given** a meal receipt is evaluated alone, **When** a second meal for the same employee-day
   arrives, **Then** the first is evaluated again, the cross-receipt rule appears on both, and the
   change is recorded as a new evaluation version.
3. **Given** a receipt whose re-evaluation produces the same result, **When** the cascade runs,
   **Then** no new version is recorded and no notice is raised.

---

### User Story 3 - Survive a crash (Priority: P1)

A worker stops in the middle of a batch (process killed, power loss). On restart every receipt
reaches the evaluated state without being lost or processed twice, and without extra billed calls.

**Why this priority**: makes the persist-first promise real end to end; "resume" is the first thing
a reviewer will test.

**Independent Test**: stop the worker after some lines of a batch are classified, restart, verify
all receipts evaluated, identical results, and zero additional billed calls.

**Acceptance Scenarios**:

1. **Given** a worker stopped mid-receipt, **When** the lease on its work expires and a worker runs,
   **Then** the work resumes at the first incomplete stage.
2. **Given** a stage already completed, **When** work resumes, **Then** the completed stage is not
   repeated (or, for classification, is answered from the cache at no cost).
3. **Given** a stage fails with an error, **When** it is retried, **Then** the receipt shows
   `failed` with the stage and reason, and a retry restarts from that stage.

---

### User Story 4 - Review a flagged receipt with four actions (Priority: P2)

After evaluation, a receipt that passed is auto-approved (a sample goes to quality review); one with
review or flag disposition waits for an auditor; one with a critical finding goes to Compliance. An
auditor can approve or reject, correct a line's category, request information from the employee, or
escalate to Compliance. Every action is recorded and measurable.

**Why this priority**: this is the "what happens after classification" gap the product plan names;
it depends on Stories 1-3 but is a separate, demonstrable slice.

**Independent Test**: take a receipt in review and perform each action through the interface;
verify the resulting state, the event trail and the agreement score.

**Acceptance Scenarios**:

1. **Given** a receipt in review, **When** the auditor approves or rejects it in line with the
   proposal, **Then** it closes; **and When** the decision overrides the proposal, **Then** a
   reason code is required or the action is refused.
2. **Given** a line's category, **When** the auditor corrects it, **Then** the engine runs again
   deterministically with the human category (source `auditor`), the new findings replace the
   proposal as a new evaluation version, and the line is marked as a candidate for the dev set.
3. **Given** a receipt in review, **When** the auditor requests information, **Then** it waits in
   `needs_info`; **and When** the employee resubmits, **Then** the resubmission is a new revision.
4. **Given** a receipt with a critical finding, **When** it is evaluated, **Then** it goes directly
   to Compliance; **and** an auditor can also escalate any receipt in review.
5. **Given** any reviewer action, **When** it is recorded, **Then** an `auditor_agreement` score is
   attached to the receipt's trace, and if Langfuse is down the action still succeeds.

---

### User Story 5 - Correct a receipt as a new revision (Priority: P2)

An employee corrects a receipt by resubmitting the same `receipt_id` with different content. The
corrected version is stored and evaluated; the earlier version stays in the audit trail.

**Why this priority**: it is how corrections and "request information" replies come back, but the
base flow works without it.

**Independent Test**: submit `R`, then `R` with a changed amount; verify revision 2 is evaluated,
revision 1 remains visible in the trail, and receipts sharing `R`'s employee-day are re-evaluated.

**Acceptance Scenarios**:

1. **Given** `R` revision 1 exists, **When** `R` arrives with different content, **Then** revision 2
   is stored and evaluated and revision 1 remains readable.
2. **Given** a revision changes the employee, date or trip, **When** it lands, **Then** both the old
   and the new group of receipts are re-evaluated.
3. **Given** revision 2 arrives while revision 1 is under review, closed or waiting for
   information, **When** it lands, **Then** the behaviour follows ADR 0007 and is visible in the
   trail.

---

### User Story 6 - Load a batch with partial success (Priority: P2)

A batch of receipts is submitted at once. Valid rows are accepted and processed; invalid rows are
reported with their row number; failed items can be retried individually. The batch shows counts
per state.

**Why this priority**: the realistic bulk path; the single-receipt path already proves the
mechanics.

**Independent Test**: submit a batch with one invalid row and one duplicate; verify counts, that
good rows proceed, and that resubmitting the batch creates nothing new.

**Acceptance Scenarios**:

1. **Given** a batch with valid and invalid rows, **When** it is submitted, **Then** valid rows are
   accepted, each invalid row is reported with its row number and reason, and the batch has a
   summary of counts per state.
2. **Given** a batch already submitted, **When** the same batch is submitted again, **Then** every
   receipt is reported as existing and no new work starts.

---

### User Story 7 - Exercise the backend from Postman (Priority: P3)

Luis (and the panel) can import one collection and one environment and run every endpoint and every
edge case by hand.

**Why this priority**: it is how the backend is checked before the front end exists.

**Independent Test**: import the collection, run it in order against a fresh local instance, all
requests' tests pass.

**Acceptance Scenarios**:

1. **Given** a fresh local instance, **When** the collection runs, **Then** it covers each
   endpoint, a repeated POST, a revision, a batch with a bad row, a cascade and each reviewer
   action, and its assertions pass.

---

### Edge Cases

- A receipt is submitted with an empty body, invalid JSON or a missing required field: rejected
  with a clear message, nothing stored.
- Two submissions of the same new receipt arrive at the same instant: one receipt, one processing.
- The same `receipt_id` is submitted twice inside one batch: the second row is reported as a
  duplicate within the batch.
- A worker dies after finishing a stage but before recording it: the stage is repeated safely and
  yields the same output.
- Two workers contend for the same work: exactly one holds it at a time.
- A reviewer acts on a receipt that has just been re-evaluated (stale decision): the action is
  refused with the current version shown.
- A reviewer action on a receipt in a state that does not allow it (for example approving one that
  is still classifying) is refused.
- The Langfuse server is unreachable: intake, processing and reviewer actions all succeed; only the
  traces and scores are missing.
- The classification service is unavailable: the receipt shows `failed` at the classification stage
  with the reason, and a retry restarts there.
- The database file is missing on start: it is created; a newer schema than the code knows is
  refused with a clear message.

## Requirements *(mandatory)*

### Functional Requirements

**Intake and idempotency**

- **FR-001**: The system MUST store a submitted receipt durably before any processing and before
  responding.
- **FR-002**: The system MUST identify a submission by the client's idempotency key when one is
  given, otherwise by the receipt's identity plus a hash of its canonical stripped content.
- **FR-003**: A repeated submission with the same key and content MUST return the existing receipt
  in its current state and MUST NOT start new work.
- **FR-004**: A repeated client idempotency key with different content MUST be rejected as a
  conflict.
- **FR-005**: A submission with an existing `receipt_id` and different content (without a reused
  client key) MUST create the next revision, and earlier revisions MUST remain readable.
- **FR-006**: The system MUST reject malformed submissions with a message naming the problem and
  MUST store nothing for them.
- **FR-007**: The system MUST accept a batch of receipts (JSONL or JSON array) and report, per row,
  whether it was accepted, existed already, or was invalid with its row number and reason; valid
  rows MUST proceed regardless of invalid ones.
- **FR-008**: A batch MUST have a summary of counts per state, and failed items MUST be retryable
  individually.

**Labels firewall**

- **FR-009**: Every receipt MUST pass through the existing receipt parser that removes answer keys
  before it is stored, hashed, processed, returned or traced.
- **FR-010**: A test MUST fail if any answer key can reach the store, an API response or a trace.

**Processing and resume**

- **FR-011**: Processing MUST run asynchronously from submission, in a worker process that can run
  separately from the API.
- **FR-012**: Processing MUST record one event per completed stage, and after an interruption MUST
  resume at the first incomplete stage.
- **FR-013**: Work MUST be claimed with a lease so that exactly one worker holds a piece of work at
  a time, and an expired lease MUST make the work available again.
- **FR-014**: A resumed receipt MUST produce a result identical to an uninterrupted one, and a
  resumed classification MUST make no additional billed call when its answer is already cached.
- **FR-015**: A failure in a stage MUST leave the receipt in a `failed` state that names the stage
  and the reason, and MUST be retryable from that stage.
- **FR-016**: The decision step (retrieve, apply rules, report) MUST be the same code path for the
  batch run and the worker, so that the two cannot diverge.

**Cross-receipt re-evaluation**

- **FR-017**: When a receipt lands, the system MUST rebuild the cross-receipt context over the
  latest revision of every receipt and re-evaluate every receipt that shares a meal day, an
  employee-date or a trip with it, including the groups it left if it is a revision that moved.
- **FR-018**: A re-evaluation that changes the result MUST be recorded as a new evaluation version
  with the earlier one kept, and MUST return the receipt to the queue with a notice; one that does
  not change the result MUST record nothing.
- **FR-019**: The final results MUST NOT depend on the arrival order of receipts.

**Lifecycle**

- **FR-020**: Every receipt MUST follow the lifecycle of ADR 0006 and MUST expose its current state,
  its history of events and its evaluation versions.
- **FR-021**: The system MUST refuse an action that the current state does not allow.

**Reviewer actions**

- **FR-022**: A reviewer MUST be able to approve or reject a receipt; when the decision differs from
  the engine's proposal, a reason code MUST be required.
- **FR-023**: A reviewer MUST be able to correct a line's category; the engine MUST then run again
  with the human category (source `auditor`) and record a new evaluation version, and the line MUST
  be flagged as a dev-set candidate.
- **FR-024**: A reviewer MUST be able to request information, moving the receipt to `needs_info`;
  the employee's resubmission MUST arrive as a new revision.
- **FR-025**: A reviewer MUST be able to escalate a receipt to Compliance, and receipts with a
  critical finding MUST go there directly.
- **FR-026**: Every reviewer action MUST be recorded as an event and MUST emit an
  `auditor_agreement` score on the receipt's trace, best effort.
- **FR-027**: A reviewer action based on a stale evaluation version MUST be refused.

**Determinism, observability, operation**

- **FR-028**: The policy engine's decisions MUST NOT change in this iteration. Any proposed engine
  change MUST be raised with Luis before it is made.
- **FR-029**: `epv run`, its committed outputs and the evaluation MUST continue to work unchanged
  and without the backend.
- **FR-030**: Every model call made by the backend MUST be traced; one trace per receipt revision
  and evaluation version; if Langfuse is down, nothing else fails.
- **FR-031**: The system MUST start with a fresh database, run the API and the worker as separate
  processes, and use only local storage under a gitignored directory.
- **FR-032**: A Postman collection and environment under `docs/api/` MUST cover every endpoint and
  the edge cases listed in User Story 7.

### Key Entities

- **Receipt**: a submitted expense document, identified by `receipt_id`, with revisions numbered
  from 1; the latest revision is the current one.
- **Revision**: one version of a receipt's content, immutable once stored, identified by receipt and
  number.
- **Submission**: one attempt to submit, carrying an idempotency key; maps to a receipt revision.
- **Event**: an append-only fact about a receipt (submitted, classified, evaluated, decided,
  requested information, escalated, failed, retried); the source of truth for state.
- **Evaluation version**: one engine result (findings and disposition) for a revision, numbered; a
  re-evaluation that changes the result adds a version.
- **Work item**: a unit of processing for a receipt, claimed under a lease, tied to a stage.
- **Batch**: a set of submissions with per-row outcomes and a summary of counts per state.
- **Reviewer action**: an approve, reject, correction, information request or escalation, with its
  actor, reason code (where required) and the evaluation version it was based on.
- **Agreement score**: a score recording whether the reviewer's decision matched the engine's
  proposal.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Submitting the 32 receipts through the API in 5 different random orders gives results
  identical to the batch run for 32 of 32 receipts in every order (N = 32 receipts × 5 orders).
- **SC-002**: Submitting any receipt or batch twice produces exactly one stored receipt per
  receipt identity and zero additional processing runs (N = 32 receipts, twice).
- **SC-003**: After a worker is stopped at a random point in a batch and restarted, 100% of
  receipts reach the evaluated state, with results identical to an uninterrupted run and zero
  additional billed model calls (N = 3 stop points).
- **SC-004**: For a cross-receipt rule, a receipt submitted before and after its partner shows the
  same final findings as the batch run in both orders.
- **SC-005**: Each of the four reviewer actions, a revision, a repeated POST, a batch with a bad
  row and a cascade is exercised by the Postman collection with all assertions passing on a fresh
  instance.
- **SC-006**: With Langfuse stopped, intake, processing and reviewer actions all complete; the run
  outputs are identical to a run with Langfuse available.
- **SC-007**: A scan of the store, every API response and every trace for the answer keys finds
  zero occurrences (N = every endpoint and the full stored data after the 32-receipt run).
- **SC-008**: `epv run` regenerates `outputs/results.jsonl` byte-identical to the committed file
  after this iteration's changes (N = 32 receipts).
- **SC-009**: The test suite, ruff and mypy pass before every commit; the engine's decision tests
  are untouched.

## Assumptions

- Authentication and authorization are out of scope (candidate L2); reviewer identity is a free-text
  actor recorded in events.
- Notification delivery to employees is out of scope; "notice" means a state and a flag the front
  end can show.
- A "sample goes to quality review" for auto-approved receipts is recorded as a flag on the receipt
  (the sampling rule is fixed in ADR 0007); the quality-review screen belongs to iteration 4.
- The local database is a single file under a gitignored directory; it mirrors the AWS design
  (queue, key-value store, object store) described in iteration 5.
- A shared process cache of classifications is already available (`.cache/`); the worker reuses it
  and the committed classification cache seeds it.
- The remaining open design questions (the API shape, what happens to a revision that arrives while
  a receipt is under review or closed, what counts as a "changed result" that reopens an approved
  receipt, which trace a score attaches to) are decided in ADR 0007 before implementation.
- The React front end, the three-model comparison and the AWS page are iterations 4 and 5.
