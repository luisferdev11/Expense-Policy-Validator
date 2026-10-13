// The guided intake form as pure functions: state, computed values, conversion to and from the
// receipt JSON, and validation. No policy lives here: the form checks only what the API itself
// refuses (specs/008-guided-intake research R4). The component only renders and wires these.

import type { Entity, Language, LineItemInputRequest, ReceiptInput } from "../api/types";
import expenseTypes from "../samples/expense-types.json";
import { add, canonical, equals, isDecimal, isPositive, mul, roundHalfUp } from "./decimal";

// ---- Options typed against the API: a missing or extra entry is a type error ----

const ENTITY_LABEL: Record<Entity, string> = {
  GLOBAL: "Global",
  APAC: "Asia-Pacific",
  EMEA: "Europe, Middle East and Africa",
};
export const ENTITIES = Object.keys(ENTITY_LABEL) as Entity[];
export const entityLabel = (e: Entity): string => ENTITY_LABEL[e];

const LANGUAGE_LABEL: Record<Language, string> = {
  en: "English",
  es: "Spanish",
  fr: "French",
  de: "German",
  pt: "Portuguese",
  ja: "Japanese",
};
export const LANGUAGES = Object.keys(LANGUAGE_LABEL) as Language[];
export const languageLabel = (l: Language): string => LANGUAGE_LABEL[l];

/** Declared types the engine knows; kept equal to the engine by tests/contract/test_expense_types.py. */
export const KNOWN_EXPENSE_TYPES: string[] = expenseTypes;

/** Suggestions only. The MCC table of data/policy-docs/merchant-category-risk.md, without its risk column. */
export const MCC_SUGGESTIONS: { mcc: number; description: string }[] = [
  { mcc: 4111, description: "Local and suburban transit" },
  { mcc: 4121, description: "Taxicabs, limousines, rideshare" },
  { mcc: 5311, description: "Department stores" },
  { mcc: 5411, description: "Grocery stores and supermarkets" },
  { mcc: 5732, description: "Electronics stores" },
  { mcc: 5734, description: "Computer software stores" },
  { mcc: 5812, description: "Eating places and restaurants" },
  { mcc: 5813, description: "Bars, taverns, cocktail lounges" },
  { mcc: 5912, description: "Drug stores and pharmacies" },
  { mcc: 5921, description: "Package stores — beer, wine, liquor" },
  { mcc: 5942, description: "Book stores" },
  { mcc: 5943, description: "Office and stationery supply" },
  { mcc: 5944, description: "Jewelry, watch, and silverware stores" },
  { mcc: 5993, description: "Cigar stores and stands" },
  { mcc: 7011, description: "Hotels, motels, resorts" },
  { mcc: 7216, description: "Dry cleaners and laundry services" },
  { mcc: 7297, description: "Massage parlors" },
  { mcc: 7995, description: "Betting, casino gaming, lottery" },
];

export const COUNTRY_SUGGESTIONS = ["US", "GB", "DE", "FR", "NL", "IE", "PT", "ES", "IN", "JP", "SG"];
export const CURRENCY_SUGGESTIONS = ["USD", "EUR", "GBP", "INR", "JPY", "SGD"];

// ---- State ----

/** A value the form can compute. "auto" follows the computation; "manual" keeps what was typed. */
export interface Derived {
  mode: "auto" | "manual";
  value: string;
}

export interface LineRow {
  key: string; // React key, stable for the row's life; never sent
  line_id: string;
  line_id_auto: boolean; // true while line_id follows `${receipt_id}-L${n}`
  description_raw: string;
  language: Language;
  quantity: string;
  unit_price: string;
  amount: Derived;
  amount_usd: Derived;
}

export interface ReceiptFormState {
  receipt_id: string;
  employee_id: string;
  employee_country: string;
  entity: Entity | "";
  submitted_expense_type: string;
  merchant_name: string;
  mcc: string;
  mcc_description: string;
  transaction_datetime: string;
  currency: string;
  fx_rate_to_usd: Derived;
  total_amount: Derived;
  total_amount_usd: Derived;
  attendee_count: string;
  trip_id: string;
  trip_nights: string;
  pre_approval_ref: string;
  itemized: boolean;
  vat_number: string;
  vat_visible_on_load: boolean;
  lines: LineRow[];
}

export interface FieldError {
  path: string; // the server's dotted loc: "employee_id", "line_items.0.amount"
  message: string;
  source: "client" | "server";
}

/** The request body: every Decimal is a string. */
export type LineItemJson = Omit<LineItemInputRequest, "quantity" | "unit_price" | "amount" | "amount_usd"> & {
  quantity: string;
  unit_price: string;
  amount: string;
  amount_usd: string;
};
export type ReceiptInputJson = Omit<ReceiptInput, "fx_rate_to_usd" | "total_amount" | "total_amount_usd" | "line_items"> & {
  fx_rate_to_usd: string | null;
  total_amount: string | null;
  total_amount_usd: string | null;
  line_items: LineItemJson[];
};

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
] as const;
const LINE_KEYS = ["line_id", "description_raw", "language", "quantity", "unit_price", "amount", "amount_usd"] as const;
const DECIMAL_KEYS = new Set<string>(["fx_rate_to_usd", "total_amount", "total_amount_usd", "quantity", "unit_price", "amount", "amount_usd"]);

const MONEY_MESSAGE = "Enter a number, for example 12.50";
const WHOLE_MESSAGE = "Enter a whole number";
const POSITIVE_MESSAGE = "Must be greater than 0";
const REQUIRED = "Required";
const SERVER_MESSAGE = "The server refused this value";

const isUsd = (currency: string): boolean => currency.trim().toUpperCase() === "USD";
const blank = (s: string): boolean => s.trim() === "";

let sequence = 0;
const keyPrefix = Math.random().toString(36).slice(2, 8);
const newKey = (): string => `${keyPrefix}-${(sequence += 1)}`;

// ---- Line IDs ----

const lineNumber = (lineId: string): number => {
  const m = /-L(\d+)$/.exec(lineId);
  return m ? Number(m[1]) : 0;
};

/** `${receiptId}-L${n}`, n one more than the highest number in use, so a removal never frees a number. */
export function nextLineId(receiptId: string, rows: LineRow[]): string {
  const highest = rows.reduce((n, r) => Math.max(n, lineNumber(r.line_id)), 0);
  return `${receiptId.trim()}-L${highest + 1}`;
}

/** Renames only the rows whose ID still follows the automatic pattern. */
export function renameLines(rows: LineRow[], oldId: string, newId: string): LineRow[] {
  const oldPrefix = `${oldId.trim()}-L`;
  return rows.map((r) =>
    r.line_id_auto && r.line_id.startsWith(oldPrefix) ? { ...r, line_id: `${newId.trim()}-L${r.line_id.slice(oldPrefix.length)}` } : r,
  );
}

export function emptyLine(receiptId: string, rows: LineRow[]): LineRow {
  return {
    key: newKey(),
    line_id: nextLineId(receiptId, rows),
    line_id_auto: true,
    description_raw: "",
    language: "en",
    quantity: "1",
    unit_price: "",
    amount: { mode: "auto", value: "" },
    amount_usd: { mode: "auto", value: "" },
  };
}

export function emptyForm(): ReceiptFormState {
  return {
    receipt_id: "",
    employee_id: "",
    employee_country: "",
    entity: "",
    submitted_expense_type: "",
    merchant_name: "",
    mcc: "",
    mcc_description: "",
    transaction_datetime: "",
    currency: "USD",
    fx_rate_to_usd: { mode: "auto", value: "1" },
    total_amount: { mode: "auto", value: "" },
    total_amount_usd: { mode: "auto", value: "" },
    attendee_count: "",
    trip_id: "",
    trip_nights: "",
    pre_approval_ref: "",
    itemized: true,
    vat_number: "",
    vat_visible_on_load: false,
    lines: [emptyLine("", [])],
  };
}

// ---- Suggestions and linked edits ----

const APAC = new Set(["IN", "JP", "SG"]);
const EMEA = new Set(["GB", "DE", "FR", "NL", "IE", "PT", "ES"]);

/** The entity a home country suggests (data/README); the person confirms it. */
export function suggestEntity(country: string): Entity {
  const c = country.trim().toUpperCase();
  if (APAC.has(c)) return "APAC";
  if (EMEA.has(c)) return "EMEA";
  return "GLOBAL";
}

/** Changing the country moves the entity along while the person has not chosen a different one. */
export function withCountry(s: ReceiptFormState, country: string): ReceiptFormState {
  const follows = s.entity === "" || s.entity === suggestEntity(s.employee_country);
  return { ...s, employee_country: country, entity: follows && country.trim() !== "" ? suggestEntity(country) : s.entity };
}

/** Changing the receipt ID renames the lines that still follow it. */
export function withReceiptId(s: ReceiptFormState, receiptId: string): ReceiptFormState {
  return { ...s, receipt_id: receiptId, lines: renameLines(s.lines, s.receipt_id, receiptId) };
}

/** The rate is 1 and read-only while the currency is USD; leaving USD empties it for the person to type. */
export function withCurrency(s: ReceiptFormState, currency: string): ReceiptFormState {
  const rate = s.fx_rate_to_usd;
  let next = rate;
  if (isUsd(currency)) {
    if (rate.mode === "manual" && (blank(rate.value) || equals(rate.value, "1"))) next = { mode: "auto", value: "1" };
  } else if (rate.mode === "auto") {
    next = { mode: "manual", value: "" };
  }
  return { ...s, currency, fx_rate_to_usd: next };
}

// ---- Computation ----

/** `auto` is what the computation gives, `value` what is shown and sent, `differs` flags an override. */
export interface Effective {
  auto: string | null;
  value: string | null;
  differs: boolean;
}
export interface Computed {
  rate: string | null;
  lines: { amount: Effective; amount_usd: Effective }[];
  total_amount: Effective;
  total_amount_usd: Effective;
}

function effective(derived: Derived, auto: string | null): Effective {
  if (derived.mode === "auto") return { auto, value: auto, differs: false };
  const typed = derived.value.trim();
  const value = typed === "" ? null : typed;
  const differs = auto !== null && value !== null && isDecimal(value) && !equals(value, auto);
  return { auto, value, differs };
}

const asDecimal = (v: string | null): string | null => (v !== null && isDecimal(v) ? v : null);

function sum(values: (string | null)[]): string | null {
  let total = "0";
  for (const v of values) {
    if (v === null) return null;
    const next = add(total, v);
    if (next === null) return null;
    total = next;
  }
  return total;
}

/** Every derived value from the current inputs; null where it cannot be computed. */
export function computed(s: ReceiptFormState): Computed {
  const usd = isUsd(s.currency);
  const rateText = s.fx_rate_to_usd.mode === "auto" ? (usd ? "1" : null) : s.fx_rate_to_usd.value.trim() || null;

  const lines = s.lines.map((l) => {
    const amount = effective(l.amount, mul(l.quantity, l.unit_price));
    const converted = usd ? asDecimal(amount.value) : rateText !== null && amount.value !== null ? roundHalfUp(mul(amount.value, rateText) ?? "x", 2) : null;
    return { amount, amount_usd: effective(l.amount_usd, converted) };
  });

  const total_amount = effective(s.total_amount, sum(lines.map((l) => l.amount.value)));
  const totalUsd = usd
    ? asDecimal(total_amount.value)
    : rateText !== null && total_amount.value !== null
      ? roundHalfUp(mul(total_amount.value, rateText) ?? "x", 2)
      : sum(lines.map((l) => l.amount_usd.value));
  return { rate: rateText, lines, total_amount, total_amount_usd: effective(s.total_amount_usd, totalUsd) };
}

// ---- Form → receipt ----

const orNull = (s: string): string | null => (blank(s) ? null : s);

function integerOrRaw(s: string): number | null {
  const t = s.trim();
  if (t === "") return null;
  return /^-?\d+$/.test(t) ? Number(t) : (t as unknown as number);
}

function datetime(s: string): string | null {
  const t = s.trim();
  if (t === "") return null;
  return /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(t) ? `${t}:00` : t;
}

/** The exact request body: every receipt key in contract order, `null` for an empty nullable field. */
export function formToReceipt(s: ReceiptFormState): ReceiptInputJson {
  const c = computed(s);
  const vatShown = s.entity === "EMEA" || s.vat_visible_on_load;
  return {
    receipt_id: s.receipt_id.trim(),
    employee_id: s.employee_id.trim(),
    employee_country: s.employee_country.trim().toUpperCase(),
    entity: s.entity as Entity,
    submitted_expense_type: s.submitted_expense_type,
    merchant_name: orNull(s.merchant_name),
    mcc: integerOrRaw(s.mcc) as number,
    mcc_description: s.mcc_description,
    transaction_datetime: datetime(s.transaction_datetime),
    currency: orNull(s.currency)?.trim() ?? null,
    fx_rate_to_usd: c.rate,
    total_amount: c.total_amount.value,
    total_amount_usd: c.total_amount_usd.value,
    attendee_count: integerOrRaw(s.attendee_count),
    trip_id: orNull(s.trip_id)?.trim() ?? null,
    trip_nights: blank(s.trip_id) ? null : integerOrRaw(s.trip_nights),
    pre_approval_ref: orNull(s.pre_approval_ref),
    itemized: s.itemized,
    vat_number: vatShown ? orNull(s.vat_number) : null,
    line_items: s.lines.map((l, i) => ({
      line_id: l.line_id.trim(),
      description_raw: l.description_raw,
      language: l.language,
      quantity: l.quantity.trim(),
      unit_price: l.unit_price.trim(),
      amount: c.lines[i].amount.value ?? "",
      amount_usd: c.lines[i].amount_usd.value ?? "",
    })),
  };
}

// ---- Receipt → form ----

type Json = Record<string, unknown>;

function text(v: unknown): string {
  if (v === null || v === undefined) return "";
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  return JSON.stringify(v);
}

const escapeRegExp = (s: string): string => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/**
 * The inverse of `formToReceipt`. Keys the form does not know (answer keys included) are dropped and
 * reported by path. A derived value that differs from its computation loads as a manual override, so
 * a stored receipt is reproduced exactly and sending it again is "Already known".
 */
export function receiptToForm(json: Json): { form: ReceiptFormState; dropped: string[] } {
  const dropped: string[] = [];
  const known = new Set<string>(RECEIPT_KEYS);
  for (const k of Object.keys(json)) if (!known.has(k)) dropped.push(k);

  const rawLines = Array.isArray(json.line_items) ? (json.line_items as Json[]) : [];
  const lineKnown = new Set<string>(LINE_KEYS);
  rawLines.forEach((l, i) => {
    for (const k of Object.keys(l ?? {})) if (!lineKnown.has(k)) dropped.push(`line_items.${i}.${k}`);
  });

  const receiptId = text(json.receipt_id);
  const autoId = new RegExp(`^${escapeRegExp(receiptId.trim())}-L\\d+$`);
  const lines: LineRow[] = rawLines.map((l) => {
    const lineId = text(l?.line_id);
    const language = text(l?.language);
    return {
      key: newKey(),
      line_id: lineId,
      line_id_auto: autoId.test(lineId),
      description_raw: text(l?.description_raw),
      language: (language === "" ? "en" : language) as Language,
      quantity: text(l?.quantity),
      unit_price: text(l?.unit_price),
      amount: { mode: "manual", value: text(l?.amount) },
      amount_usd: { mode: "manual", value: text(l?.amount_usd) },
    };
  });

  const entity = text(json.entity);
  const vat = text(json.vat_number);
  const form: ReceiptFormState = {
    receipt_id: receiptId,
    employee_id: text(json.employee_id),
    employee_country: text(json.employee_country),
    entity: (ENTITIES as string[]).includes(entity) ? (entity as Entity) : "",
    submitted_expense_type: text(json.submitted_expense_type),
    merchant_name: text(json.merchant_name),
    mcc: text(json.mcc),
    mcc_description: text(json.mcc_description),
    transaction_datetime: text(json.transaction_datetime),
    currency: text(json.currency),
    fx_rate_to_usd: { mode: "manual", value: text(json.fx_rate_to_usd) },
    total_amount: { mode: "manual", value: text(json.total_amount) },
    total_amount_usd: { mode: "manual", value: text(json.total_amount_usd) },
    attendee_count: text(json.attendee_count),
    trip_id: text(json.trip_id),
    trip_nights: text(json.trip_nights),
    pre_approval_ref: text(json.pre_approval_ref),
    itemized: typeof json.itemized === "boolean" ? json.itemized : true,
    vat_number: vat,
    vat_visible_on_load: vat !== "",
    lines: lines.length > 0 ? lines : [emptyLine(receiptId, [])],
  };

  // With every derived value held as typed, each `auto` is what that value would be computed as.
  // Switch a value to auto only where the stored text equals the computation.
  const c = computed(form);
  const follow = (d: Derived, e: Effective): Derived => (e.auto !== null && isDecimal(d.value) && equals(d.value, e.auto) ? { mode: "auto", value: d.value } : d);
  form.fx_rate_to_usd = isUsd(form.currency) && isDecimal(form.fx_rate_to_usd.value) && equals(form.fx_rate_to_usd.value, "1") ? { mode: "auto", value: "1" } : form.fx_rate_to_usd;
  form.lines = form.lines.map((l, i) => ({ ...l, amount: follow(l.amount, c.lines[i].amount), amount_usd: follow(l.amount_usd, c.lines[i].amount_usd) }));
  form.total_amount = follow(form.total_amount, c.total_amount);
  form.total_amount_usd = follow(form.total_amount_usd, c.total_amount_usd);
  return { form, dropped };
}

/** A stable text of a receipt: sorted keys, decimals in their shortest form, `vat_number` defaulted. */
export function canonicalJson(receipt: Json): string {
  const norm = (value: unknown, key?: string): unknown => {
    if (Array.isArray(value)) return value.map((v) => norm(v));
    if (value !== null && typeof value === "object") {
      return Object.fromEntries(
        Object.entries(value as Json)
          .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
          .map(([k, v]) => [k, norm(v, k)]),
      );
    }
    if (key !== undefined && DECIMAL_KEYS.has(key) && (typeof value === "number" || typeof value === "string")) {
      return canonical(String(value)) ?? value;
    }
    return value;
  };
  return JSON.stringify(norm({ vat_number: null, ...receipt }));
}

// ---- Validation ----

/** Only what the API itself refuses (research R4). Nothing from the policies. */
export function validateForm(s: ReceiptFormState): FieldError[] {
  const errors: FieldError[] = [];
  const fail = (path: string, message: string) => errors.push({ path, message, source: "client" });
  const required = (path: string, value: string) => {
    if (blank(value)) fail(path, REQUIRED);
    return !blank(value);
  };
  const wholeNumber = (path: string, value: string, minimum?: number) => {
    if (blank(value)) return;
    const t = value.trim();
    if (!/^-?\d+$/.test(t)) fail(path, WHOLE_MESSAGE);
    else if (minimum !== undefined && Number(t) < minimum) fail(path, "Enter a whole number, 0 or more");
  };

  const c = computed(s);
  required("receipt_id", s.receipt_id);
  required("employee_id", s.employee_id);
  required("employee_country", s.employee_country);
  if (s.entity === "") fail("entity", REQUIRED);
  required("submitted_expense_type", s.submitted_expense_type);
  if (required("mcc", s.mcc)) wholeNumber("mcc", s.mcc);
  required("mcc_description", s.mcc_description);

  const rate = s.fx_rate_to_usd;
  if (rate.mode === "manual" && !blank(rate.value)) {
    if (!isDecimal(rate.value)) fail("fx_rate_to_usd", MONEY_MESSAGE);
    else if (!isPositive(rate.value)) fail("fx_rate_to_usd", POSITIVE_MESSAGE);
  }
  for (const [path, derived] of [
    ["total_amount", s.total_amount],
    ["total_amount_usd", s.total_amount_usd],
  ] as const) {
    if (derived.mode === "manual" && !blank(derived.value) && !isDecimal(derived.value)) fail(path, MONEY_MESSAGE);
  }
  wholeNumber("attendee_count", s.attendee_count);
  if (!blank(s.trip_id)) wholeNumber("trip_nights", s.trip_nights, 0);

  const noRate = c.rate === null;
  s.lines.forEach((l, i) => {
    const at = (field: string) => `line_items.${i}.${field}`;
    required(at("line_id"), l.line_id);
    required(at("description_raw"), l.description_raw);
    if (!(LANGUAGES as string[]).includes(l.language)) fail(at("language"), "Choose a language");
    if (required(at("quantity"), l.quantity)) {
      if (!isDecimal(l.quantity)) fail(at("quantity"), MONEY_MESSAGE);
      else if (!isPositive(l.quantity)) fail(at("quantity"), POSITIVE_MESSAGE);
    }
    if (required(at("unit_price"), l.unit_price) && !isDecimal(l.unit_price)) fail(at("unit_price"), MONEY_MESSAGE);

    const amount = c.lines[i].amount;
    if (l.amount.mode === "manual") {
      if (required(at("amount"), l.amount.value) && !isDecimal(l.amount.value)) fail(at("amount"), MONEY_MESSAGE);
    }
    const usd = c.lines[i].amount_usd;
    if (l.amount_usd.mode === "manual") {
      if (required(at("amount_usd"), l.amount_usd.value) && !isDecimal(l.amount_usd.value)) fail(at("amount_usd"), MONEY_MESSAGE);
    } else if (usd.value === null && noRate && amount.value !== null && isDecimal(amount.value)) {
      fail(at("amount_usd"), REQUIRED);
    }
  });
  return errors;
}

/** Maps the server's field paths onto inputs; what it cannot place is returned as text. */
export function serverErrors(fields: string[], s: ReceiptFormState): { mapped: FieldError[]; unmapped: string[] } {
  const mapped: FieldError[] = [];
  const unmapped: string[] = [];
  const header = new Set<string>(RECEIPT_KEYS);
  const lineFields = new Set<string>(LINE_KEYS);
  for (const path of fields) {
    const parts = path.split(".");
    let ok = false;
    if (parts.length === 1 && header.has(parts[0])) ok = true;
    else if (parts[0] === "line_items" && parts.length >= 2 && /^\d+$/.test(parts[1]) && Number(parts[1]) < s.lines.length) {
      ok = parts.length === 2 || (parts.length === 3 && lineFields.has(parts[2]));
    }
    if (ok) mapped.push({ path, message: SERVER_MESSAGE, source: "server" });
    else unmapped.push(path);
  }
  return { mapped, unmapped };
}
