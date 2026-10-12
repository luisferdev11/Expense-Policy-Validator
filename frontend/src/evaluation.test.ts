import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const root = resolve(__dirname, "..");
const committed = JSON.parse(readFileSync(resolve(root, "public", "evaluation.json"), "utf8"));

describe("public/evaluation.json", () => {
  it("is what the committed outputs produce (run `npm run evaluation` if this fails)", async () => {
    const { build } = (await import(/* @vite-ignore */ resolve(root, "scripts", "build-evaluation.mjs"))) as {
      build: () => unknown;
    };
    expect(JSON.parse(JSON.stringify(build()))).toEqual(committed);
  });

  it("carries aggregates only: no receipt IDs, no answer keys", () => {
    const text = JSON.stringify(committed);
    expect(text).not.toMatch(/RCP-\d+/);
    expect(text).not.toMatch(/"(labels|notes|line_items)"/);
  });

  it("shows every figure with its N", () => {
    for (const s of committed.systems) {
      expect(s.dispositionAccuracy.n).toBeGreaterThan(0);
      expect(s.confusion.n).toBeGreaterThan(0);
    }
    for (const v of committed.classifiers.variants) expect(v.accuracy.n).toBe(committed.classifiers.n);
  });

  it("reproduces the committed E14 numbers for the four registered variants", () => {
    const byName = Object.fromEntries(committed.classifiers.variants.map((v: { variant: string }) => [v.variant, v]));
    expect(byName["gpt-oss-120b"].accuracy.k).toBe(123);
    expect(byName["gpt-oss-20b"].accuracy.k).toBe(122);
    expect(byName["gemma-3-12b"].accuracy.k).toBe(115);
  });
});
