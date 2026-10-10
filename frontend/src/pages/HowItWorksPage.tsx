import { Link } from "react-router-dom";

// States and moves come from src/expense_validator/domain/lifecycle.py and ADR 0007.
const ROWS: { state: string; entered: string; who: string; leaves: string; event: string }[] = [
  { state: "Submitted", entered: "A new receipt, or a new revision, is accepted. The same content again changes nothing.", who: "System", leaves: "Reading the items", event: "ReceiptSubmitted" },
  { state: "Reading the items", entered: "A worker claims the receipt.", who: "System", leaves: "In review, With Compliance, Auto-approved, or Failed", event: "ReceiptClassified · ReceiptEvaluated" },
  { state: "In review", entered: "Proposed flag or review.", who: "Auditor: approve, reject, correct a category, request information, escalate", leaves: "Approved, Rejected, Waiting for information, With Compliance; a category correction makes a new result", event: "ReceiptApproved · ReceiptRejected · LineCategoryCorrected · InformationRequested · EscalatedToCompliance" },
  { state: "Waiting for information", entered: "The auditor asked the employee a question.", who: "Employee resubmits (same receipt ID)", leaves: "Submitted again as a new revision; or Rejected if nobody answers", event: "InformationRequested" },
  { state: "With Compliance", entered: "A critical finding, or an auditor escalated.", who: "Compliance: approve, reject, correct a category, request information", leaves: "Approved, Rejected, Waiting for information", event: "ReceiptApproved · ReceiptRejected" },
  { state: "Auto-approved", entered: "Proposed pass and no critical finding.", who: "Audit lead samples about one in ten; anyone can reject it as an override", leaves: "Rejected, or stays approved", event: "ReceiptRejected" },
  { state: "Approved · Rejected", entered: "A person decided.", who: "—", leaves: "Closed; reopened only by a new revision", event: "ReceiptApproved · ReceiptRejected" },
  { state: "Failed", entered: "A stage could not finish: the model or the store was down.", who: "A person can retry; the same stage runs again", leaves: "The same stage again; never to pass", event: "StageFailed · StageRetried" },
];

export function HowItWorksPage() {
  return (
    <div className="page">
      <div>
        <h1 className="ll-display">How a receipt moves</h1>
        <p className="muted lead">
          Every move is an event appended to the receipt's log; the state you see is computed from those events. The engine proposes; only a person closes a flagged or reviewed receipt.
        </p>
      </div>

      <ol className="flow flow--big" aria-label="Main path">
        <li>
          <strong>Submitted</strong>
          <span className="muted">saved before any work</span>
        </li>
        <li aria-hidden="true">→</li>
        <li>
          <strong>Reading the items</strong>
          <span className="muted">one model call per new line</span>
        </li>
        <li aria-hidden="true">→</li>
        <li>
          <strong>Evaluated</strong>
          <span className="muted">rules, proposal, version n</span>
        </li>
        <li aria-hidden="true">→</li>
        <li className="flow-split">
          <span className="flow--pass">
            <b>Pass</b> → approved automatically; a sample goes to a person
          </span>
          <span className="flow--low">
            <b>Flag or review</b> → in review with an auditor
          </span>
          <span className="flow--critical">
            <b>Critical finding</b> → Compliance, never the audit queue
          </span>
        </li>
      </ol>

      <section className="ll-panel" aria-labelledby="tbl-h">
        <h2 className="ll-heading" id="tbl-h">
          States, who acts, and the event each move writes
        </h2>
        <div className="table-scroll">
          <table className="ll-table">
            <thead>
              <tr>
                <th>State</th>
                <th>Entered when</th>
                <th>Who acts</th>
                <th>Leaves to</th>
                <th>Event</th>
              </tr>
            </thead>
            <tbody>
              {ROWS.map((r) => (
                <tr key={r.state}>
                  <th scope="row" className="wrap">
                    {r.state}
                  </th>
                  <td className="wrap">{r.entered}</td>
                  <td className="wrap">{r.who}</td>
                  <td className="wrap">{r.leaves}</td>
                  <td className="wrap ll-num">{r.event}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <div className="grid2">
        <section className="ll-panel">
          <h2 className="ll-heading">Re-evaluation across receipts</h2>
          <p className="muted">
            When a receipt arrives or changes, every receipt sharing its employee and date (MEAL-01, REG-02, REG-03) or its trip (HEALTH-01) is evaluated again. A changed result is a new version and returns to its queue with a notice.
          </p>
        </section>
        <section className="ll-panel">
          <h2 className="ll-heading">What every decision feeds</h2>
          <p className="muted">
            An approval against the proposal needs a reason. Each decision is also recorded as agreed or disagreed with the engine, and a corrected category becomes a candidate for the classifier's test set.
          </p>
        </section>
        <section className="ll-panel">
          <h2 className="ll-heading">Retries are safe</h2>
          <p className="muted">A stage that already finished is never redone. Redoing a classification reads the cached answer: same result, no new cost. A failure sends nothing to pass.</p>
        </section>
      </div>
      <p className="muted">
        <Link to="/intake">Back to intake</Link>
      </p>
    </div>
  );
}
