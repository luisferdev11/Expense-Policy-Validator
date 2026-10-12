import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import type { Disposition, ReceiptSummary, State } from "../api/types";
import { DispositionBadge, StateChip } from "../components/Badges";
import { ReceiptPane } from "../components/ReceiptPane";
import { QUEUE_VIEWS, STATES, STATE_LABEL, ageOf, findingCount, severityRank } from "../lib/domain";
import type { QueueView } from "../lib/domain";
import { usd } from "../lib/format";
import { useDetails, usePolling, useShortcuts } from "../lib/hooks";
import { useReceipts } from "../lib/receipts";

export type WorkView = QueueView | "all";

const DISP_ORDER: Record<string, number> = { flag: 0, review: 1, pass: 2 };
const PAGE = 50;

export function WorkPage({ view }: { view: WorkView }) {
  const { id } = useParams();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const batchId = params.get("batch");
  const shared = useReceipts();
  const batchList = usePolling(
    () => (batchId ? api.listReceipts({ batch_id: batchId, limit: 500 }) : Promise.resolve(null)),
    [batchId],
    4000,
  );
  const summaries = batchId ? (batchList.data?.items ?? []) : shared.summaries;
  const total = batchId ? (batchList.data?.total ?? 0) : shared.total;
  const loading = batchId ? batchList.loading : shared.loading;
  const error = batchId ? batchList.error : shared.error;
  const reload = async () => {
    await Promise.all([shared.reload(), batchId ? batchList.reload() : Promise.resolve()]);
  };
  const [disp, setDisp] = useState<Disposition | "">("");
  const [stateFilter, setStateFilter] = useState<State | "">("");
  const [query, setQuery] = useState("");
  const [shown, setShown] = useState(PAGE);
  const searchRef = useRef<HTMLInputElement>(null);

  const cfg = view === "all" ? null : QUEUE_VIEWS[view];
  const base = view === "all" ? "/all" : `/${view}`;

  useEffect(() => {
    setShown(PAGE);
  }, [view, disp, stateFilter, query]);

  const inView = useMemo(() => {
    const list = summaries.filter((s) => (cfg ? cfg.match(s) : true));
    return list;
  }, [summaries, cfg]);

  const filtered0 = useMemo(
    () =>
      inView.filter(
        (s) => (!disp || s.disposition === disp) && (!stateFilter || s.state === stateFilter),
      ),
    [inView, disp, stateFilter],
  );

  const details = useDetails(filtered0.slice(0, shown + PAGE));

  const worst = (id: string): number => {
    const ex = details.get(id)?.result?.exceptions ?? [];
    return ex.length === 0 ? 9 : Math.min(...ex.map((e) => severityRank(e.severity)));
  };

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = q
      ? filtered0.filter((s) => {
          const d = details.get(s.receipt_id)?.receipt;
          return [s.receipt_id, d?.merchant_name, d?.employee_id, d?.submitted_expense_type]
            .filter(Boolean)
            .some((v) => String(v).toLowerCase().includes(q));
        })
      : filtered0;
    return [...list].sort((a, b) =>
      view === "all"
        ? b.updated_at.localeCompare(a.updated_at)
        : worst(a.receipt_id) - worst(b.receipt_id) ||
          (DISP_ORDER[a.disposition ?? "pass"] ?? 3) - (DISP_ORDER[b.disposition ?? "pass"] ?? 3) ||
          a.updated_at.localeCompare(b.updated_at),
    );
  }, [filtered0, query, details, view]);

  const visible = filtered.slice(0, shown);
  const advance = (closedId: string) => {
    const i = visible.findIndex((s) => s.receipt_id === closedId);
    const next = visible.slice(i + 1).concat(visible.slice(0, Math.max(i, 0))).find((s) => s.receipt_id !== closedId && (cfg ? cfg.match(s) : true));
    navigate(next ? `${base}/${encodeURIComponent(next.receipt_id)}` + (batchId ? `?batch=${batchId}` : "") : base);
  };
  const index = visible.findIndex((s) => s.receipt_id === id);

  const move = (delta: number) => {
    if (visible.length === 0) return;
    const next = index < 0 ? 0 : Math.min(visible.length - 1, Math.max(0, index + delta));
    navigate(`${base}/${encodeURIComponent(visible[next].receipt_id)}`);
  };
  useShortcuts({
    j: () => move(1),
    k: () => move(-1),
    arrowdown: () => move(1),
    arrowup: () => move(-1),
    "/": () => searchRef.current?.focus(),
    escape: () => id && navigate(base),
  });

  const now = Date.now();
  return (
    <div className={`work${id ? " has-detail" : ""}`}>
      <section className="work__list" aria-label="Receipts">
        <div className="work__head">
          <h1 className="ll-display">{cfg ? cfg.title : "All receipts"}</h1>
          <p className="muted">
            {cfg ? cfg.hint : "Every receipt in the system, newest activity first."} · <span className="ll-num">{filtered.length}</span> shown
          </p>
          {batchId && (
            <div className="callout callout--accent">
              <span>
                Showing only batch <span className="ll-num">{batchId}</span>.
              </span>
              <button type="button" className="ll-btn ll-btn--secondary" onClick={() => setParams({})}>
                Show everything
              </button>
            </div>
          )}
          {view === "sample" && (
            <p className="callout callout--accent" role="note">
              Reading a receipt here does not take it off this list: the system has no “checked, fine” action yet. Reject a receipt if the engine missed something.
            </p>
          )}
          {total > summaries.length && (
            <p className="callout callout--warm" role="status">
              Showing {summaries.length} of {total} receipts: the most recent ones. Use a batch link or the filters to narrow the list.
            </p>
          )}
          <div className="filters">
            {(["", "flag", "review", "pass"] as const).map((d) => (
              <button
                key={d || "all"}
                type="button"
                className={`chip${disp === d ? " is-on" : ""}`}
                aria-pressed={disp === d}
                onClick={() => setDisp(d)}
              >
                {d === "" ? "All proposals" : `Proposed ${d}`}
              </button>
            ))}
            {view === "all" && (
              <select className="ll-select compact" aria-label="State" value={stateFilter} onChange={(e) => setStateFilter(e.target.value as State | "")}>
                <option value="">Any state</option>
                {STATES.map((s) => (
                  <option key={s} value={s}>
                    {STATE_LABEL[s]}
                  </option>
                ))}
              </select>
            )}
            <input
              ref={searchRef}
              className="ll-input compact search"
              type="search"
              placeholder="Search receipt, merchant, employee   /"
              aria-label="Search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
        </div>

        {error && summaries.length === 0 ? (
          <p className="callout callout--error">{error.message}</p>
        ) : loading && summaries.length === 0 ? (
          <p className="muted pad">Loading…</p>
        ) : filtered.length === 0 ? (
          <div className="empty">
            <p className="empty__lead">{cfg && !disp && !query ? cfg.empty : "No receipt matches these filters."}</p>
            <p className="muted">
              {summaries.length === 0 ? (
                <>
                  The system has no receipts yet. <Link to="/intake">Submit one or a batch</Link> to start.
                </>
              ) : (
                <>
                  <Link to="/all">See all {summaries.length} receipts</Link> or <Link to="/intake">submit more</Link>.
                </>
              )}
            </p>
          </div>
        ) : (
          <div className="table-scroll">
            <table className="ll-table queue">
              <thead>
                <tr>
                  <th>Proposal</th>
                  <th>Receipt</th>
                  <th>Merchant</th>
                  <th>Employee</th>
                  <th className="col-type">Declared type</th>
                  <th className="is-num">Total</th>
                  <th className="is-num">Findings</th>
                  <th>{view === "all" ? "State" : "Age"}</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((s: ReceiptSummary) => {
                  const d = details.get(s.receipt_id);
                  const n = findingCount(d);
                  return (
                    <tr key={s.receipt_id} className={s.receipt_id === id ? "is-selected" : ""}>
                      <td>
                        <DispositionBadge disposition={s.disposition} />
                        {s.notice && (
                          <span className="dot-notice" title={s.notice} aria-label="Result changed">
                            ●
                          </span>
                        )}
                      </td>
                      <td>
                        <Link to={`${base}/${encodeURIComponent(s.receipt_id)}${batchId ? `?batch=${batchId}` : ""}`} aria-current={s.receipt_id === id ? "true" : undefined}>
                          {s.receipt_id}
                        </Link>
                      </td>
                      <td className="cell-trunc">{d?.receipt.merchant_name ?? <span className="muted">…</span>}</td>
                      <td className="ll-num">{d ? `${d.receipt.employee_id} · ${d.receipt.entity}` : ""}</td>
                      <td className="cell-trunc col-type">{d?.receipt.submitted_expense_type ?? ""}</td>
                      <td className="is-num">{d ? usd(d.receipt.total_amount_usd) : ""}</td>
                      <td className="is-num">{n === null ? "—" : n}</td>
                      <td className={view === "all" ? "" : "is-muted"}>
                        {view === "all" ? <StateChip state={s.state} /> : ageOf(s.updated_at, now)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {filtered.length > shown && (
              <div className="more">
                <button type="button" className="ll-btn ll-btn--secondary" onClick={() => setShown((n) => n + PAGE)}>
                  Show {Math.min(PAGE, filtered.length - shown)} more
                </button>
              </div>
            )}
          </div>
        )}
        <p className="keys-hint muted">
          <span className="ll-kbd">J</span> <span className="ll-kbd">K</span> move · <span className="ll-kbd">?</span> shortcuts
        </p>
      </section>

      <div className="work__detail">
        {id ? (
          <>
            <Link className="back-link" to={base}>
              ← Back to the list
            </Link>
            <ReceiptPane id={id} onChanged={() => void reload()} onDecided={view === "all" ? undefined : advance} />
          </>
        ) : (
          <div className="pane-empty muted">
            <p>Select a receipt to read the verdict, the evidence and decide.</p>
          </div>
        )}
      </div>
    </div>
  );
}
