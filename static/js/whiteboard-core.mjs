// ホワイトボードの、画面に依存しない部分（node でも試せる）。描いたものは「記録（op）」の並びとして持ち、画面は記録を順に描き直す。
export const COLORS = ["#111827", "#DC2626", "#EA580C", "#CA8A04", "#16A34A", "#2563EB", "#9333EA", "#6B7280"];
export const WIDTHS = [3, 8, 16, 22]; // 細い・ふつう・太い・帯（線の太さ。文字の大きさは TEXT_SIZES の同じ番号）。帯は工程表の期間を引く用
export const TEXT_SIZES = [24, 40, 64, 96];
export const ERASER_SCALE = 4; // 消しゴムは線の太さのこの倍
export const DRAW_TYPES = new Set(["pen", "line", "arrow", "rect", "ellipse", "text", "stamp"]);
export const STAMPS = ["▽", "△", "◇", "〇", "☆", "✕"]; // 「スタンプ」で押せる印

// 記録の並び。clear は「ここまでを消した」印。undo/redo は印も1回分として数える
export function createHistory() {
  const ops = [];
  let redoStack = [];
  const visible = () => {
    let from = 0;
    for (let i = ops.length - 1; i >= 0; i--) {
      if (ops[i].type === "clear") {
        from = i + 1;
        break;
      }
    }
    return ops.slice(from);
  };
  return {
    push(op) {
      ops.push(op);
      redoStack = [];
    },
    undo() {
      const op = ops.pop();
      if (op) redoStack.push(op);
      return !!op;
    },
    redo() {
      const op = redoStack.pop();
      if (op) ops.push(op);
      return !!op;
    },
    clear() {
      if (visible().length === 0) return false;
      ops.push({ type: "clear" });
      redoStack = [];
      return true;
    },
    visible,
    hasInk: () => visible().some(op => DRAW_TYPES.has(op.type)),
    canUndo: () => ops.length > 0,
    canRedo: () => redoStack.length > 0,
  };
}

export function normRect(x1, y1, x2, y2) {
  return { x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.abs(x2 - x1), h: Math.abs(y2 - y1) };
}

// 矢印の先の2本の線の端（先端 x2,y2 から、線の向きの後ろへ開く）
export function arrowHead(x1, y1, x2, y2, width) {
  const angle = Math.atan2(y2 - y1, x2 - x1);
  const len = Math.max(14, width * 4);
  const spread = Math.PI / 7;
  return [
    [x2 - len * Math.cos(angle - spread), y2 - len * Math.sin(angle - spread)],
    [x2 - len * Math.cos(angle + spread), y2 - len * Math.sin(angle + spread)],
  ];
}

// 手書きの点を間引く。最初と最後は必ず残す
export function thin(points, minDist = 2) {
  if (points.length <= 1) return points.slice();
  const out = [points[0]];
  for (let i = 1; i < points.length - 1; i++) {
    const [px, py] = out[out.length - 1];
    if (Math.hypot(points[i][0] - px, points[i][1] - py) >= minDist) out.push(points[i]);
  }
  const last = points[points.length - 1];
  const [lx, ly] = out[out.length - 1];
  if (last[0] !== lx || last[1] !== ly) out.push(last);
  return out;
}

const WEEKDAYS = "日月火水木金土";

// 「日付」ボタンで置く文字。例: 2026年11月3日（火）14:05
export function formatStamp(d) {
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日（${WEEKDAYS[d.getDay()]}）${hh}:${mm}`;
}

// ---- 工程表（背景） ----
export const SCHEDULE_ROWS = 12;

// "2026-11-03" に n 日足した日付（同じ形）。時差でずれないよう UTC で数える
export function addDays(iso, n) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + n)).toISOString().slice(0, 10);
}

// 見出しの上の段（月）。同じ月の続く日をまとめる。最初の月と年が違えば年も書く
export function monthGroups(days) {
  const out = [];
  const firstYear = days.length ? days[0].date.slice(0, 4) : "";
  days.forEach((d, i) => {
    const [y, m] = d.date.split("-");
    const label = (y === firstYear ? "" : `${y}年`) + `${Number(m)}月`;
    const last = out[out.length - 1];
    if (last && last.label === label) last.count++;
    else out.push({ label, from: i, count: 1 });
  });
  return out;
}

// 画面の大きさ（w×h）と日数から、表の位置と大きさ。上は書き込み用に高さの約2割を空ける
export function scheduleLayout(w, h, nDays) {
  const left = w * 0.03;
  const top = h * 0.22;
  const width = w - left * 2;
  const height = h - top - h * 0.04;
  const itemW = width * 0.2;
  const personW = width * 0.09;
  const dayW = (width - itemW - personW) / nDays;
  const rowH = height / (SCHEDULE_ROWS + 1.5); // 見出し2段で、ふつうの行の1.5行分
  return { left, top, width, height, itemW, personW, dayW, headH: rowH * 0.75, rowH, rows: SCHEDULE_ROWS };
}

// スタンプの印の大きさ（縦横の長いほう）。工程表のマス（1行の高さと1日の幅の小さいほう）に対して、細い 5割 〜 帯 8割
// nDays は工程表の日数（工程表が無いときは 0 で、行の高さだけで決める）
const STAMP_RATIOS = [0.5, 0.6, 0.7, 0.8];
export function stampSize(w, h, widthIdx, nDays = 0) {
  const L = scheduleLayout(w, h, nDays || 1);
  return (nDays ? Math.min(L.rowH, L.dayW) : L.rowH) * STAMP_RATIOS[widthIdx];
}
