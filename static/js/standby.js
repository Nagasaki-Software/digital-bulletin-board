import { isStandbyTime } from "./timeutil.mjs";

let cfg = { start: "18:00", end: "07:30", wake_idle_seconds: 300 };
let lastActivity = -Infinity;
let shown = false;
let configured = false;
let onShow = () => {};
let onHide = () => {};
const $ = id => document.getElementById(id);

// サーバーから本物の設定が届くまでは待機画面を出さない（読み込み直後のちらつき防止）
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

// 先に待機画面を消してから onHide を呼ぶ（災害事例の再開は掲示板が見えてから）
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
