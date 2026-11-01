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
