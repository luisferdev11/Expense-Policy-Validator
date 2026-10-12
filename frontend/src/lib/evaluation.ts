// Shape of public/evaluation.json, built by scripts/build-evaluation.mjs from committed outputs.

export interface Proportion {
  value: number;
  n: number;
  rate: number | null;
  interval: [number, number] | null;
}

export interface SystemMetrics {
  id: string;
  label: string;
  dispositionAccuracy: Proportion;
  falsePositives: Proportion;
  missedViolations: Proportion;
  macroF1: { value: number | null; n: number } | null;
  restrictedF1: { value: number | null; n: number } | null;
  evidenceCorrectness: Proportion;
  confusion: { axis: string[]; matrix: number[][]; n: number };
}

export interface VariantStats {
  variant: string;
  status: "reference" | "worse" | "excluded" | "superior" | "non_inferior" | "fails_a6a9_guard";
  accuracy: { value: number; k: number; n: number; interval: [number, number] };
  restricted_f1: number;
  a6a9_wrong: number;
  a6a9_n: number;
  schema_violations: { value: number; k: number; n: number };
  cost_per_1000_usd: number;
  difference?: { value: number; interval: [number, number] };
  mcnemar?: { b_challenger_only: number; c_reference_only: number; p: number };
}

export interface Calibration {
  n: number;
  brier: number;
  ece: number;
}

export interface EvalData {
  sources: string[];
  run: {
    classifier: string;
    model_id: string;
    prompt_version: string;
    rules_version: string;
    exc03_threshold: number;
    exc03_threshold_status: string;
    confidence_source: string;
  };
  systems: SystemMetrics[];
  perRule: { rule: string; tp: number; fp: number; fn: number; precision: number | null; recall: number | null }[];
  reviewSignals: { tp: number; fp: number; fn: number; n: number };
  exc03: { signals: number; receipts: number; dispositions_changed: number };
  oracle: { pipeline: Proportion; oracle: Proportion; limitation: string; stages: Record<string, number> };
  baseRate: {
    detectionRate: number;
    falsePositiveRate: number;
    nFlag: number;
    nPass: number;
    receipts: number;
    rows: { prevalence: number; violations: number; true_flags: number; false_flags: number; false_share: number }[];
  };
  decisions: { experiment: string; factor: string; winner: string; evidence: string; why_others_lost: string }[];
  devSetSha256: string;
  spendUsd: number;
  e7: { threshold: number; firesOnDev: number; n: number; curve: { threshold: number; coverage: number; accuracy: number }[] };
  classifiers: {
    generatedAt: string;
    devSetSha256: string;
    n: number;
    jev: {
      modelId: string;
      promptVersion: string;
      servedBy: string[];
      latency: { n: number; mean: number; p50: number; p95: number; note: string };
    };
    variants: VariantStats[];
    calibration: Record<string, Calibration | null>;
    confusions: Record<string, { expected: string; predicted: string; count: number }[]>;
  };
}

export const pct = (v: number | null | undefined, digits = 1): string =>
  v === null || v === undefined ? "n/a" : `${(v * 100).toFixed(digits)} %`;

export const ci = (interval: [number, number] | null): string =>
  interval ? `${(interval[0] * 100).toFixed(1)}–${(interval[1] * 100).toFixed(1)} %` : "";

export const frac = (p: { value: number; n: number }): string => `${p.value} of ${p.n}`;

export const STATUS_TEXT: Record<VariantStats["status"], string> = {
  reference: "Reference, in use",
  worse: "Not shown as good as the reference",
  excluded: "Excluded: too many invalid answers",
  superior: "Better on this set (paired test)",
  non_inferior: "Not worse than the reference",
  fails_a6a9_guard: "Fails the subtype and recipient guard",
};

/** The model the app's decision runs on, for the chart's reference row. */
export const REFERENCE = "gpt-oss-120b";
