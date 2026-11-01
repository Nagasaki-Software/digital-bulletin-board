import test from "node:test";
import assert from "node:assert/strict";
import { isSafeUrl, buildLinkList, clampStay, MAX_LINKS, DEFAULT_STAY } from "../../static/js/links.js";

const OK = [
  "http://localhost:5000/",
  "https://example.com",
  "HTTP://EXAMPLE.com/a?b=1#c",
  "http://192.168.0.5:5000/x",
  "http://[::1]:5000/",
  "http://サーバーPC:5000/",
  "http://a.b/" + "x".repeat(489),
];
const NG = [
  "javascript:alert(1)", "JaVaScRiPt:alert(1)", "file:///c:/x", "ftp://a/b", "data:text/html,x", "vbscript:x", "blob:http://a/b",
  "//host/x", "/relative", "relative", "host:5000/", "example.com", "http://", "https://", "http:///x", "http://:80/",
  "http:example.com", "http:\\\\host", "http://a b/", "http://a\tb/", "http://a\nb/", "http://a\x00b/", "http://a\x7fb/",
  "http://a\u3000b/", " http://x/", "http://x/ ", "http://x:99999/", "http://[::1/",
  "http://a.b/" + "x".repeat(490), "", null, undefined, 5, true, {}, ["http://x/"],
];

test("isSafeUrl accepts http/https only", () => {
  for (const u of OK) assert.equal(isSafeUrl(u), true, String(u));
});

test("isSafeUrl rejects everything else", () => {
  for (const u of NG) assert.equal(isSafeUrl(u), false, String(u));
});

test("isSafeUrl length limit is 500", () => {
  const base = "http://a.b/";
  assert.equal(isSafeUrl(base + "x".repeat(500 - base.length)), true);
  assert.equal(isSafeUrl(base + "x".repeat(501 - base.length)), false);
});

test("buildLinkList keeps valid items (max 2), trims labels, skips bad ones", () => {
  const items = [
    { label: "  点検 ", url: "http://localhost:5000/" },
    { label: "悪い", url: "javascript:alert(1)" },
    { label: "", url: "http://a/" },
    null,
    "http://a/",
    { label: "Web2", url: "https://example.com/" },
    { label: "3つ目", url: "http://c/" },
  ];
  assert.deepEqual(buildLinkList(items), [
    { label: "点検", url: "http://localhost:5000/" },
    { label: "Web2", url: "https://example.com/" },
  ]);
  assert.equal(MAX_LINKS, 2);
});

test("buildLinkList returns [] for anything that is not a list", () => {
  for (const v of [undefined, null, {}, "x", 5, true]) assert.deepEqual(buildLinkList(v), []);
  assert.deepEqual(buildLinkList([]), []);
});

test("buildLinkList drops labels over 100 chars and non-string labels", () => {
  assert.equal(buildLinkList([{ label: "あ".repeat(100), url: "http://a/" }]).length, 1);
  assert.equal(buildLinkList([{ label: "あ".repeat(101), url: "http://a/" }]).length, 0);
  assert.equal(buildLinkList([{ label: 5, url: "http://a/" }]).length, 0);
});

test("clampStay clamps to 60..3600 and falls back to 300", () => {
  assert.equal(DEFAULT_STAY, 300);
  assert.equal(clampStay(300), 300);
  assert.equal(clampStay(60), 60);
  assert.equal(clampStay(3600), 3600);
  assert.equal(clampStay(10), 60);
  assert.equal(clampStay(0), 60);
  assert.equal(clampStay(-5), 60);
  assert.equal(clampStay(99999), 3600);
  assert.equal(clampStay(120.4), 120);
  for (const v of [NaN, Infinity, undefined, null, "300", "abc", {}, true]) assert.equal(clampStay(v), 300, String(v));
});

// ---- 修正: URL の ユーザー名:パスワード@（Python 側 tests/test_links.py と同じ表） ----
import { readFileSync } from "node:fs";
import { hasControlChar, createStayTimer, isLinkOpen, WARN_SECONDS } from "../../static/js/links.js";

const URL_CASES = JSON.parse(readFileSync(new URL("../link_url_cases.json", import.meta.url), "utf8"));

test("isSafeUrl rejects user:password@ in the address (shared table)", () => {
  for (const u of URL_CASES.ng) assert.equal(isSafeUrl(u), false, u);
});

test("isSafeUrl still accepts @ outside the host part (shared table)", () => {
  for (const u of URL_CASES.ok) assert.equal(isSafeUrl(u), true, u);
});

test("hasControlChar finds newlines, tabs and other control/format characters", () => {
  for (const s of ["a\nb", "a\tb", "a\x00b", "a\x1bb", "a​b", "a\x7fb", "a\r\nb"]) assert.equal(hasControlChar(s), true, JSON.stringify(s));
  for (const s of ["", "点検（A）・B", "plain text", "a b", "全角　スペース"]) assert.equal(hasControlChar(s), false, JSON.stringify(s));
});

test("buildLinkList drops items whose label has control characters", () => {
  const got = buildLinkList([
    { label: "a\nb", url: "http://a/" },
    { label: "a\tb", url: "http://a/" },
    { label: "良い", url: "http://b/" },
  ]);
  assert.deepEqual(got, [{ label: "良い", url: "http://b/" }]);
});

// ---- 修正: 最大滞在の前の警告（単一のタイマー） ----

// setTimeout / clearTimeout の代わり。いま待っているタイマーを数えられる
function fakeTimers() {
  const pending = new Map();
  let id = 0;
  return {
    set(fn, ms) {
      pending.set(++id, { fn, ms });
      return id;
    },
    clear(handle) {
      pending.delete(handle);
    },
    pending,
    fireOnly() {
      assert.equal(pending.size, 1, "待っているタイマーは常に1つ以下");
      const [[handle, t]] = [...pending];
      pending.delete(handle);
      t.fn();
      return t.ms;
    },
  };
}

function makeTimer(stay = 300) {
  const ft = fakeTimers();
  const events = [];
  const timer = createStayTimer({ onWarn: () => events.push("warn"), onExpire: () => events.push("expire"), set: ft.set, clear: ft.clear });
  return { ft, events, timer, stay };
}

test("warning comes 30 seconds before the end, then the board returns", () => {
  assert.equal(WARN_SECONDS, 30);
  const { ft, events, timer } = makeTimer();
  timer.start(300);
  assert.equal(ft.pending.size, 1);
  assert.equal(ft.fireOnly(), 270 * 1000);
  assert.deepEqual(events, ["warn"]);
  assert.equal(ft.fireOnly(), 30 * 1000);
  assert.deepEqual(events, ["warn", "expire"]);
  assert.equal(ft.pending.size, 0);
});

test("continue restarts the whole stay (max stay stays a hard cap per click)", () => {
  const { ft, events, timer } = makeTimer();
  timer.start(120);
  assert.equal(ft.fireOnly(), 90 * 1000);
  timer.restart();
  assert.equal(ft.pending.size, 1);
  assert.equal(ft.fireOnly(), 90 * 1000); // また「滞在 − 30秒」から
  assert.equal(ft.fireOnly(), 30 * 1000);
  assert.deepEqual(events, ["warn", "warn", "expire"]);
});

test("restart before the warning also restarts from zero, and never leaves two timers", () => {
  const { ft, timer } = makeTimer();
  timer.start(300);
  for (let i = 0; i < 5; i++) {
    timer.restart();
    assert.equal(ft.pending.size, 1);
  }
  timer.start(60);
  assert.equal(ft.pending.size, 1);
  assert.equal(ft.fireOnly(), 30 * 1000);
});

test("stop clears the timer and nothing fires afterwards", () => {
  const { ft, events, timer } = makeTimer();
  timer.start(300);
  timer.stop();
  assert.equal(ft.pending.size, 0);
  timer.stop();
  timer.restart(); // 開いていないときの「続ける」は何もしない
  assert.equal(ft.pending.size, 0);
  assert.deepEqual(events, []);
});

test("stop after the warning clears the final timer too", () => {
  const { ft, events, timer } = makeTimer();
  timer.start(100);
  ft.fireOnly();
  assert.equal(ft.pending.size, 1);
  timer.stop();
  assert.equal(ft.pending.size, 0);
  assert.deepEqual(events, ["warn"]);
});

test("a stay not longer than the warning time warns at once", () => {
  const { ft, events, timer } = makeTimer();
  timer.start(20);
  assert.equal(ft.fireOnly(), 0);
  assert.deepEqual(events, ["warn"]);
  assert.equal(ft.fireOnly(), 20 * 1000);
});

test("isLinkOpen is false until a link is opened", () => {
  assert.equal(isLinkOpen(), false);
});
