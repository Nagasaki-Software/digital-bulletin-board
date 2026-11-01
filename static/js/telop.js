import { api } from "./api.js";
import { buildSegments, telopKey, marqueeParams, DEFAULT_SPEED } from "./telop-text.mjs";

const RESIZE_MS = 300; // 画面の大きさが変わり終わってから作り直す
const RETRY_MS = 500; // 幅がまだ 0 のとき（描画前）に少し待って再試行する間隔
const $ = id => document.getElementById(id);

let items = [];
let speed = DEFAULT_SPEED;
let anim = null; // 動いているアニメーションは常に1つだけ
let builtKey = null;
let resizeTimer = null;
let retryTimer = null;
let seq = 0;

// 内容・速度・幅のどれかが変わったときだけ、文字を並べ直してアニメーションを作り直す
function render() {
  clearTimeout(retryTimer);
  retryTimer = null;
  const width = $("telop-scroll").clientWidth;
  if (width === 0) {
    retryTimer = setTimeout(render, RETRY_MS);
    return;
  }
  const key = telopKey(items, speed, width);
  if (anim && key === builtKey) return;
  if (anim) {
    anim.cancel();
    anim = null;
  }
  const track = $("telop-track");
  // ファイルの文字は textContent だけで入れる（HTML としては解釈させない）
  track.replaceChildren(
    ...buildSegments(items).map(seg => {
      if (!seg.badge) return document.createTextNode(seg.text);
      const badge = document.createElement("span");
      badge.className = "telop-badge";
      badge.textContent = seg.text;
      return badge;
    })
  );
  const { from, to, durationMs } = marqueeParams(width, track.scrollWidth, speed);
  anim = track.animate(
    [{ transform: `translateX(${from}px)` }, { transform: `translateX(${to}px)` }],
    { duration: durationMs, iterations: Infinity, easing: "linear" }
  );
  builtKey = key;
}

// 画面を取り直すたびに呼ぶ。サーバーの速度設定を反映し、お知らせの文章を読み直す
export async function updateTelop(settings) {
  const s = Number(settings && settings.speed);
  speed = Number.isFinite(s) ? s : DEFAULT_SPEED;
  const mine = ++seq;
  try {
    const r = await api("GET", "/api/telop");
    if (mine !== seq) return; // もっと新しい呼び出しがある
    items = Array.isArray(r.items) ? r.items.filter(x => typeof x === "string") : [];
  } catch (_) {
    // 読めなかったときは、いまの表示を続ける
  }
  if (mine === seq) render();
}

export function initTelop() {
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(render, RESIZE_MS);
  });
}
