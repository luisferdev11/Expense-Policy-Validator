import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { EventItem, ReceiptSummary } from "../api/types";
import { DISPOSITION_LABEL, STATES, STATE_LABEL } from "../lib/domain";
import { percent } from "../lib/format";
import { useDetails } from "../lib/hooks";
import { computeInsights, sortedEntries } from "../lib/insights";
import { useReceipts } from "../lib/receipts";

/** Events per receipt, fetched once per receipt and revision of its row (FINDINGS.md F-02). */
function useEventsFor(summaries: ReceiptSummary[]): Map<string, EventItem[]> {
  const cache = useRef(new Map<string, EventItem[]>());
  const [, bump] = useState(0);
  useEffect(() => {
    let cancelled = false;
    const todo = summaries.filter((s) => !cache.current.has(`${s.receipt_id}:${s.updated_at}`));
    const queue = [...todo];
    const worker = async () => {
      for (let s = queue.shift(); s; s = queue.shift()) {
        try {
          cache.current.set(`${s.receipt_id}:${s.updated_at}`, await api.getEvents(s.receipt_id));
        } catch {
          /* skipped */
        }
        if (!cancelled) bump((n) => n + 1);
      }
    };
    void Promise.all([worker(), worker(), worker(), worker()]);
    return () => {
      cancelled = true;
    };
  }, [summaries]);
  const map = new Map<string, EventItem[]>();
  for (const s of summaries) {
    const e = cache.current.get(`${s.receipt_id}:${s.updated_at}`);
    if (e) map.set(s.receipt_id, e);
  }
  return map;
}

function Bars({ rows, total, label }: { rows: [string, number][]; total: number; label: (k: string) => string }) {
  if (rows.length === 0) return <p className="muted">Nothing to show yet.</p>;
  const max = Math.max(...rows.map(([, n]) => n));
  return (
    <ul className="bars">
      {rows.map(([k, n]) => (
        <li key={k}>
          <span className="bars__label">{label(k)}</span>
          <span className="bars__track" aria-hidden="true">
            <span className="bars__fill" style={{ width: `${(n / max) * 100}%` }} />
          </span>
          <span className="ll-num bars__n">
            {n} <span className="muted">({percent(n, total)})</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

export function InsightsPage() {
  const { summaries, loading } = useReceipts();
  const details = useDetails(summaries);
  const events = useEventsFor(summaries);
  const ins = useMemo(() => computeInsights(summaries, details, events), [summaries, details, events]);
  const loaded = details.size === summaries.length && events.size === summaries.length;

  const decisions = ins.agreement.decisions;
  return (
    <div className="page">
      <h1 className="ll-display">Insights</h1>
      <p className="muted lead">
        How the queue is doing and where people disagree with the engine. Every figure shows the number of receipts or decisions behind it.
        {!loaded && summaries.length > 0 && " Loading the details…"}
      </p>

      {summaries.length === 0 && !loading ? (
        <div className="empty">
          <p className="empty__lead">No receipts yet.</p>
          <p className="muted">
            <Link to="/intake">Submit receipts</Link> and these figures fill in.
          </p>
        </div>
      ) : (
        <>
          <div className="kpis">
            <div className="ll-panel kpi">
              <span className="ll-label">Receipts</span>
              <strong className="kpi__n ll-num">{ins.total}</strong>
            </div>
            <div className="ll-panel kpi">
              <span className="ll-label">Waiting for a person</span>
              <strong className="kpi__n ll-num">{ins.open}</strong>
              <span className="muted">of {ins.total}</span>
            </div>
            <div className="ll-panel kpi">
              <span className="ll-label">Agreement with the engine</span>
              <strong className="kpi__n ll-num">{percent(ins.agreement.agreed, decisions)}</strong>
              <span className="muted">N = {decisions} decision{decisions === 1 ? "" : "s"}</span>
            </div>
            <div className="ll-panel kpi">
              <span className="ll-label">Result changed, to re-read</span>
              <strong className="kpi__n ll-num">{ins.notices}</strong>
            </div>
            <div className="ll-panel kpi">
              <span className="ll-label">Quality sample waiting</span>
              <strong className="kpi__n ll-num">{ins.qaWaiting}</strong>
              <Link to="/sample">Open</Link>
            </div>
            <div className="ll-panel kpi">
              <span className="ll-label">Failed</span>
              <strong className="kpi__n ll-num">{ins.failed}</strong>
            </div>
          </div>

          <div className="grid2">
            <section className="ll-panel">
              <h2 className="ll-heading">Receipts by state (N = {ins.total})</h2>
              <Bars
                rows={STATES.filter((s) => ins.byState[s]).map((s) => [s, ins.byState[s]] as [string, number])}
                total={ins.total}
                label={(k) => STATE_LABEL[k as keyof typeof STATE_LABEL]}
              />
            </section>
            <section className="ll-panel">
              <h2 className="ll-heading">Proposed verdicts (N = {ins.byProposal.flag + ins.byProposal.review + ins.byProposal.pass || 0})</h2>
              <Bars
                rows={(["flag", "review", "pass"] as const).filter((d) => ins.byProposal[d]).map((d) => [d, ins.byProposal[d]] as [string, number])}
                total={Object.values(ins.byProposal).reduce((a, b) => a + b, 0)}
                label={(k) => DISPOSITION_LABEL[k as keyof typeof DISPOSITION_LABEL]}
              />
            </section>
            <section className="ll-panel">
              <h2 className="ll-heading">Waiting time of open receipts (N = {ins.open})</h2>
              <Bars rows={Object.entries(ins.aging).filter(([, n]) => n > 0)} total={ins.open} label={(k) => k} />
            </section>
            <section className="ll-panel">
              <h2 className="ll-heading">Where people agree with the engine</h2>
              {decisions === 0 ? (
                <p className="muted">No decision has been recorded yet.</p>
              ) : (
                <table className="ll-table ll-table--compact">
                  <thead>
                    <tr>
                      <th>Action</th>
                      <th className="is-num">Decisions</th>
                      <th className="is-num">Agreed</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(ins.agreement.byAction).map(([a, r]) => (
                      <tr key={a}>
                        <td>{a.replace("-", " ")}</td>
                        <td className="is-num">{r.n}</td>
                        <td className="is-num">
                          {r.agreed} ({percent(r.agreed, r.n)})
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              <p className="muted">A decision “agrees” when it matches the engine's proposal; a category correction always counts as a disagreement with the classifier.</p>
            </section>
            <section className="ll-panel">
              <h2 className="ll-heading">Rules that fire most (N = {ins.withResult} receipts with a result)</h2>
              <Bars rows={sortedEntries(ins.ruleFrequency).slice(0, 8)} total={ins.withResult} label={(k) => k} />
            </section>
            <section className="ll-panel">
              <h2 className="ll-heading">Findings on receipts where someone disagreed</h2>
              <Bars rows={sortedEntries(ins.disagreementByRule).slice(0, 8)} total={Math.max(1, ins.agreement.decisions - ins.agreement.agreed)} label={(k) => k} />
              <p className="muted">By rule on the receipt's current result. A rule that is often overridden is a candidate for a closer look.</p>
            </section>
          </div>
        </>
      )}
    </div>
  );
}
