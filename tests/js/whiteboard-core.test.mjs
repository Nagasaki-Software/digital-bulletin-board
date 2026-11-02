import test from "node:test";
import assert from "node:assert/strict";
import { COLORS, WIDTHS, TEXT_SIZES, createHistory, normRect, arrowHead, thin } from "../../static/js/whiteboard-core.mjs";

const pen = { type: "pen", color: "#111827", width: 3, points: [[0, 0], [5, 5]] };
const rect = { type: "rect", color: "#DC2626", width: 8, x: 1, y: 1, w: 10, h: 10 };
const erase = { type: "erase", color: "#000", width: 8, points: [[0, 0]] };

test("constants: 8 colors, 3 widths, 3 text sizes", () => {
  assert.equal(COLORS.length, 8);
  assert.equal(new Set(COLORS).size, 8);
  assert.equal(WIDTHS.length, 3);
  assert.equal(TEXT_SIZES.length, 3);
});

test("undo and redo walk the history; a new op drops the redo stack", () => {
  const h = createHistory();
  assert.equal(h.undo(), false);
  assert.equal(h.redo(), false);
  h.push(pen);
  h.push(rect);
  assert.deepEqual(h.visible(), [pen, rect]);
  assert.equal(h.undo(), true);
  assert.deepEqual(h.visible(), [pen]);
  assert.equal(h.canRedo(), true);
  assert.equal(h.redo(), true);
  assert.deepEqual(h.visible(), [pen, rect]);
  h.undo();
  h.push(erase);
  assert.equal(h.canRedo(), false);
  assert.deepEqual(h.visible(), [pen, erase]);
});

test("clear hides everything before it and can be undone", () => {
  const h = createHistory();
  assert.equal(h.clear(), false); // 何も無いときは記録しない
  h.push(pen);
  h.push(rect);
  assert.equal(h.clear(), true);
  assert.deepEqual(h.visible(), []);
  assert.equal(h.hasInk(), false);
  h.push(rect);
  assert.deepEqual(h.visible(), [rect]);
  h.undo();
  h.undo(); // clear を取り消す
  assert.deepEqual(h.visible(), [pen, rect]);
  assert.equal(h.hasInk(), true);
});

test("hasInk ignores eraser-only history", () => {
  const h = createHistory();
  assert.equal(h.hasInk(), false);
  h.push(erase);
  assert.equal(h.hasInk(), false);
  h.push({ type: "text", color: "#000", size: 24, x: 0, y: 0, text: "あ" });
  assert.equal(h.hasInk(), true);
});

test("normRect orders corners", () => {
  assert.deepEqual(normRect(10, 20, 4, 8), { x: 4, y: 8, w: 6, h: 12 });
  assert.deepEqual(normRect(1, 2, 3, 4), { x: 1, y: 2, w: 2, h: 2 });
});

test("arrowHead: both barbs are the same distance from the tip and point back along the line", () => {
  const [a, b] = arrowHead(0, 0, 100, 0, 8);
  const da = Math.hypot(a[0] - 100, a[1]);
  const db = Math.hypot(b[0] - 100, b[1]);
  assert.ok(Math.abs(da - db) < 1e-9);
  assert.ok(da >= 14);
  assert.ok(a[0] < 100 && b[0] < 100);
  assert.ok(a[1] * b[1] < 0); // 線をはさんで反対側
});

test("thin keeps first and last points and drops near neighbours", () => {
  const pts = [[0, 0], [0.5, 0.5], [1, 1], [10, 10], [10.2, 10.1]];
  assert.deepEqual(thin(pts, 2), [[0, 0], [10, 10], [10.2, 10.1]]);
  assert.deepEqual(thin([[3, 3]], 2), [[3, 3]]);
  assert.deepEqual(thin([[3, 3], [3, 3]], 2), [[3, 3]]);
  assert.deepEqual(thin([], 2), []);
});

import { formatStamp } from "../../static/js/whiteboard-core.mjs";

test("formatStamp: date, weekday and zero-padded time", () => {
  assert.equal(formatStamp(new Date(2026, 10, 3, 14, 5)), "2026年11月3日（火）14:05");
  assert.equal(formatStamp(new Date(2026, 0, 4, 0, 0)), "2026年1月4日（日）00:00");
});
