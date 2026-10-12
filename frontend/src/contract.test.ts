import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

// The types in src/api/types.ts are written by hand from docs/api/openapi.json. This test fails
// when the API drops or renames a field or a route the front end uses, so drift shows up before a
// screen breaks. After a backend merge, a failure here is the first thing to read.
const doc = JSON.parse(readFileSync(resolve(__dirname, "../../docs/api/openapi.json"), "utf8")) as {
  paths: Record<string, Record<string, unknown>>;
  components: { schemas: Record<string, { properties?: Record<string, unknown> }> };
};

const USED_FIELDS: Record<string, string[]> = {
  ReceiptSummary: ["receipt_id", "revision", "state", "disposition", "evaluation_version", "notice", "qa_sample", "updated_at"],
  ReceiptList: ["items", "total"],
  ReceiptDetail: ["receipt_id", "revision", "state", "disposition", "evaluation_version", "notice", "qa_sample", "updated_at", "failed", "receipt", "result", "allowed_actions"],
  ActionResponse: ["agreement", "allowed_actions", "receipt", "result", "state"],
  ActionBody: ["actor", "evaluation_version", "note", "reason_code", "line_id", "category", "question", "reason"],
  SubmitResponse: ["receipt_id", "revision", "outcome", "state", "superseded"],
  BatchResponse: ["batch_id", "total", "counts", "items"],
  BatchItem: ["row", "receipt_id", "outcome", "error", "state"],
  EventItem: ["seq", "revision", "type", "actor", "at", "payload"],
  EventList: ["items"],
  RevisionDetail: ["receipt_id", "revision", "status", "created_at", "receipt", "evaluations"],
  EvaluationItem: ["version", "created_at", "result"],
  FailureInfo: ["stage", "reason"],
  Health: ["status", "schema_version"],
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
    for (const n of ["state", "disposition", "batch_id", "limit", "offset"]) expect(names).toContain(n);
  });
});
