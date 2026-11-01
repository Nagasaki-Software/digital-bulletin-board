import { api, isAsciiKey } from "./api.js";
import { normalizeHHMM, secondsValue } from "./timeutil.mjs";
import { isSafeUrl, hasControlChar, MAX_LABEL, MAX_URL, MIN_STAY, MAX_STAY, DEFAULT_STAY } from "./links.js";

const LINK_ROWS = 2; // リンクボタンの最大数
const ROWS = 5; // 文書ボタンの最大数。入力欄は常に5行出し、ボタン数を超える行は使えない（灰色）状態にする
const MIN_SPEED = 20;
const MAX_SPEED = 500;
const $ = id => document.getElementById(id);
// [送る名前, 入力欄の id, 画面の項目名]
const SECONDS_FIELDS = [
  ["wake", "sleep-wake-idle", "操作なしでスリープに戻る（秒）"],
  ["accident", "accident-seconds", "災害事例の表示秒数"],
  ["idle", "doc-idle-seconds", "文書の操作なし戻り（秒）"],
  ["lock", "edit-lock-seconds", "編集の自動終了（秒）"],
];

// 別のPC（localhost 以外の宛先でこの画面を開いている）から保存するときだけ、管理者キーが要る
const isRemote = !["localhost", "127.0.0.1", "[::1]", "::1"].includes(location.hostname);
const KEY_STORE = "admin-key";

// このタブの間だけ覚える（sessionStorage が使えない環境では、毎回入力になるだけ）
function rememberedKey() {
  try {
    return sessionStorage.getItem(KEY_STORE) || "";
  } catch (_) {
    return "";
  }
}

function rememberKey(key) {
  try {
    sessionStorage.setItem(KEY_STORE, key);
  } catch (_) {}
}

// 管理者キーの欄。別のPCで開いているときは最初から出す。localhost でも、キーを求められた（403）あとは出す
function showKeyRow() {
  $("admin-key-row").hidden = false;
}

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
  if (isRemote) showKeyRow();
  $("admin-key").value = rememberedKey(); // 設定を開くたびに、このタブで覚えているキーを入れ直す
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
    const sb = s.standby || {};
    $("sleep-start").value = sb.start || "";
    $("sleep-end").value = sb.end || "";
    $("sleep-wake-idle").value = sb.wake_idle_seconds ?? "";
    $("accident-seconds").value = s.accident_seconds ?? "";
    $("doc-idle-seconds").value = s.documents.idle_return_seconds ?? "";
    $("edit-lock-seconds").value = s.edit_lock_seconds ?? "";
    $("holidays-file").value = s.custom_holidays_file || "";
    const ln = s.links || {};
    for (let i = 0; i < LINK_ROWS; i++) {
      const it = (ln.items || [])[i];
      $(`link-label-${i}`).value = it ? it.label : "";
      $(`link-url-${i}`).value = it ? it.url : "";
    }
    $("link-stay").value = String(ln.max_stay_seconds ?? DEFAULT_STAY);
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
    if (hasControlChar(label)) return { error: `ラベル ${i + 1} に使えない文字（改行・タブなど）が含まれています`, focus: field("label", i) };
    if (!folder) return { error: `フォルダパス ${i + 1} を入力してください`, focus: field("folder", i) };
    buttons.push({ label, folder });
  }
  const raw = $("telop-speed").value.trim();
  const speed = Number(raw);
  if (raw === "" || !Number.isInteger(speed) || speed < MIN_SPEED || speed > MAX_SPEED) {
    return { error: `テロップ速度は ${MIN_SPEED}〜${MAX_SPEED} の整数で入力してください`, focus: $("telop-speed") };
  }
  // スリープ・時間: 時刻は HH:MM（文字欄になるブラウザでも "8:00" を受け付ける）、秒数は 1〜86400
  const start = normalizeHHMM($("sleep-start").value);
  if (!start) return { error: "スリープ開始は 18:00 のような時刻で入力してください", focus: $("sleep-start") };
  const end = normalizeHHMM($("sleep-end").value);
  if (!end) return { error: "スリープ終了は 08:00 のような時刻で入力してください", focus: $("sleep-end") };
  const seconds = {};
  for (const [key, id, label] of SECONDS_FIELDS) {
    seconds[key] = secondsValue($(id).value);
    if (seconds[key] === null) return { error: `${label}は 1〜86400 の数で入力してください`, focus: $(id) };
  }
  // リンクボタン: 名前もアドレスも空の行は使わない。片方だけは誤り
  const linkItems = [];
  for (let i = 0; i < LINK_ROWS; i++) {
    const label = $(`link-label-${i}`).value.trim();
    const url = $(`link-url-${i}`).value.trim();
    if (!label && !url) continue;
    if (!label) return { error: `リンクボタン ${i + 1} の名前を入力してください（使わないときは名前もアドレスも空にします）`, focus: $(`link-label-${i}`) };
    if (label.length > MAX_LABEL) return { error: `リンクボタン ${i + 1} の名前は ${MAX_LABEL} 文字以内で入力してください`, focus: $(`link-label-${i}`) };
    if (hasControlChar(label)) return { error: `リンクボタン ${i + 1} の名前に使えない文字（改行・タブなど）が含まれています`, focus: $(`link-label-${i}`) };
    if (!isSafeUrl(url)) {
      return { error: `リンクボタン ${i + 1} のアドレスを http:// か https:// で始まる正しい形で入力してください（空白・ユーザー名:パスワード@ なし・${MAX_URL}文字以内）`, focus: $(`link-url-${i}`) };
    }
    linkItems.push({ label, url });
  }
  const stayRaw = $("link-stay").value.trim();
  const stay = Number(stayRaw);
  if (stayRaw === "" || !Number.isInteger(stay) || stay < MIN_STAY || stay > MAX_STAY) {
    return { error: `リンクの最大滞在（秒）は ${MIN_STAY}〜${MAX_STAY} の整数で入力してください`, focus: $("link-stay") };
  }
  // テロップフォルダ・会社の休日ファイルが空欄なら、サーバーが既定の場所にする
  return {
    body: {
      company_name: company,
      documents: { buttons, idle_return_seconds: seconds.idle },
      telop: { speed, folder: $("telop-folder").value.trim() },
      standby: { start, end, wake_idle_seconds: seconds.wake },
      accident_seconds: seconds.accident,
      edit_lock_seconds: seconds.lock,
      custom_holidays_file: $("holidays-file").value.trim(),
      links: { items: linkItems, max_stay_seconds: stay },
    },
  };
}

// notify(メッセージ, 成功か)・onSaved() は board.js から受け取る（トースト表示と画面の取り直し）
export function initAdminSettings({ notify, onSaved }) {
  $("btn-gear").addEventListener("click", load);
  if (isRemote) showKeyRow();
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
    const key = $("admin-key-row").hidden ? "" : $("admin-key").value.trim();
    if (key && !isAsciiKey(key)) {
      setStatus("管理者キーは半角英数字です");
      $("admin-key").focus();
      return;
    }
    busy = true;
    setStatus("保存しています…", false);
    try {
      const r = await api("POST", "/api/admin-settings", body, undefined, key ? { "X-Admin-Key": key } : {});
      if (key) rememberKey(key);
      setStatus("");
      $("settings").hidden = true;
      const warn = r.warnings && r.warnings.length ? r.warnings.join(" / ") : "";
      notify(warn ? "保存しました。ただし " + warn : "全端末共通の設定を保存しました", !warn);
      await onSaved();
    } catch (e) {
      if (e.status === 403) {
        showKeyRow();
        setStatus(e.message); // 管理者キーが無い・違う。サーバーの文言をそのまま出して、キー欄に戻る
        $("admin-key").focus();
      } else {
        setStatus("保存できませんでした: " + e.message);
      }
      notify("保存できませんでした: " + e.message, false);
    } finally {
      busy = false;
    }
  });
}
