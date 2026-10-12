import { useEffect, useState } from "react";
import { ConfusionMatrix, CoverageCurve, ForestPlot } from "../components/EvalCharts";
import { REFERENCE, STATUS_TEXT, ci, frac, pct } from "../lib/evaluation";
import type { EvalData, VariantStats } from "../lib/evaluation";

const SECTIONS = [
  ["scored", "Scored receipts"],
  ["errors", "Where errors come from"],
  ["rules", "Rules"],
  ["classifiers", "Classifiers"],
  ["calibration", "Confidence"],
  ["decisions", "Decisions"],
  ["base-rate", "Base rate"],
] as const;

function Kpi({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="ll-panel kpi">
      <span className="ll-label">{label}</span>
      <strong className="kpi__n ll-num">{value}</strong>
      <span className="hint">{detail}</span>
    </div>
  );
}

const money = (v: number) => v.toFixed(3);

/**
 * The lead and developer area. Every figure comes from committed outputs through
 * `npm run evaluation` (no model call) and shows its N. The engine that decides is code; the
 * models below only read each item into a category.
 */
export function EvaluationPage() {
  const [data, setData] = useState<EvalData | null>(null);
  const [error, setError] = useState(false);
  const [system, setSystem] = useState("pipeline");

  useEffect(() => {
    fetch("/evaluation.json")
      .then((r) => (r.ok ? (r.json() as Promise<EvalData>) : Promise.reject(new Error("missing"))))
      .then(setData)
      .catch(() => setError(true));
  }, []);

  if (error) return <div className="page"><p className="callout callout--error">The evaluation file could not be loaded.</p></div>;
  if (!data) return <div className="page muted">Loading…</div>;

  const pipeline = data.systems[0];
  const baselines = data.systems.slice(1);
  const sel = data.systems.find((s) => s.id === system) ?? pipeline;
  const cls = data.classifiers;
  const ref = cls.variants.find((v) => v.variant === REFERENCE)!;
  const jev = cls.variants.find((v) => v.variant === "jev-1.13");
  const byAcc: VariantStats[] = [...cls.variants].sort((a, b) => b.accuracy.value - a.accuracy.value || a.variant.localeCompare(b.variant));

  return (
    <div className="page eval">
      <div className="history-head">
        <div>
          <h1 className="ll-display">Evaluation</h1>
          <p className="muted lead">
            How well the system decides, and why it runs the way it does. Every number shows its N. Choices were made on the synthetic dev set; the 28 scored receipts informed none of them. The models only read each item into a category: the policy engine that raises findings and proposes the verdict is plain code.
          </p>
        </div>
        <span className="muted eval-run ll-num">
          {data.run.model_id} · prompt {data.run.prompt_version} · rules {data.run.rules_version} · EXC-03 {data.run.exc03_threshold}
        </span>
      </div>

      <nav className="eval-nav" aria-label="Sections">
        {SECTIONS.map(([id, label]) => (
          <a key={id} href={`#${id}`}>
            {label}
          </a>
        ))}
      </nav>

      <section id="scored" aria-labelledby="scored-h" className="stack-col">
        <h2 className="ll-heading" id="scored-h">
          On the 28 scored receipts
        </h2>
        <div className="kpis kpis--wide">
          <Kpi label="Dispositions correct" value={frac(pipeline.dispositionAccuracy)} detail={`95 % CI ${ci(pipeline.dispositionAccuracy.interval)}`} />
          <Kpi label="Missed violations" value={frac(pipeline.missedViolations)} detail={`should be flagged · CI ${ci(pipeline.missedViolations.interval)}`} />
          <Kpi label="False positives" value={frac(pipeline.falsePositives)} detail={`should pass · CI ${ci(pipeline.falsePositives.interval)}`} />
          <Kpi label="Line categories, macro F1" value={pipeline.macroF1?.value?.toFixed(3) ?? "n/a"} detail={`N = ${pipeline.macroF1?.n} scored lines`} />
        </div>

        <div className="ll-panel">
          <h3 className="ll-heading">Against two keyword baselines</h3>
          <div className="table-scroll">
            <table className="ll-table">
              <thead>
                <tr>
                  <th>System</th>
                  <th className="is-num">Dispositions correct (N = 28)</th>
                  <th className="is-num">False positives (of 9)</th>
                  <th className="is-num">Missed violations (of 16)</th>
                  <th className="is-num">Macro F1 (N = 65)</th>
                  <th className="is-num">Restricted F1 (N = 65)</th>
                </tr>
              </thead>
              <tbody>
                {[pipeline, ...baselines].map((s) => (
                  <tr key={s.id} className={s.id === "pipeline" ? "is-selected" : ""}>
                    <th scope="row">{s.label}</th>
                    <td className="is-num">
                      {s.dispositionAccuracy.value} · {pct(s.dispositionAccuracy.rate)}
                      <div className="sub">CI {ci(s.dispositionAccuracy.interval)}</div>
                    </td>
                    <td className="is-num">
                      {s.falsePositives.value}
                      <div className="sub">CI {ci(s.falsePositives.interval)}</div>
                    </td>
                    <td className="is-num">
                      {s.missedViolations.value}
                      <div className="sub">CI {ci(s.missedViolations.interval)}</div>
                    </td>
                    <td className="is-num">{s.macroF1?.value?.toFixed(3) ?? "n/a"}</td>
                    <td className="is-num">{s.restrictedF1?.value?.toFixed(3) ?? "n/a"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="hint">A baseline does better on nothing measured here. With N = 28 the intervals are wide: 28 of 28 does not mean the system never errs.</p>
        </div>

        <div className="ll-panel">
          <div className="batch-head">
            <h3 className="ll-heading">Proposed versus correct disposition</h3>
            <div className="row gap" style={{ marginTop: 0 }} role="group" aria-label="System">
              {data.systems.map((s) => (
                <button key={s.id} type="button" className={`chip${system === s.id ? " is-on" : ""}`} aria-pressed={system === s.id} onClick={() => setSystem(s.id)}>
                  {s.label}
                </button>
              ))}
            </div>
          </div>
          <ConfusionMatrix labels={sel.confusion.axis} matrix={sel.confusion.matrix} />
          <p className="hint">N = {sel.confusion.n} receipts. Rows are the correct answer, columns what the system proposed; the diagonal is agreement.</p>
        </div>
      </section>

      <section id="errors" aria-labelledby="err-h" className="ll-panel">
        <h2 className="ll-heading" id="err-h">
          Where errors come from
        </h2>
        <p className="muted">The same engine fed each line's correct category with confidence 1 (the oracle) separates classification errors from rule errors.</p>
        <div className="kpis kpis--wide">
          <Kpi label="Pipeline, dispositions correct" value={frac(data.oracle.pipeline)} detail={`CI ${ci(data.oracle.pipeline.interval)}`} />
          <Kpi label="Oracle, dispositions correct" value={frac(data.oracle.oracle)} detail={`CI ${ci(data.oracle.oracle.interval)}`} />
        </div>
        <p className="hint">{data.oracle.limitation}</p>
      </section>

      <section id="rules" aria-labelledby="rules-h" className="ll-panel">
        <h2 className="ll-heading" id="rules-h">
          Rules the pipeline raised, against the answers
        </h2>
        <div className="table-scroll">
          <table className="ll-table ll-table--compact">
            <thead>
              <tr>
                <th>Rule</th>
                <th className="is-num">Correct (TP)</th>
                <th className="is-num">Extra (FP)</th>
                <th className="is-num">Missed (FN)</th>
                <th className="is-num">Precision</th>
                <th className="is-num">Recall</th>
              </tr>
            </thead>
            <tbody>
              {data.perRule.map((r) => (
                <tr key={r.rule}>
                  <th scope="row" className="ll-num">
                    {r.rule}
                  </th>
                  <td className="is-num">{r.tp}</td>
                  <td className="is-num">{r.fp}</td>
                  <td className="is-num">{r.fn}</td>
                  <td className="is-num">{r.precision?.toFixed(2) ?? "n/a"}</td>
                  <td className="is-num">{r.recall?.toFixed(2) ?? "n/a"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="hint">
          {data.perRule.length} rules fired across the scored receipts, most of them once or twice, so a perfect score per rule rests on very few cases. Evidence (the cited lines) was right for {frac(pipeline.evidenceCorrectness)} matched exceptions. Review signals: {data.reviewSignals.tp} of {data.reviewSignals.n} matched, {data.reviewSignals.fp} extra, {data.reviewSignals.fn} missed.
        </p>
      </section>

      <section id="classifiers" aria-labelledby="cls-h" className="ll-panel">
        <div>
          <h2 className="ll-heading" id="cls-h">
            Five classifiers on the frozen dev set
          </h2>
          <p className="muted">
            N = {cls.n} synthetic items, reviewed blind (set <span className="ll-num">{cls.devSetSha256.slice(0, 8)}…</span>). The first four runs were registered and decided in iteration 2; the jev-1.13 run was added afterwards to see how a decision model does. It is not a registered experiment and changes nothing.
          </p>
        </div>

        <ForestPlot variants={byAcc} highlight={REFERENCE} />

        <div className="table-scroll">
          <table className="ll-table">
            <thead>
              <tr>
                <th>Model</th>
                <th className="is-num">Category accuracy</th>
                <th className="is-num">Restricted F1</th>
                <th className="is-num">Subtype or recipient wrong</th>
                <th className="is-num">Invalid answers</th>
                <th className="is-num">USD per 1,000 items</th>
                <th className="is-num">Latency</th>
                <th>Against the reference</th>
              </tr>
            </thead>
            <tbody>
              {byAcc.map((v) => {
                const isJev = v.variant === "jev-1.13";
                return (
                  <tr key={v.variant} className={v.variant === REFERENCE ? "is-selected" : ""}>
                    <th scope="row" className="ll-num">
                      {v.variant}
                    </th>
                    <td className="is-num">
                      {v.accuracy.k} / {v.accuracy.n}
                      <div className="sub">{ci(v.accuracy.interval)}</div>
                    </td>
                    <td className="is-num">{v.restricted_f1.toFixed(3)}</td>
                    <td className="is-num">{isJev ? <span className="muted">not returned</span> : `${v.a6a9_wrong} / ${v.a6a9_n}`}</td>
                    <td className="is-num">
                      {v.schema_violations.k} / {v.schema_violations.n}
                    </td>
                    <td className="is-num">{money(v.cost_per_1000_usd)}</td>
                    <td className="is-num">
                      {isJev ? (
                        <>
                          {cls.jev.latency.mean.toFixed(2)} s
                          <div className="sub">p95 {cls.jev.latency.p95.toFixed(2)} s</div>
                        </>
                      ) : (
                        <span className="muted">not recorded</span>
                      )}
                    </td>
                    <td className="wrap">
                      <strong>{STATUS_TEXT[v.status]}</strong>
                      {v.difference && v.mcnemar && (
                        <div className="sub">
                          difference {(v.difference.value * 100).toFixed(1)} points (CI {(v.difference.interval[0] * 100).toFixed(1)} to {(v.difference.interval[1] * 100).toFixed(1)}); right where the reference was wrong: {v.mcnemar.b_challenger_only}, the reverse: {v.mcnemar.c_reference_only}; exact test p = {v.mcnemar.p}
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {cls.confusions[REFERENCE]?.length > 0 && (
          <p className="hint">
            Where the reference was wrong ({cls.confusions[REFERENCE].reduce((n, c) => n + c.count, 0)} items, correct category → what it said):{" "}
            {cls.confusions[REFERENCE].map((c) => `${c.expected} → ${c.predicted}${c.count > 1 ? ` ×${c.count}` : ""}`).join("; ")}.
          </p>
        )}

        {jev && (
          <div className="callout callout--accent eval-note">
            <div>
              <strong>Reading the jev-1.13 row.</strong> It got every category right on this set ({jev.accuracy.k} of {jev.accuracy.n}; interval {ci(jev.accuracy.interval)}), seven more than the reference and none fewer, at {money(jev.cost_per_1000_usd)} USD per 1,000 items against {money(ref.cost_per_1000_usd)} and about {cls.jev.latency.mean.toFixed(1)} s per item. Three limits keep it from replacing the classifier today: it returns a category only, so subtype and recipient (which ENT-01, TECH-03 and the gift rules need) would still come from another model; the dev set is small and synthetic, so a perfect score is not proof it will hold on real receipts; and it is an early-access model. Served by {cls.jev.servedBy.join(", ")}, prompt {cls.jev.promptVersion}.
            </div>
          </div>
        )}
      </section>

      <section id="calibration" aria-labelledby="cal-h" className="ll-panel">
        <h2 className="ll-heading" id="cal-h">
          How far to trust a model's own confidence
        </h2>
        <p className="muted">
          EXC-03 sends a line to review when the classifier's confidence is below {data.e7.threshold}. Lower Brier and ECE mean the stated confidence matches how often the model is right.
        </p>
        <div className="table-scroll">
          <table className="ll-table ll-table--compact">
            <thead>
              <tr>
                <th>Confidence</th>
                <th className="is-num">Items (N)</th>
                <th className="is-num">Brier score</th>
                <th className="is-num">Calibration error (ECE)</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(cls.calibration)
                .filter(([, c]) => c)
                .map(([name, c]) => (
                  <tr key={name}>
                    <th scope="row" className="wrap">
                      {name}
                    </th>
                    <td className="is-num">{c!.n}</td>
                    <td className="is-num">{c!.brier.toFixed(4)}</td>
                    <td className="is-num">{c!.ece.toFixed(4)}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
        <p className="hint">jev's confidence is a statistic of its answer distribution, not a measured calibration (its documentation says to test it on your own data), and ECE depends on how the confidences are binned. Treat both as indications.</p>
        <h3 className="ll-heading">Accuracy of the kept items as the EXC-03 threshold rises (gpt-oss-120b, N = {data.e7.n})</h3>
        <CoverageCurve curve={data.e7.curve} threshold={data.e7.threshold} />
        <p className="hint">The chosen threshold {data.e7.threshold} fires on {data.e7.firesOnDev} of {data.e7.n} dev items. Accuracy stays above 96 % at every threshold, so the point is a choice, not a calibrated probability (ADR 0005).</p>
      </section>

      <section id="decisions" aria-labelledby="dec-h" className="ll-panel">
        <div>
          <h2 className="ll-heading" id="dec-h">
            Decisions taken on the dev set
          </h2>
          <p className="muted">Each rule was registered and approved before its run (ADR 0005).</p>
        </div>
        <div className="table-scroll">
          <table className="ll-table">
            <thead>
              <tr>
                <th>Experiment</th>
                <th>Question</th>
                <th>Chosen</th>
                <th>Evidence</th>
                <th>Why the others lost</th>
              </tr>
            </thead>
            <tbody>
              {data.decisions.map((d) => (
                <tr key={d.experiment}>
                  <th scope="row" className="ll-num">
                    {d.experiment}
                  </th>
                  <td className="wrap">{d.factor}</td>
                  <td className="wrap">{d.winner}</td>
                  <td className="wrap">{d.evidence}</td>
                  <td className="wrap">{d.why_others_lost}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section id="base-rate" aria-labelledby="br-h" className="ll-panel">
        <h2 className="ll-heading" id="br-h">
          What this means at volume
        </h2>
        <p className="muted">
          Measured here: false-positive rate {pct(data.baseRate.falsePositiveRate)} (N = {data.baseRate.nPass} receipts that should pass) and detection rate {pct(data.baseRate.detectionRate)} (N = {data.baseRate.nFlag} that should be flagged). Per {data.baseRate.receipts.toLocaleString("en-US")} receipts:
        </p>
        <div className="table-scroll">
          <table className="ll-table ll-table--compact">
            <thead>
              <tr>
                <th className="is-num">Prevalence of violations</th>
                <th className="is-num">Violations</th>
                <th className="is-num">True flags</th>
                <th className="is-num">False flags</th>
                <th className="is-num">Share of flags that are false</th>
              </tr>
            </thead>
            <tbody>
              {data.baseRate.rows.map((r) => (
                <tr key={r.prevalence}>
                  <td className="is-num">{pct(r.prevalence)}</td>
                  <td className="is-num">{r.violations}</td>
                  <td className="is-num">{r.true_flags}</td>
                  <td className="is-num">{r.false_flags}</td>
                  <td className="is-num">{pct(r.false_share)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="hint">With only {data.baseRate.nPass} should-pass receipts the false-positive rate is very uncertain (its interval above runs to {ci(pipeline.falsePositives.interval).split("–")[1]}); a production estimate needs a larger, realistic sample.</p>
      </section>

      <p className="hint">
        Sources: {data.sources.map((s) => <code key={s}>{s}</code>)} Regenerate with <code>npm run evaluation</code> (no model call); the jev-1.13 run with <code>uv run python -I frontend/scripts/jev_dev_run.py</code>, run on {cls.generatedAt.slice(0, 10)}.
      </p>
    </div>
  );
}
