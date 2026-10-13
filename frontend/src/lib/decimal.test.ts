import { describe, expect, it } from "vitest";
import { add, canonical, equals, isDecimal, isPositive, mul, parseDecimal, roundHalfUp } from "./decimal";

describe("isPositive", () => {
  it("is true only above zero", () => {
    expect(isPositive("0.01")).toBe(true);
    expect(isPositive("0")).toBe(false);
    expect(isPositive("-1")).toBe(false);
    expect(isPositive("x")).toBe(false);
  });
});

describe("parseDecimal", () => {
  it.each(["12", "12.50", "-3.1", " 7 ", "0", "0.0067"])("accepts %j", (s) => {
    expect(isDecimal(s)).toBe(true);
    expect(parseDecimal(s)).not.toBeNull();
  });

  it.each(["12,5", "abc", "", "1e3", "1.", ".5", "--1", "1 2", "+3"])("rejects %j", (s) => {
    expect(isDecimal(s)).toBe(false);
    expect(parseDecimal(s)).toBeNull();
  });
});

describe("exact arithmetic", () => {
  it("multiplies without binary error", () => {
    expect(mul("8000", "0.0067")).toBe("53.6000");
    expect(mul("3", "0.1")).toBe("0.3");
    expect(mul("2", "15.00")).toBe("30.00");
  });

  it("adds without binary error", () => {
    expect(add("0.1", "0.2")).toBe("0.3");
    expect(add("12.5", "30")).toBe("42.5");
    expect(add("-1.5", "0.5")).toBe("-1.0");
  });

  it("keeps large values exact", () => {
    expect(add("123456789012.123456", "0.000001")).toBe("123456789012.123457");
    expect(mul("123456789012", "1000000")).toBe("123456789012000000");
  });

  it("returns null when an input is not a decimal", () => {
    expect(add("1", "x")).toBeNull();
    expect(mul("", "2")).toBeNull();
  });
});

describe("roundHalfUp", () => {
  it("rounds half away from zero", () => {
    expect(roundHalfUp("53.6000", 2)).toBe("53.60");
    expect(roundHalfUp("0.125", 2)).toBe("0.13");
    expect(roundHalfUp("-0.125", 2)).toBe("-0.13");
    expect(roundHalfUp("0.124", 2)).toBe("0.12");
  });

  it("pads when there are fewer digits", () => {
    expect(roundHalfUp("7", 2)).toBe("7.00");
    expect(roundHalfUp("7.5", 2)).toBe("7.50");
  });

  it("returns null for a non-decimal", () => {
    expect(roundHalfUp("abc", 2)).toBeNull();
  });
});

describe("equals and canonical", () => {
  it("compares by value, not by text", () => {
    expect(equals("12.5", "12.50")).toBe(true);
    expect(equals("12.5", "12.51")).toBe(false);
    expect(equals("0", "-0.00")).toBe(true);
    expect(equals("x", "1")).toBe(false);
  });

  it("writes the shortest text for a value", () => {
    expect(canonical("12.50")).toBe("12.5");
    expect(canonical("12.0")).toBe("12");
    expect(canonical("-0.00")).toBe("0");
    expect(canonical("0.0067")).toBe("0.0067");
    expect(canonical("x")).toBeNull();
  });
});
