# Phase 0 Research: Iteration 2, Decide on the Dev Set

The architecture is ADR 0003 (domain, ports, adapters, app). Each decision below has its
rationale and the alternatives considered.

## R1. Model pins for E14, generalising the OpenRouter adapter

- **Decision:** `adapters/openrouter/models.py` defines a `ModelPin` for each candidate: model ID,
  endpoint, reasoning setting, and whether temperature is sent. `OpenRouterClassifier` takes a
  pin, defaulting to the reference.

  | Model | Endpoint | Reasoning | Temperature |
  |---|---|---|---|
  | `openai/gpt-oss-120b` | `deepinfra/bf16` | low | 0 |
  | `openai/gpt-oss-20b` | `deepinfra/bf16` | low | 0 |
  | `qwen/qwen3.5-9b` | `deepinfra/bf16` | off (`{"enabled": false}`, as in the E13 deviation) | 0 |
  | `google/gemma-3-12b-it` | `deepinfra/bf16` | not sent (unsupported) | 0 |

  The pins come from `explorations/research/openrouter_pins.json`.
- **Rationale:** the adapter that serves the pipeline is the one that runs the experiment
  (FR-010). The cache-key formula is unchanged (model and endpoint are already in it), so the 78
  cached rows stay valid.
- **Alternatives:** reusing `explorations/lib/run_trial.py`. Rejected: that is cls-v1 code, not
  the pipeline's.

## R2. The frozen dev set

- **Decision:**
  - After Luis's review, `explorations/dev_set/build_frozen.py` writes
    `explorations/dev_set/dev_set_v2.jsonl`. Each item holds its reviewed category, restricted
    flag, subtype, recipient kind and recipient name. Unreviewed A6/A9 fields default to `none`,
    `none` and null.
  - `explorations/dev_set/FROZEN.md` records its SHA-256 and the date.
  - All 130 items decide (clarification). The draft file stays as history.
- **Rationale:** labels the runner can read without merging reviews at run time; a hash that a
  test can check.

## R3. Registering the decisions

- **Decision:** entries in `explorations/research/experiments_plan.yaml`, each with:
  - `id`, `factor`, `variants` and `held_fixed`;
  - `metrics` and `decision_rule`;
  - `approved_by`, `registered_at` (local date) and `amendments`.

  They are drafted by the assistant, approved by Luis, and committed before the first call
  (SC-002). E14 gets an amendment, made before it runs: cls-v2, the four candidates, all 130
  items.

## R4. The dev-set runner

- **Decision:** `explorations/experiments/run_dev.py` runs one variant over the frozen set. Each
  run:
  - uses the pipeline's normaliser, request builder and `OpenRouterClassifier`;
  - writes to a per-variant cache, `explorations/results/iter2/cache/<variant>.jsonl`;
  - opens one Langfuse trace per item (`classify-dev-item`, holding the `classify-item`
    generation);
  - writes `explorations/results/iter2/<experiment>/<variant>.jsonl` with one prediction per item,
    including the raw cached answer.

  Langfuse is used through the tracer port, so it never gates a run. The experiment scores are
  posted as trace scores with the variant name.
- **Rationale:** the same code path as the pipeline, an offline replay from the cache, and
  inspectable traces.
- **Alternatives:** Langfuse's dataset experiment API. It is optional, and verified at
  implementation; scores on tagged traces are the fallback, so Langfuse never gates.

## R5. Statistics

- **Decision:** a pure module, `eval/stats.py`:
  - Wilson 95 % intervals (moved from `eval/metrics.py`, re-exported there);
  - McNemar's exact test (binomial on the discordant pairs);
  - a paired bootstrap of an accuracy difference, with 10,000 resamples and a fixed seed;
  - Brier score, ECE over 10 bins, and the coverage-accuracy curve.

  Each is tested against hand-computed values.
- **Rationale:** the methods of the evaluation study notebook, ported and tested, with seeded
  determinism.

## R6. E5, translation

- **Decision:** `adapters/openrouter/translator.py`:
  - prompt `tr-v1`: "translate this expense line to English; output only the translation";
  - plain text, with the same pin as the reference, a cache and a traced generation
    (`translate-item`).

  The variant classifies the translated text with cls-v2. It runs only on non-English items
  (clarification).
  - **If E5 wins,** a `Translator` port is added and the pipeline gets the step (ADR 0004).
  - **If it loses,** no port is added. The constitution forbids unused interfaces.

## R7. E15, null subtype

- **Decision:** `parse(content, null_subtype_as_none=False)`. E15 is evaluated offline by
  re-parsing every cached raw answer from E14's reference run under both settings: no new calls.
- **Rationale:** the cache keeps literal answers (AI_NOTES 30), which makes this experiment free.

## R8. E7, confidence

- **Decision:**
  - **Sources.** Self-reported confidence comes from the E14 reference run. Agreement is 1 when
    120b and 20b give the same category, and 0 otherwise; it also comes from E14 runs, with no
    new calls.
  - **Metrics.** Brier score, ECE and the coverage-accuracy curve.
  - **Rule (proposed).** Pick the source with the lower Brier score. Then pick the highest
    threshold whose coverage-accuracy point keeps the accuracy of the items kept ≥ the
    reference's overall accuracy while sending ≤ 10 % of correct items to review. Ties go to the
    lower threshold.
  - **If agreement wins,** the pipeline adds an `AgreementClassifier` adapter that composes two
    classifiers: confidence is 1.0 when they agree, 0.0 when they do not, and EXC-03 fires on
    disagreement.

## R9. The retriever comparison

- **Decision:** `explorations/experiments/retriever_check.py` runs the engine with the trigger
  map and with every rule. It covers the 13 engine fixtures and the 32 receipts, using cached
  classifications (inputs only, no labels), and counts the differences.
- **Rationale:** it decides on fixtures, not scores. Outcomes are compared, never answers.

## R10. The oracle ablation

- **Decision:** `eval/oracle.py` builds an `OracleClassifier` from the answers, inside `eval/`
  only:
  - the answer's category and restricted flag;
  - confidence 1.0;
  - subtype and recipient `none`, because the answers do not label them. This limitation is
    stated in the report.

  It runs the same pipeline code over the 28 receipts. Attribution per receipt:
  - pipeline wrong and oracle right gives **classification**;
  - both wrong gives **rule logic or retrieval**. The retriever is a proven superset, so it is
    rule logic, or a convention gap;
  - pipeline right and oracle wrong gives "right for the wrong reason".

## R11. Applying the winners

- **Decision:** ADR 0004 records each winner. Settings live in two places:
  - **`config/pipeline.yaml`**, read by `adapters/config_files.py`: the classifier pin, the
    confidence source, translation on or off, and the null-subtype parsing;
  - **`policy_decisions.yaml`**: `exc03.threshold`, with its status `chosen_on_dev`, carried
    into `RunMetadata`.
- **Rationale:** a setting change is a configuration change, recorded with its experiment.

## R12. The experiments table

- **Decision:** `explorations/experiments/decide.py` applies each registered rule to the
  committed results. It writes `outputs/eval/experiments.json` with, for each experiment:
  - the factor and variants, and the rule;
  - the metrics with N and intervals;
  - the winner, the margin, and why the others lost;
  - the spend.

  The report and a fourth viewer view render it. The file is re-derivable with no model call
  (SC-004).

## R13. Spend

- **Estimate:** about 520 calls for E14 (4 × 130) and about 90 for E5, at USD 0.00002–0.00005
  each. Under USD 0.05 in total.
- **Cap:** USD 1.00 for the iteration, enforced by the adapter across all caches.
