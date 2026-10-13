import { describe, expect, it } from "vitest";
import type { Finding } from "../api/types";
import {
  ageBucket,
  ageOf,
  confidenceWord,
  describeEvent,
  diffRevisions,
  findingTitle,
  REASON_CODES,
  overrides,
  reasonsFor,
  showsReason,
  sortFindings,
  verdictLine,
} from "./domain";
import { money, recordedDate, usd } from "./format";
import { planIntake, refusedRowsText, sourceRows } from "./intake";

const finding = (over: Partial<Finding>): Finding => ({
  rule_id: "REG-01",
  policy_doc: "regional-addendum.md",
  severity: "high",
  line_ids: ["L1"],
  evidence: "e",
  explanation: "REG-01: line L1 is alcohol.",
  decisions: [],
  computed: {},
  ...over,
});

describe("format", () => {
  it("groups digits without touching precision", () => {
    expect(money("28000")).toBe("28,000");
    expect(money("1234567.8900", "JPY")).toBe("1,234,567.8900 JPY");
    expect(money(null)).toBe("—");
  });
  it("formats USD to cents", () => {
    expect(usd("187.6")).toBe("$187.60");
  });
  it("keeps the recorded local time", () => {
    expect(recordedDate("2026-05-12T19:30:00")).toBe("2026-05-12 19:30");
  });
});

describe("domain", () => {
  it("shows confidence as a word, uncertain below the EXC-03 threshold", () => {
    expect(confidenceWord(0.99)).toBe("certain");
    expect(confidenceWord(0.98)).toBe("likely");
    expect(confidenceWord(0.96)).toBe("uncertain");
    expect(confidenceWord(null)).toBe("uncertain");
  });
  it("detects overrides (ADR 0007 D8)", () => {
    expect(overrides("approve", "flag")).toBe(true);
    expect(overrides("reject", "pass")).toBe(true);
    expect(overrides("approve", "review")).toBe(false);
    expect(overrides("reject", "flag")).toBe(false);
  });
  it("offers each decision only the reasons that can describe it (spec 008 FR-019)", () => {
    expect(reasonsFor("approve").map((r) => r.id)).toEqual(["policy_exception_granted", "engine_false_positive", "documentation_provided", "other"]);
    expect(reasonsFor("reject").map((r) => r.id)).toEqual(["engine_missed_issue", "other"]);
    const all = REASON_CODES.map((r) => r.id);
    for (const action of ["approve", "reject"] as const) for (const r of reasonsFor(action)) expect(all).toContain(r.id);
  });
  it("shows the reason list for approve always, and for reject only when it overrides a pass (FR-020)", () => {
    for (const d of ["flag", "review", "pass", null] as const) expect(showsReason("approve", d)).toBe(true);
    expect(showsReason("reject", "pass")).toBe(true);
    for (const d of ["flag", "review", null] as const) expect(showsReason("reject", d)).toBe(false);
  });
  it("drops the rule id from a finding title", () => {
    expect(findingTitle(finding({}))).toBe("Line L1 is alcohol.");
  });
  it("orders findings by severity", () => {
    const sorted = sortFindings([finding({ severity: "low", rule_id: "A" }), finding({ severity: "critical", rule_id: "B" })]);
    expect(sorted.map((f) => f.severity)).toEqual(["critical", "low"]);
  });
  it("leads the verdict with the worst finding", () => {
    expect(verdictLine("flag", [finding({})], [])).toBe("Line L1 is alcohol.");
    expect(verdictLine("review", [], [{ rule_id: "EXC-03", policy_doc: "x", reason: "uncertain", line_ids: [] }])).toBe("uncertain");
    expect(verdictLine("pass", [], [])).toBe("No policy exception found.");
  });
  it("buckets ages", () => {
    const now = Date.parse("2026-10-10T12:00:00Z");
    expect(ageBucket("2026-10-10T11:30:00Z", now)).toBe("<1 h");
    expect(ageBucket("2026-10-08T11:30:00Z", now)).toBe("1–3 d");
    expect(ageOf("2026-10-10T10:00:00Z", now)).toBe("2 h");
  });
  it("describes every event it knows", () => {
    expect(
      describeEvent({ seq: 1, revision: 1, type: "ReceiptEvaluated", actor: "system", at: "", payload: { version: 2, disposition: "flag", changed: true } }),
    ).toContain("version 2");
  });
});

describe("diffRevisions", () => {
  it("lists changed fields and treats lines as a whole", () => {
    const a = { receipt_id: "R", attendee_count: null, merchant_name: "A", line_items: [{ line_id: "L1" }] };
    const b = { receipt_id: "R", attendee_count: 2, merchant_name: "A", line_items: [{ line_id: "L1" }, { line_id: "L2" }] };
    expect(diffRevisions(a, b)).toEqual([
      { field: "attendee_count", before: "—", after: "2" },
      { field: "line_items", before: "1 line", after: "2 lines, changed" },
    ]);
    expect(diffRevisions(a, a)).toEqual([]);
  });
});

describe("refused rows", () => {
  it("returns the source text of the rows the server refused", () => {
    const plan = planIntake('{"a":1}\nnot json\n{"a":3}');
    const rows = sourceRows(plan);
    expect(rows).toHaveLength(3);
    expect(refusedRowsText([{ row: 1, outcome: "accepted" }, { row: 2, outcome: "invalid" }], rows)).toBe("not json");
  });
});

describe("planIntake", () => {
  it("reads an empty box", () => {
    expect(planIntake("  ").kind).toBe("empty");
  });
  it("reads one pretty-printed receipt", () => {
    const plan = planIntake('{\n "receipt_id": "R-1"\n}');
    expect(plan).toMatchObject({ kind: "single", receiptId: "R-1" });
  });
  it("reads a JSON array as a batch", () => {
    expect(planIntake('[{"a":1},{"a":2}]')).toMatchObject({ kind: "batch", rows: 2, contentType: "application/json" });
  });
  it("reads JSON Lines as a batch and keeps bad rows for the server to report", () => {
    expect(planIntake('{"a":1}\nnot json\n{"a":3}')).toMatchObject({ kind: "batch", rows: 3, contentType: "application/x-ndjson" });
  });
  it("rejects text that is not JSON", () => {
    expect(planIntake("hello").kind).toBe("invalid");
    expect(planIntake("[]").kind).toBe("invalid");
  });
});
