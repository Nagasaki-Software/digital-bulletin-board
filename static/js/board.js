import { api } from "./api.js";
import { pickOption, inputText, confirmBox, alertBox } from "./picker.js";
import { formatRange, formatRangeOrDash, orDash, contactText, visibleHolidayRows, worksFor } from "./timeutil.mjs";
import { setPlaylist, setSeconds, pause as pauseAccident, resume as resumeAccident } from "./accident.js";
import { renderDocButtons, closeDocuments } from "./documents.js";
import { renderLinkButtons, closeLink, initLinks } from "./links.js";
import { isEditable, initLock, setLockSeconds, setDefaultEditButton } from "./lock.js";
import { initStandby, setStandbyConfig } from "./standby.js";
import { initTheme, setDefaultTheme } from "./theme.js";
import { initClock } from "./clock.js";
import { initTelop, updateTelop } from "./telop.js";
import { initAdminSettings } from "./admin-settings.js";

const MIN_SCHEDULE_ROWS = 7;
const MIN_HOLIDAY_ROWS = 2;
const POLL_MS = 3000;
const TOAST_MS = 6000;
const ALERT_ICON =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>';

const $ = id => document.getElementById(id);
let state = null;
let lastRev = null;
let lastToday = null;

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

function td(text, { cls = "", onClick = null } = {}) {
  const e = el("td", cls, text);
  if (onClick) {
    e.addEventListener("click", () => {
      if (isEditable()) onClick();
    });
  }
  return e;
}

// 休日出勤予定の表だけ、空の欄を「―」で出す（薄い色。押すと選ぶ画面が開くのは入力済みの欄と同じ）
function holidayTd(value, cls, onClick) {
  return td(orDash(value), { cls: (cls + (value ? "" : " dash")).trim(), onClick });
}

function actBtn(label, onClick, disabled = false, extraCls = "") {
  const b = el("button", "act-btn" + (extraCls ? " " + extraCls : ""), label);
  b.type = "button";
  b.disabled = disabled;
  b.addEventListener("click", onClick);
  return b;
}

function fillerRow() {
  const tr = el("tr");
  for (let i = 0; i < 6; i++) tr.appendChild(td("", { cls: i === 5 ? "edit-only" : "" }));
  return tr;
}

function keepScroll(id, fn) {
  const box = $(id);
  const top = box.scrollTop;
  fn();
  box.scrollTop = top;
}

function dateClass(kind) {
  return kind === "saturday" ? "sat" : kind === "holiday" ? "red" : "";
}

function setWarnings(list) {
  const box = $("warnings");
  box.hidden = list.length === 0;
  box.textContent = list.join(" / ");
}

// 保存の失敗などを、操作を止めずに画面の下へ数秒だけ出す
let toastTimer = null;
function showToast(message, ok = false) {
  let box = $("toast");
  if (!box) {
    box = el("div");
    box.id = "toast";
    box.setAttribute("role", "alert");
    document.body.appendChild(box);
  }
  box.classList.toggle("ok", ok);
  box.textContent = message;
  box.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    box.hidden = true;
  }, TOAST_MS);
}

// ---- 描画 ----
function renderHeader() {
  const title = $("date-title");
  title.textContent = "";
  const m = state.date_label.match(/^(.*日)(（.）)$/);
  if (m) title.append(m[1], el("span", "wd", m[2]));
  else title.textContent = state.date_label;
  $("company-name").textContent = state.company_name;
}

function renderNotices() {
  const box = $("notices");
  const top = box.scrollTop;
  box.innerHTML = "";
  const removable = state.notices.length > 3;
  for (const n of state.notices) {
    const line = el("div", "notice-line" + (n.red ? " red" : ""));
    if (n.red) line.insertAdjacentHTML("beforeend", ALERT_ICON);
    line.appendChild(el("span", "notice-text", n.text));
    if (removable) {
      line.appendChild(actBtn("✕", e => {
        e.stopPropagation();
        removeRow(`/api/notices/${n.id}`);
      }, false, "edit-only"));
    }
    line.addEventListener("click", () => {
      if (isEditable()) editNotice(n);
    });
    box.appendChild(line);
  }
  box.scrollTop = top;
}

function renderSchedule() {
  keepScroll("schedule-wrap", () => {
    const body = document.querySelector("#schedule tbody");
    body.innerHTML = "";
    const rows = state.schedule;
    rows.forEach((r, i) => {
      const tr = el("tr");
      tr.appendChild(td(r.construction, { cls: "constr", onClick: () => editSchedule(r, "construction") }));
      tr.appendChild(td(r.company, { cls: "b", onClick: () => editSchedule(r, "company") }));
      const leader = td(r.leader, { cls: "b", onClick: () => editSchedule(r, "leader") });
      const contact = r.leader ? contactText(r.ext, r.outside) : "";
      if (contact) leader.appendChild(el("div", "contact", contact));
      tr.appendChild(leader);
      tr.appendChild(td(r.work, { onClick: () => editSchedule(r, "work") }));
      tr.appendChild(td(formatRange(r.start_time, r.end_time), { cls: "b c", onClick: () => editTimes(`/api/schedule/${r.id}`, r) }));
      const act = td("", { cls: "edit-only" });
      act.append(
        actBtn("▲", () => save("POST", `/api/schedule/${r.id}/move`, { direction: "up" }), i === 0),
        actBtn("▼", () => save("POST", `/api/schedule/${r.id}/move`, { direction: "down" }), i === rows.length - 1),
        actBtn("✕", () => removeRow(`/api/schedule/${r.id}`))
      );
      tr.appendChild(act);
      body.appendChild(tr);
    });
    for (let i = rows.length; i < MIN_SCHEDULE_ROWS; i++) body.appendChild(fillerRow());
  });
}

function renderHolidays() {
  keepScroll("holiday-wrap", () => {
    const body = document.querySelector("#holidays tbody");
    body.innerHTML = "";
    const holidayRows = visibleHolidayRows(state.holiday_rows);
    for (const r of holidayRows) {
      const tr = el("tr");
      tr.appendChild(td(r.label, { cls: ("b " + dateClass(r.kind)).trim(), onClick: () => editHolidayDate(r) }));
      tr.appendChild(holidayTd(r.construction, "constr", () => editHoliday(r, "construction")));
      tr.appendChild(holidayTd(r.person, "b", () => editHoliday(r, "person")));
      tr.appendChild(holidayTd(r.work, "", () => editHoliday(r, "work")));
      const range = formatRangeOrDash(r.start_time, r.end_time);
      tr.appendChild(td(range, { cls: "c" + (r.start_time || r.end_time ? "" : " dash"), onClick: () => editTimes(`/api/holiday-rows/${r.id}`, r) }));
      const act = td("", { cls: "edit-only" });
      act.appendChild(actBtn("✕", () => removeRow(`/api/holiday-rows/${r.id}`)));
      tr.appendChild(act);
      body.appendChild(tr);
    }
    for (let i = holidayRows.length; i < MIN_HOLIDAY_ROWS; i++) body.appendChild(fillerRow());
  });
}

function renderGenres() {
  keepScroll("genres", () => {
    const box = $("genres");
    box.innerHTML = "";
    for (const g of state.masters.genres) {
      const on = state.checked_genres.includes(g);
      const b = el("button", "genre" + (on ? " on" : ""), g);
      b.type = "button";
      b.addEventListener("click", () => {
        if (isEditable()) save("POST", "/api/genres/toggle", { name: g, checked: !on });
      });
      box.appendChild(b);
    }
  });
}

// 災害事例・文書ボタン・編集ロック・スリープ画面の更新。設定が変わったときも、画面を取り直すたびにここで新しい値が渡る
function renderParts() {
  setSeconds(state.settings.accident_seconds);
  setPlaylist(
    state.accident,
    state.checked_genres.length ? "該当する災害事例がありません" : "作業ジャンルを選ぶと災害事例が表示されます"
  );
  renderDocButtons(state.doc_buttons, state.settings.documents_idle_seconds);
  renderLinkButtons(state.links);
  setLockSeconds(state.settings.edit_lock_seconds);
  setStandbyConfig(state.settings.standby);
  updateTelop(state.settings.telop);
}

function render() {
  setDefaultTheme(state.settings.default_theme);
  setDefaultEditButton(state.settings.default_edit_button);
  // HTML は最初「閉じた状態」。編集できる状態（lock.js）に合わせて開け閉めする
  document.body.classList.toggle("locked", !isEditable());
  renderHeader();
  renderNotices();
  renderSchedule();
  renderGenres();
  renderHolidays();
  renderParts();
  setWarnings(state.warnings);
}

// ---- 保存と更新 ----
async function refresh() {
  state = await api("GET", "/api/board");
  lastToday = state.today;
  render();
}

async function save(method, url, body) {
  try {
    await api(method, url, body);
  } catch (e) {
    showToast("保存できませんでした: " + e.message);
  }
  try {
    await refresh();
  } catch (_) {}
}

async function removeRow(url) {
  if (await confirmBox("この行を削除しますか？", "削除する")) await save("DELETE", url);
}

// rev（内容の版）と today（日付）のどちらかが変われば画面を取り直す。0時を過ぎたときも更新される
async function poll() {
  try {
    const r = await api("GET", "/api/rev");
    if (r.rev !== lastRev || r.today !== lastToday) {
      await refresh();
      lastRev = r.rev;
    } else {
      setWarnings(state ? state.warnings : []);
    }
  } catch (_) {
    setWarnings(["サーバーに接続できません。再接続しています…"]);
  }
  setTimeout(poll, POLL_MS);
}

// ---- 入力 ----
async function editNotice(n) {
  const r = await inputText({ title: `連絡事項 ${n.position}行目`, value: n.text, flagLabel: "赤字で表示する", flag: n.red });
  if (!r) return;
  await save("PATCH", `/api/notices/${n.id}`, { text: r.text, red: r.flag });
}

async function editSchedule(row, field) {
  const m = state.masters;
  let options;
  let title;
  if (field === "company") {
    options = m.companies;
    title = "所属・会社名";
  } else if (field === "leader") {
    if (!row.company) {
      await alertBox("先に所属・会社名を選んでください");
      return;
    }
    options = m.leaders.filter(l => l.company === row.company).map(l => l.leader_name);
    if (!options.length) {
      await alertBox("この会社の責任者は登録されていません");
      return;
    }
    title = "責任者";
  } else if (field === "construction") {
    options = m.constructions;
    title = "工事件名";
  } else {
    options = worksFor(row.construction, m);
    title = "作業内容";
  }
  const v = await pickOption({ title, options, current: row[field] });
  if (v === undefined) return;
  await save("PATCH", `/api/schedule/${row.id}`, { [field]: v });
}

async function editHoliday(row, field) {
  const kinds = {
    person: { title: "氏名・会社名", options: state.masters.companies },
    construction: { title: "工事件名", options: state.masters.constructions },
    work: { title: "作業内容", options: worksFor(row.construction, state.masters) },
  };
  const { title, options } = kinds[field];
  const v = await pickOption({ title, options, current: row[field] });
  if (v === undefined) return;
  await save("PATCH", `/api/holiday-rows/${row.id}`, { [field]: v });
}

async function editHolidayDate(row) {
  const options = state.week_holidays.map(w => ({ value: w.date, label: w.label }));
  const v = await pickOption({ title: "日付", options, current: row.date, allowClear: false });
  if (!v) return;
  await save("PATCH", `/api/holiday-rows/${row.id}`, { date: v });
}

async function editTimes(url, row) {
  const times = state.masters.times;
  const start = await pickOption({ title: "開始時刻", options: times, current: row.start_time });
  if (start === undefined) return;
  if (start === "") {
    await save("PATCH", url, { start_time: "", end_time: "" });
    return;
  }
  const end = await pickOption({ title: "終了時刻", options: times, current: row.end_time });
  if (end === undefined) return;
  await save("PATCH", url, { start_time: start, end_time: end });
}

async function addHoliday() {
  if (!state.week_holidays.length) {
    await alertBox("今週は休日がありません。会社の休日は data/custom_holidays.csv に登録します。");
    return;
  }
  const options = state.week_holidays.map(w => ({ value: w.date, label: w.label }));
  const date = await pickOption({ title: "休日出勤の日付", options, allowClear: false });
  if (!date) return;
  await save("POST", "/api/holiday-rows", { date });
}

// 追加ボタンの連打対策: 処理中の押し直しは無視する
function guarded(fn) {
  let busy = false;
  return async () => {
    if (busy) return;
    busy = true;
    try {
      await fn();
    } finally {
      busy = false;
    }
  };
}

initTheme();
initClock();
$("btn-add-notice").addEventListener("click", guarded(async () => {
  await save("POST", "/api/notices");
  const box = $("notices");
  box.scrollTop = box.scrollHeight;
}));
$("btn-add-schedule").addEventListener("click", guarded(() => save("POST", "/api/schedule")));
$("btn-add-holiday").addEventListener("click", guarded(addHoliday));
initLock();
initTelop();
initAdminSettings({
  notify: showToast,
  onSaved: async () => {
    try {
      await refresh();
    } catch (_) {}
  },
});
// リンク先を開いている間は災害事例を止める（文書の閲覧と同時には開かない）。閉じて掲示板が見えてから再開する
initLinks({
  onOpen: () => {
    closeDocuments();
    pauseAccident();
  },
  onClose: resumeAccident,
});
// スリープに入るとき: 文書の閲覧・リンク先と設定メニューを閉じ、災害事例を止める
initStandby(() => {
  closeDocuments();
  closeLink(false); // 再開はしない（スリープが終わるときに再開される）
  $("settings").hidden = true;
  pauseAccident();
}, resumeAccident);
poll();
