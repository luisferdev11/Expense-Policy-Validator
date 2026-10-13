import { useEffect, useRef } from "react";
import type { Language } from "../api/types";
import { LANGUAGES, emptyLine, languageLabel } from "../lib/receiptForm";
import type { Computed, FieldError, LineRow } from "../lib/receiptForm";
import { DerivedField, SelectField, TextField, fieldId } from "./FormFields";

const LANGUAGE_OPTIONS = LANGUAGES.map((l) => ({ value: l, label: languageLabel(l) }));

/** The repeatable rows. Focus moves to the new row on "Add line", and to a sensible place on a removal. */
export function LineItemsEditor({
  rows,
  receiptId,
  itemized,
  computed,
  noRate,
  errors,
  onChange,
}: {
  rows: LineRow[];
  receiptId: string;
  itemized: boolean;
  computed: Computed;
  noRate: boolean;
  errors: Map<string, FieldError>;
  onChange: (rows: LineRow[]) => void;
}) {
  const focus = useRef<string | null>(null);

  useEffect(() => {
    if (focus.current) {
      document.getElementById(focus.current)?.focus();
      focus.current = null;
    }
  });

  const update = (i: number, patch: Partial<LineRow>) => onChange(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const at = (i: number, field: string) => `line_items.${i}.${field}`;

  function add() {
    focus.current = fieldId(at(rows.length, "description_raw"));
    onChange([...rows, emptyLine(receiptId, rows)]);
  }

  function remove(i: number) {
    focus.current = i === 0 ? "add-line" : `remove-line-${i - 1}`;
    onChange(rows.filter((_, j) => j !== i));
  }

  const listError = errors.get("line_items");
  return (
    <div className="lines">
      {listError && <p className="field-error">{listError.message}</p>}
      {rows.map((row, i) => {
        const c = computed.lines[i];
        const rowError = errors.get(`line_items.${i}`);
        const legend = !itemized && i === 0 ? "The charge" : `Line ${i + 1}`;
        return (
          <fieldset key={row.key} className="line-row">
            <legend>{legend}</legend>
            {rowError && <p className="field-error">{rowError.message}</p>}
            <div className="line-row__grid">
              <TextField
                path={at(i, "description_raw")}
                label="Description (as printed)"
                value={row.description_raw}
                onChange={(v) => update(i, { description_raw: v })}
                error={errors.get(at(i, "description_raw"))}
                className="span-2"
              />
              <SelectField
                path={at(i, "language")}
                label="Language of the description"
                value={row.language}
                options={LANGUAGE_OPTIONS}
                onChange={(v) => update(i, { language: v as Language })}
                error={errors.get(at(i, "language"))}
              />
              <TextField
                path={at(i, "quantity")}
                label="Quantity"
                value={row.quantity}
                inputMode="decimal"
                onChange={(v) => update(i, { quantity: v })}
                error={errors.get(at(i, "quantity"))}
              />
              <TextField
                path={at(i, "unit_price")}
                label="Unit price"
                value={row.unit_price}
                inputMode="decimal"
                onChange={(v) => update(i, { unit_price: v })}
                error={errors.get(at(i, "unit_price"))}
              />
              <DerivedField
                path={at(i, "amount")}
                label="Amount"
                derived={row.amount}
                eff={c.amount}
                warning="Differs from quantity × unit price"
                onChange={(d) => update(i, { amount: d })}
                error={errors.get(at(i, "amount"))}
              />
              <DerivedField
                path={at(i, "amount_usd")}
                label="Amount in USD"
                derived={row.amount_usd}
                eff={c.amount_usd}
                warning="Differs from amount × rate"
                emptyHint={noRate ? "No rate on this receipt: type the USD amount" : undefined}
                onChange={(d) => update(i, { amount_usd: d })}
                error={errors.get(at(i, "amount_usd"))}
              />
              <TextField
                path={at(i, "line_id")}
                label="Line ID"
                value={row.line_id}
                onChange={(v) => update(i, { line_id: v, line_id_auto: false })}
                error={errors.get(at(i, "line_id"))}
              />
            </div>
            <button
              type="button"
              id={`remove-line-${i}`}
              className="ll-btn ll-btn--ghost"
              disabled={rows.length === 1}
              aria-label={`Remove line ${i + 1}`}
              onClick={() => remove(i)}
            >
              Remove
            </button>
          </fieldset>
        );
      })}
      <button type="button" id="add-line" className="ll-btn ll-btn--secondary" onClick={add}>
        Add line
      </button>
    </div>
  );
}
