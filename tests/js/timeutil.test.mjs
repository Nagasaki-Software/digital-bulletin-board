import test from "node:test";
import assert from "node:assert/strict";
import { formatRange, contactText, visibleHolidayRows } from "../../static/js/timeutil.mjs";

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

import { orDash, formatRangeOrDash, EMPTY_MARK } from "../../static/js/timeutil.mjs";

test("orDash: an empty value is shown as the U+2015 bar, a real value is unchanged", () => {
  assert.equal(EMPTY_MARK, "―");
  assert.equal(orDash(""), "―");
  assert.equal(orDash(undefined), "―");
  assert.equal(orDash(null), "―");
  assert.equal(orDash("電気工事"), "電気工事");
});

test("formatRangeOrDash: empty range is the bar, a half-filled range keeps formatRange", () => {
  assert.equal(formatRangeOrDash("", ""), "―");
  assert.equal(formatRangeOrDash("9:00", ""), "9:00～");
  assert.equal(formatRangeOrDash("", "15:00"), "～15:00");
  assert.equal(formatRangeOrDash("9:00", "15:00"), "9:00～15:00");
});

test("visibleHolidayRows: 入力のある行があれば、同じ日の「―」だけの行は出さない", () => {
  const empty = (id, date) => ({ id, date, construction: "", person: "", work: "", start_time: "", end_time: "" });
  const filled = (id, date, extra = {}) => ({ ...empty(id, date), person: "1班", ...extra });
  // 入力がなければ、休日ごとに「―」の行が出る
  assert.deepEqual(visibleHolidayRows([empty(1, "2026-10-31"), empty(2, "2026-11-01")]).map((r) => r.id), [1, 2]);
  // 10/31 に入力のある行があれば、10/31 の「―」の行だけが消える（11/1 は残る）
  assert.deepEqual(visibleHolidayRows([empty(1, "2026-10-31"), empty(2, "2026-11-01"), filled(3, "2026-10-31")]).map((r) => r.id), [2, 3]);
  // 入力済みの行は、何があっても出る。時刻だけ・工事件名だけの入力も「入力あり」と数える
  assert.deepEqual(visibleHolidayRows([empty(1, "2026-10-31"), filled(2, "2026-10-31", { person: "", start_time: "8:00" })]).map((r) => r.id), [2]);
  assert.deepEqual(visibleHolidayRows([empty(1, "2026-10-31"), filled(2, "2026-10-31", { person: "", construction: "電気工事" })]).map((r) => r.id), [2]);
  // 入力のある行を消すと（配列から無くなると）、「―」の行がまた出る
  assert.deepEqual(visibleHolidayRows([empty(1, "2026-10-31")]).map((r) => r.id), [1]);
  // 同じ日に「―」の行が2つあって、入力がない場合は、どちらも出る（勝手に消さない）
  assert.deepEqual(visibleHolidayRows([empty(1, "2026-10-31"), empty(2, "2026-10-31")]).map((r) => r.id), [1, 2]);
  assert.deepEqual(visibleHolidayRows([]), []);
});
