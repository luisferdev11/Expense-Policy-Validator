# Implementation Plan: Iteration 2, Decide on the Dev Set

**Branch**: `feat/002-decide-on-dev` | **Date**: 2026-10-09 | **Spec**: [spec.md](spec.md)

**Input**:
- the feature specification in `specs/002-decide-on-dev/spec.md`;
- the architecture in ADRs 0002 and 0003;
- the scope in `docs/roadmap.md`, iteration 2.

## Summary

Replace iteration 1's provisional choices with choices made on a frozen, Luis-reviewed dev set
of 130 synthetic items. Each choice follows a decision rule registered before it runs:
- **E14**, the model, among four pinned candidates;
- **E7**, the EXC-03 confidence source and threshold;
- **E5**, translation, on the reference model and non-English items only;
- **E15**, null-subtype parsing, offline;
- **the retriever.**

An oracle ablation inside the evaluation attributes each error on the 28 receipts to a stage.
The winners are applied through configuration (ADR 0005), the finalist runs once, and an
experiments table joins the report and the viewer.

## Technical Context

**Language/Version**: Python 3.12 with uv. The architecture is ADR 0003's layers.

**Primary Dependencies**: as in iteration 1. Statistics are hand-written and tested; no scipy.

**Storage**: local files.
- **Experiment results:** under `explorations/results/iter2/`, committed.
- **Per-variant caches:** committed, as in iteration 1.
- **Outcomes:** `outputs/eval/experiments.json`.

**Testing**: pytest, test-first for every deterministic piece: statistics, decision rules,
dev-set freezing, the parser option, oracle attribution, the experiments table. The adapters
(pins, translator) get contract tests with fake transports.

**Target Platform**: a local CLI

**Project Type**: the same as iteration 1, plus experiment scripts in `explorations/`.

**Performance Goals**: not a constraint. The dev runs are about 610 calls.

**Constraints**:
- no decision uses the 28 receipts;
- every metric carries its N;
- spend stays under USD 1.00;
- every call is traced, and tracing never gates a run;
- prompt `cls-v2` stays frozen;
- the domain stays pure.

**Scale/Scope**: 130 dev items, 4 models, 5 experiments, 28 receipts once.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Compliance | Pre | Post |
|---|---|---|---|
| I. Labels evaluation-only | The dev set is synthetic. The oracle reads answers only inside `eval/`. Experiment code never touches the receipts' answers | ✅ | ✅ |
| II. Deterministic decisions | The engine is unchanged. Each decision rule is deterministic code over committed results, with a seeded bootstrap | ✅ | ✅ |
| III. Policy text is the source of truth | No rule changes. The configuration changes cite their experiments (ADR 0005) | ✅ | ✅ |
| IV. Evidence or nothing | Unchanged | ✅ | ✅ |
| V. Decide on dev, report on test | The rules are registered and approved before any call. The 28 receipts run once per finalist | ✅ | ✅ |
| VI. Honest measurement | N, Wilson intervals, bootstrap and McNemar on every metric. Partial or failed variants are reported as such | ✅ | ✅ |
| VII. Reproducibility | Pinned endpoints and versioned prompts (`cls-v2`, `tr-v1`). Caches of literal answers are committed. Runs can be replayed offline | ✅ | ✅ |
| VIII. Separation of components | The pins and the translator are adapters. A port appears only if its experiment wins | ✅ | ✅ |
| IX. Secrets stay out | Unchanged | ✅ | ✅ |
| X. Observability | `classify-dev-item` traces with their generations, and `translate-item` generations. Scores per variant | ✅ | ✅ |
| XI. Iterative delivery | No L1–L8 item and no iteration 3 deliverable. The reporter comparison is cut | ✅ | ✅ |
| Test-first | The tasks put each test first | ✅ | ✅ |

**Gate:** pass.

## Project Structure

### Documentation

```text
specs/002-decide-on-dev/
├── spec.md, plan.md, research.md, data-model.md, quickstart.md
├── contracts/experiments-cli.md
└── tasks.md
```

### Source Code (changes only)

```text
src/expense_validator/
├── adapters/openrouter/models.py      # NEW: ModelPin for the 4 candidates (R1)
├── adapters/openrouter/classifier.py  # takes a ModelPin; reasoning and temperature per pin
├── adapters/openrouter/prompt.py      # parse(..., null_subtype_as_none) (R7)
├── adapters/openrouter/translator.py  # NEW: tr-v1, cached and traced (R6)
├── adapters/config_files.py           # reads config/pipeline.yaml (R11)
└── app/pipeline.py, app/cli.py        # apply the winners; record them in RunMetadata

eval/
├── stats.py                           # NEW: Wilson, McNemar, paired bootstrap, Brier, ECE (R5)
├── oracle.py                          # NEW: oracle ablation and attribution (R10)
├── experiments/                       # NEW: run_dev.py, retriever_check.py, decide.py (R4, R9, R12)
│                                      #   never reads data/receipts.jsonl (architecture test)
└── report.py                          # oracle section and experiments table

explorations/
├── dev_set/build_frozen.py, dev_set_v2.jsonl, FROZEN.md   # R2
├── research/experiments_plan.yaml     # registrations (R3)
└── results/iter2/                     # predictions and caches

config/pipeline.yaml                   # NEW (R11)
viewer/app.py                          # an Experiments view
docs/decisions/0005-iteration-2-decisions.md   # winners, written after the decisions
```

**Structure decision.** The experiment scripts live in `eval/experiments/`. The session's
permissions blocked new folders under `explorations/` (2026-10-09), and the scripts do evaluate
variants. They reuse the pipeline's adapters. Unlike `eval/answers.py`, they never read the
receipts' answers, and an architecture test enforces it. Their results are written by the code
to `explorations/results/iter2/`. The domain does not change.

## Delivery order (input to `/speckit-tasks`)

1. **Runs offline, possible now:**
   - statistics;
   - the parser option;
   - model pins;
   - the translator with fakes;
   - the runner;
   - the retriever check;
   - the oracle ablation;
   - `decide.py`;
   - the experiments table.
2. **Draft the registrations** for Luis's approval.
3. **Gate:** Luis finishes the label review. Then freeze the set and approve the rules.
4. **Run** E14 (4 pins), then E5, then E15 and E7 offline, then the retriever check.
5. **`decide.py`,** then ADR 0005, then apply the configuration.
6. **The finalist run** on the 28 receipts, then eval, then the viewer.

## Complexity Tracking

No violations. A `Translator` port, or an `AgreementClassifier`, is added only if its experiment
wins.
