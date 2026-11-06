import test from "node:test";
import assert from "node:assert/strict";
import { formatRange, contactText, visibleHolidayRows, formatClock } from "../../static/js/timeutil.mjs";

test("formatClock は 24 時間・ゼロ埋めの HH:MM", () => {
  assert.equal(formatClock(new Date(2026, 10, 1, 9, 5)), "09:05");
  assert.equal(formatClock(new Date(2026, 10, 1, 14, 35, 59)), "14:35");
  assert.equal(formatClock(new Date(2026, 10, 1, 0, 0)), "00:00");
  assert.equal(formatClock(new Date(2026, 10, 1, 23, 59)), "23:59");
});

test("formatRange", () => {
  assert.equal(formatRange("9:00", "15:00"), "9:00～15:00");
  assert.equal(formatRange("9:00", ""), "9:00～");
  assert.equal(formatRange("", "15:00"), "～15:00");
  assert.equal(formatRange("", ""), "");
  assert.equal(formatRange("22:00", "6:00"), "22:00～翌6:00");
  assert.equal(formatRange("23:30", "0:00"), "23:30～翌0:00");
  assert.equal(formatRange("8:00", "8:00"), "8:00～8:00");
  assert.equal(formatRange("0:00", "5:30"), "0:00～5:30");
  assert.equal(formatRange("22:00", ""), "22:00～");
});

test("contactText", () => {
  assert.equal(contactText("1234", ""), "内線 1234");
  assert.equal(contactText("", "03-0000-0001"), "外線 03-0000-0001");
  assert.equal(contactText("1234", "03-0000-0001"), "内線 1234\n外線 03-0000-0001"); // 両方あるときは2行（番号の途中で折り返さない）
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
  // 責任者だけの入力も「入力あり」と数える
  assert.deepEqual(visibleHolidayRows([empty(1, "2026-10-31"), filled(2, "2026-10-31", { person: "", leader: "佐藤" })]).map((r) => r.id), [2]);
  // 「＋ 行を追加」で足した空の行は、入力するまで出る（最初から並ぶ「―」の行＝その日の最初の行だけを隠す）
  assert.deepEqual(visibleHolidayRows([filled(1, "2026-10-31"), empty(3, "2026-10-31"), empty(2, "2026-11-01")]).map((r) => r.id), [1, 3, 2]);
  assert.deepEqual(visibleHolidayRows([empty(1, "2026-10-31"), filled(2, "2026-10-31"), empty(3, "2026-10-31")]).map((r) => r.id), [2, 3]);
  assert.deepEqual(visibleHolidayRows([filled(1, "2026-10-31"), empty(3, "2026-10-31"), empty(4, "2026-10-31")]).map((r) => r.id), [1, 3, 4]);
  // 行の並びが日付順・id順でなくても、「最初の行」は id の小さいほうで決める
  assert.deepEqual(visibleHolidayRows([empty(3, "2026-10-31"), filled(1, "2026-10-31")]).map((r) => r.id), [3, 1]);
});

import { worksFor } from "../../static/js/timeutil.mjs";

test("worksFor: 工事件名のファイルに書いた作業内容だけを、ファイルの順で返す。無ければ全部", () => {
  const masters = {
    works: ["組み立て作業", "配線工事", "清掃", "搬入作業"],
    construction_works: { 配管工事: ["搬入作業", "組み立て作業"], 電気工事: ["配線工事"] },
  };
  assert.deepEqual(worksFor("配管工事", masters), ["搬入作業", "組み立て作業"]);
  assert.deepEqual(worksFor("電気工事", masters), ["配線工事"]);
  // 対応の行がない工事件名・空・未定義は、登録されている作業内容をすべて返す
  const all = ["組み立て作業", "配線工事", "清掃", "搬入作業"];
  assert.deepEqual(worksFor("塗装工事", masters), all);
  assert.deepEqual(worksFor("", masters), all);
  assert.deepEqual(worksFor(undefined, masters), all);
  assert.deepEqual(worksFor(null, masters), all);
  // 対応表が無い（古い応答・ファイルなし）ときも全部。Object の標準の名前に引っかからない
  assert.deepEqual(worksFor("配管工事", { works: all }), all);
  assert.deepEqual(worksFor("配管工事", { works: all, construction_works: {} }), all);
  assert.deepEqual(worksFor("constructor", masters), all);
  assert.deepEqual(worksFor("__proto__", masters), all);
  assert.deepEqual(worksFor("toString", masters), all);
});
