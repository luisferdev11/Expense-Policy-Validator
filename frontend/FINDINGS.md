# Findings from iteration 4 (front end)

Gaps, mismatches and suggested changes found while building the front end. **Nothing outside
`frontend/` was changed.** Each entry: what I expected, what happened, how to reproduce, what I
propose, and how the front end copes today. Luis reviews these after the backend review.

## F-01. The list endpoint returns too little for a queue table

- **Date:** 2026-10-10
- **Expected:** `GET /receipts` rows carry what the brand book's queue columns need: merchant,
  employee and entity, declared type, total in USD, number of findings.
- **What happened:** `ReceiptSummary` has only `receipt_id`, `revision`, `state`, `disposition`,
  `evaluation_version`, `notice`, `qa_sample`, `updated_at`. The list also has no filter for
  `qa_sample` and no ordering parameter.
- **Reproduce:** `curl localhost:8000/receipts` and compare with `docs/design/components/QueueTable.md`.
- **Proposal:** add `merchant_name`, `employee_id`, `entity`, `submitted_expense_type`,
  `total_amount_usd` and `finding_count` to `ReceiptSummary`; add `qa_sample` and `order` query
  parameters; consider `updated_since` so a poller does not re-read 500 rows every few seconds.
- **Today:** the list is polled every 4 s, and the details of the visible rows are fetched one by
  one (4 at a time) and cached by `receipt_id` and `updated_at`. That is N+1 requests; it is fine
  for a demo and a few hundred receipts, not for production volume. The quality-sample view
  filters on the client.

## F-02. No aggregate endpoint for insights

- **Date:** 2026-10-10
- **Expected:** the audit lead's screen (volume, aging, agreement with the engine, rules that are
  often overridden) reads aggregates from the API.
- **What happened:** there is none. The Insights screen builds the numbers on the client from
  `GET /receipts`, `GET /receipts/{id}` and `GET /receipts/{id}/events` for every receipt
  (agreement comes from `payload.agreement` of the reviewer events).
- **Reproduce:** open Insights with 100+ receipts and watch the network tab.
- **Proposal:** `GET /insights` (counts by state and disposition, aging buckets, agreement by
  action and by rule, each with its N). The same numbers are already available as Langfuse
  `auditor_agreement` scores, but the product never links to Langfuse (brand book).
- **Today:** client-side computation, every figure shown with its N. "Findings on receipts where
  someone disagreed" uses the receipt's *current* result, not the one the reviewer saw, so it is
  an approximation. Labelled as such on the screen.

## F-03. The Evaluation screen has no data source

- **Date:** 2026-10-10
- **Expected:** a demonstrative comparison of gpt-oss-120b, gpt-oss-20b and jev-1.13
  (`docs/roadmap.md`, iteration 4).
- **What happened:** no endpoint serves evaluation figures, and the jev-1.13 dev-set run planned in
  `docs/plans/2026-10-10-product-plan.md` needs model calls (not allowed in this session). I also
  did not read `outputs/` or `eval/`, to keep the labels firewall intact.
- **Proposal:** decide where the figures come from (a committed JSON of per-model metrics, each
  with its N, produced by `epv eval` with no model call; or an endpoint reading it).
- **Today:** the screen reads `frontend/public/evaluation.json`. It ships with the three models and
  **no figures**, and says so ("No measurements loaded yet"). Filling `metrics` and setting
  `status: "measured"` is enough to show a table with each figure's N. I did not invent numbers.

## F-04. The API sends no CORS headers

- **Date:** 2026-10-10
- **Expected:** a browser app on another origin can call the API.
- **What happened:** `OPTIONS /receipts` with an `Origin` header answers `405 method_not_allowed`.
- **Reproduce:** `curl -i -X OPTIONS localhost:8000/receipts -H 'Origin: http://localhost:5173' -H 'Access-Control-Request-Method: POST'`.
- **Proposal:** either serve the built front end from the API process (`frontend/dist` as static
  files under `/`, API under `/api`), or add CORS middleware with an allow-list setting.
- **Today:** the app calls a same-origin `/api` prefix that the Vite dev and preview servers proxy
  to the API (`EPV_API`, default `http://localhost:8000`). Deployment needs one of the two options.

## F-05. No endpoint for the category list or for rule titles

- **Date:** 2026-10-10
- **Expected:** the correct-category dialog and the "rules checked and passed" section of the
  detail pane (brand book) read their lists from the API.
- **What happened:**
  - the 21 categories exist only in `src/expense_validator/domain/taxonomy.py`, so the front end
    keeps a copy (`src/lib/domain.ts`) with nothing that detects drift;
  - findings carry `rule_id`, `policy_doc`, `evidence` and an `explanation` that starts with the
    rule ID, but no plain-language title, so the finding title is the explanation without its
    prefix;
  - the list of rules that were checked and passed is not in the result, so that section of the
    detail pane is not built.
- **Proposal:** `GET /taxonomy` (id, restricted flag) and `GET /rules` (id, policy doc, title, text);
  put `rules_checked` in the result or in the evaluation.
- **Today:** hard-coded category list; titles derived from `explanation`.

## F-06. Validation errors name fields but not the reason

- **Date:** 2026-10-10
- **Expected:** `invalid_receipt` tells the user what is wrong with each field.
- **What happened:** `details.fields` lists field names only. `{"receipt_id":"X","entity":"MARS"}`
  returns every missing field and `entity` in the same flat list, so a wrong value cannot be told
  from a missing one. The `message` is truncated after five names.
- **Reproduce:** `curl -X POST localhost:8000/receipts -H 'Content-Type: application/json' -d '{"receipt_id":"X","entity":"MARS"}'`.
- **Proposal:** `details.errors: [{field, message}]`, as FastAPI's validation already has.
- **Today:** the form shows "Fields to check" as a list of names.

## F-07. The override reason codes in the design differ from the API's

- **Date:** 2026-10-10
- **Expected:** `docs/design/brand-book.md` and the API agree.
- **What happened:** the brand book lists *Policy exception approved*, *Wrong category*, *Wrong
  amount or currency*, *Duplicate of another receipt*, *Other*. ADR 0007 D8 and the API allow
  `policy_exception_granted`, `engine_false_positive`, `engine_missed_issue`,
  `documentation_provided`, `other`. The brand book also maps `A` to "confirm the proposal" and `O`
  to "override", while the API has no "confirm": confirming a flag is `reject`, confirming a pass is
  `approve`.
- **Proposal:** decide which side moves. Changing the API's closed list changes the agreement
  semantics (D10), so this is a product decision.
- **Today:** the front end follows the API: reasons are the API's five codes, and the keys are `A`
  approve, `R` reject, `I` request information, `E` escalate, `C` correct a category.

## F-08. `docs/design/ledgerline.css` depends on a file that is not there

- **Date:** 2026-10-10
- **Expected:** the CSS "comes from `tokens.css`" (its first comment).
- **What happened:** `docs/design/` has `tokens.json` but no `tokens.css`; and the CSS imports the
  Geist fonts from Google Fonts, so an offline demo falls back to system fonts.
- **Proposal:** commit a generated `tokens.css`, or say in the overview that it is generated from
  the JSON; self-host the two font families if the demo has to work offline.
- **Today:** `npm run styles` generates `src/styles/tokens.css` from `tokens.json` (light, dark and
  a manual theme switch) and copies `ledgerline.css`. Both outputs are git-ignored.

## F-09. A reviewer cannot see who decided in the list

- **Date:** 2026-10-10
- **Expected:** the closed-receipts list shows the decision and who made it.
- **What happened:** the summary has `state` only; the decision and the actor are in the events.
- **Proposal:** `decided_by` and `decided_at` in the summary and detail, next to the state.
- **Today:** the detail pane shows them in the audit trail.
