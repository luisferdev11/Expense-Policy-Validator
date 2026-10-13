import { useEffect, useMemo, useRef, useState } from "react";
import type { DragEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ApiError, api } from "../api/client";
import type { BatchResponse, ReceiptDetail, RowOutcome, State, SubmitResponse } from "../api/types";
import { DispositionBadge, StateChip } from "../components/Badges";
import { Icon } from "../components/Icon";
import { ReceiptForm } from "../components/ReceiptForm";
import { STATES, STATE_LABEL, isInProgress, sortFindings } from "../lib/domain";
import { usd } from "../lib/format";
import { clearDraft, loadDraft, saveDraft } from "../lib/draft";
import type { IntakeDraft } from "../lib/draft";
import { useDetails, usePolling, useToast } from "../lib/hooks";
import { planIntake, refusedRowsText, sourceRows } from "../lib/intake";
import { emptyForm, formToReceipt, receiptToForm, serverErrors, validateForm } from "../lib/receiptForm";
import type { FieldError, ReceiptFormState } from "../lib/receiptForm";
import { useReceipts } from "../lib/receipts";
import { SAMPLE_BATCH, SAMPLE_RECEIPT } from "../samples/samples";

const OUTCOME_TEXT: Record<RowOutcome, string> = {
  accepted: "Accepted",
  existing: "Already known",
  revision: "New revision",
  invalid: "Rejected, not saved",
  duplicate_in_batch: "Repeated in this batch",
};

const OUTCOME_HELP: Record<string, string> = {
  accepted: "A new receipt. The engine is reading it now.",
  existing: "The system already has exactly this receipt, so nothing was started.",
  revision: "The same receipt ID with different content. It replaces the earlier one, which stays in its history, and the check starts again.",
};

const STATE_NOTE: Partial<Record<State, string>> = {
  submitted: "Received, waiting for the engine",
  classifying: "Reading the items",
  in_review: "In review with an auditor",
  compliance: "Sent to Compliance: critical finding or escalation, never the audit queue",
  auto_approved: "Approved automatically",
  needs_info: "Waiting for information from the employee",
};

type Mode = "form" | "single" | "batch";

const MODE_LABEL: Record<Mode, string> = {
  form: "One receipt (form)",
  single: "One receipt (JSON)",
  batch: "A batch",
};

function download(name: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "application/x-ndjson" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

export function IntakePage() {
  const [params, setParams] = useSearchParams();
  const { reload } = useReceipts();
  const { toast } = useToast();
  const revise = params.get("revise");
  // A draft is restored once, on arrival, unless the person came to revise a stored receipt.
  const [restored] = useState(() => (revise ? null : loadDraft()));
  const [restoredAt, setRestoredAt] = useState<string | null>(restored?.savedAt ?? null);
  const [mode, setMode] = useState<Mode>(restored?.mode ?? "batch");
  const [text, setText] = useState(restored?.text ?? "");
  const [fileName, setFileName] = useState<string | null>(null);
  const [key, setKey] = useState(restored?.idempotencyKey ?? "");
  // The draft is written only after the person has edited something this visit, and not again after a send.
  const [touched, setTouched] = useState(false);
  const sent = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ message: string; fields?: string[] } | null>(null);
  const [single, setSingle] = useState<SubmitResponse | null>(null);
  const [batch, setBatch] = useState<{ response: BatchResponse; rows: string[]; sentAt: Date; fileName: string | null } | null>(null);
  const [dragging, setDragging] = useState(false);
  const [form, setForm] = useState<ReceiptFormState>(() => restored?.form ?? emptyForm());
  const [attempted, setAttempted] = useState(false);
  const [serverFields, setServerFields] = useState<{ mapped: FieldError[]; unmapped: string[] } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const plan = useMemo(() => planIntake(text), [text]);
  const inForm = mode === "form";

  // The mode follows what was pasted or loaded between the two text modes; the form is never left on its own.
  useEffect(() => {
    if (mode === "form") return;
    if (plan.kind === "single") setMode("single");
    else if (plan.kind === "batch") setMode("batch");
  }, [plan.kind, mode]);

  const formErrors = useMemo(
    () => (attempted ? [...validateForm(form), ...(serverFields?.mapped ?? [])] : (serverFields?.mapped ?? [])),
    [attempted, form, serverFields],
  );

  /** Every edit by the person goes through here: it makes the draft worth saving again. */
  function edited() {
    sent.current = false;
    setTouched(true);
  }

  function changeForm(next: ReceiptFormState) {
    edited();
    reset();
    setServerFields(null);
    setForm(next);
  }

  function discardDraft() {
    clearDraft();
    sent.current = true;
    setRestoredAt(null);
    setForm(emptyForm());
    setText("");
    setKey("");
    setFileName(null);
    setAttempted(false);
    setServerFields(null);
    reset();
  }

  // Keep what is being typed in this browser: debounced while typing, flushed when the page goes away.
  const latest = useRef<IntakeDraft | null>(null);
  latest.current = { version: 1, mode, form, text, idempotencyKey: key, savedAt: new Date().toISOString() };
  useEffect(() => {
    if (!touched || sent.current) return;
    const timer = setTimeout(() => {
      if (!sent.current && latest.current) saveDraft(latest.current);
    }, 400);
    return () => clearTimeout(timer);
  }, [mode, form, text, key, touched]);
  useEffect(() => {
    const flush = () => {
      if (touched && !sent.current && latest.current) saveDraft(latest.current);
    };
    window.addEventListener("pagehide", flush);
    return () => window.removeEventListener("pagehide", flush);
  }, [touched]);

  // "Submit a corrected revision": prefill with the current stripped receipt.
  useEffect(() => {
    if (!revise) return;
    let cancelled = false;
    api
      .getReceipt(revise)
      .then((d) => {
        if (!cancelled) setText(JSON.stringify(d.receipt, null, 2));
      })
      .catch((e: Error) => !cancelled && setError({ message: e.message }));
    return () => {
      cancelled = true;
    };
  }, [revise]);

  function reset() {
    setSingle(null);
    setBatch(null);
    setError(null);
  }

  async function submit() {
    reset();
    setServerFields(null);
    if (inForm) {
      setAttempted(true);
      if (validateForm(form).length > 0) return;
    } else if (plan.kind === "empty" || plan.kind === "invalid") {
      return;
    }
    setBusy(true);
    try {
      if (inForm || plan.kind === "single") {
        const body = inForm ? formToReceipt(form) : plan.kind === "single" ? plan.receipt : null;
        const res = await api.submitReceipt(body, key.trim() || undefined);
        setSingle(res);
        toast(`${res.receipt_id}: ${OUTCOME_TEXT[res.outcome].toLowerCase()}.`);
      } else if (plan.kind === "batch") {
        const res = await api.submitBatch(plan.body, plan.contentType);
        setBatch({ response: res, rows: sourceRows(plan), sentAt: new Date(), fileName });
        toast(`Batch ${res.batch_id}: ${res.total} row${res.total === 1 ? "" : "s"} processed.`);
      }
      // Sent: the draft has done its job. It stays gone until the person edits again.
      sent.current = true;
      clearDraft();
      setRestoredAt(null);
      void reload();
    } catch (e) {
      if (e instanceof ApiError) {
        const fields = (e.body.details as { fields?: string[] }).fields;
        if (inForm && e.code === "invalid_receipt") {
          const placed = serverErrors(fields ?? [], form);
          if (placed.mapped.length + placed.unmapped.length > 0) {
            setServerFields(placed);
            return;
          }
        }
        const messages: Record<string, string> = {
          idempotency_key_reuse: "This idempotency key was already used with different content. Use a new key, or leave it empty.",
        };
        setError({ message: messages[e.code] ?? e.message, fields });
      } else {
        setError({ message: (e as Error).message });
      }
    } finally {
      setBusy(false);
    }
  }

  async function readFile(file: File) {
    edited();
    reset();
    setFileName(file.name);
    setText(await file.text());
    if (params.get("revise")) setParams({});
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) void readFile(file);
  }

  const summary =
    plan.kind === "single"
      ? `One receipt: ${plan.receiptId}`
      : plan.kind === "batch"
        ? `A batch of ${plan.rows} row${plan.rows === 1 ? "" : "s"} (${plan.contentType === "application/json" ? "JSON array" : "JSON Lines"})`
        : plan.kind === "invalid"
          ? plan.message
          : "";

  const showDrop = mode === "batch" && text.trim() === "";
  const mismatch =
    (mode === "single" && plan.kind === "batch") || (mode === "batch" && plan.kind === "single");

  return (
    <div className="page">
      <div>
        <h1 className="ll-display">Intake</h1>
        <p className="muted lead">
          Send one receipt or a batch. Each receipt is saved before any work starts, so a dropped connection never loses it, and sending it again finds the one we already have.
        </p>
      </div>

      <div className={`intake-grid${inForm ? " intake-grid--form" : ""}`}>
        <section className="ll-panel" aria-labelledby="send-h">
          <h2 className="ll-heading" id="send-h">
            Send receipts
          </h2>
          <form
            noValidate
            onSubmit={(e) => {
              e.preventDefault();
              void submit();
            }}
          >
          <div role="group" aria-label="What to send" className="row gap" style={{ marginTop: 0 }}>
            {(["form", "single", "batch"] as const).map((m) => (
              <button key={m} type="button" className={`chip${mode === m ? " is-on" : ""}`} aria-pressed={mode === m} onClick={() => (edited(), setMode(m))}>
                {MODE_LABEL[m]}
              </button>
            ))}
          </div>
          {revise && (
            <p className="callout callout--accent">
              Editing a copy of <strong className="ll-num">{revise}</strong>. Change what is wrong and send it: it becomes a new revision of the same receipt.
            </p>
          )}
          {restoredAt && (
            <p className="callout callout--accent" role="status">
              <span>Draft restored from {new Date(restoredAt).toLocaleString()}.</span>
              <button type="button" className="ll-btn ll-btn--secondary" onClick={discardDraft}>
                Discard draft
              </button>
            </p>
          )}
          {inForm && <ReceiptForm form={form} onChange={changeForm} errors={formErrors} unmapped={serverFields?.unmapped ?? []} />}
          {!inForm && (
          <div
            className={`drop${dragging ? " is-over" : ""}`}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
          >
            {showDrop && (
              <button type="button" className="dropzone" onClick={() => fileRef.current?.click()}>
                <Icon name="upload" size={24} />
                <span className="dropzone__lead">Drop a .jsonl or .json file, or choose one</span>
                <span className="muted dropzone__hint">One receipt per line, or a JSON array. Up to 1,000 receipts per batch. Or paste below.</span>
              </button>
            )}
            <label htmlFor="intake-text" className="ll-label">
              {mode === "single" ? "Receipt JSON" : "Batch (JSON Lines or a JSON array)"}
              {fileName && text ? ` · ${fileName}` : ""}
            </label>
            <textarea
              id="intake-text"
              className="ll-input textarea mono"
              aria-label="Receipt JSON or batch"
              rows={showDrop ? 5 : 14}
              wrap="off"
              spellCheck={false}
              value={text}
              placeholder={mode === "single" ? '{ "receipt_id": "R-1", "employee_id": "E-1001", … }' : '{"receipt_id": "R-1", …}\n{"receipt_id": "R-2", …}'}
              onChange={(e) => {
                reset();
                setFileName(null);
                edited();
                setText(e.target.value);
              }}
            />
          </div>
          )}
          <input
            ref={fileRef}
            type="file"
            accept=".json,.jsonl,.ndjson,application/json,text/plain"
            hidden
            data-testid="file-input"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void readFile(f);
              e.target.value = "";
            }}
          />
          {inForm ? (
            <div className="row gap" style={{ marginTop: 0 }}>
              <button type="button" className="ll-btn ll-btn--ghost" onClick={() => changeForm(receiptToForm(JSON.parse(SAMPLE_RECEIPT) as Record<string, unknown>).form)}>
                Load a sample receipt
              </button>
            </div>
          ) : (
            <div className="row gap" style={{ marginTop: 0 }}>
              <button type="button" className="ll-btn ll-btn--secondary" onClick={() => fileRef.current?.click()}>
                <Icon name="upload" />
                Choose a file
              </button>
              <button type="button" className="ll-btn ll-btn--ghost" onClick={() => (edited(), reset(), setFileName(null), setMode("single"), setText(SAMPLE_RECEIPT))}>
                Load a sample receipt
              </button>
              <button type="button" className="ll-btn ll-btn--ghost" onClick={() => (edited(), reset(), setFileName(null), setMode("batch"), setText(SAMPLE_BATCH))}>
                Load a sample batch
              </button>
            </div>
          )}
          {!inForm && summary && (
            <p className={`intake-summary${plan.kind === "invalid" ? " is-bad" : ""}`} aria-live="polite">
              {summary}
              {mismatch ? ` — switched to ${plan.kind === "batch" ? "“A batch”" : "“One receipt”"}.` : ""}
            </p>
          )}
          {(plan.kind === "single" || inForm) && (
            <div className="ll-field">
              <label htmlFor="idem">Idempotency key (optional)</label>
              <input id="idem" className="ll-input" value={key} maxLength={255} onChange={(e) => (edited(), setKey(e.target.value))} placeholder="e.g. upload-2026-10-10-001" />
              <span className="hint">Sending the same key again never creates a second receipt. Using it with different content is refused.</span>
            </div>
          )}
          <div className="row">
            <button type="submit" className="ll-btn ll-btn--primary" disabled={busy || (!inForm && (plan.kind === "empty" || plan.kind === "invalid"))}>
              {busy ? "Validating…" : "Validate"}
            </button>
            <span className="hint">{inForm ? "The form checks only what the server would refuse; the policy checks run after you send." : "Answer fields such as labels are ignored if present."}</span>
          </div>
          </form>
          {error && (
            <div role="alert" className="callout callout--error">
              <div>
                <strong>Not submitted.</strong> {error.message}
                {error.fields && error.fields.length > 0 && (
                  <div className="fields">
                    Fields to check: {error.fields.map((f) => <code key={f}>{f}</code>)}
                  </div>
                )}
              </div>
            </div>
          )}
          <div className="retry-help">
            <h3 className="ll-heading">What a retry does</h3>
            <ul>
              <li>
                <strong>Same receipt, sent again:</strong> you get the one we have, with its current state. Nothing runs twice.
              </li>
              <li>
                <strong>Same ID, changed content:</strong> saved as a new revision and evaluated; the earlier revision stays in its history.
              </li>
              <li>
                <strong>Connection lost mid-batch:</strong> finished receipts keep their state; the rest resume where they stopped.
              </li>
            </ul>
          </div>
        </section>

        <div className="stack-col">
          {!single && !batch && (
            <section className="ll-panel result-empty" aria-label="Results">
              <h2 className="ll-heading">Results appear here</h2>
              <p className="muted">After you validate, each row shows what happened to it and moves through its states live: received, reading the items, evaluated, then approved automatically, in review or with Compliance.</p>
            </section>
          )}
          {single && (
            <section className="ll-panel result" aria-label="Submission result">
              <h2 className="ll-heading">Result</h2>
              <p>
                <strong>{OUTCOME_TEXT[single.outcome]}.</strong> {OUTCOME_HELP[single.outcome]}
                {single.superseded ? " This key belongs to a revision that a newer one has replaced." : ""}
              </p>
              <p>
                <Link to={`/all/${encodeURIComponent(single.receipt_id)}`} className="ll-num">
                  {single.receipt_id}
                </Link>{" "}
                · revision {single.revision} · <StateChip state={single.state} />
              </p>
            </section>
          )}
          {batch && <BatchResult key={batch.response.batch_id} initial={batch.response} rows={batch.rows} sentAt={batch.sentAt} fileName={batch.fileName} />}
          <section className="ll-panel" aria-labelledby="states-h">
            <h2 className="ll-heading" id="states-h">
              Each row moves through these states, live
            </h2>
            <ol className="flow" aria-label="Receipt states">
              <li>Received</li>
              <li aria-hidden="true">→</li>
              <li>Reading the items</li>
              <li aria-hidden="true">→</li>
              <li>Evaluated</li>
              <li aria-hidden="true">→</li>
              <li className="flow--pass">Approved automatically</li>
              <li className="muted">or</li>
              <li className="flow--low">In review</li>
              <li className="muted">or</li>
              <li className="flow--critical">Compliance</li>
            </ol>
            <p className="muted">
              A stage that fails is retried from that stage; nothing failed is ever passed. <Link to="/how-it-works">How it works</Link>
            </p>
          </section>
        </div>
      </div>
    </div>
  );
}

function BatchResult({
  initial,
  rows,
  sentAt,
  fileName,
}: {
  initial: BatchResponse;
  rows: string[];
  sentAt: Date;
  fileName: string | null;
}) {
  const poll = usePolling<BatchResponse>(() => api.getBatch(initial.batch_id), [initial.batch_id], 2000);
  const list = usePolling(() => api.listReceipts({ batch_id: initial.batch_id, limit: 500 }), [initial.batch_id], 2000);
  const batch = poll.data ?? initial;
  const summaries = list.data?.items ?? [];
  const details = useDetails(summaries);
  const { reload } = useReceipts();
  const { toast } = useToast();
  const working = batch.items.some((i) => i.state !== null && isInProgress(i.state));
  const failed = batch.items.filter((i) => i.state === "failed" && i.receipt_id);
  const refused = refusedRowsText(batch.items, rows);

  async function retryAll() {
    let ok = 0;
    for (const i of failed) {
      try {
        await api.retry(i.receipt_id!);
        ok += 1;
      } catch (e) {
        toast(`${i.receipt_id}: ${(e as Error).message}`, "error");
      }
    }
    if (ok > 0) toast(`Retry started for ${ok} receipt${ok === 1 ? "" : "s"}.`);
    void poll.reload();
    void reload();
  }

  const countsOrder = [...STATES.map((s) => s as string), "invalid", "duplicate_in_batch"];
  const counts = countsOrder.filter((k) => batch.counts[k]);
  const detailOf = (id: string | null): ReceiptDetail | undefined => (id ? details.get(id) : undefined);

  return (
    <section className="ll-panel result" aria-label="Batch result">
      <div className="batch-head">
        <h2 className="ll-heading">
          Batch <span className="ll-num">{batch.batch_id}</span>
        </h2>
        <span className="muted">
          {fileName ? `${fileName} · ` : ""}
          {batch.total} row{batch.total === 1 ? "" : "s"} · sent <span className="ll-num">{sentAt.toLocaleString()}</span>
        </span>
      </div>
      <div className="chips">
        {counts.map((k) => (
          <span key={k} className="count-chip">
            <strong className="ll-num">{batch.counts[k]}</strong>{" "}
            {k === "invalid" ? "refused" : k === "duplicate_in_batch" ? "repeated" : STATE_LABEL[k as State].toLowerCase()}
          </span>
        ))}
        {working && <span className="muted">Working… this updates by itself.</span>}
        {!working && counts.length > 0 && <span className="muted">Done.</span>}
      </div>
      <div className="table-scroll">
        <table className="ll-table">
          <thead>
            <tr>
              <th className="is-num">Row</th>
              <th>Receipt</th>
              <th className="is-num">USD</th>
              <th>State</th>
              <th>Proposed</th>
            </tr>
          </thead>
          <tbody>
            {batch.items.map((i) => {
              const d = detailOf(i.receipt_id);
              const findings = sortFindings(d?.result?.exceptions ?? []);
              const bad = i.outcome === "invalid" || i.outcome === "duplicate_in_batch";
              return (
                <tr key={i.row} className={bad ? "row-bad" : ""}>
                  <td className="is-num">{i.row}</td>
                  <td className="wrap">
                    {i.receipt_id ? <Link to={`/all/${encodeURIComponent(i.receipt_id)}`}>{i.receipt_id}</Link> : <span className="muted">—</span>}
                    {d && (
                      <div className="sub">
                        {d.receipt.merchant_name ?? "—"} · {d.receipt.employee_id}
                      </div>
                    )}
                  </td>
                  <td className="is-num">{d ? usd(d.receipt.total_amount_usd) : "—"}</td>
                  <td className="wrap">
                    {bad ? (
                      <>
                        <span className="outcome outcome--invalid">{OUTCOME_TEXT[i.outcome]}</span>
                        <div className="sub">{i.error ?? "Fix the row and send it again."}</div>
                      </>
                    ) : (
                      <>
                        {i.state ? <StateChip state={i.state} /> : null}
                        {i.outcome !== "accepted" && <span className="tag">{OUTCOME_TEXT[i.outcome].toLowerCase()}</span>}
                        <div className="sub">
                          {i.state === "failed" ? (
                            <>
                              Failed at “{d?.failed?.stage ?? "a stage"}”.{" "}
                              <button type="button" className="link-btn" onClick={() => api.retry(i.receipt_id!).then(() => (void poll.reload(), void reload()), (e: Error) => toast(e.message, "error"))}>
                                Retry
                              </button>
                            </>
                          ) : i.state ? (
                            STATE_NOTE[i.state] ?? ""
                          ) : (
                            ""
                          )}
                        </div>
                      </>
                    )}
                  </td>
                  <td>
                    {!bad && d ? (
                      <>
                        <DispositionBadge disposition={d.disposition} />
                        {findings.slice(0, 3).map((f) => (
                          <span key={f.rule_id + f.line_ids.join()} className={`ll-chip ll-chip--${f.severity} chip-gap ll-num`}>
                            {f.rule_id}
                          </span>
                        ))}
                      </>
                    ) : (
                      ""
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="row gap">
        <Link className="ll-btn ll-btn--primary" to={`/all?batch=${encodeURIComponent(batch.batch_id)}`}>
          Open in the review queue
        </Link>
        <button type="button" className="ll-btn ll-btn--secondary" disabled={!refused} onClick={() => download(`${batch.batch_id}-refused.jsonl`, refused)}>
          Download rejected rows
        </button>
        <button type="button" className="ll-btn ll-btn--secondary" disabled={failed.length === 0} onClick={retryAll}>
          Retry failed ({failed.length})
        </button>
      </div>
      <p className="muted">Refused rows stored nothing. Submitting this same batch again starts no new work: receipts that exist are reported as already known.</p>
    </section>
  );
}
