import { Link, useParams } from "react-router-dom";
import { ApiError, api } from "../api/client";
import type { ReceiptDetail, RevisionDetail } from "../api/types";
import { DispositionBadge } from "../components/Badges";
import { Timeline } from "../components/Timeline";
import { diffRevisions, sortFindings } from "../lib/domain";
import { localStamp, usd } from "../lib/format";
import { usePolling } from "../lib/hooks";

/** Receipt history: events, what each revision changed, and the evaluation versions. */
export function HistoryPage() {
  const { id = "" } = useParams();
  const detailQ = usePolling<ReceiptDetail>(() => api.getReceipt(id), [id], 5000);
  const eventsQ = usePolling(() => api.getEvents(id), [id, detailQ.data?.updated_at], 0);
  const revision = detailQ.data?.revision ?? 0;
  const revisionsQ = usePolling<RevisionDetail[]>(
    () => Promise.all(Array.from({ length: revision }, (_, i) => api.getRevision(id, i + 1))),
    [id, revision, detailQ.data?.updated_at],
    0,
  );

  const detail = detailQ.data;
  if (detailQ.error && !detail) {
    const notFound = detailQ.error instanceof ApiError && detailQ.error.status === 404;
    return (
      <div className="page">
        <p className="callout callout--error">{notFound ? `No receipt with the ID “${id}”.` : detailQ.error.message}</p>
      </div>
    );
  }
  if (!detail) return <div className="page muted">Loading…</div>;

  const revisions = revisionsQ.data ?? [];
  const r = detail.receipt;
  const pairs = revisions.slice(1).map((rev, i) => ({ from: revisions[i], to: rev, changes: diffRevisions(revisions[i].receipt, rev.receipt) }));

  return (
    <div className="page">
      <div className="history-head">
        <div>
          <Link to={`/all/${encodeURIComponent(id)}`}>← Back to the receipt</Link>
          <h1 className="ll-display">
            <span className="ll-num">{id}</span> · history
          </h1>
          <p className="muted">
            {r.merchant_name ?? "—"} · <span className="ll-num">{r.employee_id}</span> · {usd(r.total_amount_usd)}. Every change is an event; nothing is overwritten.
          </p>
        </div>
        <div className="row gap" style={{ marginTop: 0 }}>
          <DispositionBadge disposition={detail.disposition} proposed />
          <span className="muted">
            revision {detail.revision} · evaluation version {detail.evaluation_version ?? "—"}
          </span>
        </div>
      </div>

      <div className="history-grid">
        <section className="ll-panel" aria-labelledby="ev-h">
          <h2 className="ll-heading" id="ev-h">
            Events
          </h2>
          <Timeline events={eventsQ.data ?? []} currentRevision={detail.revision} />
        </section>

        <div className="stack-col">
          <section className="ll-panel" aria-labelledby="rev-h">
            <h2 className="ll-heading" id="rev-h">
              Revisions
            </h2>
            {revisions.length <= 1 ? (
              <p className="muted">Only revision 1 so far. Sending the same receipt ID with new content creates revision 2 and keeps this one readable.</p>
            ) : (
              pairs.map((p) => (
                <div key={p.to.revision}>
                  <h3 className="ll-heading">
                    Revision {p.from.revision} → {p.to.revision}
                  </h3>
                  {p.changes.length === 0 ? (
                    <p className="muted">No field changed.</p>
                  ) : (
                    <div className="table-scroll">
                      <table className="ll-table ll-table--compact">
                        <thead>
                          <tr>
                            <th>Field</th>
                            <th>Rev. {p.from.revision}</th>
                            <th>Rev. {p.to.revision}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {p.changes.map((c) => (
                            <tr key={c.field}>
                              <td className="ll-num">{c.field}</td>
                              <td className="ll-num muted wrap">{c.before}</td>
                              <td className="ll-num wrap">
                                <strong>{c.after}</strong>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              ))
            )}
            <ul className="plain">
              {revisions.map((rev) => (
                <li key={rev.revision}>
                  <strong>Revision {rev.revision}</strong> · {rev.status} · <span className="ll-num">{localStamp(rev.created_at)}</span>
                </li>
              ))}
            </ul>
          </section>

          <section className="ll-panel" aria-labelledby="ver-h">
            <h2 className="ll-heading" id="ver-h">
              Evaluation versions
            </h2>
            {revisions.flatMap((rev) => rev.evaluations.map((e) => ({ rev, e }))).length === 0 ? (
              <p className="muted">No policy check has been recorded yet.</p>
            ) : (
              <ul className="versions-list">
                {revisions.flatMap((rev) =>
                  rev.evaluations.map(({ version, result }) => (
                    <li key={`${rev.revision}-${version}`}>
                      <span className="ll-num muted">v{version}</span>
                      <DispositionBadge disposition={result.disposition} />
                      {sortFindings(result.exceptions)
                        .slice(0, 3)
                        .map((f) => (
                          <span key={f.rule_id} className={`ll-chip ll-chip--${f.severity} ll-num`}>
                            {f.rule_id}
                          </span>
                        ))}
                      <span className="muted">
                        revision {rev.revision}
                        {result.exceptions.length === 0 ? " · no findings" : ""}
                      </span>
                    </li>
                  )),
                )}
              </ul>
            )}
            <p className="hint">
              A new version appears when the receipt changes, when an auditor corrects a category, or when a receipt that shares its meal day or trip arrives or changes.
            </p>
          </section>
        </div>
      </div>
    </div>
  );
}
