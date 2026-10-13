// Exact decimal arithmetic on strings, over BigInt with a scale. The backend is exact (Decimal), so
// the form must not compute money with binary floats. No dependency (specs/008 research R3).

interface Dec {
  int: bigint; // the digits with the point removed
  scale: number; // how many of them are after the point
}

const PATTERN = /^-?\d+(\.\d+)?$/;

export function parseDecimal(text: string): Dec | null {
  const s = text.trim();
  if (!PATTERN.test(s)) return null;
  const negative = s.startsWith("-");
  const [whole, fraction = ""] = (negative ? s.slice(1) : s).split(".");
  const int = BigInt(whole + fraction);
  return { int: negative ? -int : int, scale: fraction.length };
}

export const isDecimal = (text: string): boolean => parseDecimal(text) !== null;

function show({ int, scale }: Dec): string {
  const negative = int < 0n;
  let digits = (negative ? -int : int).toString();
  if (scale > 0) {
    digits = digits.padStart(scale + 1, "0");
    digits = `${digits.slice(0, -scale)}.${digits.slice(-scale)}`;
  }
  return negative ? `-${digits}` : digits;
}

const POW10 = (n: number): bigint => 10n ** BigInt(n);

function align(a: Dec, b: Dec): [bigint, bigint, number] {
  const scale = Math.max(a.scale, b.scale);
  return [a.int * POW10(scale - a.scale), b.int * POW10(scale - b.scale), scale];
}

export function add(a: string, b: string): string | null {
  const x = parseDecimal(a);
  const y = parseDecimal(b);
  if (!x || !y) return null;
  const [p, q, scale] = align(x, y);
  return show({ int: p + q, scale });
}

export function mul(a: string, b: string): string | null {
  const x = parseDecimal(a);
  const y = parseDecimal(b);
  if (!x || !y) return null;
  return show({ int: x.int * y.int, scale: x.scale + y.scale });
}

/** Round half away from zero to `scale` places (0.125 → 0.13, -0.125 → -0.13); pads with zeros. */
export function roundHalfUp(text: string, scale: number): string | null {
  const x = parseDecimal(text);
  if (!x) return null;
  if (x.scale <= scale) return show({ int: x.int * POW10(scale - x.scale), scale });
  const divisor = POW10(x.scale - scale);
  const negative = x.int < 0n;
  const magnitude = negative ? -x.int : x.int;
  let quotient = magnitude / divisor;
  if ((magnitude % divisor) * 2n >= divisor) quotient += 1n;
  return show({ int: negative ? -quotient : quotient, scale });
}

/** True when the text is a decimal greater than zero. */
export function isPositive(text: string): boolean {
  const x = parseDecimal(text);
  return x !== null && x.int > 0n;
}

export function equals(a: string, b: string): boolean {
  const x = parseDecimal(a);
  const y = parseDecimal(b);
  if (!x || !y) return false;
  const [p, q] = align(x, y);
  return p === q;
}

/** The shortest text of the same value: "12.50" → "12.5", "12.0" → "12", "-0.00" → "0". */
export function canonical(text: string): string | null {
  const x = parseDecimal(text);
  if (!x) return null;
  let { int, scale } = x;
  while (scale > 0 && int % 10n === 0n) {
    int /= 10n;
    scale -= 1;
  }
  return show({ int, scale });
}
