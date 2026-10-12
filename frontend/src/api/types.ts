// Types for docs/api/openapi.json and specs/004-backend-lifecycle/contracts/api.md.
// The OpenAPI document leaves `receipt` and `result` as plain objects, so their shape is
// written here from ReceiptInput and ReceiptResult (src/expense_validator/domain/models.py).
// Money is a string in JSON.

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

export interface LineItem {
  line_id: string;
  description_raw: string;
  language: string;
  quantity: string;
  unit_price: string;
  amount: string;
  amount_usd: string;
}

export interface Receipt {
  receipt_id: string;
  employee_id: string;
  employee_country: string;
  entity: "GLOBAL" | "APAC" | "EMEA";
  submitted_expense_type: string;
  merchant_name: string | null;
  mcc: number;
  mcc_description: string;
  transaction_datetime: string | null;
  currency: string | null;
  fx_rate_to_usd: string | null;
  total_amount: string | null;
  total_amount_usd: string | null;
  attendee_count: number | null;
  trip_id: string | null;
  trip_nights: number | null;
  pre_approval_ref: string | null;
  itemized: boolean;
  vat_number: string | null;
  line_items: LineItem[];
}

export interface OutputLine {
  line_id: string;
  description_raw: string;
  category: string | null;
  restricted: boolean | null;
  confidence: number | null;
  subtype: string;
  recipient_kind: string;
  recipient_name: string | null;
  status: "classified" | "unclassified";
  unclassified_reason: string | null;
}

export interface Finding {
  rule_id: string;
  policy_doc: string;
  severity: Severity;
  line_ids: string[];
  evidence: string;
  explanation: string;
  decisions: string[];
  computed: Record<string, string>;
}

export interface ReviewSignal {
  rule_id: string;
  policy_doc: string;
  reason: string;
  line_ids: string[];
}

export interface RunMetadata {
  classifier: string;
  model_id: string;
  provider_endpoint: string;
  prompt_version: string;
  rules_version: string;
  exc03_threshold: number;
  exc03_threshold_status: string;
  confidence_source: string;
  pipeline_config_version: string | null;
}

export interface Result {
  receipt_id: string;
  disposition: Disposition;
  line_items: OutputLine[];
  exceptions: Finding[];
  review_signals: ReviewSignal[];
  run: RunMetadata;
}

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
