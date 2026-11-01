export function formatRange(start, end) {
  if (!start && !end) return "";
  return `${start}～${end}`;
}

// 休日出勤予定の表: 空の欄は「―」で表す（保存する値は空のまま）
export const EMPTY_MARK = "―";

export function orDash(text) {
  return text ? text : EMPTY_MARK;
}

// 開始・終了のどちらも空なら「―」。片方だけ入っているときは formatRange のまま
export function formatRangeOrDash(start, end) {
  return formatRange(start, end) || EMPTY_MARK;
}

// 同じ日に、1つでも入力のある行があれば、その日の「―」だけの行（何も入力されていない行）は出さない。
// 入力のある行をすべて消したときは、「―」の行がまた出る（休日の日付がいつも分かるように）
export function visibleHolidayRows(rows) {
  const filled = (r) => Boolean(r.construction || r.person || r.work || r.start_time || r.end_time);
  const datesWithEntry = new Set(rows.filter(filled).map((r) => r.date));
  return rows.filter((r) => filled(r) || !datesWithEntry.has(r.date));
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

// 作業内容の選択肢。工事件名のファイルに作業内容が書いてあれば、その作業内容だけ（ファイルに書いた順）。無ければ登録済みの全部
export function worksFor(construction, masters) {
  const mapped = masters.construction_works && masters.construction_works[construction];
  if (!Array.isArray(mapped) || !mapped.length) return masters.works;
  return mapped.slice();
}
