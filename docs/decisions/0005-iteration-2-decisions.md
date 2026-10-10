# ADR 0005: The iteration 2 settings, chosen on the dev set

- **Status:** accepted
- **Date:** 2026-10-09
- **Decided by:** the rules Luis approved before any run (`explorations/research/experiments_plan.yaml`,
  `iteration_2`), applied mechanically by `eval/experiments/decide.py`. Luis approved applying
  the EXC-03 threshold after seeing its effect on the dev set.
- **Evidence:** `outputs/eval/experiments.json`. Frozen dev set SHA-256 `5f34f08e…`, 130 items
  reviewed blind by Luis. None of the 28 scored receipts informed a choice.

## Decisions

| Experiment | Winner | Evidence (N) | Why the others lost |
|---|---|---|---|
| E14 classifier model | gpt-oss-120b (unchanged) | 123/130 correct; restricted F1 0.991; 3 of 29 A6/A9 items wrong | gpt-oss-20b 122/130 and gemma-3-12b 115/130: the bootstrap lower bound of the difference (-0.062 and -0.123) is below the -0.02 margin, so non-inferiority is not shown. qwen3.5-9b: 4/130 schema violations, over the 2 % exclusion |
| E7 EXC-03 source | self-reported confidence | Brier 0.060 vs 0.0625 for 120b/20b agreement (N = 128) | Agreement has a higher Brier score and costs a second call per item |
| E7 EXC-03 threshold | 0.95 | Fires on 6/128 dev items; sends 5 correct items to review; leaves 4/122 errors unflagged (0.5 left 5/125) | Highest accuracy on the kept items with at most 10 % of correct items sent to review |
| E5 translation | original text | 54/56 either way; McNemar p = 1.0 | No evidence of a gain at N = 56 |
| E15 null subtype | strict parser | 2 null subtypes observed in 520 answers, 0 fixed | Reading null as none fixed nothing on dev |
| RET retriever | trigger map | 0 differences on 47 receipts | Every rule gives the same findings and is harder to explain |

## Configuration it sets

- `config/pipeline.yaml`: `classifier_model: gpt-oss-120b`, `confidence_source: self_reported`,
  `translate: false`, `null_subtype_as_none: false`. Its 12-hex hash is recorded in every
  result as `pipeline_config_version`.
- `docs/decisions/policy_decisions.yaml`, A3: `exc03.threshold: 0.95`,
  `exc03.threshold_status: chosen_on_dev`.

## Consequences and limits

- **Calibration cannot be measured.** Self-reported confidence fills one bin with 10 or more
  items, so 0.95 is the point on a nearly flat curve that the rule picked, not a calibrated
  probability.
- **A high threshold can hide a violation behind a review.** EXC-03 leaves an uncertain item out
  of every other rule. Synthetic engine case CASE-03 has a gift line at confidence 0.93: at 0.95
  the receipt goes to `review` instead of a critical GIFT-04 `flag`. A person still sees it, but
  without the critical label. The engine cases keep running at the threshold they were
  reviewed under (0.5), because they test rule logic.
- **The model is not one fixed artefact under routing** (ADR 0004). gemma-3-12b was served 73
  times out of 130 by an int4 endpoint. Results record the serving provider.
- **Low power.** At N = 130 a 2-point non-inferiority margin is hard to show. gpt-oss-20b costs half as much per
  1,000 items (USD 0.027 vs 0.054) and was within one item of the reference. A larger dev set
  could change E14.
