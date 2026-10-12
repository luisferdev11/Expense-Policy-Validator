export type IntakePlan =
  | { kind: "empty" }
  | { kind: "invalid"; message: string }
  | { kind: "single"; receipt: Record<string, unknown>; receiptId: string }
  | { kind: "batch"; body: string; contentType: "application/json" | "application/x-ndjson"; rows: number };

export const MAX_BATCH_ROWS = 1000;

/** Decide what the pasted or uploaded text is: one receipt, a JSON array, or JSON Lines. */
export function planIntake(text: string): IntakePlan {
  const trimmed = text.trim();
  if (!trimmed) return { kind: "empty" };

  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch {
    parsed = undefined;
  }

  if (Array.isArray(parsed)) {
    if (parsed.length === 0) return { kind: "invalid", message: "The array is empty." };
    if (parsed.length > MAX_BATCH_ROWS) {
      return { kind: "invalid", message: `A batch has at most ${MAX_BATCH_ROWS} rows; this one has ${parsed.length}.` };
    }
    return { kind: "batch", body: trimmed, contentType: "application/json", rows: parsed.length };
  }
  if (parsed !== null && typeof parsed === "object") {
    const receipt = parsed as Record<string, unknown>;
    return { kind: "single", receipt, receiptId: String(receipt.receipt_id ?? "(no receipt_id)") };
  }

  const lines = trimmed.split(/\r?\n/).filter((l) => l.trim() !== "");
  if (lines.length === 0) return { kind: "empty" };
  if (lines.length > MAX_BATCH_ROWS) {
    return { kind: "invalid", message: `A batch has at most ${MAX_BATCH_ROWS} rows; this one has ${lines.length}.` };
  }
  if (lines.length === 1) {
    return { kind: "invalid", message: "This is not valid JSON. Check for a missing quote, comma or bracket." };
  }
  // Rows that do not parse are reported one by one by the server; only reject obvious non-JSON.
  const startsLikeJson = lines.some((l) => l.trim().startsWith("{"));
  if (!startsLikeJson) return { kind: "invalid", message: "No line looks like a JSON object." };
  return { kind: "batch", body: lines.join("\n"), contentType: "application/x-ndjson", rows: lines.length };
}

/** The source text of each batch row, in the server's row order (1-based rows). */
export function sourceRows(plan: IntakePlan): string[] {
  if (plan.kind !== "batch") return [];
  if (plan.contentType === "application/x-ndjson") return plan.body.split("\n");
  try {
    return (JSON.parse(plan.body) as unknown[]).map((r) => JSON.stringify(r));
  } catch {
    return [];
  }
}

/** The rows a batch refused, as JSON Lines, so they can be fixed and sent again. */
export function refusedRowsText(
  items: { row: number; outcome: string }[],
  rows: string[],
): string {
  return items
    .filter((i) => i.outcome === "invalid" || i.outcome === "duplicate_in_batch")
    .map((i) => rows[i.row - 1])
    .filter((r): r is string => typeof r === "string")
    .join("\n");
}
