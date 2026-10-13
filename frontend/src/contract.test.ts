import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

// The domain types in src/api/types.ts come from src/api/generated.ts, which is generated from
// docs/api/openapi.json (generated.test.ts keeps it fresh); the rest are written by hand. This test
// fails when the API drops or renames a field or a route the front end uses, so drift shows up
// before a screen breaks. After a backend merge, a failure here is the first thing to read.
const doc = JSON.parse(readFileSync(resolve(__dirname, "../../docs/api/openapi.json"), "utf8")) as {
  paths: Record<string, Record<string, unknown>>;
  components: { schemas: Record<string, { properties?: Record<string, unknown> }> };
};

const USED_FIELDS: Record<string, string[]> = {
  ReceiptSummary: ["receipt_id", "revision", "state", "disposition", "evaluation_version", "notice", "qa_sample", "updated_at", "created_at", "decided_by", "decided_at"],
  ReceiptList: ["items", "total"],
  ReceiptDetail: ["receipt_id", "revision", "state", "disposition", "evaluation_version", "notice", "qa_sample", "updated_at", "created_at", "decided_by", "decided_at", "failed", "receipt", "result", "allowed_actions"],
  ActionResponse: ["agreement", "allowed_actions", "receipt", "result", "state"],
  ActionBody: ["actor", "evaluation_version", "note", "reason_code", "line_id", "category", "question", "reason"],
  SubmitResponse: ["receipt_id", "revision", "outcome", "state", "superseded"],
  BatchResponse: ["batch_id", "total", "created_at", "counts", "items"],
  BatchItem: ["row", "receipt_id", "outcome", "error", "state"],
  EventItem: ["seq", "revision", "type", "actor", "at", "payload"],
  EventList: ["items"],
  RevisionDetail: ["receipt_id", "revision", "status", "created_at", "receipt", "evaluations"],
  EvaluationItem: ["version", "created_at", "result"],
  FailureInfo: ["stage", "reason"],
  Health: ["status", "schema_version", "open_work"],
  // `receipt` and `result` are typed since spec 006; the front end reads these fields from them
  // (src/api/types.ts). Spec 008's form reads the request schemas.
  ReceiptInput: ["receipt_id", "employee_id", "employee_country", "entity", "submitted_expense_type", "merchant_name", "mcc", "mcc_description", "transaction_datetime", "currency", "fx_rate_to_usd", "total_amount", "total_amount_usd", "attendee_count", "trip_id", "trip_nights", "pre_approval_ref", "itemized", "vat_number", "line_items"],
  LineItemInput: ["line_id", "description_raw", "language", "quantity", "unit_price", "amount", "amount_usd"],
  ReceiptResult: ["receipt_id", "disposition", "line_items", "exceptions", "review_signals", "run"],
  ReceiptInputRequest: ["receipt_id", "employee_id", "employee_country", "entity", "submitted_expense_type", "merchant_name", "mcc", "mcc_description", "transaction_datetime", "currency", "fx_rate_to_usd", "total_amount", "total_amount_usd", "attendee_count", "trip_id", "trip_nights", "pre_approval_ref", "itemized", "vat_number", "line_items"],
  LineItemInputRequest: ["line_id", "description_raw", "language", "quantity", "unit_price", "amount", "amount_usd"],
};

const USED_ROUTES: [string, string][] = [
  ["/receipts", "get"],
  ["/receipts", "post"],
  ["/receipts/{receipt_id}", "get"],
  ["/receipts/{receipt_id}/events", "get"],
  ["/receipts/{receipt_id}/revisions/{revision}", "get"],
  ["/receipts/{receipt_id}/retry", "post"],
  ["/receipts/{receipt_id}/actions/{action}", "post"],
  ["/batches", "post"],
  ["/batches/{batch_id}", "get"],
  ["/health", "get"],
];

describe("API contract the front end relies on", () => {
  for (const [schema, fields] of Object.entries(USED_FIELDS)) {
    it(`schema ${schema} still has the fields the front end reads`, () => {
      const props = Object.keys(doc.components.schemas[schema]?.properties ?? {});
      expect(props, `schema ${schema} is missing`).not.toHaveLength(0);
      for (const f of fields) expect(props, `${schema}.${f}`).toContain(f);
    });
  }

  it.each(USED_ROUTES)("route %s %s exists", (path, method) => {
    expect(Object.keys(doc.paths[path] ?? {}), `${method.toUpperCase()} ${path}`).toContain(method);
  });

  it("the list endpoint still takes the query parameters the front end sends", () => {
    const get = doc.paths["/receipts"].get as { parameters: { name: string }[] };
    const names = get.parameters.map((p) => p.name);
    for (const n of ["state", "disposition", "batch_id", "limit", "offset", "order"]) expect(names).toContain(n);
  });
});
