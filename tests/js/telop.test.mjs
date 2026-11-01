import test from "node:test";
import assert from "node:assert/strict";
import { splitBadges, buildSegments, telopKey, marqueeParams, SEPARATOR, EMPTY_TEXT } from "../../static/js/telop-text.mjs";

test("splitBadges: plain text has one plain segment", () => {
  assert.deepEqual(splitBadges("今日は晴れ"), [{ text: "今日は晴れ", badge: false }]);
});

test('splitBadges: "..." parts become badges, quotes removed', () => {
  assert.deepEqual(splitBadges('"安全"第一で"作業"'), [
    { text: "安全", badge: true },
    { text: "第一で", badge: false },
    { text: "作業", badge: true },
  ]);
  assert.deepEqual(splitBadges('前 "A" 後'), [
    { text: "前 ", badge: false },
    { text: "A", badge: true },
    { text: " 後", badge: false },
  ]);
});

test("splitBadges: unmatched or empty quotes, curly quotes stay as plain text", () => {
  assert.deepEqual(splitBadges('abc"def'), [{ text: 'abc"def', badge: false }]);
  assert.deepEqual(splitBadges('a""b'), [{ text: "a", badge: false }, { text: "b", badge: false }]);
  assert.deepEqual(splitBadges(""), []);
});

test("splitBadges: curly and full-width quotes also make badges, in any open/close combination", () => {
  for (const [open, close] of [["“", "”"], ["”", "”"], ["“", "“"], ["＂", "＂"], ['"', "”"], ["＂", '"']]) {
    assert.deepEqual(splitBadges(`前${open}重要${close}後`), [
      { text: "前", badge: false },
      { text: "重要", badge: true },
      { text: "後", badge: false },
    ]);
  }
});

test("splitBadges: odd or unterminated quotes of any kind stay plain text", () => {
  assert.deepEqual(splitBadges("“未完了"), [{ text: "“未完了", badge: false }]);
  assert.deepEqual(splitBadges("終わり”"), [{ text: "終わり”", badge: false }]);
  assert.deepEqual(splitBadges('“a”b"c'), [
    { text: "a", badge: true },
    { text: 'b"c', badge: false },
  ]);
  assert.deepEqual(splitBadges("‘単一’"), [{ text: "‘単一’", badge: false }]); // 一重引用符は対象外
});

test("splitBadges: HTML-looking text is kept verbatim (never interpreted here)", () => {
  assert.deepEqual(splitBadges('<img src=x onerror=alert(1)>"<b>"'), [
    { text: "<img src=x onerror=alert(1)>", badge: false },
    { text: "<b>", badge: true },
  ]);
});

test("splitBadges: non-string input does not throw", () => {
  for (const v of [null, undefined, 5, {}, []]) assert.deepEqual(splitBadges(v), []);
});

test("buildSegments: items are joined with wide spaces", () => {
  assert.equal(SEPARATOR, "　　　　");
  assert.deepEqual(buildSegments(["A", '"B"C']), [
    { text: "A", badge: false },
    { text: SEPARATOR, badge: false },
    { text: "B", badge: true },
    { text: "C", badge: false },
  ]);
});

test("buildSegments: empty list shows the no-news message", () => {
  assert.equal(EMPTY_TEXT, "お知らせはありません");
  assert.deepEqual(buildSegments([]), [{ text: EMPTY_TEXT, badge: false }]);
  assert.deepEqual(buildSegments(undefined), [{ text: EMPTY_TEXT, badge: false }]);
});

test("telopKey changes only when items, speed or width change", () => {
  const k = telopKey(["a", "b"], 100, 1920);
  assert.equal(telopKey(["a", "b"], 100, 1920), k);
  assert.notEqual(telopKey(["a", "c"], 100, 1920), k);
  assert.notEqual(telopKey(["a", "b"], 120, 1920), k);
  assert.notEqual(telopKey(["a", "b"], 100, 1919), k);
  assert.notEqual(telopKey(["a b"], 100, 1920), telopKey(["a", "b"], 100, 1920));
});

test("marqueeParams: right-to-left over container + track at speed px/s", () => {
  assert.deepEqual(marqueeParams(1000, 3000, 100), { from: 1000, to: -3000, durationMs: 40000 });
});

test("marqueeParams: speed is clamped to 20..500 and bad values use 100", () => {
  assert.equal(marqueeParams(1000, 1000, 1).durationMs, 100000);
  assert.equal(marqueeParams(1000, 1000, 5000).durationMs, 4000);
  assert.equal(marqueeParams(1000, 1000, "abc").durationMs, 20000);
  assert.equal(marqueeParams(1000, 1000, undefined).durationMs, 20000);
});
