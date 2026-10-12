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

## F-03. The Evaluation screen had no data source (resolved in the front end, 2026-10-11)

- **Expected:** the comparison of the classifiers (`docs/roadmap.md`, iteration 4) reads committed
  figures, and jev-1.13 appears with a measured result.
- **What happened:** no endpoint serves evaluation figures; jev-1.13 had only a draft-set result.
- **Done (inside `frontend/`):** `npm run evaluation` builds `public/evaluation.json` from
  `outputs/eval/metrics.json` and `experiments.json` (aggregates only, no model call) and from
  `frontend/data/classifier-comparison.json`. A unit test fails if the committed JSON is stale or
  carries a receipt ID or an answer key. The canvas figures were checked against the committed
  report: they match.
- **jev-1.13 run:** `uv run python -I frontend/scripts/jev_dev_run.py` ran it on the frozen dev set
  (N = 130, hash `5f34f08e…`) with the E13 decision payload (`dec-v1`) over normalised text, traced
  in Langfuse (`classify-dev-item` and `classify-item`), USD 0.0055 billed. Statistics come from
  `eval.experiments.decide.e14`, and the four registered variants reproduce their committed
  numbers. Result: 130 of 130 categories, restricted F1 1.000, 0.59 s per item, USD 0.043 per
  1,000 items; 7 items right where gpt-oss-120b was wrong and none the reverse (exact p = 0.0156).
  It returns no subtype or recipient, so it cannot replace the classifier alone. It is not a
  registered experiment and decides nothing.
- **Still open (for Luis):** whether to register a follow-up (jev for the category plus a
  generative model for subtype and recipient), and a larger or real-world dev set, because a
  perfect score at N = 130 says little about real receipts. See `MEJORAS-ITERACION-FINAL.md`.

## F-04. The API sends no CORS headers

- **Date:** 2026-10-10
- **Expected:** a browser app on another origin can call the API.
- **What happened:** `OPTIONS /receipts` with an `Origin` header answers `405 method_not_allowed`.
- **Reproduce:** `curl -i -X OPTIONS localhost:8000/receipts -H 'Origin: http://localhost:5173' -H 'Access-Control-Request-Method: POST'`.
- **Update 2026-10-11:** fixed on main (CORS for ports 5173 and 4173, `--cors-origin`). The proxy stays as the default for development.
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

## F-10. The quality sample can never be cleared

- **Date:** 2026-10-10
- **Expected:** a reviewer who looks at a sampled auto-approved receipt and finds it fine can
  record that, and it leaves the sample list (ADR 0007 D12: "sampled for quality review").
- **What happened:** `auto_approved` allows only `reject` (`domain/lifecycle.py`). There is no `confirm-sample`
  action or `qa_reviewed` flag, so `/sample` never empties after a check.
- **Proposal:** a `confirm-sample` action (event `SampleChecked`, agreement 1) that clears `qa_sample`
  from the queue, or a `qa_reviewed` flag on the projection and a filter on the list.
- **Today:** the Quality sample screen says that reading a receipt does not take it off the list
  and that rejecting is the only action.

## F-11. The mockups promise things the API does not expose

- **Date:** 2026-10-10
- **Expected:** the canvas (`9v6nEUUa73z4WyNrnQu5U3`) and the API agree.
- **What happened:**
  - *Linked receipts*: the history board shows "Linked by a shared meal day" and an event
    "Linked receipt re-evaluated". The API exposes neither the group a receipt shares nor an event
    on the partner receipt that says why it was re-evaluated.
  - *Batch header*: the canvas shows a file name and a sent time; `BatchResponse` has no
    `created_at` or file name.
  - *Compliance*: the lifecycle board says a Compliance officer leaves a case as "rejected and
    referred, rejected, or back to review". The API lets `compliance` approve, reject, correct a
    category or request information; there is no role, no "referred" outcome and no way back to
    review. The board's event names (`ReviewDecided`, `CaseClosed`, `ReceiptClosed`, `LinesClassified`) are
    not the log's (`ReceiptApproved`, `ReceiptRejected`, `ReceiptClassified`).
  - *Plain titles and rules passed*: see F-05.
- **Proposal:** `linked_receipts` (id, shared key) on the detail; `created_at` and `source_name` on a
  batch; decide whether Compliance needs its own role and outcomes, and fix the board or the API.
- **Today:** the front end shows the file name and the sent time it knows on the client (lost on
  reload), omits linked receipts, and its "How a receipt moves" page follows the API and the log's
  real event names.

## Assistant mistakes to merge into AI_NOTES.md

Each one was caught during this iteration. `AI_NOTES.md` was not edited here (it is outside
`frontend/`); Luis can fold these in.

1. **Never opened the design canvas the brief named.** Built from `docs/design/` and the brief's
   description only. *Caught by:* the advisor review before delivery. *Changed:* read the five
   boards and added the history page, the lifecycle page, the batch result layout, auto-advance
   after a decision and the evaluation figures.
2. **Evaluation screen shipped with no figures** although the plan said E14 results were committed.
   *Caught by:* the same review. *Changed:* figures from the canvas, with their provenance on the screen (F-03).
3. **Layout bug: the line-items table was covered by the pane.** Flex children of the scrolling
   pane shrank. *Caught by:* a Playwright click that was "intercepted". *Changed:* `flex-shrink: 0` on the pane's children.
4. **Playwright browser mismatch.** The installed package wanted a Chromium build that was not in
   the cache. *Caught by:* the first e2e run. *Changed:* pinned `@playwright/test` to the version that matches the cached build.
5. **A one-line batch was sent as a single receipt**, so the test that expected a batch hung.
   *Caught by:* the e2e timeout. *Changed:* the test sends a JSON array for one row; the app explains which mode it detected.
6. **Ambiguous test selectors** (a word that appeared in three places) made three assertions fail
   for the wrong reason. *Caught by:* Playwright's strict mode. *Changed:* selectors scoped to the element.
7. **Toast told the auditor "Differs from the engine's proposal" after every category correction.**
   Agreement is always 0 for corrections (ADR 0007 D10), so it read like an error. *Caught by:* the advisor review. *Changed:* the toasts no longer mention agreement.
