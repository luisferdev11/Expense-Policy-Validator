// Types for docs/api/openapi.json and specs/004-backend-lifecycle/contracts/api.md.
// The receipt and the result are generated from the document (see below); the unions of states,
// actions and reason codes, and the response wrappers, are written here. Money is a string in JSON.

import type { components } from "./generated";

export type State =
  | "submitted"
  | "classifying"
  | "auto_approved"
  | "in_review"
  | "compliance"
  | "needs_info"
  | "approved"
  | "rejected"
  | "failed";

export type Disposition = "flag" | "review" | "pass";
export type Severity = "critical" | "high" | "medium" | "low";
export type Action = "approve" | "reject" | "correct-category" | "request-info" | "escalate";
export type ReasonCode =
  | "policy_exception_granted"
  | "engine_false_positive"
  | "engine_missed_issue"
  | "documentation_provided"
  | "other";

// The domain shapes come from the OpenAPI document through `generated.ts` (`npm run gen:api`).
// Everything the app imports is re-exported here; nothing else imports `generated.ts` directly.
type S = components["schemas"];
export type Receipt = S["ReceiptInput"]; // what the API returns
export type LineItem = S["LineItemInput"];
export type ReceiptInput = S["ReceiptInputRequest"]; // what a client submits
export type LineItemInputRequest = S["LineItemInputRequest"];
export type Entity = ReceiptInput["entity"];
export type Language = ReceiptInput["line_items"][number]["language"];
export type Result = S["ReceiptResult"];
export type OutputLine = S["OutputLineItem"];
export type Finding = S["ExceptionFinding"];
export type ReviewSignal = S["ReviewSignal"];
export type RunMetadata = S["RunMetadata"];

export interface FailureInfo {
  stage: "classify" | "evaluate";
  reason: string | null;
}

export interface ReceiptSummary {
  receipt_id: string;
  revision: number;
  state: State;
  disposition: Disposition | null;
  evaluation_version: number | null;
  notice: string | null;
  qa_sample: boolean;
  updated_at: string;
  created_at: string; // when revision 1 was stored; never changes
  decided_by: string | null; // the reviewer, or "system" for an auto-approval
  decided_at: string | null;
}

export interface ReceiptList {
  items: ReceiptSummary[];
  total: number;
}

export interface ReceiptDetail extends ReceiptSummary {
  failed: FailureInfo | null;
  receipt: Receipt;
  result: Result | null;
  allowed_actions: Action[];
}

export interface ActionResponse extends ReceiptDetail {
  agreement: 0 | 1;
}

export interface EventItem {
  seq: number;
  revision: number;
  type: string;
  actor: string;
  at: string;
  payload: Record<string, unknown>;
}

export interface RevisionDetail {
  receipt_id: string;
  revision: number;
  status: string;
  created_at: string;
  receipt: Receipt;
  evaluations: { version: number; created_at: string; result: Result }[];
}

export type SubmitOutcome = "accepted" | "existing" | "revision";

export interface SubmitResponse {
  receipt_id: string;
  revision: number;
  outcome: SubmitOutcome;
  state: State;
  superseded?: boolean;
}

export type RowOutcome = SubmitOutcome | "invalid" | "duplicate_in_batch";

export interface BatchItem {
  row: number;
  receipt_id: string | null;
  outcome: RowOutcome;
  error: string | null;
  state: State | null;
}

export interface BatchResponse {
  batch_id: string;
  total: number;
  created_at: string;
  counts: Record<string, number>;
  items: BatchItem[];
}

export interface ActionBody {
  actor: string;
  evaluation_version: number;
  note?: string;
  reason_code?: ReasonCode;
  line_id?: string;
  category?: string;
  question?: string;
  reason?: string;
}
