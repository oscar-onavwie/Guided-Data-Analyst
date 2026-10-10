import { test } from "node:test";
import assert from "node:assert/strict";
import { checkFile, compactNumber, correlationColour, formatDate, formatNumber, formatPercent } from "../src/lib/format.ts";

test("formatNumber handles integers, decimals, negatives and missing values", () => {
  assert.equal(formatNumber(1234567), "1,234,567");
  assert.equal(formatNumber(12.3456), "12.35");
  assert.equal(formatNumber(-0.05), "-0.05");
  assert.equal(formatNumber(1234.56), "1,235");
  assert.equal(formatNumber(null), "–");
  assert.equal(formatNumber(Number.NaN), "–");
});

test("compactNumber shortens large values", () => {
  assert.equal(compactNumber(1200), "1.2k");
  assert.equal(compactNumber(3_400_000), "3.4M");
  assert.equal(compactNumber(2000), "2k");
  assert.equal(compactNumber(-1500), "-1.5k");
});

test("formatPercent and formatDate", () => {
  assert.equal(formatPercent(24.7321), "24.7%");
  assert.equal(formatPercent(null), "–");
  assert.equal(formatDate("2025-01-03"), "3 Jan 2025");
  assert.equal(formatDate("not a date"), "not a date");
});

test("checkFile mirrors the backend's upload rules", () => {
  assert.deepEqual(checkFile("sales.CSV", 100, 20), { ok: true, extension: ".csv" });
  assert.deepEqual(checkFile("book.xlsx", 100, 20), { ok: true, extension: ".xlsx" });
  assert.equal(checkFile("old.xls", 100, 20).ok, false);
  assert.equal(checkFile("notes.txt", 100, 20).ok, false);
  assert.equal(checkFile("noextension", 100, 20).ok, false);
  assert.equal(checkFile("empty.csv", 0, 20).ok, false);
  const big = checkFile("big.csv", 21 * 1024 * 1024, 20);
  assert.equal(big.ok, false);
  if (!big.ok) assert.match(big.message, /20 MB limit/);
});

test("correlationColour is diverging and transparent for missing", () => {
  assert.equal(correlationColour(null), "transparent");
  assert.match(correlationColour(0.9), /^rgba\(15, 118, 110/);
  assert.match(correlationColour(-0.9), /^rgba\(185, 28, 28/);
});
