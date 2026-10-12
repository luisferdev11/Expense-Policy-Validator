// Synthetic receipts for the smoke tests. None of them is a real receipt.
const base = {
  employee_country: "US",
  entity: "GLOBAL",
  mcc: 5943,
  mcc_description: "Office supply stores",
  transaction_datetime: "2026-10-01T10:30:00",
  currency: "USD",
  fx_rate_to_usd: 1.0,
  attendee_count: null,
  trip_id: null,
  trip_nights: null,
  pre_approval_ref: null,
  itemized: true,
};

export function receipt(id: string, over: Record<string, unknown> = {}) {
  return {
    ...base,
    receipt_id: id,
    employee_id: "E-E2E",
    submitted_expense_type: "Office Supplies",
    merchant_name: "E2E Stationers",
    total_amount: 20,
    total_amount_usd: 20,
    line_items: [
      { line_id: `${id}-L1`, description_raw: "Sticky notes", language: "en", quantity: 1, unit_price: 12, amount: 12, amount_usd: 12 },
      { line_id: `${id}-L2`, description_raw: "Wine bottle", language: "en", quantity: 1, unit_price: 8, amount: 8, amount_usd: 8 },
    ],
    ...over,
  };
}

/** An APAC receipt: once a person marks the second line as alcohol, REG-01 fires. */
export const apac = (id: string) => receipt(id, { entity: "APAC", employee_country: "JP" });

export const jsonl = (rows: unknown[]) => rows.map((r) => JSON.stringify(r)).join("\n");
