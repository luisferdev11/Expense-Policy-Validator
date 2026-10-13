# Roadmap

How the Expense Policy Validator is delivered: an end-to-end MVP first, then small iterations.
Each iteration ends runnable, with passing tests and an updated evaluation report (constitution,
principle XI). Each one is its own `/speckit-specify` → `/speckit-plan` → `/speckit-tasks` cycle,
with its own ADR when it changes the architecture.

- **Decided by:** Luis, on 2026-10-08. The assistant proposed the cut.
- **Calendar:** last change Saturday 2026-10-10, review session Monday 2026-10-12. Three
  iterations fit before delivery. Everything after them is a candidate, not a commitment.

## Iteration 1: MVP, end to end

**Goal.** The smallest system that runs the brief's whole pipeline on the 28 in-scope receipts,
passes the brief's tests and produces an honest evaluation report.

**Shape.** A batch CLI over local files. No authentication, no queue, no server.

| Component | In scope | Deferred, and to where |
|---|---|---|
| Loader | Splits inputs from labels. A test enforces the firewall (principle I) | — |
| Normaliser | Deterministic cleanup (Unicode NFKC, whitespace, casing), no translation. The classifier reads the original language: the brief accepts "a multilingual classifier" as the translation step | A translation step, if E5 shows it helps (iteration 2) |
| Item classifier | `openai/gpt-oss-120b` on OpenRouter with a pinned provider, temperature 0, a per-item cache and Langfuse tracing. Prompt `cls-v2`: `cls-v1` plus the closed `subtype` for `other` (ADR 0001, A6) | The final model choice (E14, iteration 2) |
| Policy retriever | Deterministic trigger map over items, MCC and metadata | Comparison with alternatives (iteration 2) |
| Policy engine | **All 37 in-scope rules** (every rule except TIME-01 to TIME-04), decisions A1 to A8, EXC-01 disposition, EXC-03 with a *provisional* threshold. A failed or invalid classification sends the receipt to review, never to pass | The EXC-03 threshold chosen on dev (A3, iteration 2) |
| Exception reporter | Deterministic template: rule, line ids, literal policy text and the arithmetic behind each threshold | An LLM-drafted explanation judged for faithfulness (iteration 2) |
| Evaluation | The brief's seven items, each with its N: macro F1 and restricted F1 on 65 items, the 3×3 disposition matrix, false positives out of 9, missed violations out of 16, the keyword baseline, a slot for two failure cases, and the base-rate computation. Also per-rule precision and recall and evidence correctness | The oracle-classifier ablation (iteration 2); writing the failure cases up (iteration 3) |
| Viewer v1 | Streamlit with three views (receipt list, receipt detail, metrics), read from committed outputs only, no model calls | The Ledgerline front end (candidate L3) |
| CLI | One command to run the pipeline, one to evaluate, one to launch the viewer | — |

**Order of work.** The tasks open a thin path first: one receipt through all five components, a
few rules, outputs and evaluation. Only then do they widen it to all 37 rules. The plan has an
explicit "MVP done" checkpoint.

**Exit criteria.**
- These tests pass:
  - the five brief test cases (RCP-027, RCP-016, RCP-006 and RCP-026, RCP-031, RCP-028);
  - the 13 synthetic engine cases;
  - the determinism test;
  - the labels-firewall test.
- ruff, mypy and pytest are clean.
- Per-receipt results are committed as JSONL. Every record carries the model ID, the provider,
  the prompt version and the rules version.
- `eval` reproduces every number from the committed outputs with no model call.
- The viewer starts with one command.
- Every model call has a Langfuse trace, and the run also completes with Langfuse down.
- Luis has reviewed the 13 synthetic engine cases against the policy text. They are used as DRAFT
  fixtures until then.

**Status: done on 2026-10-09** (task T093). Every criterion was checked on a clean checkout with
no `.env`:

| Criterion | Evidence |
|---|---|
| Brief cases, synthetic cases, determinism and firewall tests pass | `uv run pytest`: 233 passed |
| ruff, mypy and pytest are clean | pre-commit on every commit |
| Results committed, with model, provider, prompt and rules versions | `outputs/results.jsonl`, `run` field on every line |
| `eval` reproduces every number with no model call | `epv eval` without a key leaves `outputs/eval/` byte-identical |
| The viewer starts with one command | `uv run epv view`; smoke tests cover its three views |
| Every model call traced; runs complete with Langfuse down | 78 `classify-item` generations linked to `cls-v2`; tracer fallback tests; the clean-checkout run had tracing off |
| Luis reviewed the 13 engine cases | `tests/engine_cases/fixtures/REVIEW.md` |

Spend for the whole iteration: USD 0.003205 of the USD 1.00 cap.

## Iteration 2: decide on the dev set

**Goal.** Replace the MVP's provisional choices with choices measured on the synthetic dev set,
each against a decision rule registered before its run (principle V).

**Scope.**
- Harden the dev set first: Luis reviews the 101 labels that are still DRAFT.
- Run these experiments:

  | Experiment | Decides |
  |---|---|
  | E14 | The classifier model, with a 2-point paired-bootstrap non-inferiority margin |
  | E7 | The EXC-03 confidence source and threshold (A3) |
  | E5 | Whether to translate before classifying |
  | E15 | Whether the parser reads `"subtype": null` as `"none"`. The iteration 1 run saw it on 2 of 79 lines, and it caused the run's only disposition error. Luis decided on 2026-10-09 to keep the parser strict until the dev set decides |

- Make these comparisons:
  - retriever variants (trigger map against passing every rule);
  - ~~template reporter against an LLM-drafted reporter~~: cut on 2026-10-09 (clarification).
    The template stays ("the explanation is the computation"). An LLM-drafted reporter judged for
    faithfulness is future work;
  - the oracle-classifier ablation, which attributes every error to its stage.
- Run the 28 receipts once per finalist.

**Exit criteria.**
- An experiments table with, for each experiment, the registered rule, the winner, the margin
  and why the others lost.
- The pipeline runs with the chosen settings, and the report and viewer are updated.

**Status: done on 2026-10-09** (release `v0.2.0`). ADR 0004 replaced the provider pin with
OpenRouter routing; ADR 0005 records the winners: gpt-oss-120b, self-reported confidence with
EXC-03 at 0.97, original text, strict parser, trigger map. The finalist run scores 28/28
dispositions. Its first pass scored 27/28: malformed CoreWeave answers with confidence 0 sent
RCP-012 to review, which led to ignoring CoreWeave (ADR 0004, amendment); iteration 3 writes it
up as a failure case of the provider stage. Carried forward: a larger dev set to separate
gpt-oss-20b (half the cost, one item behind) from the reference.

## Iterations 2.1 to 5 (planned 2026-10-10)

Luis asked for a real product before delivery: loading new receipts, a review lifecycle, and an
application beyond Streamlit. ADR 0006 records the intake and lifecycle decisions. Order of work:

| Iteration | Release | Content |
|---|---|---|
| 2.1 · intake in the viewer | v0.2.1 | Streamlit page to upload one receipt (JSON) or a batch (JSONL), run the existing pipeline on it (traced, cached, answer keys stripped by the loader) and show the results. **Done 2026-10-10** (`specs/003-intake-viewer/spec.md`) |
| 3 · intake and lifecycle backend | v0.3.0 | Event store, idempotent single and batch intake with revisions, worker that resumes after a crash, cross-receipt re-evaluation, reviewer actions, Langfuse `auditor_agreement` scores. Postman collection and environment under `docs/api/`. Tests: idempotency, crash-resume, cascade, parity with `epv run`. **Released 2026-10-10** (`specs/004-backend-lifecycle/`, ADR 0007): `epv serve`, `epv worker`, `epv openapi`; the 32 receipts through the API equal `epv run` byte for byte in 10 arrival orders; 51 Postman requests with 99 assertions pass against a live offline server |
| 4 · application | v0.4.0 | React + Vite front on the API with the Ledgerline design: intake, queue and workbench, compliance, receipt timeline, insights, and an evaluation area with a demonstrative comparison of the classifiers. **Released 2026-10-11** (`frontend/`, ADR 0008). jev-1.13 ran once on the frozen dev set: 130 of 130 categories (N = 130, USD 0.0055), category only, so it decides nothing; a follow-up experiment is proposed in the improvements list |
| 5 · delivery package | v1.0.0 | The scope below, plus the engine adjustments from Luis's review. **In progress:** the AWS design (`docs/aws.md`, with the monthly cost worked out), the two failure cases in the evaluation report, and the README draft; the engine adjustments wait for Luis's review session |
| 6 · final improvements | v1.1.0 to v1.3.0 | Seven improvements Luis picked on 2026-10-12, specified in full before any code. See the section below |

## Iteration 5: delivery package

**Scope.**
- The README, at most 2 pages, with the brief's sections.
- The AWS one-page design, with the monthly cost worked out by hand at 50,000 receipts a day (the
  brief's figure) and at 100,000 (the production target). The database choice is ADR 0009.
  It also answers candidates L1 to L8 for production. Its "before production" list must include
  the recipient-abuse risk (Q3, L8).
- The two failure cases, each with its stage.
- The base-rate paragraph with the real numbers.
- `AI_NOTES.md` closed out.
- The viewer shows the experiments table and each exception's arithmetic.

**Exit criteria.** Everything in the brief's "What to submit" list is present and reproducible
from the repository.

## Iteration 6: final improvements (specified 2026-10-12)

Luis picked seven items from the improvements list. Each implementable group has a full Spec Kit
chain (spec, research, data model, contracts, plan, tasks, quickstart), so an implementation
session only runs `/speckit-implement`. Order: 006 first (its schema migration is the base), then
007, then 008 (it uses the types 006 generates).

| Spec | Release | Content | Status |
|---|---|---|---|
| `specs/006-api-hardening/` | v1.1.0 | Classification cache as a table behind a port (the committed JSONL stays as seed and export); schema v2 with the first real migration; `created_at` (first receipt) and one timestamp format; `decided_by` and `decided_at`; `receipt` and `result` typed in OpenAPI with generated front-end types; a Locust load test with a committed report | Implemented on `feat/006-api-hardening` (2026-10-12), pending review; no tag yet |
| `specs/007-jev-classifier/` | v1.2.0 | The jev decision adapter and a hybrid classifier (jev for the category, gpt-oss-120b for subtype and recipient); shadow mode in the worker with an agreement report; E16 registered before running, with the A6/A9 guard checked before "superior"; switching the classifier is a configuration change, gated on E16 and an ADR | Phases 0 to 4 built on `feat/007-jev-classifier`: the adapter, the hybrid, one factory, the corrected decide rule, and E16 run on 2026-10-12 (N = 130, USD 0.0064 of 0.10). The hybrid is superior under the registered rule (130 of 130 against 123 of 130, McNemar b = 7, c = 0, p = 0.0156, A6/A9 wrong 2 of 29 as the reference), but costs USD 0.103 per 1,000 items against 0.061; jev alone fails the A6/A9 guard (23 of 29 wrong). The configured classifier is still `gpt-oss-120b`: switching needs an ADR (not written). Pending: shadow storage, stage and report (phases 5 to 7), after spec 006 |
| `specs/008-guided-intake/` | v1.3.0 | A guided form for one receipt, with a draft saved in the browser and revision prefill | Specified |
| `specs/009-roles/` | – | Roles and access (ADR 0010): five roles from the identity provider, OIDC, actor from the token | Designed, deferred. Luis answered R1 to R4 on 2026-10-12; R5 (whose identity provider) is open |

## Candidates after delivery

None of these is built before delivery. The MVP only leaves the seam each one needs. The AWS page
explains how each would be handled in production.

| # | Candidate | What would justify it | Seam the MVP leaves | Size |
|---|---|---|---|---|
| L1 | Asynchronous processing behind a queue (for example SQS with a DLQ) | Real volume (about 50,000 receipts a day), retries when the model is down | Validation is one pure function from a receipt plus an explicit cross-receipt context to a result. The batch CLI only loops over it. MEAL-01 (per employee per day) and HEALTH-01 (per trip) span receipts, so their aggregates are an explicit input, never hidden batch state | M, 1–2 days. The cost is in the cross-receipt rules, not the queue |
| L2 | Authentication in front of the viewer or API | Leaving localhost, or real employee data | The viewer reads results through a single read-only module. No auth code is written | S–M |
| L3 | An API and a sturdier UI replacing Streamlit (Ledgerline mockups) | More than one reviewer, or auditors needing to record decisions | The viewer depends only on the output schema (typed models exported as JSON Schema), never on pipeline internals | L, 2–4 days |
| L4 | Auditor overrides, with a human in the loop | Real reviewers | Needs L2 and L3. Overrides are recorded as a score in Langfuse | M |
| L5 | Versioned policies: a new policy is a deployment with tests | The first policy change | Every result already records `rules_version` | S |
| L6 | Timing rules TIME-01 to TIME-04, and receipts RCP-020, RCP-021, RCP-029 and RCP-030 (a stretch goal in the brief) | Time left, or the panel asks | The same cross-receipt context as L1 | M |
| L7 | Observability of the parts that call no model (engine, retriever, viewer, infrastructure), the ADR that CLAUDE.md rule 11 defers | Running as a service | Each component already has its own span in the receipt's trace | S |
| L8 | Recipient abuse controls (ADR 0001, Q3): verify named recipients against a CRM, add a review signal for restricted items justified only by recipient text, track per-employee gift patterns, sample approved gifts | The panel's answer to Q3, or real employees' receipts | The recipient fields are closed classifier outputs (A9). The engine reads them in one place per rule (`domain/engine/rules/gifts.py`) | M |

**Why they wait.** None of them is needed for the brief's tests or for the evaluation, and the
calendar leaves about two working days. Building them early would mean speculative abstractions
(principle XI). Leaving their seams keeps each one cheap to add later.
