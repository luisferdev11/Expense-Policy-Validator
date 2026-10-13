import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DRAFT_KEY, clearDraft, isEmptyDraft, loadDraft, saveDraft } from "./draft";
import type { IntakeDraft } from "./draft";
import { emptyForm } from "./receiptForm";

let store: Map<string, string>;

beforeEach(() => {
  store = new Map();
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
    removeItem: (k: string) => void store.delete(k),
  });
});
afterEach(() => vi.unstubAllGlobals());

function draft(over: Partial<IntakeDraft> = {}): IntakeDraft {
  const form = emptyForm();
  form.receipt_id = "R-DRAFT";
  return { version: 1, mode: "form", form, text: "", idempotencyKey: "", savedAt: "2026-10-12T10:00:00.000Z", ...over };
}

describe("draft storage", () => {
  it("saves and loads the same draft", () => {
    const d = draft({ text: "{}", idempotencyKey: "k-1" });
    saveDraft(d);
    expect(loadDraft()).toEqual(d);
  });

  it("returns null when nothing is saved", () => {
    expect(loadDraft()).toBeNull();
  });

  it("ignores and removes a draft of another version", () => {
    store.set(DRAFT_KEY, JSON.stringify({ ...draft(), version: 2 }));
    expect(loadDraft()).toBeNull();
    expect(store.has(DRAFT_KEY)).toBe(false);
  });

  it("ignores and removes text that is not JSON, or not a draft", () => {
    store.set(DRAFT_KEY, "{not json");
    expect(loadDraft()).toBeNull();
    expect(store.has(DRAFT_KEY)).toBe(false);
    store.set(DRAFT_KEY, JSON.stringify({ version: 1, mode: "form" }));
    expect(loadDraft()).toBeNull();
    expect(store.has(DRAFT_KEY)).toBe(false);
  });

  it("never throws when the storage does", () => {
    vi.stubGlobal("localStorage", {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("blocked");
      },
      removeItem: () => {
        throw new Error("blocked");
      },
    });
    expect(() => saveDraft(draft())).not.toThrow();
    expect(() => clearDraft()).not.toThrow();
    expect(loadDraft()).toBeNull();
  });

  it("clears the draft", () => {
    saveDraft(draft());
    clearDraft();
    expect(store.has(DRAFT_KEY)).toBe(false);
  });

  it("does not save an empty draft, and removes one that became empty", () => {
    saveDraft(draft());
    expect(store.has(DRAFT_KEY)).toBe(true);
    saveDraft(draft({ form: emptyForm() }));
    expect(store.has(DRAFT_KEY)).toBe(false);
  });
});

describe("isEmptyDraft", () => {
  it("is true for a fresh form with no text and no key, whatever the row keys", () => {
    expect(isEmptyDraft(draft({ form: emptyForm() }))).toBe(true);
  });

  it("is false once anything is typed", () => {
    expect(isEmptyDraft(draft())).toBe(false);
    expect(isEmptyDraft(draft({ form: emptyForm(), text: "x" }))).toBe(false);
    expect(isEmptyDraft(draft({ form: emptyForm(), idempotencyKey: "k" }))).toBe(false);
  });
});
