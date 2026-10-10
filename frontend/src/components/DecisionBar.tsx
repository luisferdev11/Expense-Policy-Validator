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
const VARIANT: Record<Action, string> = {
  approve: "primary",
  reject: "secondary",
  "request-info": "secondary",
  escalate: "secondary",
  "correct-category": "secondary",
};

const ORDER: Action[] = ["approve", "reject", "request-info", "escalate", "correct-category"];

export function decisionKeys(): Record<string, Action> {
  const map: Record<string, Action> = {};
  for (const [action, key] of Object.entries(KEY)) map[key.toLowerCase()] = action as Action;
  return map;
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
      return "The engine proposes; you decide.";
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
        <button key={a} type="button" className={`ll-btn ll-btn--${VARIANT[a]}`} onClick={() => onAction(a)}>
          <Icon name={ICON[a]} />
          {ACTION_LABEL[a]}
          <span className="ll-kbd">{KEY[a]}</span>
        </button>
      ))}
      <span className="ll-decision__hint">{message}</span>
    </div>
  );
}
