# Feature Specification: Iteration 1, an End-to-End MVP of the Expense Policy Validator

**Feature Branch**: `chore/spec-kit-init`

**Created**: 2026-10-08

**Status**: Draft

**Input**: User description: "Iteration 1 (MVP) of the Expense Policy Validator, exactly as scoped
in docs/roadmap.md 'Iteration 1: MVP, end to end'." The full description lists:
- the five separate components;
- the brief's output shape;
- the deterministic engine over all 37 in-scope rules;
- the five brief test cases;
- committed outputs;
- the evaluation on the 28 in-scope receipts;
- a three-view viewer;
- one-command run, evaluation and viewer;
- model calls through the brief's gateway under its budget, with a per-item cache;
- tracing of every model call, never gating a run;
- review, never pass, when the model fails.

Its MVP decisions:
- no translation step;
- the classifier also returns a closed subtype;
- a template reporter;
- a provisional uncertainty threshold.

**Sources**:
- `docs/roadmap.md` (iteration 1);
- `docs/decisions/0001-policy-ambiguities.md` and `policy_decisions.yaml` (decisions A1–A8);
- `data/README.md`;
- `data/category-taxonomy.md`;
- `data/policy-docs/`;
- `.specify/memory/constitution.md`.

**Labels firewall.** This spec was written without reading `labels`, `line_items[].labels` or
`notes` in `data/receipts.jsonl`. Everything it says about the answers comes from the data
dictionary.

## Clarifications

### Session 2026-10-08

- Q: Who reads, from the line text, whom an item is for and whether it names a recipient (needed
  by GIFT-01, GIFT-03 and GIFT-04)? → A: The classifier, in the same call that returns the
  category. It returns two closed fields:
  - `recipient_kind`: `none`, `client_or_prospect`, `employee` or `government_official`;
  - `recipient_name`: a normalised name, or null.

  The engine reads only these fields. This is decision A9.
- Q: What provisional confidence threshold does EXC-03 use in the MVP? → A: 0.5, declared as
  provisional in configuration and in every result. The final value is chosen on the dev set in
  iteration 2 (A3).
- Q: What keyword baseline do we compare against? → A: Two deterministic baselines, both run on
  the same receipts and both in the report:
  - **keyword-classifier**: restricted-word lists per category, in the six languages, replace the
    classifier, and the same engine runs downstream. It yields every measure.
  - **keyword-flagger**: the legacy system. Any restricted word on a line makes the receipt
    `flag`, otherwise `pass`. It yields restricted F1 and dispositions only. Macro F1 is reported
    as not applicable.
- Q: How do the 13 DRAFT synthetic engine cases enter the engine tests? → A: As fixtures from
  the start, marked DRAFT.
  - A failing case is resolved against the policy text, never by bending the case to the code.
  - Luis's review of all 13 is an exit criterion of the "MVP done" checkpoint.
- Consistency fix, made without a question: the viewer shows the correct answers by reading the
  evaluation's committed comparison output, never the receipts file (constitution, principle I).

## User Scenarios & Testing *(mandatory)*

The actors:
- the **auditor**, who reviews the validator's findings;
- the **evaluator**, the review panel or Luis, who checks how good the findings are;
- the **maintainer**, who changes rules and needs to trust the engine.

### User Story 1 - Validate a batch of receipts end to end (Priority: P1)

An auditor runs one command over the receipt file and gets, for every receipt, a result in the
brief's shape:
- each line item's category, restricted flag and confidence;
- the exceptions, each citing its rule, policy document, line items and the literal policy text;
- the review signals;
- a disposition of flag, review or pass.

The results are written to a committed file. A second run over the same input gives
byte-identical output and makes no paid model call.

**Why this priority**: This is the product. Every other story reads its output.

**Independent Test**: Run the command on the receipt file in a clean checkout with a warm cache.
Check that every receipt has a result in the required shape. Check that a second run is
byte-identical and makes zero billed calls.

**Acceptance Scenarios**:

1. **Given** the 32 receipts and a valid model key, **When** the auditor runs the validation
   command, **Then** each receipt gets exactly one result, and every line item has a category from
   the 21-category taxonomy, a restricted flag and a confidence between 0 and 1.
2. **Given** a completed run, **When** the command runs again with the cache in place, **Then**
   the output is byte-identical and no billed model call is made.
3. **Given** the model gateway fails, or returns an unusable answer for an item, **When** the
   receipt is validated, **Then** that item raises an `EXC-03` review signal saying why, and the
   receipt is never `pass`.
4. **Given** the tracing service is unreachable, **When** the auditor runs the command, **Then**
   the run completes and writes the same results. A warning says that traces were not recorded.
5. **Given** any result, **When** the auditor reads it, **Then** it records the model ID, the
   pinned provider, the prompt version and the rules version that produced it.

---

### User Story 2 - Trust the engine's decisions (Priority: P1)

A maintainer can check every engine decision against the policy text without any model involved.
The engine takes classified items, the receipt details and the applicable rules, and applies the
37 in-scope rules exactly as written. Where the text is ambiguous, it follows decisions A1–A8 and
cites them.

The brief's five cases and the synthetic engine cases run as automated tests on hand-built inputs.

**Why this priority**: The brief says the engine is "the part of the project you fully own".
The panel will question it in detail.

**Independent Test**: Run the engine test suite with no model key and no network. Every brief
case and every synthetic engine case passes, and so does a determinism test that repeats each
decision.

**Acceptance Scenarios**:

1. **Given** clothing with no baggage-delay reference (the brief's RCP-027 case), **When**
   evaluated, **Then** a PERS-02 exception is raised. A pre-approval reference does not waive it
   (EXC-02, A5).
2. **Given** an APAC-entity employee's client-entertainment receipt with alcohol and an attendee
   count of two or more (the RCP-016 case), **When** evaluated, **Then** REG-01 is raised at high
   severity, and no ALC-01, ALC-02 or ALC-03 is raised.
3. **Given** a computer accessory with a unit price of $189 and no pre-approval (the RCP-006
   case), **When** evaluated, **Then** no TECH-02 exception is raised.
4. **Given** a $329 monitor and no pre-approval (the RCP-026 case), **When** evaluated, **Then**
   TECH-02 is raised at medium severity.
5. **Given** a receipt whose only exception is low severity (the RCP-031 case), **When** the
   disposition is computed, **Then** it is `review`, not `flag` (EXC-01).
6. **Given** a receipt at a medium-risk MCC whose items are all compliant (the RCP-028 case),
   **When** evaluated, **Then** it has no exceptions, one MCC-02 review signal, and the
   disposition `review`.
7. **Given** any set of inputs, **When** the engine runs twice, **Then** the two outputs are
   byte-identical.

---

### User Story 3 - Measure the system honestly (Priority: P2)

An evaluator runs one command and gets the brief's evaluation on the 28 in-scope receipts,
computed only from committed outputs, with no model call. Every number states its N.

**Why this priority**: The brief cuts "UI polish first and the evaluation last". Measurement is
graded; a high score without its N is not.

**Independent Test**: In a checkout without a model key, run the evaluation command. It
reproduces the committed report exactly.

**Acceptance Scenarios**:

1. **Given** committed results, **When** the evaluator runs the evaluation, **Then** the report
   contains:
   - macro F1 across categories and F1 on the restricted decision, over the 65 in-scope items;
   - the 3×3 disposition confusion matrix over the 28 receipts;
   - false positives out of the 9 receipts that should pass;
   - missed violations out of the 16 receipts that should be flagged;
   - the same measures for both keyword baselines (FR-032);
   - per-rule precision and recall;
   - evidence correctness;
   - two marked failure-case slots;
   - the base-rate computation.
2. **Given** a metric, **When** it is shown, **Then** its N is shown with it, and an interval
   where the report defines one.
3. **Given** the four out-of-scope receipts (RCP-020, RCP-021, RCP-029, RCP-030), **When** the
   evaluation runs, **Then** they are excluded from every score and listed as not scored.
4. **Given** the evaluation code, **When** the pipeline runs, **Then** no pipeline component has
   read the answers. A test proves the labels firewall.

---

### User Story 4 - Browse results in a viewer (Priority: P3)

During the review session, the presenter opens a viewer with one command. It has three views:
- **Receipt list**: every receipt with the system's disposition next to the correct one, and
  mismatches easy to spot.
- **Receipt detail**: line items with category and confidence; exceptions with their cited
  policy text and arithmetic; the correct answer alongside.
- **Metrics**: the evaluation numbers in one place.

The viewer reads committed outputs only and makes no model call.

**Why this priority**: The brief requires it for the demo, but grades no polish. It only adds
value once stories 1–3 exist.

**Independent Test**: Launch the viewer offline from committed outputs. Open any receipt the
panel names, and check that its detail matches the results file.

**Acceptance Scenarios**:

1. **Given** committed results and the evaluation report, **When** the viewer starts, **Then**
   all three views load without network access or a model key.
2. **Given** a receipt whose disposition differs from the correct one, **When** the list is
   shown, **Then** the mismatch is visually distinct.
3. **Given** a receipt with an exception, **When** its detail is opened, **Then** the exception
   shows its rule ID, its policy document, its line items, the literal policy text and the
   explanation.

### Edge Cases

- **Non-itemized receipt.** Its single charge is `other` and raises no EXC-03. DOC-01 applies
  above $75, and MEAL-01 uses the full total for meal-type receipts.
- **Foreign currency.** Thresholds are evaluated in USD using the rate recorded on the receipt
  (A1 defaults). A missing currency or rate raises DOC-04.
- **EUR thresholds.** REG-03 and REG-04 compare against EUR thresholds. When the needed euro
  rate is not on the record, it comes from a versioned table. If it is missing there too, the
  receipt goes to review, never to pass (A1).
- **Uncertain item** (confidence below the threshold). It raises EXC-03 and is left out of every
  other rule's calculation for that receipt, including meal spend, DOC-03 and the gift caps.
- **Cross-receipt rules.**
  - MEAL-01, REG-02 and REG-03 add up one employee's meal receipts on the same calendar date.
  - HEALTH-01 adds up OTC medication across all receipts of one trip, and raises on every
    contributing receipt (A4).
  - The result must not depend on the order of the receipts.
- **Gratuities and service fees.** They count in meal spend, but are never cited in `line_ids`.
- **Whole-receipt rules.** MCC-01, MEAL-01, MEAL-02, DOC-01 to DOC-04 and REG-02 to REG-04 cite
  an empty `line_ids`.
- **One exception per rule per receipt.** Each rule appears at most once on a receipt. When
  several items break it, one exception lists them all.
- **Government official.** GIFT-04 replaces GIFT-01 for the lines provided to the official,
  including a meal line that also covers the employee, but not the gratuity. The meal cap still
  applies.
- **Retail alcohol at a high-risk MCC** (for example 5921). Both ALC-03 and MCC-01 are raised.
  For an APAC employee, it is REG-01 and MCC-01.
- **Bars (MCC 5813).** ALC-01 and ALC-02 apply, never ALC-03 (MCC-03).
- **A `PA-` reference.** It satisfies only TECH-02. It never satisfies ENT-01, TECH-04 or the
  baggage-delay carve-outs (A5).
- **Missing attendee count.** The meal per-person divisor is 1. ALC-01 is not satisfied.
- **An item the taxonomy sends to `other`** (event ticket, mobile handset, prescription
  medication). Its closed subtype drives ENT-01, TECH-03 and the prescription part of HEALTH-01
  (A6).
- **Out-of-scope receipts.** They are still processed and shown, but never scored. The timing
  rules TIME-01 to TIME-04 are not evaluated.
- **Budget exhausted.** Model calls fail, and the affected items follow the model-failure path.
  The run still completes.

## Requirements *(mandatory)*

### Functional Requirements

**Input and the labels firewall**

- **FR-001**: The system MUST load receipts with every answer field (`labels`,
  `line_items[].labels`, `notes`) removed before any pipeline component receives them. Only the
  evaluation MAY read those fields.
- **FR-002**: An automated test MUST fail if any pipeline component can reach an answer field.
- **FR-003**: The system MUST accept an optional VAT number on a receipt. In this dataset it is
  always absent and is treated as missing (A2).

**Normaliser**

- **FR-004**: The normaliser MUST clean each line's text deterministically: Unicode
  normalisation, whitespace and casing. It keeps the original language and the raw description
  unchanged in the output. Translation is out of scope for this iteration.

**Item classifier**

- **FR-005**: For every line item, the classifier MUST return:
  - a category from the 21-category taxonomy, as given;
  - the restricted flag that the taxonomy assigns to that category;
  - a confidence between 0 and 1;
  - when the category is `other`, a subtype from the closed set `event_ticket`,
    `mobile_handset`, `prescription_medication`, `none` (A6).
- **FR-006**: In the same call, the classifier MUST read from the line text only:
  - `recipient_kind`: `none`, `client_or_prospect`, `employee` or `government_official`;
  - `recipient_name`: a normalised name, or null when the line names nobody.

  Lines on one receipt with the same `recipient_name` are the same recipient for GIFT-01. These
  fields feed GIFT-01, GIFT-03 and GIFT-04, and the engine reads only them, never free text
  (decision A9).
- **FR-007**: The classifier MUST NOT receive the declared expense type or the attendee count. It
  MAY receive the merchant name and MCC.
- **FR-008**: Every classification MUST be cached under its normalised input, model and prompt
  version. A repeated item makes no new call.
- **FR-009**: When a model call fails or returns an answer that breaks the schema, the item MUST
  be marked unclassified. That raises EXC-03 with a reason. It is never silently treated as
  compliant.

**Policy retriever**

- **FR-010**: For each receipt, the retriever MUST select the in-scope rules that could apply,
  using only its items' categories and subtypes, its MCC and its metadata.
- **FR-011**: The selection MUST be deterministic, and it MUST never omit a rule that the engine
  would raise on that receipt. A test checks the selection against the engine's output on every
  fixture.

**Policy engine**

- **FR-012**: The engine MUST be deterministic code, with no model call. It MUST implement every
  in-scope rule in the Rule Catalogue below, from the policy text, citing each rule's ID and any
  decision (A1–A8) it follows.
- **FR-013**: The engine MUST convert every amount to USD with the rate recorded on the receipt
  before comparing it with a threshold. TECH-02 is judged on the unit price in USD.
- **FR-014**: The engine MUST apply carve-outs only when their evidence is recorded:
  - an attendee count of two or more on Client Entertainment for ALC-01;
  - a reference of the required kind for TECH-02, ENT-01, TECH-04, PERS-01 and PERS-02, using
    the prefix table (A5);
  - a trip record for HEALTH-01;
  - a trip of four or more nights for LAUNDRY-01.
- **FR-015**: The engine MUST apply the regional overrides:
  - for APAC employees, REG-01 replaces ALC-01, ALC-02 and ALC-03;
  - for APAC employees, REG-02 replaces MEAL-01;
  - for EMEA employees, REG-03 replaces MEAL-01;
  - merchant rules such as MCC-01 still apply.
- **FR-016**: The engine MUST compute the disposition exactly as EXC-01 states:
  - any critical, high or medium exception → `flag`;
  - otherwise, any low exception or any review signal → `review`;
  - otherwise → `pass`.
- **FR-017**: The engine MUST raise EXC-03 for every item whose confidence is below a single named
  threshold, and MUST leave that item out of every other rule's calculation. The MVP threshold is
  0.5, provisional, recorded in configuration and stated in the output. The final value is chosen on
  the dev set in iteration 2 (A3).
- **FR-018**: Every exception MUST carry:
  - `rule_id`, `policy_doc` and `severity`;
  - `line_ids`, following the conventions in `data/README.md`;
  - `evidence`, the literal policy sentence it relies on (EXC-04).

  An exception that cannot be given evidence MUST NOT be raised.
- **FR-019**: Each rule MUST appear at most once per receipt.
- **FR-020**: MCC-02 MUST always be its own review signal, never an exception, even when another
  rule raises an exception on the same receipt.
- **FR-021**: Cross-receipt rules (MEAL-01, REG-02, REG-03, HEALTH-01) MUST produce the same
  result whatever order the receipts are processed in.

**Exception reporter**

- **FR-022**: The reporter MUST turn each engine finding into a readable explanation, from a
  deterministic template. Each explanation states the rule, the lines involved and the
  arithmetic behind any threshold, for example the per-person amount against the cap. It MUST
  NOT add a claim that the engine did not compute.

**Output**

- **FR-023**: The system MUST write one result per receipt in the brief's shape. Fields may be
  added; none may be removed or renamed. The results file is committed.
- **FR-024**: Every result MUST record the model ID, the pinned provider, the prompt version, the
  rules version and the EXC-03 threshold that produced it.

**Model access and observability**

- **FR-025**: Model calls MUST go only through the brief's model gateway, with a pinned model and
  provider, temperature 0 where the endpoint supports it, and a spend cap inside the brief's $5
  budget. Spend MUST be measured from the gateway's reported cost.
- **FR-026**: Every model call MUST be traced. Each receipt is one trace, with one span per
  component. Each model call is one generation recording:
  - the model and the exact input;
  - the output and any reasoning;
  - token usage and billed cost;
  - the linked prompt version;
  - the gateway's request id.
- **FR-027**: Traces MUST NOT contain answer fields or per-receipt correct answers. Only the
  evaluation may attach results, and only as scores.
- **FR-028**: When tracing is unavailable, every command MUST still complete and produce the
  same outputs.

**Evaluation**

- **FR-029**: The evaluation MUST read only committed outputs and the answers, make no model
  call, and score only the 28 in-scope receipts.
- **FR-030**: The evaluation MUST report every item in the brief's Part 3, with its N:
  - macro F1 over the categories present in the answers, where a category never predicted
    counts as zero precision;
  - restricted F1, with restricted = true as the positive class;
  - the 3×3 disposition matrix;
  - false positives out of 9;
  - missed violations out of 16;
  - both keyword baselines on the same measures (FR-032);
  - two failure-case slots;
  - the base-rate computation.
- **FR-031**: The evaluation MUST also report:
  - per-rule precision and recall, matched on receipt and `rule_id`;
  - evidence correctness: among matched exceptions, the share whose `line_ids` equal the
    answer's;
  - how many EXC-03 signals fired, and which dispositions they changed;
  - how many REG-04 exceptions come only from the absent VAT field (A2).
- **FR-032**: The evaluation MUST include two deterministic keyword baselines over restricted
  words, run on the same receipts:
  - **keyword-classifier**: keyword lists per category in the six languages replace the
    classifier, and the same engine runs downstream. It is scored on every measure.
  - **keyword-flagger**: the legacy kind of system this project replaces. Any restricted word
    flags the receipt; otherwise it passes. It is scored on restricted F1 and dispositions, and
    macro F1 is shown as not applicable.

  The report MUST say honestly where either baseline does better.
- **FR-033**: The base-rate section MUST compute, from the measured false-positive and
  missed-violation rates, how many flags out of 10,000 receipts would be false at realistic
  prevalence, for example 1 %, 3 % and 5 %.

**Viewer**

- **FR-034**: The viewer MUST provide the receipt list, receipt detail and metrics views. It
  reads only committed outputs, the evaluation report and the evaluation's committed comparison
  output, and makes no model call. It shows the correct answers from that comparison output and
  MUST NOT read the receipts file's answer fields itself.

**Commands**

- **FR-035**: Validation, evaluation and the viewer MUST each start with one documented command.

### Rule Catalogue (in scope for iteration 1)

There are 37 rules: every rule in `data/policy-docs/` except TIME-01 to TIME-04. "Receipt" means a
whole-receipt rule, which cites empty `line_ids`.

| Policy document | Rule | Severity / effect | Scope | Decisions |
|---|---|---|---|---|
| meals-and-entertainment-policy.md | MEAL-01 | medium | receipt, cross-receipt per employee per day | A8 |
| | MEAL-02 | low | receipt | |
| | ALC-01 | high | items | |
| | ALC-02 | medium | items | |
| | ALC-03 | high | items | |
| | ENT-01 | medium | items | A5, A6 |
| | ENT-02 | high | items | |
| technology-and-equipment-policy.md | TECH-01 | high | items | |
| | TECH-02 | medium | items, unit price in USD | A5 |
| | TECH-03 | high | items | A6 |
| | TECH-04 | low | items | A5 |
| gifts-and-awards-policy.md | GIFT-01 | medium | items, per recipient per receipt | A7, A9 |
| | GIFT-02 | high | items | |
| | GIFT-03 | medium | items | A9 |
| | GIFT-04 | critical | items, replaces GIFT-01 for those lines | A9 |
| non-reimbursable-items.md | PERS-01 | medium | items | A5 |
| | PERS-02 | medium | items | A5 |
| | PERS-03 | high | items | |
| | HOUSE-01 | medium | items | |
| | HEALTH-01 | low for OTC, medium for prescription | items, cross-receipt per trip | A4, A6 |
| | LAUNDRY-01 | low | items | |
| merchant-category-risk.md | MCC-01 | high | receipt | |
| | MCC-02 | review signal | receipt | |
| | MCC-03 | modifier: bars are on-premises for ALC-01/02 | — | |
| receipt-documentation-requirements.md | DOC-01 | medium | receipt | |
| | DOC-02 | medium | receipt | |
| | DOC-03 | medium | receipt | A7 |
| | DOC-04 | medium | receipt | A1 |
| regional-addendum.md | REG-01 | high | items, APAC | |
| | REG-02 | medium | receipt, APAC, cross-receipt per day | |
| | REG-03 | medium | receipt, EMEA, cross-receipt per day | A1 |
| | REG-04 | low | receipt, EMEA | A1, A2 |
| | REG-05 | modifier: which rate converts | — | A1 |
| approval-and-exception-handling.md | EXC-01 | modifier: disposition | — | |
| | EXC-02 | modifier: reference kinds | — | A5 |
| | EXC-03 | review signal | items | A3 |
| | EXC-04 | modifier: evidence | — | |

### Key Entities

- **Receipt input**: the receipt's identity, employee, country and entity, declared expense
  type, merchant and MCC, date and time, currency and rate, totals, attendee count, trip and
  trip length, approval reference, itemized flag, an optional VAT number, and its line items. It
  never contains answer fields.
- **Line item input**: line ID, raw description, language, quantity, unit price, amount and
  amount in USD.
- **Normalised item**: a line item plus its cleaned text.
- **Classification**: per line, the category, restricted flag, confidence, subtype for `other`,
  `recipient_kind` and `recipient_name`, plus the model ID and prompt version. A classification
  can also be marked unclassified, with a reason.
- **Applicable rule set**: per receipt, the rule IDs the retriever selected.
- **Exception**: rule ID, policy document, severity, line IDs, literal evidence, explanation, and
  the computed values behind it.
- **Review signal**: rule ID, policy document and reason.
- **Receipt result**: receipt ID, disposition, classified line items, exceptions, review
  signals, and run metadata (model ID, provider, prompt version, rules version, EXC-03
  threshold).
- **Cross-receipt context**: per employee per date, the meal spend per person; per trip, the OTC
  medication total. It is an explicit input to the engine, never hidden state.
- **Evaluation report**: every metric in FR-030 and FR-031 with its N, for the system and for the
  keyword-classifier and keyword-flagger baselines.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All 32 receipts get a result in the required shape from one command. The 28
  in-scope receipts are scored.
- **SC-002**: The five brief cases, every synthetic engine case and the determinism check pass,
  with no model key and no network.
- **SC-003**: Re-running validation on a warm cache gives byte-identical results and costs
  $0.00 in billed calls.
- **SC-004**: Every number in the evaluation report is reproduced exactly from committed outputs
  by one command with no model call, and every number states its N.
- **SC-005**: 100 % of exceptions carry a rule ID, policy document, line IDs that follow the
  conventions, and literal policy text.
- **SC-006**: No receipt whose classification failed or was uncertain ends as `pass`.
- **SC-007**: Validation, evaluation and the viewer still complete with the tracing service
  down. With it up, 100 % of billed model calls appear as traced generations.
- **SC-008**: Total model spend for the iteration stays below $1 of the $5 budget, measured from
  the gateway's reported costs.
- **SC-009**: A panel member can open any receipt they name in the viewer, and see its
  exceptions with policy text and arithmetic, within one minute of launching it.
- **SC-010**: Before the MVP is declared done, Luis has reviewed all 13 synthetic engine cases
  against the policy text. Any case he changed is recorded with its reason.

## Assumptions

- **Constraints from the brief and the constitution:**
  - the model gateway is OpenRouter;
  - the tracing service is Langfuse;
  - the viewer is Streamlit;
  - model calls use the brief's key, kept outside the repository.

  They are named here, not in the requirements, so the requirements stay testable without them.
- **The provisional MVP classifier** is the reference model from the exploration trials,
  `openai/gpt-oss-120b` with a pinned provider. The final model is chosen in iteration 2 (E14).
- **A9 (decided 2026-10-08, recorded in ADR 0001):** the classifier returns `recipient_kind` and
  `recipient_name` from the line text. The data dictionary says that whether a recipient is a
  government official, a client or an employee "is stated only in the line text".
- **The provisional EXC-03 threshold** is 0.5. It was set before the 28-receipt run and is not
  tuned on it.
- **The 13 synthetic engine cases** in `explorations/dev_set/engine_cases_draft.jsonl` are test
  fixtures from the start, marked DRAFT. Luis reviews them before the "MVP done" checkpoint
  (SC-010).
- **The four out-of-scope receipts** are processed but neither scored nor tested on timing rules.
- **The two failure-case analyses** are written in iteration 3. The MVP report holds their slots.
- **Seams only, no features** (constitution XI):
  - validation is a function of one receipt plus an explicit cross-receipt context;
  - the viewer depends only on the output schema;
  - results are read through one read-only module.

  This keeps candidates L1–L3 cheap to add. None of them is built.

## Out of Scope

Deferred by `docs/roadmap.md`. See it for the trigger, seam and size of each.

- **Iteration 2:**
  - hardening the dev set;
  - choosing the model (E14);
  - choosing the EXC-03 threshold and confidence source (E7);
  - a translation step (E5);
  - retriever variants;
  - an LLM-drafted reporter;
  - the oracle-classifier ablation;
  - the finalist runs on the 28 receipts.
- **Iteration 3:** the README, the AWS design page, the two failure-case write-ups, the final
  base-rate paragraph, closing `AI_NOTES.md`, and the experiments table in the viewer.
- **Candidates after delivery:**
  - L1, asynchronous processing behind a queue;
  - L2, authentication;
  - L3, an API and a sturdier UI replacing Streamlit;
  - L4, auditor overrides;
  - L5, versioned policy deployment;
  - L6, the timing rules TIME-01 to TIME-04 and their four receipts;
  - L7, observability of the parts that call no model.
