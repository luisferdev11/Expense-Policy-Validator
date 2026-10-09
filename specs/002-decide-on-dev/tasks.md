---

description: "Task list for iteration 2, decide on the dev set"
---

# Tasks: Iteration 2, Decide on the Dev Set

**Input**: `specs/002-decide-on-dev/`: plan.md, spec.md, research.md (R1–R13), data-model.md,
contracts/experiments-cli.md and quickstart.md.

**Tests**: Requested. Constitution v1.1.0 makes test-first mandatory for every deterministic
piece. Adapters get contract tests with fake transports.

**Standing rules**:
- **Labels firewall.** Only `eval/` reads the receipts' answers.
- **The 28 receipts.** They never inform a choice.
- **Commits.** Small Conventional Commits; `exp:` for experiment results.
- **AI_NOTES.** Each assistant mistake gets an entry in the same commit as its fix.
- **Language.** Everything written is in English.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

- [X] T001 Create the folders `eval/experiments/` and `explorations/results/iter2/`, each with a README line saying what it holds

## Phase 2: Foundational (offline pieces, test-first)

- [X] T002 [P] Write `tests/unit/test_stats.py` with hand-computed values:
  - Wilson 1/9 is about [0.0199, 0.4350];
  - McNemar's exact two-sided p for b=1, c=6 is 0.125;
  - the paired bootstrap of a known difference is deterministic for a fixed seed, and its CI contains the observed difference;
  - the Brier score of perfect predictions is 0;
  - ECE over 10 bins on a hand example;
  - the coverage-accuracy points are monotone in coverage.
- [X] T003 Implement `eval/stats.py` (R5). Move `wilson` there and re-export it from `eval/metrics.py`
- [X] T004 [P] Extend `tests/contract/test_prompt_schema.py`:
  - `parse` of an answer with `"subtype": null` raises `ParseError` by default;
  - it returns `subtype == "none"` with `null_subtype_as_none=True`;
  - every other violation still raises in both modes.
- [X] T005 Implement the `null_subtype_as_none` parameter in `src/expense_validator/adapters/openrouter/prompt.py`, and thread it through `OpenRouterClassifier` (default False) (R7)
- [X] T006 [P] Write `tests/contract/test_model_pins.py`, using a fake transport, so that:
  - each of the 4 pins sends its model, the order `[deepinfra/bf16]` and temperature 0;
  - Qwen sends `{"reasoning": {"enabled": false}}`;
  - Gemma sends no reasoning field;
  - the gpt-oss pins send effort `low`;
  - cache keys differ per pin and are unchanged for the reference (the 78 committed rows still hit).
- [X] T007 Implement `src/expense_validator/adapters/openrouter/models.py` (`ModelPin`, `PINS`, `REFERENCE`) and make `OpenRouterClassifier` take `pin: ModelPin = REFERENCE` (R1)
- [X] T008 [P] Write `tests/contract/test_translator.py` with a fake transport:
  - prompt version `tr-v1`;
  - the output is plain text, stripped;
  - the result is cached and a second call is a hit;
  - one `translate-item` generation per billed call;
  - a gateway error returns None and the caller falls back to the original text.
- [X] T009 Implement `src/expense_validator/adapters/openrouter/translator.py` (R6) with its own cache file path argument
- [X] T010 [P] Write `tests/unit/test_build_frozen.py` on a temporary copy:
  - it refuses while any item is unreviewed;
  - it applies the reviewed category, subtype and recipient;
  - unproposed A6/A9 fields default to `none`, `none` and null;
  - it writes the SHA-256 of `dev_set_v2.jsonl` to `FROZEN.md`;
  - it is deterministic.
- [X] T011 Implement `explorations/dev_set/build_frozen.py` (R2, data-model "Frozen dev item")
- [ ] T012 [P] Write `tests/unit/test_dev_runner.py` with a fake classifier. The runner:
  - refuses without an approved registration, and refuses a hash mismatch;
  - writes one prediction row per item, with every field in the data model;
  - replays offline from the cache;
  - opens one `classify-dev-item` trace per item.
- [ ] T013 Implement `eval/experiments/run_dev.py`, using the pipeline normaliser, request builder, `OpenRouterClassifier(pin)`, per-variant caches and the tracer (R4)

**Checkpoint**: every offline piece is tested. No model call has been made.

## Phase 3: User Story 1, A trustworthy dev set (P1)

- [ ] T014 [US1] Draft every registration in `explorations/research/experiments_plan.yaml` (R3):
  - **E14 amendment:** cls-v2, 4 pins, all 130 items, the 2-point margin on category accuracy, and secondary minimums on subtype, recipient and restricted F1;
  - **E7:** Brier, then the threshold rule from R8;
  - **E5:** on non-English items, translate wins only if its category accuracy is higher by McNemar p < 0.05 and the bootstrap lower bound is > 0. Otherwise keep the simpler option;
  - **E15:** tolerate null only if it changes no correct answer to a wrong one, and fixes at least one;
  - **retriever:** keep the trigger map if 0 outcome differences, else investigate.

  Each entry has `approved_by: null` until Luis approves.
- [ ] T015 [US1] **GATE, Luis.**
  1. Luis finishes the blind review of all 130 items in the review page.
  2. The assistant commits `label_reviews.jsonl` and runs `build_frozen.py`, then commits `dev_set_v2.jsonl` and `FROZEN.md`.
  3. Luis approves or edits each registration; the assistant sets `approved_by`, `registered_at` and the `data` hash.

  Commit before any experiment call (SC-001, SC-002).

## Phase 4: User Story 2, Choices made on dev (P1)

- [ ] T016 [US2] Run E14: `run_dev.py --experiment E14 --variant` for each pin, starting with the reference. Commit the predictions and caches with an `exp:` commit that records the calls, spend and failures
- [ ] T017 [US2] Run E5: `run_dev.py --experiment E5 --variant translate` on the non-English items with the reference pin. Commit with an `exp:` commit
- [ ] T018 [P] [US2] Write `tests/unit/test_decide.py` on synthetic predictions:
  - each registered rule picks the expected winner, including the "nothing qualifies, keep the reference" case;
  - E15 is computed by re-parsing the raw answers;
  - E7 picks the lower Brier score and its threshold by R8;
  - the output matches the data model "Experiment outcome".
- [ ] T019 [US2] Implement `eval/experiments/decide.py` (R12), which writes `outputs/eval/experiments.json` deterministically
- [ ] T020 [P] [US2] Implement `eval/experiments/retriever_check.py` (R9). Its result feeds `decide.py`
- [ ] T021 [US2] Run `decide.py`. Commit `outputs/eval/experiments.json` with an `exp:` commit that summarises each winner and margin

## Phase 5: User Story 3, Know where errors come from (P2)

- [ ] T022 [P] [US3] Write `tests/unit/test_oracle.py` on synthetic rows. Attribution maps:
  - (pipeline wrong, oracle right) to `classification`;
  - (both wrong) to `rule_logic_or_convention`;
  - (pipeline right, oracle wrong) to `right_for_wrong_reason`;
  - (both right) to `none`.

  The oracle classifier builds a confidence-1.0 classification with subtype and recipient `none`.
- [ ] T023 [US3] Implement `eval/oracle.py` (R10) and add the oracle section to `eval/report.py`. The section shows accuracy with N and an interval, the rows with their stage, and the stated limitation

## Phase 6: User Story 4, Apply the winners and report once (P2)

- [ ] T024 [US4] Write `docs/decisions/0004-iteration-2-decisions.md` from `outputs/eval/experiments.json`: each winner, its margin, and the configuration it sets
- [ ] T025 [P] [US4] Write a test that `adapters/config_files.py` reads `config/pipeline.yaml` (`classifier_model`, `confidence_source`, `translate`, `null_subtype_as_none`). `RunMetadata` records `confidence_source`, `pipeline_config_version` and `exc03_threshold_status == "chosen_on_dev"`
- [ ] T026 [US4] Implement `config/pipeline.yaml` and its reading. Wire the settings through `app/cli.py` and `app/pipeline.py`. Set `exc03.threshold` in `policy_decisions.yaml` to E7's value, with status `chosen_on_dev`.
  - **Only if E5 won:** add a `Translator` port and the pipeline step.
  - **Only if agreement won E7:** add an `AgreementClassifier` adapter.

  Each conditional piece comes with its own tests first.
- [ ] T027 [US4] Finalist run: `uv run epv run` (once), `uv run epv run --classifier keyword`, `uv run epv eval`. Commit the outputs with an `exp:` commit that records the model, config, spend and 28-receipt results
- [ ] T028 [US4] Add the experiments table to `eval/report.py`, and an "Experiments" view to `viewer/app.py`, both from `experiments.json`. Extend `tests/smoke/test_viewer.py` to cover the new view

## Phase 7: Polish and checkpoint

- [ ] T029 [P] Update `AI_NOTES.md` with this iteration's mistakes, and `docs/ai/prompt-log.md` with its prompts
- [ ] T030 [P] Update `docs/roadmap.md`: iteration 2 exit criteria ticked, with evidence
- [ ] T031 **Decide-on-dev done:** run every scenario in `specs/002-decide-on-dev/quickstart.md`, then run `uv run pre-commit run -a` and `uv run pytest`. Open the PR with a pass list per scenario, and merge it

## Dependencies

- Phase 2's pieces are independent and can run in parallel; each pairs a test with its implementation.
- **T015 (the gate)** blocks every model call (T016, T017).
- T018–T021 need T016 and T017. T023 can start any time.
- T024–T028 need T021. T031 comes last.

## Implementation Strategy

1. **Phase 2 first, while Luis reviews.** Build everything offline.
2. **The gate.** Luis's approvals and the freeze.
3. **The runs** (cents), then the decisions applied mechanically.
4. **The finalist runs once,** then the report and the checkpoint.

**Out of scope:** iteration 3 deliverables, L1–L8, decisions on Q1–Q3, and the LLM reporter
comparison, which was cut.
