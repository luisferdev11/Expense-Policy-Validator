# Feature Specification: Iteration 2, Decide on the Dev Set

**Feature Branch**: `feat/002-decide-on-dev`

**Created**: 2026-10-09

**Status**: Draft

**Input**: User description: "Iteration 2 of the Expense Policy Validator: decide on the dev set,
as scoped in docs/roadmap.md (Iteration 2), plus E15 and the dev-set extension already committed."

The full description is preserved in the session prompt log. It covers:
1. hardening the dev set;
2. registering every decision rule before its run;
3. running E14, E7, E5, E15 and the retriever comparison on the dev set;
4. an oracle-classifier ablation;
5. applying the winners, one finalist run on the 28 receipts, and an experiments table.

**Sources**:
- `docs/roadmap.md` (iteration 2);
- `explorations/research/experiments_plan.yaml` (E5, E7 and the registered E14);
- `docs/decisions/` (ADR 0001 including A9 and Q3; ADRs 0002 and 0003);
- the constitution v1.1.0;
- the iteration 1 evaluation report.

**Labels firewall**: the dev set is synthetic and may be read. The answers in
`data/receipts.jsonl` are read only inside the evaluation.

## User Scenarios & Testing *(mandatory)*

The actors:
- **Luis**, who reviews labels and approves decision rules;
- **the evaluator** (the panel), who checks that every choice was made on the dev set;
- **the auditor**, who uses the final outputs.

### User Story 1 - A trustworthy dev set (Priority: P1)

Luis reviews every DRAFT item of the synthetic dev set, blind to model outputs. He confirms or
corrects the category and, where proposed, the subtype (A6) and the recipient (A9). The set is
then frozen: its content hash and a fixed decision split are recorded before any experiment runs
on it.

**Why this priority**: Every later decision is only as good as these labels. Iteration 1's model
comparison was marked preliminary for exactly this reason.

**Independent Test**: The review record holds one decision per item. The frozen hash matches
the file. The decision split is written down and never changes afterwards.

**Acceptance Scenarios**:

1. **Given** the 130 dev items, **When** Luis finishes reviewing, **Then** every item has a
   recorded decision (confirmed or changed, with a note for each change), and none was reviewed
   with a model output in view.
2. **Given** the reviewed set, **When** it is frozen, **Then** its hash and the list of items in
   the decision split are committed before the first experiment call.

---

### User Story 2 - Choices made on dev, against rules written first (Priority: P1)

For each open choice there is a decision rule, which Luis approves before any run:
- the classifier model (E14);
- the EXC-03 confidence source and threshold (E7);
- translation before classification (E5);
- whether `"subtype": null` reads as `"none"` (E15);
- the retriever.

Each experiment then runs on the dev set's decision split only, through the same classifier code
the pipeline uses. The rule picks the winner mechanically.

**Why this priority**: This is principle V and the heart of what the team asked to see: "see
many different options, attack them and take the right decision".

**Independent Test**: For every experiment, the registered rule predates the run in the
history, and the winner can be re-derived from the committed results with no model call.

**Acceptance Scenarios**:

1. **Given** a registered rule and the frozen decision split, **When** the experiment runs,
   **Then** results record each variant's metrics with N and intervals, and the rule's outcome
   is applied as written. A result that contradicts intuition is reported, not overridden.
2. **Given** any experiment, **When** its calls run, **Then** every model call is traced, cached
   and counted against the spend cap.
3. **Given** the 28 in-scope receipts, **When** any choice is made, **Then** none of them was
   used.

---

### User Story 3 - Know where errors come from (Priority: P2)

The evaluator sees, for the 28 in-scope receipts, what the engine does with perfect
classifications (an oracle). Every remaining error is attributed to a stage: classification,
retrieval or rule logic.

**Why this priority**: The brief asks which stage caused each failure, and the panel will probe
the engine. An oracle run separates engine errors from classifier errors.

**Independent Test**: The evaluation shows the engine's dispositions under oracle
classifications next to the pipeline's, and lists each disagreement with its stage.

**Acceptance Scenarios**:

1. **Given** the correct categories (read only inside the evaluation), **When** the engine runs
   on them, **Then** the report shows its disposition accuracy with N, and each receipt where the
   pipeline and the oracle differ.

---

### User Story 4 - Apply the winners and report once (Priority: P2)

The pipeline adopts the winning settings and runs once on the 28 in-scope receipts. The
evaluation report and the viewer gain an experiments table: each experiment's rule, winner,
margin, and why the other variants lost.

**Why this priority**: It turns the iteration 1 provisional results into final ones, with the
reasoning visible for the presentation.

**Independent Test**: Re-running the evaluation reproduces the table and every number with no
model call.

**Acceptance Scenarios**:

1. **Given** the winners, **When** the finalist runs, **Then** each result records the chosen
   model, prompt version, rules version and EXC-03 threshold, now marked as chosen on dev.
2. **Given** the committed outputs, **When** the viewer opens, **Then** an experiments view lists
   every experiment with its rule, winner and margin.

### Edge Cases

- **A tie, or no variant passing the non-inferiority margin.** The reference (gpt-oss-120b) is
  kept, and the report says so.
- **A model that cannot return the subtype or recipient fields** (decision models). It is
  excluded from E14, with the reason recorded.
- **A label Luis changes after a run has used it.** The set's hash changes. Affected experiments
  are re-run and the history shows both.
- **Calibration with little spread** (iteration 1 found almost every confidence in the top bin).
  E7 reports that honestly. A threshold that never fires on dev is a valid outcome, stated with
  its consequence.
- **A provider endpoint that is retired or refuses a parameter.** The variant is recorded as
  failed, with the error, and not silently substituted.
- **Spend nearing the cap.** Runs stop. Partial results are reported as partial.

## Requirements *(mandatory)*

### Functional Requirements

**Dev set**

- **FR-001**: Every dev item MUST carry a review decision by Luis, blind to model outputs, before
  any decision run. Changed labels need a note.
- **FR-002**: Items that exercise A6 or A9 MUST carry reviewed subtype and recipient labels. All
  other items default to `none`, `none` and null.
- **FR-003**: The reviewed set MUST be frozen by content hash. A fixed decision split, disjoint
  from any items used to develop prompts, MUST be recorded before the first experiment call.

**Registered decisions**

- **FR-004**: Each experiment MUST have a decision rule, registered and approved by Luis before
  its first call. The rule names the metric, the margin or threshold, the tie-break, and what
  happens when nothing qualifies.
- **FR-005**: E14 (the model) MUST compare candidates against `openai/gpt-oss-120b` on cls-v2 with
  the registered non-inferiority margin of 2 accuracy points on category. Subtype and recipient
  accuracy and restricted F1 are reported as secondary, with any minimum they must meet stated in
  the rule. Anthropic models MAY appear only as disclosed comparisons. They MUST NOT become the
  delivered model (team request).
- **FR-006**: E7 MUST compare confidence sources available on cls-v2, using Brier score, ECE and
  the coverage-accuracy curve. It MUST choose the EXC-03 threshold by the registered rule, and
  report how often the threshold fires on dev.
- **FR-007**: E5 MUST compare classifying the original text against translating to English
  first. The translation step is itself a traced model call.
- **FR-008**: E15 MUST compare a strict parser against one that reads `"subtype": null` as
  `"none"`, on the same cached answers, without new calls where possible.
- **FR-009**: The retriever comparison MUST show whether passing every rule changes any engine
  outcome against the trigger map, on every engine fixture.

**Running**

- **FR-010**: Experiments MUST run only on the decision split, through the pipeline's own
  classifier code. Every model call is traced, cached and counted against the spend cap.
- **FR-011**: Every metric MUST carry its N and, for proportions, a 95 % interval. Each
  experiment's outcome MUST be re-derivable from committed results with no model call.

**Ablation and reporting**

- **FR-012**: The evaluation MUST run the engine on the correct categories of the 28 in-scope
  receipts (an oracle classifier, inside the evaluation only). It MUST report the oracle's
  disposition accuracy with N, and attribute each pipeline error to a stage.
- **FR-013**: The pipeline MUST adopt the winners. Its results MUST record the threshold as
  chosen on dev, and the finalist MUST run once on the 28 in-scope receipts.
- **FR-014**: The evaluation report and the viewer MUST show an experiments table:
  - experiment, factor and variants;
  - the registered rule;
  - the winner and its margin, with N;
  - why the others lost;
  - spend.

### Key Entities

- **Dev item**: description, language, merchant, MCC, and the reviewed category, restricted
  flag, subtype and recipient (kind, name). It also records its split and review decision.
- **Frozen dev set**: the item file's content hash, the decision split, and the date.
- **Experiment registration**: ID, factor, variants, what is held fixed, metric, decision rule,
  approval, and registration time.
- **Experiment result**: per variant, the metrics with N and intervals, cost, and failures; and
  the rule's outcome.
- **Oracle ablation**: per in-scope receipt, the pipeline disposition, the oracle disposition,
  the correct disposition, and the attributed stage.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100 % of the 130 dev items carry Luis's review before the first decision run.
- **SC-002**: Every experiment's registration predates its first model call in the commit
  history.
- **SC-003**: Zero decisions use the 28 in-scope receipts. They run once per finalist.
- **SC-004**: Every chosen setting can be re-derived from committed results with no model call.
- **SC-005**: Every reported metric shows its N. Every proportion shows a 95 % interval.
- **SC-006**: Every pipeline error on the 28 receipts is attributed to a stage, using the oracle
  ablation.
- **SC-007**: Iteration spend stays within its cap, measured from reported costs. 100 % of
  billed calls are traced.

## Assumptions

- **Tools.** The model gateway is OpenRouter, tracing is Langfuse, and the review page is
  Streamlit. These are named here only, as in iteration 1.
- **E14 candidates by default:**
  - the reference `gpt-oss-120b`;
  - `gpt-oss-20b`;
  - the strongest small open models from E13 that return strict JSON.

  Decision models are excluded because they cannot return the cls-v2 subtype and recipient
  fields. Haiku is excluded from the delivered pipeline. The exact list is a clarification item.
- **The LLM-drafted reporter comparison** is deferred unless Luis keeps it. It needs a
  faithfulness judge, and time is short. This is a clarification item.
- **Spend cap for the iteration:** USD 1.00, the same as iteration 1. Iteration 1 spent USD
  0.0032.
- **The decision split** is fixed by item ID before any run. Its construction is decided in the
  plan.
- **Iteration 1's provisional threshold of 0.5** stays until E7 decides.

## Out of Scope

Deferred by `docs/roadmap.md`; see it for the trigger, seam and size of each.

- **Iteration 3:** the README, the AWS design page, the two failure-case write-ups, the final
  base-rate paragraph, and closing `AI_NOTES.md`.
- **Candidates L1 to L8**, including L8, the recipient-abuse controls.
- **Open questions Q1 (FX), Q2 (VAT) and Q3 (recipient named only by kind, and abuse).** They go
  to the panel. No experiment here decides them.
