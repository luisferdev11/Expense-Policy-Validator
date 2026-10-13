# Prompt log

The prompts that shaped the project, kept so the way the work was steered can be reviewed. Luis
writes to the assistant in Spanish. Each entry is translated faithfully into English and ends with
what came out of it. Mistakes and corrections live in `AI_NOTES.md`; decisions live in
`docs/decisions/`.

## 2026-10-07: overnight exploration run

**Prompt (written in English).** It defined six exploration packages, all written under
`explorations/`:

1. a rule inventory;
2. an input EDA and a metadata retriever;
3. a synthetic dev set and engine edge cases;
4. an evaluation study;
5. a provider spike with a model shortlist;
6. a model trial.

It set these constraints:
- an acceptance checker written beforehand, with its SHA-256 recorded, as the only definition of done;
- anti-gaming rules: no fabricated numbers, no edited labels, blocks only for external failures, with evidence;
- a labels firewall;
- a $0.50 budget with measured spend;
- no git writes;
- English everywhere;
- a morning report.

**Outcome.** All packages were done. The checker ended with 25/27 criteria passing and 2 blocked
by the expired OpenRouter key. The main finding was that the dev set does not separate the
models. PR #1.

## 2026-10-08: "Did you leave the door open for decision models?"

> Did you leave the door open for models like jev, OpenAI's Decisions, "decision 2.0" from vLLM,
> these new classifiers I'd like to explore? If not, make light changes; don't test them yet
> because you have no API key, but leave the ground ready. Also other classification
> experiments. Remind me of your final notes from this run. Then commit and push. Maybe branches,
> merged as each piece is complete, would have been the better way to work.

**Outcome.**
- The `ItemClassifier` interface and decision-model endpoints, all unverified and refused until configured.
- `experiments_plan.yaml` with experiments E1–E12.
- The branch + PR + merge workflow.
- The assistant could not find "vLLM decision 2.0" and said so.

## 2026-10-08: "Use the renewed OpenRouter key in the experiments"

> You can make commits and push what you consider necessary. You can start adding yourself as a
> co-author. I have the renewed OpenRouter key: use it and involve it in the experimentation.
> Start thinking about what we can do next. Remember we must do everything within the
> requirements we were given.

**Outcome.** PR #2 (design system) and PR #3:
- OpenRouter pinned to DeepInfra bf16, with its own spend cap;
- verification of calls against `/generation`;
- dev-set runs;
- repeatability experiment E11.

## 2026-10-08: "Log every fix in a document"

> Every time I ask you for adjustments because of something you did wrong, I need you to write it
> down in a document, to show how I use coding agents and how we resolve each part.

**Outcome.** `AI_NOTES.md` was started with 11 entries, and a standing rule was saved to the
assistant's memory so later sessions keep it.

## 2026-10-08: "What should we do next?"

> From the parts the brief mentions, what you know of the project and what we have done, what do
> you recommend we do next?

**Outcome.**
- A status table against the brief.
- A plan:
  1. Decide the ambiguities.
  2. Spec Kit.
  3. Engine with TDD.
  4. The rest of the pipeline.
  5. `eval/` on the 28 receipts.
  6. Viewer, AWS page and README.

## 2026-10-08: ambiguities, memory and versions

> OK, let's do that. When we have it, we commit and start the next session from the Spec Kit
> initialisation. I'd also like to use engram to manage memory across Claude Code sessions:
> research what it is and whether we can use it for the next stages. Without Spec Kit we still
> have to keep saving the most important prompts. And so we don't forget: we will iterate in
> versions. The brief says Streamlit, which I don't like, but the first version is fine that way;
> if there is time, we build a front end like the artifact we made. Now let's go with the
> ambiguities.

**Outcome.**
- All eight ambiguities decided by Luis: `docs/decisions/0001-policy-ambiguities.md`.
- Two of his answers opened questions for the review session:
  - **FX conversion:** which date (transaction or billing) and which rate (recorded, mid, high or low). It is built as a switch.
  - **VAT:** the field may exist in production, so it is modelled as an optional input.
- Engram was researched (`explorations/research/notes/engram.md`). The recommendation is not to adopt it before delivery, because it is a side channel around the labels firewall and is changing quickly.
- Version plan: v1 viewer in Streamlit, as the brief asks; v2 a custom front end following the Ledgerline mockups, if time allows.

## 2026-10-08: language with Spec Kit, a cleaner explorations folder, architecture first

> Before that, a few questions and maybe a small adjustment. With Spec Kit, will we keep the same
> rules, speaking Spanish while the specs are written in English? How will we make sure? Also, the
> explorations folder has everything mixed up; I'd like something cleaner. And before we start
> coding, I want us to discuss in the session the architecture we want, whether we do TDD, settle
> the architecture for the project, and of course discuss the important modules.

**Outcome.**
- The English-only rule is now enforced in three places:
  - CLAUDE.md rule 10 names every Spec Kit artifact and says the conversation stays in Spanish;
  - the constitution will repeat it;
  - `/speckit-analyze` checks it before implementation.
- `explorations/` was reorganised by type (`lib/`, `scripts/`, `notebooks/`, `dev_set/`, `policy/`, `results/`, `research/`) with an `INDEX.md`. Files were moved with `git mv`, and every data and results file is byte-identical.
- The next session holds an architecture discussion before `/speckit-plan`: architecture options, TDD, and the modules and their interfaces. The outcome goes into ADR 0002.

## 2026-10-08: OpenRouter only, decision models, Langfuse, a clearer study

> The re-run command in the notebooks no longer works, so fix every path. I won't use the other
> providers any more: I have the OpenRouter key and that is what they ask for, so we keep only
> that. That affects the experimentation: run it again under this rule, try several models and
> analyse the results, and update Langfuse (it is not running, so start it) so we have the new
> picture. Remember the approach. I'd also like jev-1.13 and gpt-6-luna-decisions as candidates,
> and to explore decision models in general (OpenRouter's decisions ranking). The normaliser needs
> an LLM, but for the use cases where decision models can help, like classification, we should
> explore them; eventually we will explore many options and must know how to decide. The
> synthetic set looks good (I haven't finished reviewing it). I didn't understand the evaluation
> study because you give the results directly. I liked the local model trial's approach, but it
> is what changes now that we use only OpenRouter.

Follow-up decisions:
- **Langfuse:** the keys in `.env` belong to this case.
- **Old runs:** archive them.
- **Models:** 10 generative models (Haiku included as a normal candidate, despite the team's
  earlier request not to use Anthropic models) and the top 5 decision models.
- **Evaluation study:** rewrite it in a pedagogical form.

**Outcome.** Three PRs:
1. OpenRouter-only refactor, the multi-provider trial archived, and the re-run command fixed
   (AI_NOTES 15).
2. The new model trial with Langfuse.
3. The rewritten evaluation study.

## 2026-10-08: make the experiments inspectable in Langfuse, show where the runs come from

> I saw the spend, but it was not recorded in Langfuse. I also can't find in the code where the
> model test runs are; I don't see them in the notebooks. We also need to review those labels:
> ask me and we check them. Then we start the other Claude session. In the Langfuse dashboard
> things don't look organised and I don't see the experiments. I think you have access to the
> Langfuse MCP, so make good use of it, so that it is easy to show the judges what we did; from
> OpenRouter I only see calls and costs. I want to open the experiment for each model, see what
> it generated, compare it with the correct answer, and see the system prompt and every step.
> Explore experiments, datasets and tracing for this. With so many calls I'm not sure how we
> will keep control of all of it.

**Outcome.**
- **Langfuse rebuilt.**
  - The prompts are versioned.
  - The dataset holds the expected outputs.
  - The experiment has one run per model.
  - Each item trace has a `classify-item` generation with input, output, reasoning, tokens,
    billed cost and the linked prompt.
  - `docs/ai/langfuse-guide.md` walks through it.
- **Langfuse MCP.** The project-data MCP server was not connected in this session (only the docs
  MCP was). Luis can add it locally with his keys.
- **Notebook 05** now shows how the runs were produced and re-runs them from the cache with no
  billed call.
- **Labels.** The 8 debatable labels were confirmed by Luis blind to model outputs
  (`explorations/dev_set/label_reviews.jsonl`).
- **AI_NOTES.** Entries 20 and 21.

## 2026-10-08: observability as a system rule

> In the system rules make it clear that everything must run on Langfuse so we have observability
> of everything, and that generated code must rely on it. In general we must have observability of
> everything. Langfuse is for the generative models; in other sessions we will explore other
> things for the rest of the solution.

**Outcome.**
- CLAUDE.md gains rule 11, "Observability of everything":
  - every model call (pipeline, eval, explorations) is traced in Langfuse;
  - code is instrumented with the Langfuse SDK from the start;
  - each trace has a defined shape;
  - the labels firewall applies to traces;
  - Langfuse never gates a run, so the panel can re-run everything without it;
  - observability for the rest of the solution is left to a later ADR.
- The starter prompt adds observability to the constitution and to the architecture discussion.

## 2026-10-08: Spec Kit session, iterative delivery

The session opened with the starter prompt below, written in English, plus three changes:

- **How we work, iteratively.**
  > We want a working, end-to-end MVP early and improve it in small, reviewable iterations. Each
  > iteration ends in a runnable system with passing tests and an updated report. Design seams
  > for likely future changes (e.g. a message queue between ingestion and validation,
  > authentication in front of the viewer, replacing the Streamlit viewer with a more robust
  > UI/API), but do not build them before their iteration: no speculative abstractions, no unused
  > interfaces beyond the seam itself.
- **Iteration scoping before specifying.** A new step proposes the MVP cut and the later
  candidates (each with its trigger, the seam it needs in the MVP and a rough size), recorded in
  `docs/roadmap.md`. `/speckit-specify`, `/speckit-plan` and `/speckit-tasks` cover iteration 1
  only. The deferred items are listed as out of scope.
- **The architecture discussion** also scores each option on evolvability: the cost of adding a
  queue, adding auth and swapping the viewer. ADR 0002 records the seams and the deferred items.
  The tasks put a thin end-to-end path first, include an "MVP done" checkpoint, and
  `/speckit-analyze` checks that no task implements a deferred item.

**Outcome.**
- Spec Kit 1.1.2 initialised with the Claude Code integration, on branch `chore/spec-kit-init`.
  A probe run in a scratch directory showed beforehand that `--force` only adds files.
- Constitution v1.0.0 has eleven principles. Whether the work is test-first is left as a TODO for
  ADR 0002.
- Iteration cut, decided by Luis and recorded in `docs/roadmap.md`. The assistant proposed it and
  recommended each of these options:
  - The MVP covers all 37 in-scope rules, with a thin path first inside the iteration.
  - The MVP normaliser does not translate; E5 decides later.
  - Queue, auth, API and the other candidates stay after delivery. Only their seams are built
    now, and the AWS page explains them.
- The UTC dates were corrected (AI_NOTES 22).
- `specs/001-mvp-end-to-end/spec.md` covers iteration 1 only. `/speckit-clarify` asked Luis four
  questions:
  - **Recipient fields.** The classifier returns them. This is the new decision A9 in ADR 0001.
  - **EXC-03 threshold.** 0.5, provisional.
  - **Keyword baselines.** Two: one through the same engine, and the legacy flagger.
  - **The 13 DRAFT engine cases.** They are fixtures from the start, and Luis reviews them
    before "MVP done".
- ADR 0002, the architecture: ports and adapters around a pure core, plus a committed
  classification cache. Luis chose it from three options. Test-first for the deterministic
  core, so the constitution is now v1.1.0.
- The plan, research (R1–R13), data model, contracts and quickstart, and 97 tasks with a thin
  path first and an "MVP done" checkpoint.

### Follow-up: "Let's resolve what you found so we can continue"

> Let's resolve what you point out so we can continue. Document the findings you mention, and do
> everything needed so we can move on to implementing the first version.

**Outcome.**
- `/speckit-analyze` had found one critical issue, two high, three medium and two low. All were
  fixed and documented in `specs/001-mvp-end-to-end/checklists/analysis.md`.
- AI_NOTES entries 23–26.
- The branch was pushed and merged through a PR, so implementation starts from `main`.

## 2026-10-09: `/speckit-implement` for iteration 1

> (Luis ran `/speckit-implement` with no further instructions, after the planning PR was merged.)

Two follow-ups during the run:

- **Permissions.** The overnight run's deny rules blocked `uv add` and edits to
  `pyproject.toml` and `uv.lock`. The assistant asked rather than change its own permissions.
  Luis removed the three rules himself ("listo, ya quité las reglas"). The firewall rule that
  blocks reading `data/receipts.jsonl` stayed.
- **Null subtype.** After the full cold run, the only disposition error came from the model
  returning `"subtype": null`. The assistant asked whether to tolerate it. Luis chose to keep the
  parser strict and decide on the dev set in iteration 2 (E15).

**Outcome.**
- Tasks T001 to T091 done, test-first for the deterministic core, ending with 233 tests.
- A thin end-to-end path came first: run, eval and view worked on two receipts. Then:
  - all 37 rules;
  - both keyword baselines;
  - the full evaluation with N and intervals;
  - the three viewer views.
- One full cold run: 78 billed calls, USD 0.003205 in total.
- Pipeline results on the 28 in-scope receipts: dispositions 27/28, macro F1 0.995 (N = 65),
  0 of 16 violations missed. The keyword baselines scored 20/28 and 16/28.
- AI_NOTES entries 27 to 34.
- Waiting for Luis: his review of the 13 DRAFT engine cases (T092), then "MVP done" (T093).

## 2026-10-09: "How do I test it, and I'm not convinced by the architecture"

> This iteration doesn't have Streamlit, or how can I test this MVP? Also, I'm not sure the
> architecture convinces me: I see .py files in expense_validator, but I don't see a structure
> that tells me it follows a specific architecture. Maybe it's just me and I haven't reviewed it
> in depth. So how do I test the application? Describe better what I need to do to move to the
> next iteration, and tell me which iterations we expect before we finish and what each
> includes.

**Outcome.**
- The viewer was confirmed to start (`uv run epv view`), with a step-by-step test guide.
- The assistant agreed with the architecture critique. Ports and adapters existed only as
  dependency rules, and two file-I/O leaks sat inside the core (AI_NOTES 35). Luis chose to
  refactor now:
  - ADR 0003 records the decision;
  - the package is layered as `domain/`, `ports/`, `adapters/` and `app/`;
  - the architecture test is stricter;
  - behaviour is unchanged, and the outputs differ only in `rules_version`.
- The assistant found a gap: the dev set labels only categories, not the A6 and A9 fields that
  cls-v2 returns.
- A blind label-review page was built so Luis could review the 101 DRAFT labels while the
  refactor ran in a separate worktree.
- The remaining plan is iteration 1.1 (the refactor), iteration 2 (decide on dev), iteration 3
  (delivery package), and Sunday for rehearsal only.

## 2026-10-09: "No more DeepInfra; everything is plain OpenRouter"

During the E14 runs, DeepInfra rate-limited gemma-3-12b (HTTP 429). Luis's instruction, translated:

```
Stop trying DeepInfra, everything is plain OpenRouter now. I'll leave the keys commented out.
```

Asked how to route, he chose OpenRouter's own routing with the serving provider recorded on every
call, and a re-run of all four E14 models under it. Recorded in ADR 0004 and E14's `amendment_2`.

## 2026-10-09: "A release per finished iteration"

```
I want a release for every finished iteration, so I can easily show how we progressed between
versions, what each one included and how we reached the final product. Focus on real progress,
we are running out of time, don't get stuck on small things.
```

Tags `v0.1.0` (iteration 1) and `v0.1.1` (iteration 1.1) were published as GitHub releases;
T031 now ends with `v0.2.0`.

## 2026-10-10: "Let us load new data, and think about what happens after a review"

Luis, translated:

```
We have an artifact that was more or less the interface proposal; with Ledgerline we could get
something very good, and it is not the last word. To show the application, let us allow loading
new data, one by one or in batches. We need to know how we face this, it is a backend matter,
the event-related idea we talked about: an order can be saved even though the user gets an error.
If they retry, do we create another order? Do we show the existing one? Do we know where the
operation stopped? Also: if receipts are sent to review, what does the user get, what happens
after we classify, or after a review? Use this session to define these parts; another session
starts from that plan.
```

The answers (revisions for a changed receipt, re-evaluation of affected receipts, four reviewer
actions, Streamlit intake first, then the backend with Postman collections, then the front)
are in ADR 0006 and `docs/plans/2026-10-10-product-plan.md`.

## 2026-10-10: "Move on to the next iteration; this one must be clean"

Luis, translated:

```
We closed 2.1, I think, because I have merged. I want you to move on to the next iteration. This
one is very important. It has to end clean, with good software engineering practices.
```

The assistant tagged v0.2.1, consulted the advisor model before starting, and ran the whole Spec
Kit cycle on branch `feat/004-backend-lifecycle`. The advisor's plan: vertical slices that each end
green and committed, ADR 0007 before any code, parity with `epv run` by construction (one decision
step shared by the batch run and the worker), the cascade without touching the engine, the
labels firewall stated before `/speckit-specify`.

The `/speckit-specify` prompt, which states the firewall as the parent `CLAUDE.md` requires:

```
Iteration 3 (release v0.3.0): the intake and lifecycle backend. LABELS FIREWALL (rule 1):
data/receipts.jsonl contains the correct answers (labels, line_items[].labels, notes). Do NOT read
that file and do not load it into context; only code under eval/ may read labels. Everything the
backend stores, returns or traces is the stripped ReceiptInput (via parse_receipt_line); the
idempotency hash is computed on the stripped canonical form. Build from ADR 0006 and the product
plan. Scope: SQLite append-only event store with projections and an outbox; FastAPI `epv serve`
and a separate `epv worker`; persist-first idempotent POST /receipts and POST /batches; revisions;
stage-by-stage resume with leased outbox claims; cascade re-evaluation using build_context
unchanged; the lifecycle state machine; four reviewer actions; Langfuse auditor_agreement scores
(best effort); a Postman collection. Success criteria: the 32 receipts through the API equal
`epv run`; the same POST twice is one receipt and one processing; a crashed worker resumes with
zero extra billed calls; outcomes do not depend on arrival order. The engine's decisions must not
change (alert Luis before any engine change).
```

## 2026-10-12: prompt `dec-v1`, the decision payload for jev (iteration 6, spec 007)

`dec-v1` is the prompt a *decision model* (jev, `typesafe/jev-1.13`) receives. It is not a chat
prompt: OpenRouter's decisions endpoint (`POST /api/alpha/decisions`) takes a `state` (the item
text, the merchant, the MCC as a string) and `questions`, each with `instructions` and a closed
`criteria` map from option to description, and answers with a `choice`, a probability per option and
a `confidence`. Questions are answered in isolation, so everything the model needs is in the
instructions and the criteria. It returns a category only: no subtype and no recipient.

The instructions, verbatim (they are the E13 text, moved into
`src/expense_validator/adapters/openrouter/decision_prompt.py`):

```
Choose the spend category of one line item from an expense receipt. The state gives the item text
exactly as printed (it may be in English, Spanish, French, German, Portuguese or Japanese), the
merchant name and the merchant category code (MCC). Classify what the item IS, not the words in its
name: food cooked with alcohol (beer-battered fish, rum cake, wine sauce) is food_beverage;
non-alcoholic drinks and mocktails are food_beverage; cooking wine is alcohol; barware and
drinkware are household_goods. Accessories made for a personal device (cases, chargers) are
personal_electronics; non-electronic watches are jewelry. Mobile phones, prescription medication and
event tickets have no category of their own: choose other. A charge with unknown contents is other.
```

The criteria are the 21 categories of `data/category-taxonomy.md`, each with the example text of its
table row, generated from the package taxonomy (so the options never drift from the engine's).

Why it exists: jev classified 130 of 130 dev items on 2026-10-11 against 123 of 130 for
`gpt-oss-120b`, but cannot return a subtype or a recipient (A6, A9). The prompt was written for
experiment E13, used unchanged in the demonstrative run of 2026-10-11, and is the one experiment
E16 and the hybrid classifier use. A test (`tests/fixtures/dec_v1_payload.json`, captured once
from `explorations/lib/decision_adapters.py`) proves the moved payload equals the one those runs
sent, so their evidence stays valid. It is synced to Langfuse Prompt Management as
`classify-item-decision`, label `dec-v1`.

## 2026-10-12: "Implement spec 006, API hardening, test first"

The implementation session of iteration 6, slice 006, started from a written directive (the specs
were written in an earlier session, `specs/006-api-hardening/`). The directive, translated:

```
Implement spec 006 (api-hardening, release v1.1.0) in its own worktree on feat/006-api-hardening.
Use the Spec Kit skill speckit-implement and follow tasks.md exactly, test first, ticking each task.
Keep the documents current: if reality differs from spec, plan, research or contracts, edit them in
the same commit with a one-line reason. Rules: English everywhere; small Conventional Commits; ruff,
mypy and pytest green before every commit; never --no-verify; labels firewall; no key is read or
printed; no Anthropic models; the policy engine's decisions must not change (stop and tell me if
they must). Record every mistake or deviation in a notes draft, not in AI_NOTES.md. No billed model
call: use the simulated or keyword classifier. Push the branch when green; do not open the PR.
```

Follow-ups, translated: a note that spec 007 bumps the version lines to 1.2.0, so the change to
those lines had to stay minimal; a restart of the machine in the middle of the `peak` load run (the
partial run was discarded and the three profiles were rerun on committed code, so no report comes
from a killed run).

## Starter prompt for the Spec Kit session, as prepared

The first message of the Spec Kit session, prepared in the previous session so the context
carries over. The entry above lists what changed when it was sent:

```markdown
We continue the Oversight take-home (Expense Policy Validator). Talk to me in Spanish; every
artifact you write (constitution, specs, plans, tasks, code, docs, commits) is in English.
Read first: CLAUDE.md, ../CLAUDE.md, AI_NOTES.md, docs/decisions/0001-policy-ambiguities.md,
docs/ai/prompt-log.md and explorations/INDEX.md.

Today we set up the spec-driven flow and decide the architecture before any code:
1. Spec Kit. On a new branch, check `specify init --help`, then run
   `specify init --here --force --integration claude` (older versions: `--ai claude`). Review the
   diff, commit, and tell me to restart the session so the /speckit-* skills load.
2. After the restart: /speckit-constitution, from the strategy draft (deterministic engine, labels
   evaluation-only, policy text as source of truth, evidence or nothing, decide on dev / report on
   test, honest measurement, reproducibility, separation of components, secrets out, English
   artifacts with Spanish conversation, decisions recorded before implementation, observability of
   every model call in Langfuse per CLAUDE.md rule 11). Add whether we work test-first only after
   we discuss it in step 4.
3. /speckit-specify for the whole system (normaliser, classifier, retriever, engine, reporter,
   eval, viewer v1 in Streamlit), using docs/decisions/. Labels firewall: never read labels,
   line_items[].labels or notes outside eval/. Then /speckit-clarify.
4. Architecture discussion, before /speckit-plan. Present two or three options with trade-offs
   (for example: a plain Python package with a batch CLI; ports-and-adapters around a pure engine;
   a pipeline of typed stages with a cache layer). Cover: module boundaries and typed interfaces
   for the five components plus eval and viewer; where the cache, the FX component and the
   decision IDs live; how the LLM is isolated so the engine stays pure; how every model call is
   traced in Langfuse (one trace per receipt, one span per component, one generation per call)
   without Langfuse ever gating a run; the test strategy (TDD for
   the engine and loader, fixtures from the 13 synthetic engine cases and the five brief tests,
   a determinism test, contract tests for the classifier). I decide; record it in
   docs/decisions/0002-architecture.md.
5. /speckit-plan and /speckit-tasks from that decision, then /speckit-analyze (including the
   English-only check).
Log every correction in AI_NOTES.md and every important prompt in docs/ai/prompt-log.md.
```
