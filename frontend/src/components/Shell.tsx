import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { QUEUE_VIEWS } from "../lib/domain";
import { useActor, usePolling, useShortcuts, useTheme } from "../lib/hooks";
import { useReceipts } from "../lib/receipts";
import { Icon } from "./Icon";

function ShortcutSheet({ onClose }: { onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    ref.current?.showModal();
  }, []);
  const rows: [string, string][] = [
    ["J / K", "Next / previous receipt in the list"],
    ["A", "Approve"],
    ["R", "Reject"],
    ["I", "Request information"],
    ["E", "Escalate to Compliance"],
    ["C", "Correct a category"],
    ["/", "Search the list"],
    ["Esc", "Close the receipt or a dialog"],
    ["?", "This sheet"],
  ];
  return (
    <dialog ref={ref} className="dialog" onClose={onClose} aria-labelledby="keys-title">
      <div className="dialog__body">
        <header className="dialog__head">
          <h3 id="keys-title">Keyboard shortcuts</h3>
          <button type="button" className="icon-btn" aria-label="Close" onClick={() => ref.current?.close()}>
            <Icon name="x" />
          </button>
        </header>
        <table className="keys">
          <tbody>
            {rows.map(([k, d]) => (
              <tr key={k}>
                <td>
                  {k.split(" / ").map((x) => (
                    <span key={x} className="ll-kbd">
                      {x}
                    </span>
                  ))}
                </td>
                <td>{d}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="hint">Shortcuts act on the receipt that is open and never while you type in a field.</p>
      </div>
    </dialog>
  );
}

export function Shell() {
  const { summaries } = useReceipts();
  const { actor, setActor } = useActor();
  const [theme, cycleTheme] = useTheme();
  const [sheet, setSheet] = useState(false);
  const navigate = useNavigate();
  const health = usePolling(() => api.health(), [], 10000);

  useShortcuts({ "?": () => setSheet(true), g: () => navigate("/queue") });

  const count = (view: keyof typeof QUEUE_VIEWS) => summaries.filter(QUEUE_VIEWS[view].match).length;
  const link = (to: string, label: string, n?: number) => (
    <NavLink to={to} className={({ isActive }) => `nav__link${isActive ? " is-active" : ""}`}>
      {label}
      {n !== undefined && n > 0 && <span className="nav__count ll-num">{n}</span>}
    </NavLink>
  );

  return (
    <div className="ll-root shell">
      <header className="nav">
        <span className="nav__brand">Expense Policy Validator</span>
        <nav className="nav__links" aria-label="Main">
          {link("/intake", "Intake")}
          {link("/queue", "Review queue", count("queue"))}
          {link("/compliance", "Compliance", count("compliance"))}
          {link("/sample", "Quality sample", count("sample"))}
          {link("/all", "All receipts")}
          {link("/insights", "Insights")}
          {link("/evaluation", "Evaluation")}
        </nav>
        <div className="nav__right">
          <span
            className={`nav__health${health.error ? " is-down" : ""}`}
            title={health.error ? "The API does not answer" : "API connected"}
            role="status"
          >
            <span aria-hidden="true">●</span> {health.error ? "API offline" : "API connected"}
          </span>
          <label className="nav__actor">
            <Icon name="user" />
            <input
              aria-label="Your name"
              placeholder="Your name"
              value={actor}
              onChange={(e) => setActor(e.target.value)}
            />
          </label>
          <button type="button" className="nav__btn" onClick={cycleTheme} aria-label={`Theme: ${theme}. Change theme`} title={`Theme: ${theme}`}>
            <Icon name="moon" />
            <span className="nav__theme">{theme}</span>
          </button>
          <button type="button" className="nav__btn" onClick={() => setSheet(true)} aria-label="Keyboard shortcuts">
            <Icon name="help" />
          </button>
        </div>
      </header>
      {health.error && (
        <div className="banner-down" role="alert">
          Cannot reach the API. Start it with <code>uv run epv serve --with-worker</code>; this page reconnects by itself.
        </div>
      )}
      <main className="main">
        <Outlet />
      </main>
      {sheet && <ShortcutSheet onClose={() => setSheet(false)} />}
    </div>
  );
}
