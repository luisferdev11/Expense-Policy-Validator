import { useEffect, useState } from "react";

interface Metric {
  name: string;
  value: string;
  n: number;
}
interface Model {
  id: string;
  label: string;
  role: string;
  metrics: Metric[];
}
interface Evaluation {
  status: "measured" | "no-measurements";
  note: string;
  dataset: { name: string; n: number | null };
  models: Model[];
}

/**
 * Demonstrative comparison of the classifier candidates. It shows only figures that a committed
 * file provides, each with its N; the engine that decides is code, never one of these models.
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

  const metricNames = Array.from(new Set((data?.models ?? []).flatMap((m) => m.metrics.map((x) => x.name))));
  const measured = data?.status === "measured" && metricNames.length > 0;

  return (
    <div className="page">
      <h1 className="ll-display">Evaluation</h1>
      <p className="muted lead">
        How the models that read the items compare. The model only reads each line item into a category; the policy engine that raises findings and proposes the verdict is plain code,
        so the same input always gives the same output.
      </p>

      <section className="ll-panel">
        <h2 className="ll-heading">Classifier comparison</h2>
        {error && <p className="callout callout--error">The evaluation file could not be loaded.</p>}
        {data && !measured && (
          <p className="callout callout--accent" role="status">
            <strong>No measurements loaded yet.</strong> The three candidates are listed below; their figures appear here once they are provided with their N.
          </p>
        )}
        {data && (
          <div className="table-scroll">
            <table className="ll-table">
              <thead>
                <tr>
                  <th>Model</th>
                  <th>Role</th>
                  {measured ? metricNames.map((n) => <th key={n} className="is-num">{n}</th>) : <th>Measured figures</th>}
                </tr>
              </thead>
              <tbody>
                {data.models.map((m) => (
                  <tr key={m.id}>
                    <td className="ll-num">{m.label}</td>
                    <td>{m.role}</td>
                    {measured ? (
                      metricNames.map((n) => {
                        const x = m.metrics.find((v) => v.name === n);
                        return (
                          <td key={n} className="is-num">
                            {x ? (
                              <>
                                {x.value} <span className="muted">N={x.n}</span>
                              </>
                            ) : (
                              <span className="muted">not measured</span>
                            )}
                          </td>
                        );
                      })
                    ) : (
                      <td className="muted">not measured</td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data && <p className="muted">{data.dataset.name}{data.dataset.n !== null ? `, N = ${data.dataset.n}` : ""}. {data.note}</p>}
      </section>

      <section className="ll-panel">
        <h2 className="ll-heading">How to read this</h2>
        <ul className="plain">
          <li>Every figure carries the number of items or receipts behind it. A difference of one item on a small set is not a difference.</li>
          <li>Models are compared on a synthetic dev set; the real receipts are scored once per finalist and reported separately.</li>
          <li>Per-call detail (prompts, tokens, cost, latency) lives in Langfuse, not in this product.</li>
        </ul>
      </section>
    </div>
  );
}
