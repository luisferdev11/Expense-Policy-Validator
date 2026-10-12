import type { Action, ReceiptDetail } from "../api/types";
import { ACTION_LABEL } from "../lib/domain";
import { Icon } from "./Icon";
import type { IconName } from "./Icon";

const KEY: Partial<Record<Action, string>> = {
  approve: "A",
  reject: "R",
  "request-info": "I",
  escalate: "E",
  "correct-category": "C",
};
const ICON: Record<Action, IconName> = {
  approve: "check",
  reject: "x",
  "request-info": "send",
  escalate: "triangle",
  "correct-category": "edit",
};

const ORDER: Action[] = ["approve", "reject", "request-info", "escalate", "correct-category"];

export function decisionKeys(): Record<string, Action> {
  const map: Record<string, Action> = {};
  for (const [action, key] of Object.entries(KEY)) map[key.toLowerCase()] = action as Action;
  return map;
}

/** The action that agrees with the proposal leads: reject for a flag, approve for pass or review. */
function variant(a: Action, d: ReceiptDetail["disposition"]): string {
  if (a === "reject" && d === "flag") return "critical";
  if (a === "approve" && d !== "flag") return "primary";
  return "secondary";
}

function label(a: Action, d: ReceiptDetail["disposition"]): string {
  if (a === "approve") return d === "flag" ? "Approve anyway" : "Approve";
  if (a === "reject") return "Reject expense";
  return ACTION_LABEL[a];
}

export function DecisionBar({
  detail,
  onAction,
}: {
  detail: ReceiptDetail;
  onAction: (a: Action) => void;
}) {
  const allowed = ORDER.filter((a) => detail.allowed_actions.includes(a));
  const message = (() => {
    if (allowed.length > 0) {
      if (detail.state === "auto_approved") return "The engine passed this receipt on its own. You can reject it as an override.";
      if (detail.state === "needs_info") return "Waiting for the employee. Submit the corrected receipt with the same ID to answer, or reject it if nobody answers.";
      return "Saves and opens the next receipt.";
    }
    switch (detail.state) {
      case "approved":
      case "rejected":
        return "This receipt is closed. A new revision from the employee would reopen it.";
      case "submitted":
      case "classifying":
        return "The engine is still working on this receipt.";
      case "failed":
        return "Processing failed. Retry it from the banner above.";
      default:
        return "No action is available in this state.";
    }
  })();

  return (
    <div className="ll-decision decision-bar" role="group" aria-label="Decision">
      {allowed.map((a) => (
        <button key={a} type="button" className={`ll-btn ll-btn--${variant(a, detail.disposition)}`} onClick={() => onAction(a)}>
          <Icon name={ICON[a]} />
          {label(a, detail.disposition)}
          <span className="ll-kbd">{KEY[a]}</span>
        </button>
      ))}
      <span className="ll-decision__hint">{message}</span>
    </div>
  );
}
