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

// start〜end が日付をまたぐとき（18:00〜07:30）も正しく判定する
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
