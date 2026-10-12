import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../api/client";
import type { Action, ActionResponse, ReceiptDetail, RevisionDetail } from "../api/types";
import { isInProgress, sortFindings, verdictLine } from "../lib/domain";
import { localStamp, money, recordedDate, usd } from "../lib/format";
import { useShortcuts, useToast, usePolling } from "../lib/hooks";
import { ActionDialog } from "./ActionDialog";
import { DispositionBadge, StateChip } from "./Badges";
import { DecisionBar, decisionKeys } from "./DecisionBar";
import { FindingCard, SignalCard } from "./FindingCard";
import { Icon } from "./Icon";
import { LineItems } from "./LineItems";
import { Timeline } from "./Timeline";

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="fact">
      <dt className="ll-label">{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

export function ReceiptPane({
  id,
  onChanged,
  onDecided,
}: {
  id: string;
  onChanged?: () => void;
  /** Called after a decision that closes or routes the receipt, so the list can open the next one. */
  onDecided?: (id: string) => void;
}) {
  const { toast } = useToast();
  const [dialog, setDialog] = useState<{ action: Action; lineId?: string } | null>(null);
  const [retrying, setRetrying] = useState(false);

  const detailQ = usePolling<ReceiptDetail>(() => api.getReceipt(id), [id], 3000);
  const eventsQ = usePolling(() => api.getEvents(id), [id, detailQ.data?.updated_at], 0);
  const detail = detailQ.data && detailQ.data.receipt_id === id ? detailQ.data : null;
  const revision = detail?.revision ?? 1;
  const revisionsQ = usePolling<RevisionDetail[]>(
    () => (revision > 1 ? Promise.all(Array.from({ length: revision }, (_, i) => api.getRevision(id, i + 1))) : Promise.resolve([])),
    [id, revision, detail?.updated_at],
    0,
  );

  useEffect(() => {
    setDialog(null);
  }, [id]);

  const keys = decisionKeys();
  useShortcuts(
    Object.fromEntries(
      Object.entries(keys).map(([key, action]) => [
        key,
        () => {
          if (detail?.allowed_actions.includes(action)) setDialog({ action });
        },
      ]),
    ),
    !!detail,
  );

  if (detailQ.error && !detail) {
    const notFound = detailQ.error instanceof ApiError && detailQ.error.status === 404;
    return (
      <div className="pane-empty">
        <p className="callout callout--error">{notFound ? `No receipt with the ID “${id}”.` : detailQ.error.message}</p>
      </div>
    );
  }
  if (!detail) return <div className="pane-empty muted">Loading receipt…</div>;

  const result = detail.result;
  const findings = sortFindings(result?.exceptions ?? []);
  const signals = result?.review_signals ?? [];
  const r = detail.receipt;
  const needsInfoQuestion =
    detail.state === "needs_info"
      ? [...(eventsQ.data ?? [])].reverse().find((e) => e.type === "InformationRequested")
      : undefined;

  async function retry() {
    setRetrying(true);
    try {
      await api.retry(id);
      toast("Retry started. The engine is working on it again.");
      void detailQ.reload();
      onChanged?.();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setRetrying(false);
    }
  }

  function done(updated: ActionResponse) {
    setDialog(null);
    const label: Record<Action, string> = {
      approve: "Approved",
      reject: "Rejected",
      "request-info": "Information requested",
      escalate: "Escalated to Compliance",
      "correct-category": "Category corrected, policy check run again",
    };
    const last = dialog?.action ?? "approve";
    toast(`${label[last]}: ${updated.receipt_id}.`);
    void detailQ.reload();
    void eventsQ.reload();
    onChanged?.();
    if (last !== "correct-category") onDecided?.(updated.receipt_id);
  }

  return (
    <section className="pane" aria-label={`Receipt ${detail.receipt_id}`}>
      <div className="pane__scroll">
        <header className="verdict">
          <div className="verdict__top">
            <h2 className="verdict__id ll-num">{detail.receipt_id}</h2>
            <DispositionBadge disposition={detail.disposition} proposed />
            <StateChip state={detail.state} />
            {detail.qa_sample && <span className="tag">quality sample</span>}
            {detail.revision > 1 && <span className="tag">revision {detail.revision}</span>}
          </div>
          <p className="verdict__line">{verdictLine(detail.disposition, findings, signals)}</p>
          <dl className="facts">
            <Fact label="Merchant">{r.merchant_name ?? "—"}</Fact>
            <Fact label="Employee">
              <span className="ll-num">{r.employee_id}</span> · {r.entity} · {r.employee_country}
            </Fact>
            <Fact label="Declared type">{r.submitted_expense_type}</Fact>
            <Fact label="Date">
              <span className="ll-num">{recordedDate(r.transaction_datetime)}</span>
            </Fact>
            <Fact label="Total">
              <span className="ll-num">
                {r.currency && r.currency !== "USD" && r.total_amount !== null
                  ? `${money(r.total_amount, r.currency)} × ${r.fx_rate_to_usd} = ${usd(r.total_amount_usd)}`
                  : usd(r.total_amount_usd)}
              </span>
            </Fact>
            <Fact label="Category code">
              <span className="ll-num">{r.mcc}</span> · {r.mcc_description}
            </Fact>
            {r.attendee_count !== null && <Fact label="Attendees">{r.attendee_count}</Fact>}
            {r.trip_id && (
              <Fact label="Trip">
                <span className="ll-num">{r.trip_id}</span>
                {r.trip_nights !== null ? ` · ${r.trip_nights} nights` : ""}
              </Fact>
            )}
            {r.pre_approval_ref && (
              <Fact label="Pre-approval">
                <span className="ll-num">{r.pre_approval_ref}</span>
              </Fact>
            )}
            {!r.itemized && <Fact label="Itemized">No</Fact>}
          </dl>
        </header>

        {detail.notice && (
          <div className="callout callout--accent" role="status">
            <strong>Result changed.</strong> {detail.notice}. Read the new result before you decide; your next action clears this notice.
          </div>
        )}
        {detail.failed && (
          <div className="callout callout--error" role="alert">
            <div>
              <strong>Processing failed at “{detail.failed.stage}”.</strong>
              {detail.failed.reason ? ` ${detail.failed.reason}` : ""}
              {detail.state !== "failed" ? " The receipt keeps its last result and state." : ""}
            </div>
            <button type="button" className="ll-btn ll-btn--secondary" onClick={retry} disabled={retrying}>
              <Icon name="refresh" />
              {retrying ? "Retrying…" : "Retry"}
            </button>
          </div>
        )}
        {isInProgress(detail.state) && (
          <div className="callout callout--accent" role="status">
            <Icon name="clock" /> The engine is reading the items and checking the policies. This page updates by itself.
          </div>
        )}
        {detail.state === "compliance" && (
          <div className="callout callout--critical">
            <strong>With Compliance.</strong> This case is handled by the Compliance team: a critical finding or an escalation.
          </div>
        )}
        {detail.state === "needs_info" && (
          <div className="callout callout--accent">
            <strong>Waiting for information.</strong>{" "}
            {needsInfoQuestion ? <>You asked: “{String(needsInfoQuestion.payload.question)}”</> : null}
          </div>
        )}
        {detail.state === "auto_approved" && detail.qa_sample && (
          <div className="callout callout--accent">
            <strong>Selected for a quality check.</strong> The engine passed this receipt without a person. Read the items and findings below and reject it if the engine missed something.
          </div>
        )}

        {result && (
          <>
            <h3 className="ll-heading">
              Findings <span className="muted">({findings.length})</span>
            </h3>
            {findings.length === 0 ? (
              <p className="muted">No policy exception found{signals.length > 0 ? ", but the engine left something for a person to look at." : "."}</p>
            ) : (
              <div className="stack">
                {findings.map((f) => (
                  <FindingCard key={`${f.rule_id}-${f.line_ids.join(",")}`} finding={f} />
                ))}
              </div>
            )}
            {signals.length > 0 && (
              <div className="stack">
                {signals.map((s) => (
                  <SignalCard key={`${s.rule_id}-${s.line_ids.join(",")}`} signal={s} />
                ))}
              </div>
            )}
          </>
        )}

        <h3 className="ll-heading">
          Line items <span className="muted">({r.line_items.length})</span>
        </h3>
        <LineItems detail={detail} onCorrect={(lineId) => setDialog({ action: "correct-category", lineId })} />

        {(revisionsQ.data?.length ?? 0) > 0 && (
          <>
            <h3 className="ll-heading">Revisions</h3>
            <ul className="revisions">
              {revisionsQ.data!.map((rev) => (
                <li key={rev.revision}>
                  <strong>Revision {rev.revision}</strong> · {rev.status} · submitted <span className="ll-num">{localStamp(rev.created_at)}</span>
                  <div className="muted">
                    {rev.evaluations.length === 0
                      ? "No policy check recorded."
                      : rev.evaluations
                          .map((e) => `v${e.version}: ${e.result.disposition} (${e.result.exceptions.length} finding${e.result.exceptions.length === 1 ? "" : "s"})`)
                          .join(" → ")}
                  </div>
                </li>
              ))}
            </ul>
          </>
        )}

        <h3 className="ll-heading">
          Audit trail{" "}
          <Link className="ll-heading__link" to={`/history/${encodeURIComponent(detail.receipt_id)}`}>
            History and versions
          </Link>
        </h3>
        <Timeline events={eventsQ.data ?? []} currentRevision={detail.revision} />
        {result && (
          <p className="versions ll-num">
            Policy set {result.run.rules_version} · Classifier {result.run.prompt_version} · Result version {detail.evaluation_version}
          </p>
        )}
        <p className="muted back-link-wrap">
          <Link to={`/intake?revise=${encodeURIComponent(detail.receipt_id)}`}>Submit a corrected revision of this receipt</Link> (same receipt ID).
        </p>
      </div>

      <DecisionBar detail={detail} onAction={(action) => setDialog({ action })} />

      {dialog && (
        <ActionDialog
          key={`${dialog.action}-${dialog.lineId ?? ""}`}
          detail={detail}
          action={dialog.action}
          initialLineId={dialog.lineId}
          onClose={() => setDialog(null)}
          onDone={done}
          onStale={() => {
            void detailQ.reload();
            void eventsQ.reload();
            onChanged?.();
          }}
        />
      )}
    </section>
  );
}
