// Builds public/evaluation.json for the Evaluation screen from committed outputs. No model call.
//
//   npm run evaluation
//
// Sources (read-only): outputs/eval/metrics.json and experiments.json (`epv eval`, scored on the
// 28 in-scope receipts and the synthetic dev set), and frontend/data/classifier-comparison.json
// (the jev-1.13 dev-set run, see scripts/jev_dev_run.py). Only aggregates are read: per-receipt
// answers never reach the front end (labels firewall). The output is committed, and a unit test
// fails when it is stale.
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const read = (rel) => JSON.parse(readFileSync(resolve(root, rel), "utf8"));

export const SOURCES = [
  "../outputs/eval/metrics.json",
  "../outputs/eval/experiments.json",
  "data/classifier-comparison.json",
];

const SYSTEMS = [
  ["pipeline", "Pipeline (the product)"],
  ["keyword-classifier", "Keyword classifier + rules"],
  ["keyword-flagger", "Keyword flagger"],
];

const prop = (p) => (p ? { value: p.value, n: p.n, rate: p.rate ?? null, interval: p.interval ?? null } : null);

export function build() {
  const metrics = read(SOURCES[0]);
  const experiments = read(SOURCES[1]);
  const comparison = read(SOURCES[2]);
  const e7 = experiments.experiments.find((e) => e.id === "E7");

  const systems = SYSTEMS.map(([id, label]) => {
    const s = metrics.systems[id];
    return {
      id,
      label,
      dispositionAccuracy: prop(s.disposition_accuracy),
      falsePositives: prop(s.false_positives),
      missedViolations: prop(s.missed_violations),
      macroF1: s.macro_f1 ? { value: s.macro_f1.value ?? null, n: s.macro_f1.n } : null,
      restrictedF1: s.restricted_f1 ? { value: s.restricted_f1.value ?? null, n: s.restricted_f1.n } : null,
      evidenceCorrectness: prop(s.evidence_correctness),
      confusion: { axis: s.disposition_confusion.labels, matrix: s.disposition_confusion.matrix, n: s.disposition_confusion.n },
    };
  });

  const perRule = Object.entries(metrics.systems.pipeline.per_rule)
    .map(([rule, r]) => ({ rule, tp: r.tp, fp: r.fp, fn: r.fn, precision: r.precision, recall: r.recall }))
    .sort((a, b) => a.rule.localeCompare(b.rule));

  const oracleStages = {};
  for (const row of metrics.oracle.rows) oracleStages[row.stage] = (oracleStages[row.stage] ?? 0) + 1;

  return {
    sources: SOURCES.map((s) => s.replace("../", "")),
    run: metrics.run,
    systems,
    perRule,
    reviewSignals: metrics.systems.pipeline.review_signals,
    exc03: metrics.systems.pipeline.exc03,
    oracle: {
      pipeline: prop(metrics.oracle.pipeline_accuracy),
      oracle: prop(metrics.oracle.oracle_accuracy),
      limitation: metrics.oracle.limitation,
      stages: oracleStages,
    },
    baseRate: {
      detectionRate: metrics.base_rate.detection_rate,
      falsePositiveRate: metrics.base_rate.false_positive_rate,
      nFlag: metrics.base_rate.n_flag,
      nPass: metrics.base_rate.n_pass,
      receipts: metrics.base_rate.receipts,
      rows: metrics.base_rate.rows,
    },
    decisions: experiments.table,
    devSetSha256: experiments.dev_set_sha256,
    spendUsd: experiments.spend_usd_of_kept_answers,
    e7: { threshold: e7.threshold, firesOnDev: e7.fires_on_dev.k, n: e7.n, curve: e7.curve },
    classifiers: {
      generatedAt: comparison.generated_at,
      devSetSha256: comparison.dev_set_sha256,
      n: comparison.n,
      jev: {
        modelId: comparison.model_id,
        promptVersion: comparison.prompt_version,
        servedBy: comparison.served_by,
        latency: comparison.latency_s,
      },
      variants: comparison.variants,
      calibration: comparison.calibration,
      confusions: comparison.confusions,
    },
  };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  writeFileSync(resolve(root, "public", "evaluation.json"), JSON.stringify(build(), null, 2) + "\n");
  console.log("evaluation: public/evaluation.json written");
}
