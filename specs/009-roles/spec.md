# Feature Specification: Roles and access

**Feature Branch**: `feat/009-roles` (not created; design only)

**Created**: 2026-10-12

**Status**: Designed, deferred. Not implemented in iteration 6. Implementation needs Luis's answers
to the open questions R1 to R5 in ADR 0010.

**Release**: none yet (candidate for the first iteration after delivery)

**Input**: User description (Luis, 2026-10-12, translated): "Roles: think them through and see
whether they are worth implementing (this one feels heavier and we only have a few hours)."
Decision the same day: write the ADR and the specification, do not implement.

## Context

Anyone who reaches the API can act on any receipt today, and the actor is free text (ADR 0007 D8).
`docs/decisions/0010-roles-and-access.md` records the design: five roles from the identity
provider, permissions as the intersection of state rules and role, OIDC identity, and the actor
taken from the token. This specification states the behaviour to build and how to test it, so the
implementation session only has to plan it.

Constitution principles that frame it:

- **II. Deterministic decisions.** Roles decide who may act, never what the engine decides. No
  file under `src/expense_validator/domain/engine/` changes.
- **IX. Secrets stay out.** Token-signing keys are fetched from the identity provider. No secret,
  token or client secret is written to code, logs, outputs, commits or traces.
- **X. Observability.** Traces and scores carry only an opaque principal id, never a name or an
  email.
- **XI. Iterative delivery.** Deferred on purpose: the delivery runs on synthetic data on
  localhost, where the free-text actor is acceptable and documented.

## Clarifications

### Session 2026-10-12

- Q: How far do roles go in iteration 6? → A: ADR plus specification, not implemented.
- Q: Should a client-declared role (no authentication) be built as a stopgap? → A: No. It would
  make `decided_by` look trustworthy when anyone can forge it (ADR 0010, alternatives).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Only an authenticated person can act, and the record names them (Priority: P1)

A reviewer signs in through the company's identity provider and approves a receipt. The event
records the reviewer's identity from the token. No request body can claim to be someone else.

**Why this priority**: every other part of the lifecycle relies on knowing who decided. Today that
rests on a typed name.

**Independent Test**: call an action with no token, with an expired token and with a valid token.
Verify 401, 401, and success with `events.actor` equal to the token's `sub`.

**Acceptance Scenarios**:

1. **Given** no bearer token, **When** any route other than `GET /health` is called, **Then** the
   API answers 401 `unauthenticated` and stores nothing.
2. **Given** a valid token for principal `P`, **When** `P` approves a receipt, **Then** the
   `ReceiptApproved` event's actor is `P`'s `sub`, `decided_by` (spec 006) is that same `sub`, and a
   new projection field `decided_by_name` carries `P`'s display name for the screens.
3. **Given** an action body that still contains `actor`, **When** it is sent, **Then** the API
   answers 422 and names the field.

---

### User Story 2 - Each role sees and does only its job (Priority: P1)

A reviewer works the review queue but cannot act on receipts held by Compliance. A compliance
officer works those. Internal audit reads everything and changes nothing. A developer retries
failed receipts and sees the evaluation screen.

**Why this priority**: it is the access-control core of the feature.

**Independent Test**: for each role, call every action in every state and compare the answers with
the matrix in ADR 0010 D2. Every disallowed pair returns 403 `forbidden_role` and leaves no event.

**Acceptance Scenarios**:

1. **Given** a receipt in `compliance`, **When** a `reviewer` approves it, **Then** the answer is
   403 `forbidden_role`.
2. **Given** a receipt in `compliance`, **When** a `compliance` principal approves it, **Then** it
   moves to `approved`.
3. **Given** any receipt, **When** `internal_audit` calls any action, **Then** the answer is 403 and
   `allowed_actions` in its detail view is empty.
4. **Given** a principal with roles `reviewer` and `compliance`, **When** it reads a receipt in
   `compliance`, **Then** `allowed_actions` lists the compliance actions.

---

### User Story 3 - Nobody decides on their own receipt (Priority: P1)

A reviewer who is also an employee submits a receipt. The receipt reaches the review queue, but
that reviewer cannot approve, reject, correct or escalate it.

**Why this priority**: separation of duties is the control auditors ask for first.

**Independent Test**: a principal whose employee-id claim equals the receipt's `employee_id` tries
every action and gets 403 `own_receipt`. Another reviewer succeeds.

**Acceptance Scenarios**:

1. **Given** a receipt with `employee_id` E and a reviewer whose claim is E, **When** the reviewer
   approves it, **Then** the answer is 403 `own_receipt`.
2. **Given** the same receipt, **When** the reviewer lists the queue, **Then** the receipt is shown
   with no allowed actions and a note that someone else must decide.

---

### User Story 4 - Submitters see only their own receipts (Priority: P2)

An employee submits receipts, sees their state, and answers an information request by sending a
new revision. They cannot read other employees' receipts.

**Why this priority**: needed before employees use the system directly. Reviewers can still submit
on their behalf until then.

**Independent Test**: a submitter lists receipts and reads one that is not theirs. Verify that the
list contains only their own receipts and that the foreign read returns 404, not 403, so that the
existence of the receipt does not leak.

**Acceptance Scenarios**:

1. **Given** receipts of employees E1 and E2, **When** submitter E1 lists receipts, **Then** only
   E1's appear and the total counts only E1's.
2. **Given** submitter E1, **When** E1 submits a receipt with `employee_id` E2, **Then** the answer
   is 403 `own_receipt_only`.
3. **Given** a receipt of E1 in `needs_info`, **When** E1 submits a new revision, **Then** it is
   accepted as for any revision (ADR 0007 D5).

---

### User Story 5 - The application shows each person their screens (Priority: P2)

The front end reads `GET /me` and shows only the screens the principal's roles allow. The
"Your name" field disappears.

**Why this priority**: the API already enforces the rules, so this is usability, not security.

**Independent Test**: sign in as each role in dev mode. Verify the navigation entries against
ADR 0010 D2, and that opening a hidden route directly shows a "not available for your role" page.

**Acceptance Scenarios**:

1. **Given** a `reviewer`, **When** the app loads, **Then** Evaluation is not in the navigation.
2. **Given** a `developer`, **When** the app loads, **Then** Evaluation is shown.
3. **Given** any principal, **When** the decision dialog opens, **Then** it has no name field and
   shows the signed-in name.

---

### User Story 6 - Local development and demos still work without an identity provider (Priority: P3)

A developer runs `epv serve --auth dev`. It uses a configured fixed user and roles, logs a warning
on every request, and refuses to start when `EPV_ENV=production`.

**Why this priority**: it keeps the demo, the Postman collection and the load test runnable on a
laptop.

**Independent Test**: start in dev mode, then call an action and see the warning in the log. Start
in dev mode with `EPV_ENV=production` and see a refusal with a non-zero exit code.

### Edge Cases

- **Expired token in the middle of a long batch upload.** The batch is accepted or refused as a
  whole at the start of the request. A token that expires afterwards does not split a batch.
- **Historical events with free-text actors.** They are displayed as `legacy:<name>` and are never
  rewritten (the log is append-only, ADR 0007).
- **A principal with no recognised role.** They are authenticated but can do nothing. Every route
  except `GET /me` and `GET /health` returns 403.
- **Role removed in the IdP while a token is still valid.** The change takes effect when the token
  expires. The token lifetime is short (at most 1 hour) and is documented.
- **The worker and the system.** Background events keep the system actors `system` and `worker`.
  They are not principals, and no token can claim them.
- **The QA sample when the only available reviewer approved the receipt.** This depends on R3.
- **Langfuse.** `auditor_agreement` scores carry the opaque id. Display names never reach a trace.

## Requirements *(mandatory)*

### Functional Requirements

**Identity**

- **FR-001**: The API MUST require a valid bearer token on every route except `GET /health` when
  auth mode is `oidc`. It MUST validate signature, issuer, audience and expiry against the
  provider's published keys.
- **FR-002**: The system MUST take the actor of every human event from the token's `sub` and MUST
  refuse an `actor` field in request bodies (422).
- **FR-003**: The system MUST expose `GET /me` with the principal's id, display name, roles and
  employee id.
- **FR-004**: The system MUST provide a `dev` auth mode with a configured principal, MUST log a
  warning on every request in that mode, and MUST refuse to start in it when `EPV_ENV=production`.

**Authorisation**

- **FR-005**: The system MUST allow an action only when both the state rules
  (`domain/lifecycle.py`) and the role matrix (ADR 0010 D2) allow it, and MUST answer 403
  `forbidden_role` otherwise, storing nothing.
- **FR-006**: The system MUST refuse any action by a principal on a receipt whose `employee_id`
  equals the principal's employee id (403 `own_receipt`).
- **FR-007**: `allowed_actions` in the receipt detail MUST reflect FR-005 and FR-006 for the caller.
- **FR-008**: A `submitter` MUST only list and read receipts with their own `employee_id`. A
  foreign receipt MUST answer 404.
- **FR-009**: A `developer` MUST only submit receipts whose `employee_id` starts with a configured
  test prefix.
- **FR-010**: The role matrix MUST live in one pure, tested module in `domain/`, beside the state
  rules, and MUST NOT be duplicated in routes.

**Records and observability**

- **FR-011**: Existing events MUST stay unchanged. Free-text actors MUST be displayed with the
  prefix `legacy:`.
- **FR-012**: Traces and Langfuse scores MUST carry only the opaque principal id.
- **FR-012a**: `decided_by` (spec 006) MUST hold the principal id. A new projection column and API
  field `decided_by_name` MUST hold the display name at decision time, set in the same transaction.
  Rows decided before this feature keep their free-text value in `decided_by` and show it as
  `legacy:<name>`.
- **FR-012b**: The Postman collection and the load test (spec 006) MUST use `employee_id` values
  with the test prefix `TEST-`, so they run under the `developer` role without other changes.

**Front end**

- **FR-013**: The front end MUST build its navigation and decision dialog from `GET /me` and MUST
  NOT ask for a name.

### Key Entities

- **Principal**: id (`sub`), display name, roles (set), employee id. It comes from the token; the
  application stores none of it except the id and the name on events.
- **Role**: one of `submitter`, `reviewer`, `compliance`, `internal_audit`, `developer`.
- **Permission**: a role, an action and a state. It is derived, never stored.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The permission test covers every role × action × state combination: 5 roles ×
  5 actions × 9 states = 225 cases, plus retry and intake. Every case matches ADR 0010 D2, with
  N = 225 reported.
- **SC-002**: 0 events in the test suite carry an actor that did not come from a token or a system
  actor.
- **SC-003**: The 32 receipts processed through the authenticated API (dev mode) give results byte
  for byte equal to `epv run`. The engine is unchanged.
- **SC-004**: The Postman collection and the load test run in dev mode with no change other than
  the auth header.

## Assumptions

- Production identity is OIDC through Amazon Cognito, possibly federated to the company's IdP
  (ADR 0009, open question R5).
- Group names in the IdP map one to one to the five roles.
- Display names are available as a token claim (`name` or `email`).
- Employees and reviewers have an employee-id claim. It is required for separation of duties.

## Out of scope

- Managing users or groups inside the application.
- Row-level security in the database. Authorisation is enforced in the application layer.
- The answers to R1 to R5. They are product decisions for Luis before implementation.
