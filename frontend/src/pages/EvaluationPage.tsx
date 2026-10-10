import { useEffect, useState } from "react";

interface Evaluation {
  release: string;
  provenance: string;
  scored: { title: string; cards: { label: string; value: string; detail: string }[] };
  classifiers: {
    title: string;
    note: string;
    models: {
      id: string;
      label: string;
      kind: string;
      accuracy: string | null;
      accuracyDetail: string;
      restrictedF1: string | null;
      subtypeWrong: string;
      usdPer1000: string;
      role: string;
      highlight?: boolean;
    }[];
  };
  decisions: { title: string; note: string; rows: { question: string; chosen: string; evidence: string }[] };
}

/**
 * The lead and developer area. It shows only figures that a committed file provides, each with its
 * N. The engine that decides is code, never one of these models.
 */
export function EvaluationPage() {
  const [data, setData] = useState<Evaluation | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    fetch("/evaluation.json")
      .then((r) => (r.ok ? (r.json() as Promise<Evaluation>) : Promise.reject(new Error("missing"))))
      .then(setData)
      .catch(() => setError(true));
  }, []);

  return (
    <div className="page">
      <div className="history-head">
        <div>
          <h1 className="ll-display">Evaluation</h1>
          <p className="muted lead">
            How well the system decides, and why it runs the way it does. Auditors never need this area; every number shows its N, and every choice was made on the synthetic dev set, never on the 28 scored receipts. The model only reads each item into a category; the policy engine that raises findings and proposes the verdict is plain code.
          </p>
        </div>
        {data && <span className="muted">Release {data.release}</span>}
      </div>

      {error && <p className="callout callout--error">The evaluation file could not be loaded.</p>}
      {data && (
        <>
          <section aria-labelledby="score-h" className="stack-col">
            <h2 className="ll-heading" id="score-h">
              {data.scored.title}
            </h2>
            <div className="kpis kpis--wide">
              {data.scored.cards.map((c) => (
                <div key={c.label} className="ll-panel kpi">
                  <span className="ll-label">{c.label}</span>
                  <strong className="kpi__n ll-num">{c.value}</strong>
                  <span className="hint">{c.detail}</span>
                </div>
              ))}
            </div>
          </section>

          <section className="ll-panel" aria-labelledby="models-h">
            <div>
              <h2 className="ll-heading" id="models-h">
                {data.classifiers.title}
              </h2>
              <p className="muted">{data.classifiers.note}</p>
            </div>
            <div className="table-scroll">
              <table className="ll-table">
                <thead>
                  <tr>
                    <th>Model</th>
                    <th>Kind</th>
                    <th className="is-num">Category accuracy</th>
                    <th className="is-num">Restricted F1</th>
                    <th className="is-num">Subtype or recipient wrong</th>
                    <th className="is-num">USD per 1,000 items</th>
                    <th>Role</th>
                  </tr>
                </thead>
                <tbody>
                  {data.classifiers.models.map((m) => (
                    <tr key={m.id} className={m.highlight ? "is-selected" : ""}>
                      <th scope="row" className="ll-num">
                        {m.label}
                      </th>
                      <td>{m.kind}</td>
                      <td className="is-num">
                        {m.accuracy ?? <span className="muted">not run</span>}
                        <div className="sub">{m.accuracyDetail}</div>
                      </td>
                      <td className="is-num">{m.restrictedF1 ?? <span className="muted">not run</span>}</td>
                      <td className="is-num">{m.subtypeWrong}</td>
                      <td className="is-num">{m.usdPer1000}</td>
                      <td className="wrap">{m.role}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="ll-panel" aria-labelledby="exp-h">
            <div>
              <h2 className="ll-heading" id="exp-h">
                {data.decisions.title}
              </h2>
              <p className="muted">{data.decisions.note}</p>
            </div>
            <div className="table-scroll">
              <table className="ll-table">
                <thead>
                  <tr>
                    <th>Question</th>
                    <th>Chosen</th>
                    <th>Evidence</th>
                  </tr>
                </thead>
                <tbody>
                  {data.decisions.rows.map((r) => (
                    <tr key={r.question}>
                      <td className="wrap">{r.question}</td>
                      <td className="wrap">{r.chosen}</td>
                      <td className="wrap">{r.evidence}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <p className="hint">{data.provenance}</p>
        </>
      )}
    </div>
  );
}
