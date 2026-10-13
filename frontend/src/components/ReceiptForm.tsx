import { useMemo } from "react";
import type { Entity } from "../api/types";
import {
  COUNTRY_SUGGESTIONS,
  CURRENCY_SUGGESTIONS,
  ENTITIES,
  KNOWN_EXPENSE_TYPES,
  MCC_SUGGESTIONS,
  computed,
  entityLabel,
  formToReceipt,
  withCountry,
  withCurrency,
  withReceiptId,
} from "../lib/receiptForm";
import type { FieldError, ReceiptFormState } from "../lib/receiptForm";
import { DerivedField, SelectField, TextField, errorMap, fieldId } from "./FormFields";
import { LineItemsEditor } from "./LineItemsEditor";

const ENTITY_OPTIONS = ENTITIES.map((e) => ({ value: e, label: `${e} · ${entityLabel(e)}` }));

const HEADER_LABEL: Record<string, string> = {
  receipt_id: "Receipt ID",
  employee_id: "Employee ID",
  employee_country: "Employee's home country",
  entity: "Regional entity",
  submitted_expense_type: "Declared expense type",
  merchant_name: "Merchant",
  mcc: "MCC",
  mcc_description: "MCC description",
  transaction_datetime: "Date and time",
  currency: "Currency",
  fx_rate_to_usd: "Rate to USD",
  total_amount: "Total (receipt currency)",
  total_amount_usd: "Total in USD",
  attendee_count: "People covered",
  trip_id: "Trip ID",
  trip_nights: "Trip length (nights)",
  pre_approval_ref: "Approval or exception reference",
  itemized: "The receipt lists its items",
  vat_number: "Merchant VAT number",
  line_items: "Items",
};

const LINE_LABEL: Record<string, string> = {
  line_id: "Line ID",
  description_raw: "Description",
  language: "Language",
  quantity: "Quantity",
  unit_price: "Unit price",
  amount: "Amount",
  amount_usd: "Amount in USD",
};

/** "line_items.1.quantity" → "Line 2, Quantity"; "mcc" → "MCC". */
export function pathLabel(path: string): string {
  const parts = path.split(".");
  if (parts[0] === "line_items" && parts.length >= 2) {
    const line = `Line ${Number(parts[1]) + 1}`;
    return parts[2] ? `${line}, ${LINE_LABEL[parts[2]] ?? parts[2]}` : line;
  }
  return HEADER_LABEL[path] ?? path;
}

/** Everything the page shows when something is wrong: the field errors as links, and what the server named that has no input. */
function ErrorSummary({ errors, unmapped }: { errors: FieldError[]; unmapped: string[] }) {
  if (errors.length === 0 && unmapped.length === 0) return null;
  const client = errors.some((e) => e.source === "client");
  return (
    <div role="alert" className="callout callout--error form-summary">
      <div>
        <strong>{client ? "Fix these before sending." : "The server refused some values."}</strong>
        <ul>
          {errors.map((e) => (
            <li key={e.path}>
              <a
                href={`#${fieldId(e.path)}`}
                onClick={(ev) => {
                  ev.preventDefault();
                  document.getElementById(fieldId(e.path))?.focus();
                }}
              >
                {pathLabel(e.path)}
              </a>
              : {e.message}
            </li>
          ))}
          {unmapped.length > 0 && <li>Also refused: {unmapped.map((f) => <code key={f}>{f}</code>)}</li>}
        </ul>
      </div>
    </div>
  );
}

/** One receipt as a form. Controlled: the page owns the state; this renders it and reports edits. */
export function ReceiptForm({
  form,
  onChange,
  errors,
  unmapped,
}: {
  form: ReceiptFormState;
  onChange: (next: ReceiptFormState) => void;
  errors: FieldError[];
  unmapped: string[];
}) {
  const c = useMemo(() => computed(form), [form]);
  const preview = useMemo(() => JSON.stringify(formToReceipt(form), null, 2), [form]);
  const byPath = useMemo(() => errorMap(errors), [errors]);
  const set = <K extends keyof ReceiptFormState>(key: K, value: ReceiptFormState[K]) => onChange({ ...form, [key]: value });
  const err = (path: string) => byPath.get(path);

  const usd = form.currency.trim().toUpperCase() === "USD";
  const noRate = c.rate === null;
  const showVat = form.entity === "EMEA" || form.vat_visible_on_load;

  function setMcc(value: string) {
    const known = MCC_SUGGESTIONS.find((m) => String(m.mcc) === value.trim());
    onChange({ ...form, mcc: value, mcc_description: known && form.mcc_description.trim() === "" ? known.description : form.mcc_description });
  }

  return (
    <div className="receipt-form">
      <ErrorSummary errors={errors} unmapped={unmapped} />

      <section className="form-section" aria-label="Receipt details">
        <div className="form-grid">
          <TextField path="receipt_id" label="Receipt ID" value={form.receipt_id} onChange={(v) => onChange(withReceiptId(form, v))} error={err("receipt_id")} />
          <TextField path="employee_id" label="Employee ID" value={form.employee_id} onChange={(v) => set("employee_id", v)} error={err("employee_id")} />
          <TextField
            path="employee_country"
            label="Employee's home country"
            value={form.employee_country}
            list="dl-countries"
            hint="Two letters, for example US"
            onChange={(v) => onChange(withCountry(form, v))}
            onBlur={() => set("employee_country", form.employee_country.trim().toUpperCase())}
            error={err("employee_country")}
          />
          <SelectField
            path="entity"
            label="Regional entity"
            value={form.entity}
            options={ENTITY_OPTIONS}
            placeholder="Choose…"
            hint={form.entity === "" ? "Suggested from the country once you type it" : undefined}
            onChange={(v) => set("entity", v as Entity | "")}
            error={err("entity")}
          />
          <TextField
            path="submitted_expense_type"
            label="Declared expense type"
            value={form.submitted_expense_type}
            list="dl-types"
            onChange={(v) => set("submitted_expense_type", v)}
            error={err("submitted_expense_type")}
          />
          <TextField path="merchant_name" label="Merchant" value={form.merchant_name} onChange={(v) => set("merchant_name", v)} error={err("merchant_name")} />
          <TextField path="mcc" label="MCC" value={form.mcc} list="dl-mcc" inputMode="numeric" onChange={setMcc} error={err("mcc")} />
          <TextField
            path="mcc_description"
            label="MCC description"
            value={form.mcc_description}
            onChange={(v) => set("mcc_description", v)}
            error={err("mcc_description")}
          />
          <TextField
            path="transaction_datetime"
            label="Date and time"
            type="datetime-local"
            step="1"
            hint="Local time at the merchant"
            value={form.transaction_datetime}
            onChange={(v) => set("transaction_datetime", v)}
            error={err("transaction_datetime")}
          />
          <TextField
            path="currency"
            label="Currency"
            value={form.currency}
            list="dl-currency"
            onChange={(v) => onChange(withCurrency(form, v))}
            onBlur={() => set("currency", form.currency.trim().toUpperCase())}
            error={err("currency")}
          />
          <DerivedField
            path="fx_rate_to_usd"
            label="Rate to USD"
            derived={form.fx_rate_to_usd}
            eff={{ auto: usd ? "1" : null, value: c.rate, differs: false }}
            warning=""
            readOnly={usd && form.fx_rate_to_usd.mode === "auto"}
            hint={usd ? "1 while the currency is USD" : "On the transaction date"}
            onChange={(d) => set("fx_rate_to_usd", d)}
            error={err("fx_rate_to_usd")}
          />
          <DerivedField
            path="total_amount"
            label="Total (receipt currency)"
            derived={form.total_amount}
            eff={c.total_amount}
            warning="Differs from the sum of the lines"
            onChange={(d) => set("total_amount", d)}
            error={err("total_amount")}
          />
          <DerivedField
            path="total_amount_usd"
            label="Total in USD"
            derived={form.total_amount_usd}
            eff={c.total_amount_usd}
            warning="Differs from the total × rate"
            onChange={(d) => set("total_amount_usd", d)}
            error={err("total_amount_usd")}
          />
          <TextField
            path="attendee_count"
            label="People covered"
            hint="Including the employee"
            inputMode="numeric"
            value={form.attendee_count}
            onChange={(v) => set("attendee_count", v)}
            error={err("attendee_count")}
          />
          <TextField path="trip_id" label="Trip ID" value={form.trip_id} onChange={(v) => set("trip_id", v)} error={err("trip_id")} />
          {form.trip_id.trim() !== "" && (
            <TextField
              path="trip_nights"
              label="Trip length (nights)"
              inputMode="numeric"
              value={form.trip_nights}
              onChange={(v) => set("trip_nights", v)}
              error={err("trip_nights")}
            />
          )}
          <TextField
            path="pre_approval_ref"
            label="Approval or exception reference"
            hint="For example PA-2026-0042"
            value={form.pre_approval_ref}
            onChange={(v) => set("pre_approval_ref", v)}
            error={err("pre_approval_ref")}
          />
          {showVat && (
            <TextField path="vat_number" label="Merchant VAT number" value={form.vat_number} onChange={(v) => set("vat_number", v)} error={err("vat_number")} />
          )}
          <div className="ll-field form-check">
            <label htmlFor={fieldId("itemized")}>
              <input id={fieldId("itemized")} type="checkbox" checked={form.itemized} onChange={(e) => set("itemized", e.target.checked)} /> The receipt lists its items
            </label>
          </div>
        </div>
        <datalist id="dl-countries">
          {COUNTRY_SUGGESTIONS.map((c2) => (
            <option key={c2} value={c2} />
          ))}
        </datalist>
        <datalist id="dl-types">
          {KNOWN_EXPENSE_TYPES.map((t) => (
            <option key={t} value={t} />
          ))}
        </datalist>
        <datalist id="dl-currency">
          {CURRENCY_SUGGESTIONS.map((cur) => (
            <option key={cur} value={cur} />
          ))}
        </datalist>
        <datalist id="dl-mcc">
          {MCC_SUGGESTIONS.map((m) => (
            <option key={m.mcc} value={String(m.mcc)}>
              {m.description}
            </option>
          ))}
        </datalist>
      </section>

      <section className="form-section" aria-label="Items">
        <h3 className="ll-heading">Items</h3>
        <LineItemsEditor
          rows={form.lines}
          receiptId={form.receipt_id}
          itemized={form.itemized}
          computed={c}
          noRate={noRate && !usd}
          errors={byPath}
          onChange={(lines) => set("lines", lines)}
        />
      </section>

      <details className="json-details">
        <summary>Preview JSON</summary>
        <pre className="json-preview mono" tabIndex={0}>
          {preview}
        </pre>
      </details>
    </div>
  );
}
