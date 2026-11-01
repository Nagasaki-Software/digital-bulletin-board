// お知らせ（画面下の流れる文字）の、画面に依存しない部分。node でテストできる
export const SEPARATOR = "　　　　"; // 項目と項目のあいだの広いすき間
export const EMPTY_TEXT = "お知らせはありません";
export const MIN_SPEED = 20;
export const MAX_SPEED = 500;
export const DEFAULT_SPEED = 100;

// 囲みに使える引用符: 半角 " と、全角・カーブの “ ” ＂（開きと閉じは、このどれの組み合わせでもよい）
// 対になっていない引用符は、ふつうの文字のまま残す。空の囲みは捨てる
export function splitBadges(text) {
  if (typeof text !== "string") return [];
  const parts = [];
  for (const part of text.split(/(["“”＂][^"“”＂]*["“”＂])/g)) {
    const m = /^["“”＂]([^"“”＂]*)["“”＂]$/.exec(part);
    const t = m ? m[1] : part;
    if (t) parts.push({ text: t, badge: !!m });
  }
  return parts;
}

// 全項目を1本につなぐ。項目が無いときは「お知らせはありません」
export function buildSegments(items) {
  if (!Array.isArray(items) || items.length === 0) return [{ text: EMPTY_TEXT, badge: false }];
  const segs = [];
  items.forEach((item, i) => {
    if (i > 0) segs.push({ text: SEPARATOR, badge: false });
    segs.push(...splitBadges(item));
  });
  return segs;
}

// 内容・速度・幅のどれかが変わったときだけ変わる文字列（作り直すかどうかの判定に使う）
export function telopKey(items, speed, width) {
  return JSON.stringify([items, speed, width]);
}

function clampSpeed(speed) {
  const n = Number(speed);
  return Number.isFinite(n) ? Math.min(MAX_SPEED, Math.max(MIN_SPEED, n)) : DEFAULT_SPEED;
}

// 右端から入って左端へ抜けるまでの動き。速度は px/秒
export function marqueeParams(containerWidth, trackWidth, speed) {
  return {
    from: containerWidth,
    to: -trackWidth,
    durationMs: ((containerWidth + trackWidth) / clampSpeed(speed)) * 1000,
  };
}
