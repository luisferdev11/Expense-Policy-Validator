/** Money arrives as a string; format it without going through float precision loss. */
export function money(value: string | null, currency: string | null = null): string {
  if (value === null) return "—";
  const [intPart, frac] = value.split(".");
  const neg = intPart.startsWith("-");
  const digits = neg ? intPart.slice(1) : intPart;
  const grouped = digits.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const body = `${neg ? "-" : ""}${grouped}${frac !== undefined ? `.${frac}` : ""}`;
  return currency ? `${body} ${currency}` : body;
}

export function usd(value: string | null): string {
  if (value === null) return "—";
  return `$${money(Number(value).toFixed(2))}`;
}

/** Dates are ISO with local time and no time zone, as recorded: `2026-05-12 19:30`. */
export function recordedDate(iso: string | null): string {
  if (!iso) return "—";
  return iso.replace("T", " ").slice(0, 16);
}

/** Timestamps from the API carry a UTC offset; show them in the viewer's local time. */
export function localStamp(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

export function plural(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}

export function percent(part: number, whole: number): string {
  return whole === 0 ? "—" : `${Math.round((part / whole) * 100)}%`;
}
