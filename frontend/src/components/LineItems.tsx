import type { Action, Finding, ReceiptDetail } from "../api/types";
import { categoryLabel, severityRank } from "../lib/domain";
import { money } from "../lib/format";
import { ConfidenceBand } from "./Badges";
import { Icon } from "./Icon";

/** Line items with the category each was read as. Cited lines take the finding's soft color. */
export function LineItems({
  detail,
  onCorrect,
}: {
  detail: ReceiptDetail;
  onCorrect: (lineId: string) => void;
}) {
  const { receipt, result } = detail;
  const byLine = new Map((result?.line_items ?? []).map((l) => [l.line_id, l]));
  const worst = new Map<string, Finding>();
  for (const f of result?.exceptions ?? []) {
    for (const id of f.line_ids) {
      const cur = worst.get(id);
      if (!cur || severityRank(f.severity) < severityRank(cur.severity)) worst.set(id, f);
    }
  }
  const signalLines = new Set((result?.review_signals ?? []).flatMap((s) => s.line_ids));
  const canCorrect = detail.allowed_actions.includes("correct-category" as Action);
  const threshold = result?.run.exc03_threshold;

  return (
    <div className="table-scroll">
      <table className="ll-table ll-table--compact items">
        <thead>
          <tr>
            <th>Line</th>
            <th>Description</th>
            <th className="is-num">Qty</th>
            <th className="is-num">Amount</th>
            <th className="is-num">USD</th>
            <th>Read as</th>
            <th>Confidence</th>
            {canCorrect && <th />}
          </tr>
        </thead>
        <tbody>
          {receipt.line_items.map((li) => {
            const out = byLine.get(li.line_id);
            const cited = worst.get(li.line_id);
            return (
              <tr key={li.line_id} className={cited ? `cited cited--${cited.severity}` : ""}>
                <td className="ll-num">{li.line_id.replace(`${receipt.receipt_id}-`, "")}</td>
                <td className="wrap">{li.description_raw}</td>
                <td className="is-num">{li.quantity}</td>
                <td className="is-num">{money(li.amount, receipt.currency)}</td>
                <td className="is-num">{money(li.amount_usd)}</td>
                <td>
                  {out ? (
                    <>
                      {categoryLabel(out.category)}
                      {out.restricted && <span className="tag">restricted</span>}
                      {out.subtype !== "none" && <span className="tag">{out.subtype.replace(/_/g, " ")}</span>}
                      {cited && <span className="tag tag--rule ll-num">{cited.rule_id}</span>}
                      {!cited && signalLines.has(li.line_id) && <span className="tag tag--signal ll-num">signal</span>}
                    </>
                  ) : (
                    <span className="muted">—</span>
                  )}
                </td>
                <td>{out ? <ConfidenceBand confidence={out.confidence} threshold={threshold} /> : "—"}</td>
                {canCorrect && (
                  <td>
                    <button
                      type="button"
                      className="icon-btn"
                      onClick={() => onCorrect(li.line_id)}
                      aria-label={`Correct the category of ${li.line_id}`}
                      title="Correct the category"
                    >
                      <Icon name="edit" />
                    </button>
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
