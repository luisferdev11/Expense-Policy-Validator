import type {
  Action,
  Disposition,
  EventItem,
  Finding,
  ReasonCode,
  ReceiptDetail,
  ReceiptSummary,
  ReviewSignal,
  Severity,
  State,
} from "../api/types";

// The 21 categories of data/category-taxonomy.md (src/expense_validator/domain/taxonomy.py).
// The API has no endpoint for them (FINDINGS.md), so the list is written here.
export const CATEGORIES: { id: string; restricted: boolean }[] = [
  ["alcohol", true],
  ["tobacco", true],
  ["personal_electronics", true],
  ["gift", true],
  ["gift_card", true],
  ["household_goods", true],
  ["personal_care", true],
  ["clothing", true],
  ["gambling", true],
  ["jewelry", true],
  ["food_beverage", false],
  ["computer_accessory", false],
  ["office_supplies", false],
  ["lodging", false],
  ["ground_transport", false],
  ["airfare", false],
  ["laundry_service", false],
  ["health_otc", false],
  ["software_subscription", false],
  ["service_fee", false],
  ["other", false],
].map(([id, restricted]) => ({ id: id as string, restricted: restricted as boolean }));

export const categoryLabel = (id: string | null): string =>
  id ? id.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase()) : "Not classified";

export const REASON_CODES: { id: ReasonCode; label: string }[] = [
  { id: "policy_exception_granted", label: "Policy exception granted" },
  { id: "engine_false_positive", label: "The engine flagged something that is fine" },
  { id: "engine_missed_issue", label: "The engine missed an issue" },
  { id: "documentation_provided", label: "Documentation was provided" },
  { id: "other", label: "Other (note required)" },
];

export const STATE_LABEL: Record<State, string> = {
  submitted: "Submitted",
  classifying: "Reading items",
  auto_approved: "Auto-approved",
  in_review: "In review",
  compliance: "With Compliance",
  needs_info: "Waiting for information",
  approved: "Approved",
  rejected: "Rejected",
  failed: "Failed",
};

export const STATES: State[] = [
  "submitted",
  "classifying",
  "in_review",
  "compliance",
  "needs_info",
  "auto_approved",
  "approved",
  "rejected",
  "failed",
];

export const IN_PROGRESS: State[] = ["submitted", "classifying"];
export const CLOSED: State[] = ["approved", "rejected"];

export const isInProgress = (s: State): boolean => IN_PROGRESS.includes(s);

export const ACTION_LABEL: Record<Action, string> = {
  approve: "Approve",
  reject: "Reject",
  "correct-category": "Correct a category",
  "request-info": "Request information",
  escalate: "Escalate to Compliance",
};

export const DISPOSITION_LABEL: Record<Disposition, string> = {
  flag: "Flag",
  review: "Review",
  pass: "Pass",
};

const SEVERITY_ORDER: Severity[] = ["critical", "high", "medium", "low"];
export const severityRank = (s: Severity): number => SEVERITY_ORDER.indexOf(s);

export function sortFindings(findings: Finding[]): Finding[] {
  return [...findings].sort(
    (a, b) => severityRank(a.severity) - severityRank(b.severity) || a.rule_id.localeCompare(b.rule_id),
  );
}

export const hasCritical = (findings: Finding[]): boolean =>
  findings.some((f) => f.severity === "critical");

/** Confidence as a word (brand book, principle 5). Below the EXC-03 threshold it is Uncertain. */
export type ConfidenceWord = "certain" | "likely" | "uncertain";
export function confidenceWord(confidence: number | null, threshold = 0.97): ConfidenceWord {
  if (confidence === null || confidence < threshold) return "uncertain";
  return confidence >= 0.99 ? "certain" : "likely";
}

/** A finding's explanation starts with its rule id ("REG-01: line ..."); the title drops it. */
export function findingTitle(f: Finding): string {
  const stripped = f.explanation.replace(new RegExp(`^${f.rule_id}:\\s*`), "");
  return stripped.charAt(0).toUpperCase() + stripped.slice(1);
}

export function policyDocName(file: string): string {
  const base = file.replace(/\.md$/, "").replace(/[-_]/g, " ");
  return base.charAt(0).toUpperCase() + base.slice(1);
}

/** The one-line reason that leads the verdict header. */
export function verdictLine(
  disposition: Disposition | null,
  findings: Finding[],
  signals: ReviewSignal[],
): string {
  if (disposition === null) return "Waiting for the engine.";
  if (findings.length > 0) {
    const first = sortFindings(findings)[0];
    const more = findings.length - 1;
    return more > 0
      ? `${findingTitle(first)} (and ${more} more finding${more > 1 ? "s" : ""})`
      : findingTitle(first);
  }
  if (signals.length > 0) return signals[0].reason;
  return "No policy exception found.";
}

/** Does the decision override what the engine proposed? Mirrors ADR 0007 D8. */
export function overrides(action: "approve" | "reject", disposition: Disposition | null): boolean {
  return (action === "approve" && disposition === "flag") || (action === "reject" && disposition === "pass");
}

export function reasonRequiredNote(code: ReasonCode | ""): boolean {
  return code === "other";
}

// Age ---------------------------------------------------------------------------------------

export function ageOf(iso: string, now: number = Date.now()): string {
  const ms = Math.max(0, now - new Date(iso).getTime());
  const min = Math.floor(ms / 60000);
  if (min < 1) return "just now";
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60);
  if (h < 48) return `${h} h`;
  return `${Math.floor(h / 24)} d`;
}

export function ageBucket(iso: string, now: number = Date.now()): "<1 h" | "1–24 h" | "1–3 d" | ">3 d" {
  const h = (now - new Date(iso).getTime()) / 3600000;
  if (h < 1) return "<1 h";
  if (h < 24) return "1–24 h";
  if (h < 72) return "1–3 d";
  return ">3 d";
}

// Audit trail -------------------------------------------------------------------------------

/** A readable line for each event type of the log (src/expense_validator/domain/events.py). */
export function describeEvent(e: EventItem): string {
  const p = e.payload as Record<string, string | number | boolean | null>;
  switch (e.type) {
    case "ReceiptSubmitted":
      return e.revision > 1 ? `Revision ${e.revision} submitted` : "Receipt submitted";
    case "RevisionSuperseded":
      return `Revision ${p.superseded_revision} replaced by revision ${p.by_revision}`;
    case "ReceiptClassified":
      return `${p.lines} item${p.lines === 1 ? "" : "s"} read`;
    case "ReceiptEvaluated":
      return p.changed
        ? `Policy check, result version ${p.version}: proposed ${String(p.disposition)}`
        : `Policy check repeated, result unchanged (version ${p.version})`;
    case "NoticeRaised":
      return String(p.text);
    case "StageFailed":
      return `Stage "${p.stage}" failed${p.reason ? `: ${p.reason}` : ""}`;
    case "StageRetried":
      return `Stage "${p.stage}" retried`;
    case "ReceiptApproved":
      return `Approved${p.reason_code ? ` (${reasonLabel(String(p.reason_code))})` : ""}${p.note ? `: ${p.note}` : ""}`;
    case "ReceiptRejected":
      return `Rejected${p.reason_code ? ` (${reasonLabel(String(p.reason_code))})` : ""}${p.note ? `: ${p.note}` : ""}`;
    case "LineCategoryCorrected":
      return `Category of ${p.line_id} changed from ${categoryLabel((p.from_category as string) ?? null)} to ${categoryLabel(String(p.to_category))}`;
    case "InformationRequested":
      return `Information requested: ${p.question}`;
    case "EscalatedToCompliance":
      return `Escalated to Compliance: ${p.reason}`;
    case "DevCandidateMarked":
      return `Line ${p.line_id} recorded as a candidate for the classifier's test set`;
    default:
      return e.type;
  }
}

export const reasonLabel = (code: string): string =>
  REASON_CODES.find((r) => r.id === code)?.label ?? code;

/** Events that a person caused, to tell them apart from the system's in the trail. */
export const isHumanEvent = (e: EventItem): boolean =>
  ["ReceiptApproved", "ReceiptRejected", "LineCategoryCorrected", "InformationRequested", "EscalatedToCompliance"].includes(
    e.type,
  );

// Queue presets -----------------------------------------------------------------------------

export type QueueView = "queue" | "compliance" | "sample";

export const QUEUE_VIEWS: Record<
  QueueView,
  { title: string; hint: string; empty: string; match: (r: ReceiptSummary) => boolean }
> = {
  queue: {
    title: "Review queue",
    hint: "Receipts waiting for a person to decide.",
    empty: "Queue clear. Nothing is waiting for your decision.",
    match: (r) => ["in_review", "needs_info"].includes(r.state),
  },
  compliance: {
    title: "Compliance",
    hint: "Critical findings and escalations.",
    empty: "No case is with Compliance.",
    match: (r) => r.state === "compliance",
  },
  sample: {
    title: "Quality sample",
    hint: "Receipts the engine passed on its own that are selected for a second look (about one in ten).",
    empty: "No auto-approved receipt is waiting for a sample check.",
    match: (r) => r.state === "auto_approved" && r.qa_sample,
  },
};

export type Row = { summary: ReceiptSummary; detail?: ReceiptDetail };

export const findingCount = (d?: ReceiptDetail): number | null =>
  d?.result ? d.result.exceptions.length : null;
