export function formatRange(start, end) {
  if (!start && !end) return "";
  return `${start}～${end}`;
}

export function contactText(ext, outside) {
  const parts = [];
  if (ext) parts.push("内線 " + ext);
  if (outside) parts.push("外線 " + outside);
  return parts.join(" / ");
}

// "7:30" / "07:30" を分に直す。形式が違う・文字列でないときは NaN
export function toMinutes(hhmm) {
  const m = typeof hhmm === "string" ? hhmm.match(/^(\d{1,2}):(\d{2})$/) : null;
  if (!m) return NaN;
  const h = Number(m[1]);
  const min = Number(m[2]);
  return h > 23 || min > 59 ? NaN : h * 60 + min;
}

// 設定欄の入力を "HH:MM"（24時間）にそろえる。"8:00" も可。形式が違えば null
export function normalizeHHMM(text) {
  const m = typeof text === "string" ? text.trim().match(/^([0-9]{1,2}):([0-9]{2})$/) : null;
  if (!m) return null;
  const h = Number(m[1]);
  const min = Number(m[2]);
  return h > 23 || min > 59 ? null : String(h).padStart(2, "0") + ":" + m[2];
}

// 設定欄の秒数（1〜86400 の数）。範囲外・数でないときは null
export function secondsValue(text) {
  const raw = typeof text === "string" ? text.trim() : "";
  const n = Number(raw);
  return raw !== "" && Number.isFinite(n) && n >= 1 && n <= 86400 ? n : null;
}

// start〜end が日付をまたぐとき（18:00〜08:00）も正しく判定する
export function isStandbyTime(nowMinutes, start, end) {
  const s = toMinutes(start);
  const e = toMinutes(end);
  if (Number.isNaN(s) || Number.isNaN(e) || s === e) return false;
  return s < e ? nowMinutes >= s && nowMinutes < e : nowMinutes >= s || nowMinutes < e;
}

// 編集ボタンの「あり/なし」。そのパソコンで選んだ値があればそれを使い、無ければ config.json の既定に従う
export function resolveEditMode(stored, serverDefault) {
  if (stored === "on" || stored === "off") return stored;
  return serverDefault === "on" ? "on" : "off";
}
