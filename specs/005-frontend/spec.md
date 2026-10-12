# Iteration 4: front end

Status: built 2026-10-10. Sources: `docs/api/openapi.json`, `specs/004-backend-lifecycle/contracts/api.md`,
ADR 0007, `docs/design/` (Ledgerline), roadmap iteration 4.

## Goal

An application a client can use from start to finish with no explanation: submit receipts, see
what the engine proposes and why, decide, and follow what happened afterwards.

## The flow it supports

1. **Submit** one receipt or a batch (paste, file, drop). Same receipt ID with different content
   is a new revision; the same content again changes nothing. A bad row in a batch refuses that
   row only.
2. **Wait** while the engine reads and checks. The pages update by themselves.
3. **Read** the verdict (proposed, never final), the findings with the literal policy text, and
   how each line was read, with confidence as a word.
4. **Decide**: approve, reject, request information, escalate, or correct a line's category.
   Going against the proposal needs a reason. A stale decision is refused and explained.
5. **Follow up**: result changed notices, receipts waiting for information, Compliance cases,
   the quality sample of auto-approved receipts, the full audit trail and revisions.
6. **Oversee**: insights with every figure's N, and an evaluation area that shows only measured
   figures.

## Requirements

- FR-1 Every action offered comes from the receipt's `allowed_actions`.
- FR-2 Each action sends the `evaluation_version` the reviewer saw; a 409 refreshes the receipt.
- FR-3 A reason is required exactly when the decision overrides the proposal (approve a flag,
  reject a pass); `other` requires a note.
- FR-4 Money is displayed from the API's strings, never from floats.
- FR-5 The auditor never sees model, provider, prompt, tokens or cost; version labels appear only
  in the audit trail.
- FR-6 Every aggregate is shown with its N.
- FR-7 The app works with the API down: it says so and reconnects.
- FR-8 Keyboard: J/K, A, R, I, E, C, `/`, `?`; every shortcut also has a visible button.
- FR-9 Light and dark themes; narrow screens show the detail instead of the list.

## Out of scope (see `frontend/FINDINGS.md`)

Authentication, notifications, rules-checked list, an aggregate endpoint, evaluation figures.
