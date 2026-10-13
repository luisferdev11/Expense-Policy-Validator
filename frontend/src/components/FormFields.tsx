import type { ChangeEvent, ReactNode } from "react";
import type { Derived, Effective, FieldError } from "../lib/receiptForm";

/** The DOM id of the input for a field path ("line_items.0.amount" → "f-line_items-0-amount"). */
export const fieldId = (path: string): string => `f-${path.replace(/\./g, "-")}`;

/** Index of the errors by path, first one wins. */
export function errorMap(errors: FieldError[]): Map<string, FieldError> {
  const map = new Map<string, FieldError>();
  for (const e of errors) if (!map.has(e.path)) map.set(e.path, e);
  return map;
}

function describedBy(id: string, hint: boolean, error: boolean, warning: boolean): string | undefined {
  const ids = [hint ? `${id}-hint` : "", warning ? `${id}-warn` : "", error ? `${id}-err` : ""].filter(Boolean);
  return ids.length > 0 ? ids.join(" ") : undefined;
}

interface Common {
  path: string;
  label: string;
  hint?: ReactNode;
  error?: FieldError;
  className?: string;
}

function Shell({ id, label, hint, error, warning, className, children }: Common & { id: string; warning?: string | null; children: ReactNode }) {
  return (
    <div className={`ll-field${className ? ` ${className}` : ""}`}>
      <label htmlFor={id}>{label}</label>
      {children}
      {hint && (
        <span className="hint" id={`${id}-hint`}>
          {hint}
        </span>
      )}
      {warning && (
        <span className="field-warn" id={`${id}-warn`}>
          {warning}
        </span>
      )}
      {error && (
        <span className="field-error" id={`${id}-err`}>
          {error.message}
        </span>
      )}
    </div>
  );
}

export function TextField({
  path,
  label,
  value,
  onChange,
  onBlur,
  hint,
  error,
  className,
  type = "text",
  list,
  inputMode,
  readOnly,
  step,
}: Common & {
  value: string;
  onChange: (v: string) => void;
  onBlur?: () => void;
  type?: string;
  list?: string;
  inputMode?: "numeric" | "decimal" | "text";
  readOnly?: boolean;
  step?: string;
}) {
  const id = fieldId(path);
  return (
    <Shell id={id} label={label} hint={hint} error={error} className={className} path={path}>
      <input
        id={id}
        className="ll-input"
        type={type}
        step={step}
        value={value}
        list={list}
        inputMode={inputMode}
        readOnly={readOnly}
        aria-invalid={error ? "true" : undefined}
        aria-describedby={describedBy(id, !!hint, !!error, false)}
        onChange={(e: ChangeEvent<HTMLInputElement>) => onChange(e.target.value)}
        onBlur={onBlur}
      />
    </Shell>
  );
}

export function SelectField({
  path,
  label,
  value,
  onChange,
  options,
  placeholder,
  hint,
  error,
  className,
}: Common & {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  placeholder?: string;
}) {
  const id = fieldId(path);
  return (
    <Shell id={id} label={label} hint={hint} error={error} className={className} path={path}>
      <select
        id={id}
        className="ll-select"
        value={value}
        aria-invalid={error ? "true" : undefined}
        aria-describedby={describedBy(id, !!hint, !!error, false)}
        onChange={(e) => onChange(e.target.value)}
      >
        {placeholder !== undefined && <option value="">{placeholder}</option>}
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </Shell>
  );
}

/** A number the form can compute: shows the computed value, and a typed one becomes an override. */
export function DerivedField({
  path,
  label,
  derived,
  eff,
  onChange,
  warning,
  emptyHint,
  hint,
  error,
  className,
  readOnly,
}: Common & {
  derived: Derived;
  eff: Effective;
  onChange: (d: Derived) => void;
  warning: string;
  emptyHint?: string;
  readOnly?: boolean;
}) {
  const id = fieldId(path);
  const auto = derived.mode === "auto";
  const shown = auto ? (eff.value ?? "") : derived.value;
  const showEmptyHint = emptyHint && eff.value === null && (auto || derived.value.trim() === "");
  const body = (
    <>
      {auto && eff.value !== null && !readOnly && <span className="computed-tag">computed</span>}
      {!auto && eff.auto !== null && !readOnly && (
        <button type="button" className="link-btn" onClick={() => onChange({ mode: "auto", value: eff.auto ?? "" })}>
          Use computed value
        </button>
      )}
    </>
  );
  return (
    <Shell id={id} label={label} hint={showEmptyHint ? emptyHint : hint} error={error} warning={eff.differs ? `${warning} (${eff.auto ?? ""})` : null} className={className} path={path}>
      <input
        id={id}
        className="ll-input ll-num"
        inputMode="decimal"
        value={shown}
        readOnly={readOnly}
        aria-invalid={error ? "true" : undefined}
        aria-describedby={describedBy(id, !!(showEmptyHint || hint), !!error, eff.differs)}
        onChange={(e) => onChange({ mode: "manual", value: e.target.value })}
      />
      <span className="derived-actions">{body}</span>
    </Shell>
  );
}
