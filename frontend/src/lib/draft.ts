// The intake draft: what a person was typing, kept in this browser so leaving the screen loses
// nothing. One versioned key; a draft of another version is ignored and removed (specs/008 R6).

import { readStore, removeStore, writeStore } from "./hooks";
import { emptyForm } from "./receiptForm";
import type { ReceiptFormState } from "./receiptForm";

export const DRAFT_KEY = "epv.intake.draft.v1";

export interface IntakeDraft {
  version: 1;
  mode: "form" | "single" | "batch";
  form: ReceiptFormState;
  text: string; // the textarea
  idempotencyKey: string;
  savedAt: string; // ISO time, for the "Draft restored from …" notice
}

/** Row keys are never sent and differ on every `emptyForm()`, so they do not count as typing. */
function withoutKeys(form: ReceiptFormState): string {
  return JSON.stringify({ ...form, lines: form.lines.map((l) => ({ ...l, key: "" })) });
}

export function isEmptyDraft(d: IntakeDraft): boolean {
  return d.text === "" && d.idempotencyKey === "" && withoutKeys(d.form) === withoutKeys(emptyForm());
}

function isDraft(value: unknown): value is IntakeDraft {
  if (value === null || typeof value !== "object") return false;
  const d = value as Partial<IntakeDraft>;
  return (
    d.version === 1 &&
    (d.mode === "form" || d.mode === "single" || d.mode === "batch") &&
    typeof d.text === "string" &&
    typeof d.idempotencyKey === "string" &&
    typeof d.savedAt === "string" &&
    d.form !== null &&
    typeof d.form === "object" &&
    Array.isArray((d.form as Partial<ReceiptFormState>).lines)
  );
}

export function loadDraft(): IntakeDraft | null {
  const raw = readStore(DRAFT_KEY);
  if (raw === null) return null;
  try {
    const value: unknown = JSON.parse(raw);
    if (isDraft(value)) return value;
  } catch {
    /* fall through: the entry is not usable */
  }
  removeStore(DRAFT_KEY);
  return null;
}

/** Saves the draft; an empty one is not worth keeping, so it removes what was there. */
export function saveDraft(d: IntakeDraft): void {
  if (isEmptyDraft(d)) {
    removeStore(DRAFT_KEY);
    return;
  }
  writeStore(DRAFT_KEY, JSON.stringify(d));
}

export function clearDraft(): void {
  removeStore(DRAFT_KEY);
}
