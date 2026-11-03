import test from "node:test";
import assert from "node:assert/strict";
import { COLORS, WIDTHS, TEXT_SIZES, createHistory, normRect, arrowHead, thin } from "../../static/js/whiteboard-core.mjs";

const pen = { type: "pen", color: "#111827", width: 3, points: [[0, 0], [5, 5]] };
const rect = { type: "rect", color: "#DC2626", width: 8, x: 1, y: 1, w: 10, h: 10 };
const erase = { type: "erase", color: "#000", width: 8, points: [[0, 0]] };

test("constants: 8 colors, 4 widths, 4 text sizes", () => {
  assert.equal(COLORS.length, 8);
  assert.equal(new Set(COLORS).size, 8);
  assert.equal(WIDTHS.length, 4);
  assert.equal(TEXT_SIZES.length, 4);
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

import { monthGroups, scheduleLayout, SCHEDULE_ROWS, addDays } from "../../static/js/whiteboard-core.mjs";

test("monthGroups: consecutive days of the same month become one header", () => {
  const days = ["2026-10-30", "2026-10-31", "2026-11-01", "2026-11-02"].map(date => ({ date, kind: "" }));
  assert.deepEqual(monthGroups(days), [
    { label: "10月", from: 0, count: 2 },
    { label: "11月", from: 2, count: 2 },
  ]);
  assert.deepEqual(monthGroups([{ date: "2026-12-31" }, { date: "2027-01-01" }]).map(g => g.label), ["12月", "2027年1月"]);
});

test("scheduleLayout: leaves a large top margin and fits all days and rows", () => {
  const L = scheduleLayout(1600, 900, 24);
  assert.ok(L.top >= 900 * 0.2, "top margin for handwriting");
  assert.ok(L.left > 0 && L.left + L.width <= 1600 - L.left + 0.001);
  assert.equal(L.rows, SCHEDULE_ROWS);
  assert.ok(Math.abs(L.left + L.itemW + L.personW + 24 * L.dayW - (L.left + L.width)) < 0.001);
  assert.ok(Math.abs(L.top + 2 * L.headH + L.rows * L.rowH - (L.top + L.height)) < 0.001);
  assert.ok(L.top + L.height < 900);
});

test("addDays: local dates without time-zone drift", () => {
  assert.equal(addDays("2026-11-03", 23), "2026-11-26");
  assert.equal(addDays("2026-12-31", 1), "2027-01-01");
});

import { STAMPS } from "../../static/js/whiteboard-core.mjs";

test("stamps: six outline marks are offered and a stamp counts as ink", () => {
  assert.deepEqual(STAMPS, ["▽", "△", "◇", "〇", "☆", "✕"]);
  const h = createHistory();
  h.push({ type: "stamp", color: "#111827", size: 40, x: 10, y: 10, text: "▽" });
  assert.equal(h.hasInk(), true);
});

import { stampSize } from "../../static/js/whiteboard-core.mjs";

test("stampSize: 50% of a schedule cell at the thinnest width, 80% at the thickest", () => {
  const rowH = scheduleLayout(1920, 1016, 1).rowH;
  assert.ok(Math.abs(stampSize(1920, 1016, 0) - rowH * 0.5) < 1e-9);
  assert.ok(Math.abs(stampSize(1920, 1016, WIDTHS.length - 1) - rowH * 0.8) < 1e-9);
  assert.ok(stampSize(1920, 1016, 1) < stampSize(1920, 1016, 2));
});

test("stampSize: narrow day columns of a long schedule shrink the stamp to fit the column", () => {
  const L = scheduleLayout(1920, 1016, 30);
  assert.ok(L.dayW < L.rowH);
  assert.ok(Math.abs(stampSize(1920, 1016, 3, 30) - L.dayW * 0.8) < 1e-9);
  const S = scheduleLayout(1920, 1016, 24);
  assert.ok(Math.abs(stampSize(1920, 1016, 3, 24) - Math.min(S.dayW, S.rowH) * 0.8) < 1e-9);
});
