import { useEffect, useMemo, useRef, useState } from "react";
import type { DragEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ApiError, api } from "../api/client";
import type { BatchResponse, RowOutcome, State, SubmitResponse } from "../api/types";
import { StateChip } from "../components/Badges";
import { Icon } from "../components/Icon";
import { STATES, STATE_LABEL, isInProgress } from "../lib/domain";
import { usePolling, useToast } from "../lib/hooks";
import { planIntake } from "../lib/intake";
import { useReceipts } from "../lib/receipts";
import { SAMPLE_BATCH, SAMPLE_RECEIPT } from "../samples/samples";

const OUTCOME_TEXT: Record<RowOutcome, string> = {
  accepted: "Accepted",
  existing: "Already known",
  revision: "New revision",
  invalid: "Refused",
  duplicate_in_batch: "Repeated in this batch",
};

const OUTCOME_HELP: Record<string, string> = {
  accepted: "A new receipt. The engine is reading it now.",
  existing: "The system already has exactly this receipt, so nothing was started.",
  revision: "The same receipt ID with different content. It replaces the earlier one, which stays in the trail, and the check starts again.",
};

export function IntakePage() {
  const [params, setParams] = useSearchParams();
  const { reload } = useReceipts();
  const { toast } = useToast();
  const [text, setText] = useState("");
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ message: string; fields?: string[] } | null>(null);
  const [single, setSingle] = useState<SubmitResponse | null>(null);
  const [batch, setBatch] = useState<BatchResponse | null>(null);
  const [dragging, setDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const plan = useMemo(() => planIntake(text), [text]);

  // "Submit a corrected revision": prefill with the current stripped receipt.
  const revise = params.get("revise");
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
    if (plan.kind === "empty" || plan.kind === "invalid") return;
    setBusy(true);
    try {
      if (plan.kind === "single") {
        const res = await api.submitReceipt(plan.receipt, key.trim() || undefined);
        setSingle(res);
        toast(`${res.receipt_id}: ${OUTCOME_TEXT[res.outcome].toLowerCase()}.`);
      } else {
        const res = await api.submitBatch(plan.body, plan.contentType);
        setBatch(res);
        toast(`Batch ${res.batch_id}: ${res.total} row${res.total === 1 ? "" : "s"} processed.`);
      }
      void reload();
    } catch (e) {
      if (e instanceof ApiError) {
        const fields = (e.body.details as { fields?: string[] }).fields;
        const messages: Record<string, string> = {
          idempotency_key_reuse: "This idempotency key was already used with different content. Use a new key, or leave it empty.",
          invalid_batch: e.message,
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
    reset();
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
          : "Paste a receipt or a batch, or drop a file here.";

  return (
    <div className="page">
      <h1 className="ll-display">Submit receipts</h1>
      <p className="muted lead">
        Send one receipt (JSON) or a batch (a JSON array, or one JSON receipt per line). The engine reads each item, checks the nine policies and proposes a verdict. A
        person decides.
      </p>

      <div className="two-col">
        <section className="ll-panel">
          <h2 className="ll-heading">Receipt data</h2>
          {revise && (
            <p className="callout callout--accent">
              Editing a copy of <strong className="ll-num">{revise}</strong>. Change what is wrong and submit: it becomes a new revision of the same receipt.
            </p>
          )}
          <div
            className={`drop${dragging ? " is-over" : ""}`}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
          >
            <textarea
              className="ll-input textarea mono"
              aria-label="Receipt JSON or batch"
              rows={16}
              wrap="off"
              spellCheck={false}
              value={text}
              placeholder='{"receipt_id": "R-1", ...}'
              onChange={(e) => {
                reset();
                setText(e.target.value);
              }}
            />
          </div>
          <div className="row gap">
            <button type="button" className="ll-btn ll-btn--secondary" onClick={() => fileRef.current?.click()}>
              <Icon name="upload" />
              Choose a file
            </button>
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
            <button type="button" className="ll-btn ll-btn--ghost" onClick={() => (reset(), setText(SAMPLE_RECEIPT))}>
              Load a sample receipt
            </button>
            <button type="button" className="ll-btn ll-btn--ghost" onClick={() => (reset(), setText(SAMPLE_BATCH))}>
              Load a sample batch
            </button>
          </div>
          <p className={`intake-summary${plan.kind === "invalid" ? " is-bad" : ""}`} aria-live="polite">
            {summary}
          </p>
          {plan.kind === "single" && (
            <div className="ll-field">
              <label htmlFor="idem">Idempotency key (optional)</label>
              <input id="idem" className="ll-input" value={key} maxLength={255} onChange={(e) => setKey(e.target.value)} placeholder="e.g. upload-2026-10-10-001" />
              <span className="hint">Sending the same key again never creates a second receipt. Using it with different content is refused.</span>
            </div>
          )}
          <div className="row">
            <button type="button" className="ll-btn ll-btn--primary" disabled={busy || plan.kind === "empty" || plan.kind === "invalid"} onClick={submit}>
              {busy ? "Submitting…" : plan.kind === "batch" ? "Submit batch" : "Submit receipt"}
            </button>
          </div>
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
        </section>

        <section className="ll-panel how">
          <h2 className="ll-heading">What happens next</h2>
          <ol>
            <li>
              <strong>Accepted.</strong> Each receipt gets a state and the engine starts. Answer keys, if present, are discarded.
            </li>
            <li>
              <strong>Read and checked.</strong> Items are read, policies applied, and the verdict is proposed: Flag, Review or Pass.
            </li>
            <li>
              <strong>Decided.</strong> Passes close on their own. Everything else waits in the <Link to="/queue">review queue</Link>; critical cases go to{" "}
              <Link to="/compliance">Compliance</Link>.
            </li>
            <li>
              <strong>Same receipt ID, different content</strong> is a new revision: it replaces the earlier one and starts the check again. The earlier decision stays in the trail.
            </li>
          </ol>
        </section>
      </div>

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
      {batch && <BatchResult initial={batch} />}
    </div>
  );
}

function BatchResult({ initial }: { initial: BatchResponse }) {
  const poll = usePolling<BatchResponse>(() => api.getBatch(initial.batch_id), [initial.batch_id], 2000);
  const batch = poll.data ?? initial;
  const { reload } = useReceipts();
  const { toast } = useToast();
  const working = batch.items.some((i) => i.state !== null && isInProgress(i.state));
  const stateOf = (i: BatchResponse["items"][number]): State | null => i.state;

  async function retry(id: string) {
    try {
      await api.retry(id);
      toast(`Retry started for ${id}.`);
      void poll.reload();
      void reload();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  }

  const countsOrder = [...STATES.map((s) => s as string), "invalid", "duplicate_in_batch"];
  const counts = countsOrder.filter((k) => batch.counts[k]);

  return (
    <section className="ll-panel result" aria-label="Batch result">
      <h2 className="ll-heading">
        Batch <span className="ll-num">{batch.batch_id}</span> · {batch.total} row{batch.total === 1 ? "" : "s"}
      </h2>
      <div className="chips">
        {counts.map((k) => (
          <span key={k} className="count-chip">
            <strong className="ll-num">{batch.counts[k]}</strong>{" "}
            {k === "invalid" ? "refused" : k === "duplicate_in_batch" ? "repeated" : STATE_LABEL[k as State]}
          </span>
        ))}
        {working && <span className="muted">Working… this updates by itself.</span>}
        {!working && counts.length > 0 && <span className="muted">Done.</span>}
      </div>
      <div className="table-scroll">
        <table className="ll-table ll-table--compact">
          <thead>
            <tr>
              <th className="is-num">Row</th>
              <th>Receipt</th>
              <th>Outcome</th>
              <th>State now</th>
              <th>Detail</th>
            </tr>
          </thead>
          <tbody>
            {batch.items.map((i) => (
              <tr key={i.row}>
                <td className="is-num">{i.row}</td>
                <td>{i.receipt_id ? <Link to={`/all/${encodeURIComponent(i.receipt_id)}`}>{i.receipt_id}</Link> : <span className="muted">—</span>}</td>
                <td>
                  <span className={`outcome outcome--${i.outcome}`}>{OUTCOME_TEXT[i.outcome]}</span>
                </td>
                <td>{stateOf(i) ? <StateChip state={stateOf(i)!} /> : ""}</td>
                <td className="wrap">
                  {i.error ?? ""}
                  {i.state === "failed" && i.receipt_id && (
                    <button type="button" className="ll-btn ll-btn--secondary" onClick={() => retry(i.receipt_id!)}>
                      <Icon name="refresh" />
                      Retry
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted">
        Refused rows stored nothing: fix them and submit them again. The rest are already in the system. Submitting this same batch again starts no new work.
      </p>
    </section>
  );
}
