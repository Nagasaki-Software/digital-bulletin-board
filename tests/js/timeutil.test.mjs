import test from "node:test";
import assert from "node:assert/strict";
import { formatRange, contactText } from "../../static/js/timeutil.mjs";

test("formatRange", () => {
  assert.equal(formatRange("9:00", "15:00"), "9:00～15:00");
  assert.equal(formatRange("9:00", ""), "9:00～");
  assert.equal(formatRange("", "15:00"), "～15:00");
  assert.equal(formatRange("", ""), "");
});

test("contactText", () => {
  assert.equal(contactText("1234", ""), "内線 1234");
  assert.equal(contactText("", "03-0000-0001"), "外線 03-0000-0001");
  assert.equal(contactText("1234", "03-0000-0001"), "内線 1234 / 外線 03-0000-0001");
  assert.equal(contactText("", ""), "");
});

import { resolveEditMode } from "../../static/js/timeutil.mjs";

test("resolveEditMode: stored choice wins, otherwise the server default", () => {
  assert.equal(resolveEditMode("on", "off"), "on");
  assert.equal(resolveEditMode("off", "on"), "off");
  assert.equal(resolveEditMode(null, "on"), "on");
  assert.equal(resolveEditMode(null, "off"), "off");
  assert.equal(resolveEditMode(null, undefined), "off");
  assert.equal(resolveEditMode("junk", "on"), "on");
  assert.equal(resolveEditMode(null, "junk"), "off");
});
