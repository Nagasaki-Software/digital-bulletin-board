import test from "node:test";
import assert from "node:assert/strict";
import { isStandbyTime, toMinutes } from "../../static/js/timeutil.mjs";

const at = (h, m) => h * 60 + m;

test("toMinutes", () => {
  assert.equal(toMinutes("07:30"), 450);
  assert.equal(toMinutes("18:00"), 1080);
});

test("standby across midnight (18:00 - 07:30)", () => {
  assert.equal(isStandbyTime(at(18, 0), "18:00", "07:30"), true);
  assert.equal(isStandbyTime(at(23, 59), "18:00", "07:30"), true);
  assert.equal(isStandbyTime(at(0, 0), "18:00", "07:30"), true);
  assert.equal(isStandbyTime(at(7, 29), "18:00", "07:30"), true);
  assert.equal(isStandbyTime(at(7, 30), "18:00", "07:30"), false);
  assert.equal(isStandbyTime(at(12, 0), "18:00", "07:30"), false);
  assert.equal(isStandbyTime(at(17, 59), "18:00", "07:30"), false);
});

test("standby within one day", () => {
  assert.equal(isStandbyTime(at(13, 0), "12:00", "14:00"), true);
  assert.equal(isStandbyTime(at(14, 0), "12:00", "14:00"), false);
  assert.equal(isStandbyTime(at(11, 59), "12:00", "14:00"), false);
});

test("start equal to end means never standby", () => {
  assert.equal(isStandbyTime(at(12, 0), "12:00", "12:00"), false);
});

test('"7:30" (no leading zero) is valid', () => {
  assert.equal(toMinutes("7:30"), 450);
  assert.equal(isStandbyTime(at(7, 0), "18:00", "7:30"), true);
  assert.equal(isStandbyTime(at(7, 30), "18:00", "7:30"), false);
});

test("malformed or non-string times never standby and never throw", () => {
  for (const bad of ["abc", "", "25:00", "12:75", "12", "12:3", "1:2:3", 730, null, undefined, {}, ["7:30"]]) {
    assert.doesNotThrow(() => isStandbyTime(at(12, 0), bad, "07:30"));
    assert.doesNotThrow(() => isStandbyTime(at(12, 0), "18:00", bad));
    assert.equal(isStandbyTime(at(12, 0), bad, "07:30"), false);
    assert.equal(isStandbyTime(at(23, 0), "18:00", bad), false);
    assert.equal(isStandbyTime(at(23, 0), bad, bad), false);
  }
  assert.ok(Number.isNaN(toMinutes("garbage")));
  assert.ok(Number.isNaN(toMinutes(730)));
});

test("default sleep window is 18:00 - 08:00", () => {
  assert.equal(isStandbyTime(at(7, 59), "18:00", "08:00"), true);
  assert.equal(isStandbyTime(at(8, 0), "18:00", "08:00"), false);
  assert.equal(isStandbyTime(at(7, 30), "18:00", "08:00"), true); // 旧既定（07:30）ではここは通常表示だった
  assert.equal(isStandbyTime(at(17, 59), "18:00", "08:00"), false);
  assert.equal(isStandbyTime(at(18, 0), "18:00", "08:00"), true);
  assert.equal(isStandbyTime(at(8, 0), "18:00", "8:00"), false);
});

test("standby.js default config matches the server default (08:00)", async () => {
  const { readFileSync } = await import("node:fs");
  const src = readFileSync(new URL("../../static/js/standby.js", import.meta.url), "utf8");
  assert.match(src, /let cfg = \{ start: "18:00", end: "08:00", wake_idle_seconds: 300 \}/);
});

import { normalizeHHMM, secondsValue } from "../../static/js/timeutil.mjs";

test("normalizeHHMM: 24-hour HH:MM, also from text fallback input", () => {
  assert.equal(normalizeHHMM("18:00"), "18:00");
  assert.equal(normalizeHHMM("8:00"), "08:00");
  assert.equal(normalizeHHMM(" 8:05 "), "08:05");
  assert.equal(normalizeHHMM("00:00"), "00:00");
  assert.equal(normalizeHHMM("23:59"), "23:59");
  for (const bad of ["", "24:00", "12:60", "12:5", "8", "abc", "08:00:00", "８:００", null, undefined, 800, {}]) {
    assert.equal(normalizeHHMM(bad), null, String(bad));
  }
});

test("secondsValue: numbers from 1 to 86400 only", () => {
  assert.equal(secondsValue("300"), 300);
  assert.equal(secondsValue(" 15 "), 15);
  assert.equal(secondsValue("1"), 1);
  assert.equal(secondsValue("86400"), 86400);
  assert.equal(secondsValue("7.5"), 7.5);
  for (const bad of ["", "  ", "0", "0.5", "86401", "-5", "abc", "1e9", "NaN", "Infinity", null, undefined]) {
    assert.equal(secondsValue(bad), null, String(bad));
  }
});
