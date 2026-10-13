# ADR 0010: Roles and access

- **Status:** proposed. Designed on 2026-10-12 at Luis's request; **not implemented** in this
  iteration. R1 to R4 were answered by Luis on 2026-10-12 and R5 is open (see the section below).
  The specification is `specs/009-roles/spec.md`.
- **Date:** 2026-10-12
- **Supersedes in part:** ADR 0007 D8 ("the actor is free text; no authentication in this
  iteration") once implemented.
- **Related:** ADR 0009 (production on AWS), roadmap candidates L2 and L4, `frontend/FINDINGS.md`
  F-07 and F-11, open question Q3 (recipient abuse).

## Context

Today anyone who can reach the API can do anything. Three things follow from that:

- **The actor is unchecked.** It is a free-text field in the request body (`ActionBody.actor`,
  `src/expense_validator/app/api/schemas.py`). It is stored in `events.actor` and is only checked
  for being non-blank (`app/reviewing.py`).
- **"compliance" is a state, not a role.** The allowed actions depend only on the receipt's state
  (`_ALLOWED` in `src/expense_validator/domain/lifecycle.py:29-34`).
- **The screens and the API disagree.** The front end separates screens by job (queue, compliance,
  quality sample, evaluation), but nothing enforces it. The brand book separates what an auditor
  sees from what a developer sees, and the lifecycle board promises Compliance outcomes the API
  does not have (F-11).

That is acceptable on localhost with synthetic data. It is not acceptable for real employee
receipts. The decision record of who approved what is only as good as the identity behind it.

## Decision

### D1. Five roles, assigned by the identity provider

| Role | Who | In one line |
|---|---|---|
| `submitter` | An employee | Submits and revises their own receipts and answers information requests |
| `reviewer` | An expense reviewer (the UI calls them "auditor") | Works the review queue and the quality sample |
| `compliance` | A compliance officer | Works receipts escalated to Compliance or held for a critical finding |
| `internal_audit` | Internal audit, read-only | Reads everything, including events and insights; changes nothing |
| `developer` | The team that runs the models | Evaluation screen, Langfuse, retrying failed receipts |

- A person can hold several roles.
- Roles come from identity-provider groups. The application never stores or edits role
  assignments, so there is no admin screen.

### D2. Permissions by role, action and state

The state rules of `domain/lifecycle.py` stay. A role only narrows them, never widens them.

| Action \ role | submitter | reviewer | compliance | internal_audit | developer |
|---|---|---|---|---|---|
| `POST /receipts`, `POST /batches` | own receipts only | – | – | – | test data only (D6) |
| Read receipts, events, revisions | own only | all | all | all | all |
| `approve`, `reject`, `correct-category`, `request-info` in `in_review` | – | ✓ | – | – | – |
| `escalate` in `in_review` | – | ✓ | – | – | – |
| `reject` in `auto_approved` (quality sample) | – | ✓ | – | – | – |
| Clear a receipt from the quality sample | – | ✓, not the one who approved it (R3) | – | – | – |
| `return-to-review` in `compliance` (R2) | – | – | ✓ | – | – |
| `reject` in `needs_info` | – | ✓ | – | – | – |
| `approve`, `reject`, `correct-category`, `request-info` in `compliance` | – | – | ✓ | – | – |
| `retry` a failed receipt | – | – | – | – | ✓ |
| Evaluation screen, model comparison | – | – | – | read | ✓ |
| Insights | – | ✓ | ✓ | ✓ | ✓ |

- **Separation of duties.** Nobody can act on a receipt whose `employee_id` is their own. The token
  carries the employee id as a claim, and the engine-facing data is never changed for this.
- **Compliance becomes a role.** Compliance is a state today. After this ADR, only the
  `compliance` role can act in that state, and a reviewer can only send a receipt there.

### D3. Identity through OIDC; the actor comes from the token

- **Production (ADR 0009).** Identity comes from an Amazon Cognito user pool, or the company's IdP
  federated through it. The API validates the bearer token's signature against the pool's keys,
  and checks its audience and expiry, in a FastAPI dependency `current_principal`.
- **Roles.** They are read from the groups claim (`cognito:groups`).
- **The actor.** It is the token's `sub`, an opaque id, stored in `events.actor`. A display name is
  stored with it for the screens. The free-text `actor` field is removed from `ActionBody`; a
  request that still sends it gets 422.
- **Langfuse.** Traces and scores get only the opaque id, never a name or an email.
- **Local development.** An explicit `--auth dev` mode accepts a fixed user from configuration, with
  roles listed there.
  - The server logs a warning on every request in this mode.
  - The server refuses to start in this mode when `EPV_ENV=production`.
- **Existing events.** Their free-text actors are kept as written and displayed with a `legacy:`
  prefix. The event log is append-only, so it is never rewritten.

### D4. What the API returns changes with the caller

- `allowed_actions` in `GET /receipts/{id}` is the intersection of the state rules and the
  caller's role.
- `GET /me` returns the principal (id, display name, roles, employee id).
- **Error responses.** They use the error shape of ADR 0007 D3:
  - 401 `unauthenticated` for a missing or invalid token;
  - 403 `forbidden_role` for an action the role does not allow;
  - 403 `own_receipt` for separation of duties;
  - 403 `own_receipt_only` when a submitter sends a receipt for another employee.
- **`decided_by`** (spec 006) holds the principal id. A separate `decided_by_name` holds the display
  name at decision time, so the screens never need a lookup.
- **Submitters see only their own receipts.** They do not see the engine's findings: only the state
  and, after a human decides, the decision and its reason code (R4).

### D5. The front end follows the principal

- The navigation shows only the screens the principal's roles allow.
- Evaluation is shown only to `developer`, and read-only to `internal_audit`.
- The "Your name" field disappears. The name comes from `GET /me`.

### D6. Test and demo data

- **Developer intake.** A developer may submit only receipts with a test marker, an
  `employee_id` prefix configured as test-only (`TEST-`). That keeps the demo and the load test
  (`perf/locustfile.py`, spec 006) possible without a submitter account per employee.
- **The load test.** It authenticates as a service principal holding the `developer` role, in the
  dev auth mode. Spec 006 already generates its receipts with `TEST-` employee ids. The Postman
  collection's demo receipts move to the same prefix when this ADR is implemented.

## Luis's answers to the open questions (2026-10-12)

| # | Question | Answer | Effect |
|---|---|---|---|
| R1 | Do the API's five reason codes or the brand book's codes win (F-07)? | **The API's.** | The closed list is unchanged, so `auditor_agreement` (ADR 0007 D10) is unaffected. The brand book is aligned to the API when this is implemented. |
| R2 | Does Compliance get a "rejected and referred" outcome and a "back to review" action (F-11)? | **Only "back to review".** | One new transition (`compliance` to `in_review`) and one new event. No "rejected and referred" outcome; the lifecycle board is corrected. |
| R3 | Can the reviewer who approved a receipt also clear it from the quality sample, or is a second pair of eyes required? | **A second person is the target rule, but it cannot be verified yet.** It needs roles and sessions. | Enforced only once this ADR is implemented (403 `own_decision`). Until then the same person may clear it. |
| R4 | Should a submitter see the engine's findings before a human decides? | **No, only the status.** | A submitter sees the state and, after a decision, the decision and its reason code. Findings stay with reviewers (Q3). |
| R5 | Is the IdP the company's (federated) or a Cognito pool owned by this service? | **Not known yet.** | The design reads the groups claim of a token and does not depend on it. It is settled before a real deployment. |

## Consequences

- **Before real data, this is required.** It is listed in `docs/aws.md` as a "before production"
  item.
- **Who decided becomes trustworthy.** It is the identity behind `decided_by` (spec 006) and the
  `auditor_agreement` scores, which today rest on typed names.
- **Cost.** About 2 to 3 days with tests (L): the auth dependency, a role check on every route,
  `GET /me`, filtered lists, the front-end shell, dev mode, the contract and e2e tests, and the
  Postman collection with a token.
- **The engine is untouched.** Roles decide who may act, never what the engine decides
  (principle II).

## Alternatives considered

- **A role declared by the client (header or body) without authentication.** Rejected: it looks
  like access control but anyone can forge it. It would make `decided_by` look trustworthy when it
  is not.
- **Roles stored in the application's database with an admin screen.** Rejected for now: it adds a
  security-critical screen and duplicates the IdP. Groups in the IdP are audited where the company
  already audits access.
- **API keys per team instead of user identity.** Rejected: decisions must be attributable to a
  person.
