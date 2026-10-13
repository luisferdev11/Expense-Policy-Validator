# Expense Policy Validator

Reads itemized expense receipts, classifies every line item, applies nine written expense
policies with a **deterministic rule engine**, and raises exceptions that cite the policy text,
with a final disposition of `flag`, `review` or `pass`. Scored on the 28 in-scope receipts.

**Versions.** The tag **`v1.0.0` is the stable delivery**: everything the brief asks for, plus
the API and the React front end of v0.3.0 and v0.4.0. `main` adds iteration 6 (v1.1.0 to v1.3.0,
specs 006 to 008): an answer table instead of a cache file, typed OpenAPI, a load test, the jev
classifier in shadow mode and a guided intake form. It is tested but has been used less. The
engine, the results and every number below are the same in both.

```bash
uv sync && cp .env.example .env     # OPENROUTER_API_KEY only to classify new lines; LANGFUSE_* optional
uv run epv run --offline            # rebuilds outputs/results.jsonl from the committed cache: no key, no model call
uv run epv eval                     # every number below, from committed outputs, no model call
uv run epv view                     # the viewer (Streamlit): receipt list, detail with exceptions, metrics
uv run pytest                       # 844 tests on main (562 at v1.0.0); ruff and mypy are clean
```

Optional, beyond the brief: `uv run epv serve --with-worker --offline` (API on port 8000), then
`cd frontend && npm install && npm run dev` (application on port 5173).

## Architecture

Five components, each in its own module behind a typed interface:

- **Normaliser**: deterministic cleanup. The classifier reads the original language.
- **Item classifier**: an LLM, and the only model call.
- **Policy retriever**: a trigger map over items, MCC and metadata.
- **Policy engine**: plain Python.
- **Exception reporter**: a template, so the explanation is the computation.

The package is layered (`domain` pure, `ports`, `adapters`, `app`), and a test enforces the
imports. The model only says what an item *is*; the rules and the receipt decide whether it is
allowed. Answers are cached by description, merchant, MCC, model and prompt, so re-runs are free
and byte-identical. Every result records the model, serving provider, prompt and rules version.
Every model call is traced in Langfuse, which never gates a run. The labels are evaluation-only:
one loader strips them and a test scans the code.

Beyond the brief, an HTTP API with a worker (idempotent intake, a review lifecycle) and a React
front end decide nothing on their own; they call the same engine. Decisions are in
`docs/decisions/` (ADRs 0001 to 0010), the plan in `docs/roadmap.md`, the AWS design in
`docs/aws.md`.

## Prompts

There is one prompt, `cls-v2`. It is a system prompt built from the taxonomy that says to
*classify what the item is, not its words*: "beer-battered cod" is food, "cooking wine" is
alcohol. It also asks for a closed `subtype` for `other` and for the recipient the line itself
names.

- **Strict JSON schema, temperature 0.** The engine reads closed values, so it needs them exact.
- **The model sees only the cleaned text, merchant and MCC**, never the declared type or the
  attendee count.
- **Confidence is the model's own.** In E7 its Brier score was 0.036, against 0.063 for a
  120b/20b agreement score.
- **Translation was tested and dropped** (E5): 55/56 in the original language against 54/56
  translated, McNemar p = 1.0.

Every prompt version is in `docs/ai/prompt-log.md`.

## Policy engine

All 37 in-scope rules are pure functions over the classified receipt and an explicit
cross-receipt context (meals per employee-day, OTC per trip). Each rule is registered with its
severity, its policy document and the **literal policy sentence**, which a test checks verbatim.

- **Thresholds.** Amounts are converted with the receipt's own rate.
- **Carve-outs.** One applies only if its evidence is recorded.
- **Regional overrides.** The regional addendum overrides global rules by entity.
- **Disposition.** EXC-01 exactly: any critical, high or medium exception flags; a low one or a
  signal reviews.

The policy ambiguities were decided by hand and are in ADR 0001.

**EXC-03 threshold: 0.97.** It was chosen on a frozen 130-item synthetic dev set, where it fires on
7 of 128 items. On the scored receipts it fires 0 times.

Tests: the brief's five cases, 13 synthetic engine cases, determinism and the labels firewall.

## Evaluation summary

28 scored receipts and 65 line items. Every figure and its interval is in
`outputs/eval/report.md`.

| | pipeline | keyword classifier | keyword flagger |
|---|---|---|---|
| Macro F1 / restricted F1 (N = 65) | 1.000 / 1.000 | 0.709 / 0.703 | n/a / 0.703 |
| Disposition correct (N = 28) | 28 (95 % CI 87.9 to 100) | 20 | 16 |
| False positives, of 9 that should pass | 0 (CI up to 29.9 %) | 2 | 2 |
| Missed violations, of 16 that should flag | 0 | 5 | 7 |

**What the scores say about the engine's inputs.**

- **Macro F1 matters more.** It weighs every category equally, so 1.000 means even the rare
  categories the rules key on reach the engine right: `personal_electronics` for TECH-01,
  `computer_accessory` for TECH-02, `laundry_service` for LAUNDRY-01.
- **Restricted F1 is coarser.** It only says no restricted item slips through as ordinary spend.
  The engine needs the exact category (DOC-03, TECH-02 and the meal rules), so restricted F1 alone
  would not show whether the engine gets what it needs.

The baselines do better on nothing measured.

**Reading the perfect score.** N is small, the model was chosen on the dev set (E14: gpt-oss-120b
123/130, restricted F1 0.991), and the 28 receipts ran once per finalist. An oracle ablation
attributes the only difference to a limitation of the labels (RCP-022).

**Failure cases.** RCP-007 (iteration 1) and RCP-012 (first pass of iteration 2) both failed at the
classification stage:

- RCP-007: a strict parser turned one malformed answer into a review.
- RCP-012: a provider returned confidence 0.

Details are in the report.

**Base rate.** More than half of this dataset violates policy; a real stream has a few percent. So
0 of 9 false positives says little. At 3 % prevalence and the interval's upper bound (29.9 %),
10,000 receipts give about 2,900 false flags against 300 true ones, so 91 % of flags would be
false. Before production I would measure the false-positive rate per rule on a realistic labelled
sample, and the review workload it creates.

## AI collaboration

- **Who did what.** Claude Code (Sonnet and Opus) wrote most of the code, tests and ADRs under
  Spec Kit. An advisor model reviewed the work at key points. The Langfuse MCP inspected traces.
- **Record of mistakes.** `AI_NOTES.md` has 100 entries, each with how it was caught and what
  changed.
- **Three examples:**
  1. The assistant blamed the EXC-03 threshold for RCP-012 without checking the line's
     confidence, which was 0. The cause was a provider.
  2. A test double raised on a model outage, but the real adapter returns an unclassified line. An
     outage would have sent unclassified receipts to a person. The advisor review caught it.
  3. The first cache dropped answers that broke the schema, so an offline replay was not
     byte-identical. It was caught inspecting unclassified lines before committing the outputs.
- **Checked by hand:** the policy ambiguities, all 130 dev labels (blind to model output) and the
  13 synthetic engine cases.

## Spend and data

**Model.** `openai/gpt-oss-120b` through OpenRouter. It won E14 on the dev set and costs about
USD 0.061 per 1,000 items. gpt-oss-20b is half the price and one item behind, and the dev set is
too small to separate them. In iteration 6, E16 found a jev-1.13 plus gpt-oss hybrid superior on
the dev set (130/130, p = 0.0156) at USD 0.103 per 1,000 items. It runs only in shadow; switching
needs an ADR.

**Spend recorded in the repository:** about **USD 0.15** of the USD 5 cap. A full cold run of the
32 receipts is 78 calls and USD 0.004. The OpenRouter dashboard is the authority.

**Who received data (all synthetic):**

- OpenRouter and the providers it routes to (`data_collection: deny`) got only cleaned line text,
  merchant and MCC. Early exploration also called DeepInfra and Groq the same way.
- jev-1.13, through OpenRouter, got dev-set lines.
- Claude Code saw the repository, the policies and the receipts without answers.
- Langfuse runs locally.

## One receipt, end to end (RCP-014)

1. The loader strips the answers. The receipt has four lines, MCC 5411 (a supermarket), declared
   "Office Supplies".
2. The classifier reads three household items as `household_goods` and "Cooking wine, Marsala" as
   `alcohol`, from cache (0 calls).
3. The engine raises **ALC-03** (high: alcohol outside a restaurant, bar or hotel is never
   reimbursable), plus **HOUSE-01** and **DOC-03** (medium).
4. EXC-01 gives `flag`.

Each exception carries its rule, lines and policy sentence in `outputs/results.jsonl`.

## What I would do next

1. **A larger, blind-reviewed dev set (500+ items).** Then decide on shadow data whether the
   jev hybrid is worth its higher cost, in an ADR.
2. **Retries for bad answers.** Retry schema violations, and treat a "confidence 0, no reasoning"
   answer as a failure instead of keeping a provider blocklist.
3. **Recipient-abuse controls** (ADR 0001, Q3): catch a gift justified only by what the line says.
4. **Before production:** roles and authentication (designed in ADR 0010 and spec 009), automatic
   retries with backoff, and data retention (`docs/aws.md`). Then the four timing rules.
