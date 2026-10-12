import type { EventItem, ReceiptDetail, ReceiptSummary, State } from "../api/types";
import { ageBucket } from "./domain";

export interface Insights {
  total: number;
  byState: Record<string, number>;
  byProposal: Record<string, number>;
  aging: Record<string, number>;
  open: number;
  notices: number;
  failed: number;
  qaWaiting: number;
  agreement: { decisions: number; agreed: number; byAction: Record<string, { n: number; agreed: number }> };
  /** Findings on receipts where a reviewer disagreed with the engine, by rule. */
  disagreementByRule: Record<string, number>;
  /** How often each rule appears in the current results, by rule. */
  ruleFrequency: Record<string, number>;
  withResult: number;
}

const OPEN: State[] = ["in_review", "needs_info", "compliance"];
const HUMAN: Record<string, string> = {
  ReceiptApproved: "approve",
  ReceiptRejected: "reject",
  LineCategoryCorrected: "correct-category",
  InformationRequested: "request-info",
  EscalatedToCompliance: "escalate",
};

export function computeInsights(
  summaries: ReceiptSummary[],
  details: Map<string, ReceiptDetail>,
  events: Map<string, EventItem[]>,
  now: number = Date.now(),
): Insights {
  const out: Insights = {
    total: summaries.length,
    byState: {},
    byProposal: {},
    aging: { "<1 h": 0, "1–24 h": 0, "1–3 d": 0, ">3 d": 0 },
    open: 0,
    notices: 0,
    failed: 0,
    qaWaiting: 0,
    agreement: { decisions: 0, agreed: 0, byAction: {} },
    disagreementByRule: {},
    ruleFrequency: {},
    withResult: 0,
  };
  for (const s of summaries) {
    out.byState[s.state] = (out.byState[s.state] ?? 0) + 1;
    if (s.disposition) out.byProposal[s.disposition] = (out.byProposal[s.disposition] ?? 0) + 1;
    if (OPEN.includes(s.state)) {
      out.open += 1;
      out.aging[ageBucket(s.updated_at, now)] += 1;
    }
    if (s.notice) out.notices += 1;
    if (s.state === "failed") out.failed += 1;
    if (s.state === "auto_approved" && s.qa_sample) out.qaWaiting += 1;

    const d = details.get(s.receipt_id);
    if (d?.result) {
      out.withResult += 1;
      for (const rule of new Set(d.result.exceptions.map((e) => e.rule_id))) {
        out.ruleFrequency[rule] = (out.ruleFrequency[rule] ?? 0) + 1;
      }
    }

    let disagreed = false;
    for (const e of events.get(s.receipt_id) ?? []) {
      const action = HUMAN[e.type];
      if (!action) continue;
      const agreement = e.payload.agreement === 1 ? 1 : 0;
      out.agreement.decisions += 1;
      out.agreement.agreed += agreement;
      const row = (out.agreement.byAction[action] ??= { n: 0, agreed: 0 });
      row.n += 1;
      row.agreed += agreement;
      if (agreement === 0) disagreed = true;
    }
    if (disagreed && d?.result) {
      const rules = new Set(d.result.exceptions.map((x) => x.rule_id));
      if (rules.size === 0) out.disagreementByRule["(no finding)"] = (out.disagreementByRule["(no finding)"] ?? 0) + 1;
      for (const r of rules) out.disagreementByRule[r] = (out.disagreementByRule[r] ?? 0) + 1;
    }
  }
  return out;
}

export function sortedEntries(o: Record<string, number>): [string, number][] {
  return Object.entries(o).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}
