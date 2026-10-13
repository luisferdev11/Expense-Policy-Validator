import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { apac, receipt } from "../../e2e/fixtures";
import { SAMPLE_BATCH, SAMPLE_RECEIPT } from "../samples/samples";
import {
  canonicalJson,
  computed,
  emptyForm,
  emptyLine,
  formToReceipt,
  nextLineId,
  receiptToForm,
  renameLines,
  serverErrors,
  suggestEntity,
  validateForm,
  withCountry,
  withCurrency,
  withReceiptId,
} from "./receiptForm";
import type { ReceiptFormState } from "./receiptForm";

const RECEIPT_KEYS = [
  "receipt_id",
  "employee_id",
  "employee_country",
  "entity",
  "submitted_expense_type",
  "merchant_name",
  "mcc",
  "mcc_description",
  "transaction_datetime",
  "currency",
  "fx_rate_to_usd",
  "total_amount",
  "total_amount_usd",
  "attendee_count",
  "trip_id",
  "trip_nights",
  "pre_approval_ref",
  "itemized",
  "vat_number",
  "line_items",
];
const LINE_KEYS = ["line_id", "description_raw", "language", "quantity", "unit_price", "amount", "amount_usd"];

/** A form that is valid: US, USD, two lines. */
function filled(over: Partial<ReceiptFormState> = {}): ReceiptFormState {
  const f = emptyForm();
  f.receipt_id = "T-1";
  f.employee_id = "E-1";
  f.employee_country = "US";
  f.entity = "GLOBAL";
  f.submitted_expense_type = "Office Supplies";
  f.mcc = "5943";
  f.mcc_description = "Office supply stores";
  f.lines = [
    { ...emptyLine("T-1", []), description_raw: "Pens", quantity: "2", unit_price: "15.00" },
    { ...emptyLine("T-1", [emptyLine("T-1", [])]), description_raw: "Pads", quantity: "1", unit_price: "12.50" },
  ];
  f.lines[1].line_id = "T-1-L2";
  return { ...f, ...over };
}

describe("shape and conversion", () => {
  it("emptyForm has the defaults of the data model", () => {
    const f = emptyForm();
    expect(f.currency).toBe("USD");
    expect(f.fx_rate_to_usd).toEqual({ mode: "auto", value: "1" });
    expect(f.itemized).toBe(true);
    expect(f.entity).toBe("");
    expect(f.lines).toHaveLength(1);
    expect(f.lines[0].language).toBe("en");
    expect(f.lines[0].quantity).toBe("1");
  });

  it("emits the 20 receipt keys in order and the 7 line keys", () => {
    const body = formToReceipt(emptyForm());
    expect(Object.keys(body)).toEqual(RECEIPT_KEYS);
    expect(Object.keys(body.line_items[0])).toEqual(LINE_KEYS);
  });

  it("sends null for empty nullable fields, strings for money, numbers for integers", () => {
    const f = filled();
    const body = formToReceipt(f);
    expect(body.merchant_name).toBeNull();
    expect(body.transaction_datetime).toBeNull();
    expect(body.attendee_count).toBeNull();
    expect(body.trip_id).toBeNull();
    expect(body.pre_approval_ref).toBeNull();
    expect(body.mcc).toBe(5943);
    expect(body.total_amount).toBe("42.50");
    expect(body.line_items[0].quantity).toBe("2");
    expect(typeof body.line_items[0].amount).toBe("string");
  });

  it("adds the seconds a datetime-local input leaves out", () => {
    expect(formToReceipt(filled({ transaction_datetime: "2026-10-01T10:30" })).transaction_datetime).toBe("2026-10-01T10:30:00");
    expect(formToReceipt(filled({ transaction_datetime: "2026-10-01T10:30:15" })).transaction_datetime).toBe("2026-10-01T10:30:15");
  });

  it("sends trip_nights only with a trip, and a VAT number only for EMEA or when it was already there", () => {
    const withNights = filled({ trip_nights: "3", attendee_count: "2" });
    expect(formToReceipt(withNights).trip_nights).toBeNull();
    expect(formToReceipt({ ...withNights, trip_id: "TR-1" }).trip_nights).toBe(3);
    expect(formToReceipt(withNights).attendee_count).toBe(2);

    const vat = filled({ vat_number: "DE123" });
    expect(formToReceipt(vat).vat_number).toBeNull();
    expect(formToReceipt({ ...vat, entity: "EMEA" }).vat_number).toBe("DE123");
    expect(formToReceipt({ ...vat, vat_visible_on_load: true }).vat_number).toBe("DE123");
  });

  it("treats whitespace-only text as null", () => {
    expect(formToReceipt(filled({ merchant_name: "   ", trip_id: " " })).merchant_name).toBeNull();
    expect(formToReceipt(filled({ trip_id: " " })).trip_id).toBeNull();
  });
});

describe("computation", () => {
  it("computes a line amount, the totals and the USD amounts exactly", () => {
    const c = computed(filled());
    expect(c.lines[0].amount.value).toBe("30.00");
    expect(c.lines[1].amount.value).toBe("12.50");
    expect(c.total_amount.value).toBe("42.50");
    expect(c.total_amount_usd.value).toBe("42.50");
    expect(c.lines[0].amount_usd.value).toBe("30.00");
  });

  it("converts with the rate and rounds half up", () => {
    const f = filled({ currency: "JPY", fx_rate_to_usd: { mode: "manual", value: "0.0067" } });
    f.lines[0] = { ...f.lines[0], quantity: "1", unit_price: "8000" };
    const c = computed(f);
    expect(c.lines[0].amount.value).toBe("8000");
    expect(c.lines[0].amount_usd.value).toBe("53.60");
  });

  it("uses the amount as USD for a USD receipt", () => {
    const c = computed(filled());
    expect(c.rate).toBe("1");
    expect(c.lines[1].amount_usd.value).toBe(c.lines[1].amount.value);
  });

  it("sends a manual value as typed and flags that it differs", () => {
    const f = filled();
    f.lines[0] = { ...f.lines[0], amount: { mode: "manual", value: "31.00" } };
    const c = computed(f);
    expect(c.lines[0].amount.value).toBe("31.00");
    expect(c.lines[0].amount.auto).toBe("30.00");
    expect(c.lines[0].amount.differs).toBe(true);
    expect(c.total_amount.value).toBe("43.50");
    expect(formToReceipt(f).line_items[0].amount).toBe("31.00");
    f.lines[0] = { ...f.lines[0], amount: { mode: "manual", value: "30" } };
    expect(computed(f).lines[0].amount.differs).toBe(false);
  });

  it("has no USD amount for a non-USD receipt without a rate", () => {
    const f = withCurrency(filled(), "EUR");
    const c = computed(f);
    expect(c.rate).toBeNull();
    expect(c.lines[0].amount_usd.value).toBeNull();
    expect(c.total_amount_usd.value).toBeNull();
    f.lines[0] = { ...f.lines[0], amount_usd: { mode: "manual", value: "33.00" } };
    f.lines[1] = { ...f.lines[1], amount_usd: { mode: "manual", value: "13.50" } };
    expect(computed(f).total_amount_usd.value).toBe("46.50");
  });

  it("follows the currency: the rate is 1 and read-only while USD", () => {
    const eur = withCurrency(emptyForm(), "EUR");
    expect(eur.fx_rate_to_usd).toEqual({ mode: "manual", value: "" });
    const back = withCurrency(eur, "usd");
    expect(back.fx_rate_to_usd.mode).toBe("auto");
    const typed = withCurrency({ ...eur, fx_rate_to_usd: { mode: "manual", value: "0.9" } }, "USD");
    expect(typed.fx_rate_to_usd).toEqual({ mode: "manual", value: "0.9" });
  });
});

function roundTrip(r: Record<string, unknown>): string {
  return canonicalJson(formToReceipt(receiptToForm(r).form) as unknown as Record<string, unknown>);
}

describe("round trip (SC-001)", () => {
  const dinner = SAMPLE_BATCH.split("\n").map((l) => JSON.parse(l) as Record<string, unknown>)[1];
  const demo = JSON.parse(readFileSync(resolve(__dirname, "../../../docs/samples/receipt-one.json"), "utf8")) as Record<string, unknown>;
  const samples: [string, Record<string, unknown>][] = [
    ["SAMPLE-001", JSON.parse(SAMPLE_RECEIPT) as Record<string, unknown>],
    ["SAMPLE-002", dinner],
    ["DEMO-001", demo],
    ["E2E-RT", receipt("E2E-RT")],
    ["E2E-RT-APAC", apac("E2E-RT-APAC")],
  ];

  it("covers N = 5 synthetic receipts", () => {
    expect(samples).toHaveLength(5);
  });

  it.each(samples)("%s survives the form unchanged", (_id, r) => {
    expect(roundTrip(r)).toBe(canonicalJson(r));
  });

  it("loads a line whose amount differs from quantity × unit price as manual", () => {
    const r = receipt("E2E-RT");
    (r.line_items as Record<string, unknown>[])[0].amount = 13;
    const { form } = receiptToForm(r);
    expect(form.lines[0].amount).toEqual({ mode: "manual", value: "13" });
    expect(form.lines[1].amount.mode).toBe("auto");
    expect(roundTrip(r)).toBe(canonicalJson(r));
  });

  it("keeps a null rate on a USD receipt", () => {
    const r = receipt("E2E-RT", { fx_rate_to_usd: null });
    expect(formToReceipt(receiptToForm(r).form).fx_rate_to_usd).toBeNull();
    expect(roundTrip(r)).toBe(canonicalJson(r));
  });

  it("keeps a VAT number visible and a stored receipt without the key equal to one with null", () => {
    const r = receipt("E2E-RT", { entity: "GLOBAL", vat_number: "DE999" });
    expect(roundTrip(r)).toBe(canonicalJson(r));
    expect(canonicalJson(receipt("A"))).toBe(canonicalJson({ ...receipt("A"), vat_number: null }));
  });

  it("treats 12.5 and \"12.50\" as the same value", () => {
    const a = receipt("E2E-RT", { total_amount: 20.0 });
    const b = receipt("E2E-RT", { total_amount: "20.00" });
    expect(canonicalJson(a)).toBe(canonicalJson(b));
  });
});

describe("firewall", () => {
  it("drops answer keys and unknown keys and reports them", () => {
    const r = receipt("E2E-FW", { labels: { x: 1 }, notes: "n", foo: 1 });
    (r.line_items as Record<string, unknown>[])[0].labels = { y: 2 };
    const { form, dropped } = receiptToForm(r);
    expect(dropped).toEqual(expect.arrayContaining(["labels", "notes", "foo", "line_items.0.labels"]));
    expect(dropped).toHaveLength(4);
    const body = formToReceipt(form) as unknown as Record<string, unknown>;
    expect(Object.keys(body)).toEqual(RECEIPT_KEYS);
    expect(JSON.stringify(body)).not.toMatch(/"(labels|notes|foo)":/);
  });

  it("reports nothing for a clean receipt", () => {
    expect(receiptToForm(receipt("E2E-FW")).dropped).toEqual([]);
  });
});

describe("validation (US2)", () => {
  it("has no error for a filled form", () => {
    expect(validateForm(filled())).toEqual([]);
  });

  it.each(["receipt_id", "employee_id", "employee_country", "entity", "submitted_expense_type", "mcc", "mcc_description"] as const)(
    "requires %s",
    (field) => {
      const f = filled({ [field]: "" } as Partial<ReceiptFormState>);
      const e = validateForm(f).find((x) => x.path === field);
      expect(e?.message).toBe("Required");
      expect(e?.source).toBe("client");
    },
  );

  it("requires the line fields at their dotted path", () => {
    const f = filled();
    f.lines[1] = { ...f.lines[1], description_raw: "", unit_price: "", line_id: "" };
    const paths = validateForm(f).map((e) => e.path);
    expect(paths).toEqual(expect.arrayContaining(["line_items.1.description_raw", "line_items.1.unit_price", "line_items.1.line_id"]));
  });

  it("explains a comma and a zero", () => {
    const f = filled();
    f.lines[0] = { ...f.lines[0], unit_price: "12,5", quantity: "0" };
    const errors = validateForm(f);
    expect(errors.find((e) => e.path === "line_items.0.unit_price")?.message).toBe("Enter a number, for example 12.50");
    expect(errors.find((e) => e.path === "line_items.0.quantity")?.message).toBe("Must be greater than 0");
  });

  it("wants whole numbers for the integer fields", () => {
    const errors = validateForm(filled({ mcc: "59.4", attendee_count: "2.5", trip_id: "T", trip_nights: "-1" }));
    expect(errors.find((e) => e.path === "mcc")?.message).toBe("Enter a whole number");
    expect(errors.find((e) => e.path === "attendee_count")?.message).toBe("Enter a whole number");
    expect(errors.find((e) => e.path === "trip_nights")).toBeDefined();
  });

  it("checks a typed rate", () => {
    const f = withCurrency(filled(), "EUR");
    expect(validateForm({ ...f, fx_rate_to_usd: { mode: "manual", value: "x" } }).find((e) => e.path === "fx_rate_to_usd")).toBeDefined();
    expect(validateForm({ ...f, fx_rate_to_usd: { mode: "manual", value: "0" } }).find((e) => e.path === "fx_rate_to_usd")?.message).toBe("Must be greater than 0");
  });

  it("applies no policy: a non-USD receipt with no rate and typed USD amounts is fine", () => {
    const f = withCurrency(filled(), "EUR");
    f.lines[0] = { ...f.lines[0], amount_usd: { mode: "manual", value: "33.00" } };
    f.lines[1] = { ...f.lines[1], amount_usd: { mode: "manual", value: "13.50" } };
    expect(validateForm(f)).toEqual([]);
  });

  it("asks for the USD amount when there is no rate and it is empty", () => {
    const f = withCurrency(filled(), "EUR");
    const e = validateForm(f).filter((x) => x.path.endsWith("amount_usd"));
    expect(e.map((x) => x.path)).toEqual(["line_items.0.amount_usd", "line_items.1.amount_usd"]);
    expect(e[0].message).toBe("Required");
  });
});

describe("helpers", () => {
  it("maps server paths onto inputs and leaves the rest", () => {
    const { mapped, unmapped } = serverErrors(["mcc", "line_items.1.language", "line_items", "weird"], filled());
    expect(mapped.map((e) => e.path)).toEqual(["mcc", "line_items.1.language", "line_items"]);
    expect(mapped.every((e) => e.source === "server" && e.message === "The server refused this value")).toBe(true);
    expect(unmapped).toEqual(["weird"]);
  });

  it("maps a whole row and refuses a row that does not exist", () => {
    const { mapped, unmapped } = serverErrors(["line_items.0", "line_items.9.amount"], filled());
    expect(mapped.map((e) => e.path)).toEqual(["line_items.0"]);
    expect(unmapped).toEqual(["line_items.9.amount"]);
  });

  it.each([
    ["JP", "APAC"],
    ["in", "APAC"],
    ["DE", "EMEA"],
    ["US", "GLOBAL"],
    ["", "GLOBAL"],
  ])("suggests the entity of %s", (country, entity) => {
    expect(suggestEntity(country)).toBe(entity);
  });

  it("never reuses a line number after a removal", () => {
    const rows = [
      { ...emptyLine("R", []), line_id: "R-L1" },
      { ...emptyLine("R", []), line_id: "R-L3" },
    ];
    expect(nextLineId("R", rows)).toBe("R-L4");
    expect(nextLineId("R", [])).toBe("R-L1");
  });

  it("renames only the lines that still follow the pattern", () => {
    const rows = [
      { ...emptyLine("OLD", []), line_id: "OLD-L1", line_id_auto: true },
      { ...emptyLine("OLD", []), line_id: "custom", line_id_auto: false },
    ];
    const out = renameLines(rows, "OLD", "NEW");
    expect(out.map((r) => r.line_id)).toEqual(["NEW-L1", "custom"]);
  });

  it("moves the entity with the country until the person picks another", () => {
    const f = withCountry(emptyForm(), "JP");
    expect(f.entity).toBe("APAC");
    expect(withCountry(f, "DE").entity).toBe("EMEA");
    expect(withCountry({ ...f, entity: "GLOBAL" }, "DE").entity).toBe("GLOBAL");
    expect(withCountry(f, "").entity).toBe("APAC");
  });

  it("renames the automatic line IDs with the receipt ID", () => {
    const f = withReceiptId(withReceiptId(emptyForm(), "R-1"), "R-2");
    expect(f.lines[0].line_id).toBe("R-2-L1");
  });

  it("gives every row a key of its own", () => {
    expect(emptyLine("R", []).key).not.toBe(emptyLine("R", []).key);
  });
});
