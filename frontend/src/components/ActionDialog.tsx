import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { ApiError, api } from "../api/client";
import type { Action, ActionBody, ActionResponse, ReasonCode, ReceiptDetail } from "../api/types";
import { ACTION_LABEL, CATEGORIES, categoryLabel, overrides, reasonsFor, showsReason } from "../lib/domain";
import { useActor } from "../lib/hooks";
import { Icon } from "./Icon";

export type DialogAction = Exclude<Action, never>;

/** Collects what an action needs, sends it with the evaluation version the auditor saw. */
export function ActionDialog({
  detail,
  action,
  initialLineId,
  onClose,
  onDone,
  onStale,
}: {
  detail: ReceiptDetail;
  action: DialogAction;
  initialLineId?: string;
  onClose: () => void;
  onDone: (updated: ActionResponse) => void;
  onStale: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const { actor, setActor } = useActor();
  const [actorDraft, setActorDraft] = useState(actor);
  const [reasonCode, setReasonCode] = useState<ReasonCode | "">("");
  const [note, setNote] = useState("");
  const [text, setText] = useState("");
  const [lineId, setLineId] = useState(initialLineId ?? detail.result?.line_items[0]?.line_id ?? "");
  const [category, setCategory] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stale, setStale] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (el && !el.open) el.showModal();
  }, []);

  const isDecision = action === "approve" || action === "reject";
  const needsReason = isDecision && overrides(action, detail.disposition);
  // Reject agreeing with the proposal has no reason to give: only the optional note (spec 008 FR-020).
  const withReason = isDecision && showsReason(action, detail.disposition);
  const line = detail.result?.line_items.find((l) => l.line_id === lineId);

  const missing = (() => {
    if (!actorDraft.trim()) return "Enter your name so the decision is recorded.";
    if (needsReason && !reasonCode) return "Choose a reason: this decision overrides the proposal.";
    if (isDecision && reasonCode === "other" && !note.trim()) return "Add a note for reason “Other”.";
    if (action === "request-info" && !text.trim()) return "Write the question for the employee.";
    if (action === "escalate" && !text.trim()) return "Say why this goes to Compliance.";
    if (action === "correct-category") {
      if (!lineId) return "Choose the line.";
      if (!category) return "Choose the correct category.";
    }
    return null;
  })();

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (missing || detail.evaluation_version === null) {
      setError(missing ?? "This receipt has no result yet.");
      return;
    }
    const body: ActionBody = { actor: actorDraft.trim(), evaluation_version: detail.evaluation_version };
    if (note.trim()) body.note = note.trim();
    if (withReason && reasonCode) body.reason_code = reasonCode;
    if (action === "request-info") body.question = text.trim();
    if (action === "escalate") body.reason = text.trim();
    if (action === "correct-category") {
      body.line_id = lineId;
      body.category = category;
    }
    setBusy(true);
    setError(null);
    try {
      setActor(actorDraft.trim());
      const updated = await api.act(detail.receipt_id, action, body);
      onDone(updated);
    } catch (err) {
      if (err instanceof ApiError && err.code === "stale_evaluation") {
        setStale(true);
        setError(
          `This receipt was re-evaluated while you were looking at it (now version ${String(
            err.body.details.current_evaluation_version ?? "?",
          )}). Read the new result and decide again.`,
        );
        onStale();
      } else if (err instanceof ApiError && err.code === "action_not_allowed") {
        setStale(true);
        setError("The receipt is no longer in a state that allows this action. It was refreshed.");
        onStale();
      } else {
        setError((err as Error).message);
      }
    } finally {
      setBusy(false);
    }
  }

  const title = ACTION_LABEL[action];
  const submitLabel =
    action === "request-info" ? "Send and hold" : action === "correct-category" ? "Re-run the rules" : action === "reject" ? "Reject expense" : action === "approve" && detail.disposition === "flag" ? "Approve anyway" : title;
  return (
    <dialog ref={ref} className="dialog" onClose={onClose} aria-labelledby="dlg-title">
      <form onSubmit={submit} className="dialog__body">
        <header className="dialog__head">
          <h3 id="dlg-title">
            {title} · <span className="ll-num">{detail.receipt_id}</span>
          </h3>
          <button type="button" className="icon-btn" onClick={() => ref.current?.close()} aria-label="Close">
            <Icon name="x" />
          </button>
        </header>

        {needsReason && (
          <p className="callout callout--warm">
            The engine proposed <strong>{detail.disposition}</strong>. {action === "approve" ? "Approving" : "Rejecting"} goes against that
            proposal, so a reason is required.
          </p>
        )}

        {isDecision && (
          <>
            {withReason && (
              <div className="ll-field">
                <label htmlFor="reason">Reason{needsReason ? "" : " (optional)"}</label>
                <select id="reason" className="ll-select" value={reasonCode} onChange={(e) => setReasonCode(e.target.value as ReasonCode | "")}>
                  <option value="">{needsReason ? "Choose a reason…" : "No reason"}</option>
                  {reasonsFor(action).map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.label}
                    </option>
                  ))}
                </select>
              </div>
            )}
            <div className="ll-field">
              <label htmlFor="note">Note{reasonCode === "other" ? "" : " (optional)"}</label>
              <textarea id="note" className="ll-input textarea" rows={3} value={note} onChange={(e) => setNote(e.target.value)} />
            </div>
          </>
        )}

        {action === "request-info" && (
          <div className="ll-field">
            <label htmlFor="question">Message to {detail.receipt.employee_id}</label>
            <textarea id="question" className="ll-input textarea" rows={3} value={text} onChange={(e) => setText(e.target.value)} autoFocus />
            <span className="hint">The receipt waits in “Waiting for information”; the employee's answer arrives as a new revision of the same receipt.</span>
          </div>
        )}

        {action === "escalate" && (
          <div className="ll-field">
            <label htmlFor="why">Why does this need Compliance?</label>
            <textarea id="why" className="ll-input textarea" rows={3} value={text} onChange={(e) => setText(e.target.value)} autoFocus />
          </div>
        )}

        {action === "correct-category" && (
          <>
            <div className="ll-field">
              <label htmlFor="line">Line</label>
              <select id="line" className="ll-select" value={lineId} onChange={(e) => setLineId(e.target.value)}>
                {(detail.result?.line_items ?? []).map((l) => (
                  <option key={l.line_id} value={l.line_id}>
                    {l.line_id} · {l.description_raw}
                  </option>
                ))}
              </select>
              {line && (
                <span className="hint">
                  Read as: {categoryLabel(line.category)}
                  {line.status === "unclassified" ? ` (${line.unclassified_reason ?? "not classified"})` : ""}
                </span>
              )}
            </div>
            <div className="ll-field">
              <label htmlFor="category">Correct category</label>
              <select id="category" className="ll-select" value={category} onChange={(e) => setCategory(e.target.value)}>
                <option value="">Choose a category…</option>
                {CATEGORIES.map((c) => (
                  <option key={c.id} value={c.id}>
                    {categoryLabel(c.id)}
                    {c.restricted ? " (restricted)" : ""}
                  </option>
                ))}
              </select>
              <span className="hint">
                The policy check runs again at once. The receipt stays with a person, and other receipts of the same employee-day or trip are checked again.
              </span>
            </div>
            <div className="ll-field">
              <label htmlFor="note2">Note (optional)</label>
              <textarea id="note2" className="ll-input textarea" rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
            </div>
          </>
        )}

        <div className="ll-field">
          <label htmlFor="actor">Your name</label>
          <input id="actor" className="ll-input" value={actorDraft} onChange={(e) => setActorDraft(e.target.value)} placeholder="Recorded with the decision" />
        </div>

        {error && (
          <p role="alert" className="callout callout--error">
            {error}
          </p>
        )}

        <footer className="dialog__foot">
          <button type="button" className="ll-btn ll-btn--secondary" onClick={() => ref.current?.close()}>
            {stale ? "Close and read the new result" : "Cancel"}
          </button>
          <button type="submit" className={`ll-btn ${action === "reject" ? "ll-btn--critical" : "ll-btn--primary"}`} disabled={busy || stale}>
            {busy ? "Saving…" : submitLabel}
          </button>
        </footer>
      </form>
    </dialog>
  );
}
