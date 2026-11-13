import test from "node:test";
import assert from "node:assert/strict";
import { rememberPos, recallPos, MAX_REMEMBERED } from "../../static/js/docmemory.mjs";

test("覚えたページ・拡大率・位置を、同じPDF（同じ指紋）なら返す", () => {
  let store = {};
  store = rememberPos(store, "0/手順書.pdf", { fp: "abc", page: 5, zoom: 1.5, sx: 120, sy: 300 });
  assert.deepEqual(recallPos(store, "0/手順書.pdf", "abc", 12), { page: 5, zoom: 1.5, sx: 120, sy: 300 });
});

test("PDFが差し替えられた（指紋が違う）・覚えていないときは null", () => {
  const store = rememberPos({}, "0/手順書.pdf", { fp: "abc", page: 5, zoom: 1.5, sx: 0, sy: 0 });
  assert.equal(recallPos(store, "0/手順書.pdf", "xyz", 12), null);
  assert.equal(recallPos(store, "1/手順書.pdf", "abc", 12), null);
  assert.equal(recallPos(null, "0/手順書.pdf", "abc", 12), null);
});

test("ページ数が減っていたら最後のページ、拡大率は 0.5〜5 に収める。壊れた値は1ページ目・等倍", () => {
  let store = rememberPos({}, "k", { fp: "a", page: 20, zoom: 9, sx: -5, sy: 10 });
  assert.deepEqual(recallPos(store, "k", "a", 12), { page: 12, zoom: 5, sx: 0, sy: 10 });
  store = { k: { fp: "a", page: "x", zoom: null, sx: "y", sy: undefined } };
  assert.deepEqual(recallPos(store, "k", "a", 12), { page: 1, zoom: 1, sx: 0, sy: 0 });
});

test("覚える数には上限があり、古いものから忘れる", () => {
  let store = {};
  for (let i = 0; i < MAX_REMEMBERED + 5; i++) store = rememberPos(store, "f" + i, { fp: "a", page: 1, zoom: 1, sx: 0, sy: 0 });
  assert.equal(Object.keys(store).length, MAX_REMEMBERED);
  assert.equal(recallPos(store, "f0", "a", 1), null);
  assert.notEqual(recallPos(store, "f" + (MAX_REMEMBERED + 4), "a", 1), null);
  // 覚え直したものは新しい扱いになり、忘れられない
  store = rememberPos(store, "f5", { fp: "a", page: 2, zoom: 1, sx: 0, sy: 0 });
  store = rememberPos(store, "new", { fp: "a", page: 1, zoom: 1, sx: 0, sy: 0 });
  assert.notEqual(recallPos(store, "f5", "a", 3), null);
});
