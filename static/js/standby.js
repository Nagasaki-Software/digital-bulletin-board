import { isStandbyTime } from "./timeutil.mjs";
import { isLinkOpen } from "./links.js";

let extraBusy = () => false; // ホワイトボードなど、links.js 以外で「操作中と見なす」画面があるとき
export function setBusyCheck(fn) {
  extraBusy = fn;
}
let cfg = { start: "18:00", end: "08:00", wake_idle_seconds: 300 };
let lastActivity = -Infinity;
let shown = false;
let configured = false;
let onShow = () => {};
let onHide = () => {};
const $ = id => document.getElementById(id);

// サーバーから本物の設定が届くまではスリープ画面を出さない（読み込み直後のちらつき防止）
export function setStandbyConfig(c) {
  if (!c || typeof c.start !== "string" || typeof c.end !== "string") return;
  const idle = Number(c.wake_idle_seconds);
  cfg = { start: c.start, end: c.end, wake_idle_seconds: Number.isFinite(idle) && idle >= 0 ? idle : 300 };
  configured = true;
}

function updateClock() {
  const n = new Date();
  $("standby-clock").textContent = n.getHours() + ":" + String(n.getMinutes()).padStart(2, "0");
  $("standby-date").textContent = `${n.getMonth() + 1}月${n.getDate()}日`;
}

function showStandby() {
  shown = true;
  $("standby").hidden = false;
  updateClock();
  onShow();
}

// 先にスリープ画面を消してから onHide を呼ぶ（災害事例の再開は掲示板が見えてから）
function hideStandby() {
  shown = false;
  $("standby").hidden = true;
  lastActivity = Date.now();
  onHide();
}

function tick() {
  if (!configured) return;
  const n = new Date();
  const inTime = isStandbyTime(n.getHours() * 60 + n.getMinutes(), cfg.start, cfg.end);
  if (shown) {
    if (!inTime) hideStandby();
    else updateClock();
    return;
  }
  if (isLinkOpen() || extraBusy()) { // ホワイトボードも同じ（描いている間は、スリープに入らない）
    // リンク先の中の操作は、この画面には届かない。開いている間は操作中と見なし、閉じてから「操作なし」を数え直す
    lastActivity = Date.now();
    return;
  }
  if (inTime && Date.now() - lastActivity > cfg.wake_idle_seconds * 1000) showStandby();
}

export function initStandby(show, hide) {
  onShow = show;
  onHide = hide;
  document.addEventListener("pointerdown", () => {
    lastActivity = Date.now();
  }, true);
  // 起こすのは click（指を離したあと）。pointerdown で消すと、続けて届く click が下の画面に当たってしまう
  $("standby").addEventListener("click", () => {
    if (shown) hideStandby();
  });
  setInterval(tick, 5000);
  tick();
}
