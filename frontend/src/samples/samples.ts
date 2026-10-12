// Synthetic receipts for trying the app. None of them is a real receipt.
const office = {
  receipt_id: "SAMPLE-001",
  employee_id: "E-1001",
  employee_country: "US",
  entity: "GLOBAL",
  submitted_expense_type: "Office Supplies",
  merchant_name: "Cornerstone Office Supply",
  mcc: 5943,
  mcc_description: "Office supply stores",
  transaction_datetime: "2026-10-01T10:30:00",
  currency: "USD",
  fx_rate_to_usd: 1.0,
  total_amount: 42.5,
  total_amount_usd: 42.5,
  attendee_count: null,
  trip_id: null,
  trip_nights: null,
  pre_approval_ref: null,
  itemized: true,
  line_items: [
    { line_id: "SAMPLE-001-L1", description_raw: "Legal pads 3-pack", language: "en", quantity: 1, unit_price: 12.5, amount: 12.5, amount_usd: 12.5 },
    { line_id: "SAMPLE-001-L2", description_raw: "Ballpoint pens box of 12", language: "en", quantity: 2, unit_price: 15.0, amount: 30.0, amount_usd: 30.0 },
  ],
};

const dinner = {
  receipt_id: "SAMPLE-002",
  employee_id: "E-2002",
  employee_country: "JP",
  entity: "APAC",
  submitted_expense_type: "Meals - Client Entertainment",
  merchant_name: "Sakura Dining",
  mcc: 5812,
  mcc_description: "Eating places, restaurants",
  transaction_datetime: "2026-09-20T19:30:00",
  currency: "JPY",
  fx_rate_to_usd: 0.0067,
  total_amount: 28000,
  total_amount_usd: 187.6,
  attendee_count: 4,
  trip_id: null,
  trip_nights: null,
  pre_approval_ref: null,
  itemized: true,
  line_items: [
    { line_id: "SAMPLE-002-L1", description_raw: "Set dinner", language: "en", quantity: 4, unit_price: 5000, amount: 20000, amount_usd: 134.0 },
    { line_id: "SAMPLE-002-L2", description_raw: "Sake bottle", language: "en", quantity: 2, unit_price: 4000, amount: 8000, amount_usd: 53.6 },
  ],
};

export const SAMPLE_RECEIPT = JSON.stringify(office, null, 2);

/** Two valid receipts and one row the server must refuse, to show a partial success. */
export const SAMPLE_BATCH = [
  JSON.stringify(office),
  JSON.stringify(dinner),
  JSON.stringify({ receipt_id: "SAMPLE-BAD", employee_id: "E-0" }),
].join("\n");
