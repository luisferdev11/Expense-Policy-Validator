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

## Next: starter prompt for the Spec Kit session

The first message of the next session, prepared here so the context carries over:

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
   artifacts with Spanish conversation, decisions recorded before implementation). Add whether we
   work test-first only after we discuss it in step 4.
3. /speckit-specify for the whole system (normaliser, classifier, retriever, engine, reporter,
   eval, viewer v1 in Streamlit), using docs/decisions/. Labels firewall: never read labels,
   line_items[].labels or notes outside eval/. Then /speckit-clarify.
4. Architecture discussion, before /speckit-plan. Present two or three options with trade-offs
   (for example: a plain Python package with a batch CLI; ports-and-adapters around a pure engine;
   a pipeline of typed stages with a cache layer). Cover: module boundaries and typed interfaces
   for the five components plus eval and viewer; where the cache, the FX component and the
   decision IDs live; how the LLM is isolated so the engine stays pure; the test strategy (TDD for
   the engine and loader, fixtures from the 13 synthetic engine cases and the five brief tests,
   a determinism test, contract tests for the classifier). I decide; record it in
   docs/decisions/0002-architecture.md.
5. /speckit-plan and /speckit-tasks from that decision, then /speckit-analyze (including the
   English-only check).
Log every correction in AI_NOTES.md and every important prompt in docs/ai/prompt-log.md.
```
