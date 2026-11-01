import { api } from "./api.js";

const ROWS = 5; // 文書ボタンの最大数。入力欄は常に5行出し、ボタン数を超える行は使えない（灰色）状態にする
const MIN_SPEED = 20;
const MAX_SPEED = 500;
const $ = id => document.getElementById(id);

// 保存の失敗などを、フォームの下に赤字（⚠）で出す。空文字で消す。error=false は進行中などの通常表示
function setStatus(text, error = true) {
  const box = $("settings-msg");
  box.textContent = text ? (error ? "⚠ " : "") + text : "";
  box.classList.toggle("error", !!text && error);
  box.hidden = !text;
}

function field(kind, i) {
  return $(`doc-${kind}-${i}`);
}

// ボタン数は 1〜5 の整数だけ有効。それ以外は null
function countValue() {
  const raw = $("doc-count").value.trim();
  const n = Number(raw);
  return raw !== "" && Number.isInteger(n) && n >= 1 && n <= ROWS ? n : null;
}

// ボタン数以降の行は、灰色にして入力できなくする（値は消さない。数を増やすとまた使える）
function applyCount() {
  const n = countValue();
  if (n === null) return;
  for (let i = 0; i < ROWS; i++) {
    const off = i >= n;
    field("label", i).disabled = off;
    field("folder", i).disabled = off;
    field("label", i).parentElement.classList.toggle("off", off);
  }
}

// 版数はサーバー（app.py の APP_VERSION）だけが持つ。取れたときだけ表示する（古い値や空の表示を出さない）
async function loadVersion() {
  try {
    const h = await api("GET", "/api/health");
    $("app-version").textContent = String(h.version);
    $("app-version-line").hidden = false;
  } catch (_) {
    $("app-version-line").hidden = true;
  }
}

async function load() {
  setStatus("");
  loadVersion();
  try {
    const s = await api("GET", "/api/admin-settings");
    const buttons = s.documents.buttons;
    $("doc-count").value = String(buttons.length);
    for (let i = 0; i < ROWS; i++) {
      field("label", i).value = buttons[i] ? buttons[i].label : "";
      field("folder", i).value = buttons[i] ? buttons[i].folder : "";
    }
    $("telop-speed").value = String(s.telop.speed);
    $("telop-folder").value = s.telop.folder || "";
    $("company-input").value = s.company_name || "";
    applyCount();
  } catch (e) {
    setStatus("全端末共通の設定を読み込めませんでした: " + e.message);
  }
}

// 入力を確かめて送る内容にする。誤りは { error, focus } で返す
function collect() {
  const company = $("company-input").value.trim();
  if (!company) return { error: "会社名を入力してください", focus: $("company-input") };
  const n = countValue();
  if (n === null) return { error: `ボタン数は 1〜${ROWS} の整数で入力してください`, focus: $("doc-count") };
  const buttons = [];
  for (let i = 0; i < n; i++) {
    const label = field("label", i).value.trim();
    const folder = field("folder", i).value.trim();
    if (!label) return { error: `ラベル ${i + 1} を入力してください`, focus: field("label", i) };
    if (!folder) return { error: `フォルダパス ${i + 1} を入力してください`, focus: field("folder", i) };
    buttons.push({ label, folder });
  }
  const raw = $("telop-speed").value.trim();
  const speed = Number(raw);
  if (raw === "" || !Number.isInteger(speed) || speed < MIN_SPEED || speed > MAX_SPEED) {
    return { error: `テロップ速度は ${MIN_SPEED}〜${MAX_SPEED} の整数で入力してください`, focus: $("telop-speed") };
  }
  // テロップフォルダが空欄なら、サーバーが既定の telop フォルダにする
  return {
    body: { company_name: company, documents: { buttons }, telop: { speed, folder: $("telop-folder").value.trim() } },
  };
}

// notify(メッセージ, 成功か)・onSaved() は board.js から受け取る（トースト表示と画面の取り直し）
export function initAdminSettings({ notify, onSaved }) {
  $("btn-gear").addEventListener("click", load);
  $("doc-count").addEventListener("input", applyCount);
  $("doc-count").addEventListener("change", applyCount);
  let busy = false;
  $("settings-save").addEventListener("click", async () => {
    if (busy) return;
    const { body, error, focus } = collect();
    if (error) {
      setStatus(error);
      focus.focus();
      return;
    }
    busy = true;
    setStatus("保存しています…", false);
    try {
      const r = await api("POST", "/api/admin-settings", body);
      setStatus("");
      $("settings").hidden = true;
      const warn = r.warnings && r.warnings.length ? r.warnings.join(" / ") : "";
      notify(warn ? "保存しました。ただし " + warn : "全端末共通の設定を保存しました", !warn);
      await onSaved();
    } catch (e) {
      setStatus("保存できませんでした: " + e.message);
      notify("保存できませんでした: " + e.message, false);
    } finally {
      busy = false;
    }
  });
}
