// リンクボタン: 別のページ（設備点検システムなど）を掲示板の中の枠で開く。
// 上半分は node でも試せる純粋な関数、下半分が画面の操作（設定の文字は textContent / setAttribute でだけ入れる）
export const MAX_LINKS = 2;
export const MAX_LABEL = 100;
export const MAX_URL = 500;
export const MIN_STAY = 60;
export const MAX_STAY = 3600;
export const DEFAULT_STAY = 300;
export const WARN_SECONDS = 30; // 最大滞在のこの秒数前から「あと30秒で戻ります」を出す

// 改行・タブ・制御文字などが入っているか（サーバー側 config.py の会社名・ラベルと同じ決まり）
export function hasControlChar(s) {
  return /\p{C}/u.test(s);
}

// http:// か https:// のアドレスだけ。空白・制御文字・長すぎるもの・ホストが無いもの・ユーザー名:パスワード@ 付きは使えない（サーバー側 config.py と同じ決まり）
export function isSafeUrl(u) {
  if (typeof u !== "string" || !u || u.length > MAX_URL || !/^https?:\/\/[^\/\?#]/i.test(u) || /[\p{C}\s]/u.test(u)) return false;
  if (/^https?:\/\/[^\/\?#]*@/i.test(u)) return false;
  try {
    const p = new URL(u);
    return (p.protocol === "http:" || p.protocol === "https:") && !!p.hostname;
  } catch (_) {
    return false;
  }
}

// サーバーから届いた items から、使えるものだけを最大2つ取り出す
export function buildLinkList(items) {
  if (!Array.isArray(items)) return [];
  const out = [];
  for (const it of items) {
    const label = it && typeof it.label === "string" ? it.label.trim() : "";
    if (label && label.length <= MAX_LABEL && !hasControlChar(label) && isSafeUrl(it.url)) out.push({ label, url: it.url });
  }
  return out.slice(0, MAX_LINKS);
}

// 最大滞在（秒）。数でなければ既定、範囲外は端に寄せる
export function clampStay(v) {
  if (typeof v !== "number" || !Number.isFinite(v)) return DEFAULT_STAY;
  return Math.min(MAX_STAY, Math.max(MIN_STAY, Math.round(v)));
}

// 最大滞在のタイマー（待っているのは常に1つだけ）。滞在 − 30秒で onWarn、さらに30秒後に onExpire。
// restart は「続ける」: 滞在の最初からやり直す（1回押すごとに、最大滞在までが上限）
export function createStayTimer({ onWarn, onExpire, warn = WARN_SECONDS, set = (f, ms) => setTimeout(f, ms), clear = h => clearTimeout(h) }) {
  let handle = null;
  let stay = 0;
  const stop = () => {
    if (handle !== null) clear(handle);
    handle = null;
  };
  const begin = () => {
    stop();
    handle = set(() => {
      handle = set(() => {
        handle = null;
        onExpire();
      }, Math.min(stay, warn) * 1000);
      onWarn();
    }, Math.max(0, stay - warn) * 1000);
  };
  return {
    start(seconds) {
      stay = seconds;
      begin();
    },
    restart() {
      if (handle !== null) begin();
    },
    stop,
  };
}

// ---- 画面 ----
const $ = id => document.getElementById(id);
const LINK_ICON =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/></svg>';
let stay = DEFAULT_STAY;
let isOpen = false;
let hooks = { onOpen() {}, onClose() {} };
const timer = createStayTimer({
  onWarn: () => {
    $("link-warn").hidden = false;
  },
  onExpire: () => closeLink(),
});

// リンク先を開いているか（開いている間は、スリープに入らない）
export function isLinkOpen() {
  return isOpen;
}

// 画面を取り直すたびに呼ばれる。開いている最中の表示には触らない（ボタンと、次に開くときの滞在秒数だけ更新）
export function renderLinkButtons(links) {
  const items = buildLinkList(links && links.items);
  stay = clampStay(links && links.max_stay_seconds);
  const box = $("link-buttons");
  const key = JSON.stringify(items);
  if (box.dataset.key === key) return;
  box.dataset.key = key;
  box.replaceChildren();
  box.hidden = items.length === 0;
  for (const item of items) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "link-btn";
    b.insertAdjacentHTML("beforeend", LINK_ICON);
    const t = document.createElement("span");
    t.className = "doc-label";
    t.textContent = item.label;
    b.appendChild(t);
    b.addEventListener("click", () => openLink(item));
    box.appendChild(b);
  }
}

function openLink(item) {
  if (isOpen || !isSafeUrl(item.url)) return;
  isOpen = true;
  hooks.onOpen();
  $("link-title").textContent = item.label;
  $("link-newtab").setAttribute("href", item.url);
  $("link-frame").setAttribute("src", item.url);
  $("link-warn").hidden = true;
  $("link-view").hidden = false;
  timer.start(stay);
}

// 閉じると、枠（iframe）ごと作り直して中のページを止める。resume=false は、スリープに入るときのように、掲示板に戻さないとき
export function closeLink(resume = true) {
  if (!isOpen) return;
  isOpen = false;
  timer.stop();
  $("link-warn").hidden = true;
  $("link-view").hidden = true;
  const old = $("link-frame");
  const fresh = old.cloneNode(false);
  fresh.removeAttribute("src");
  old.setAttribute("src", "about:blank");
  old.replaceWith(fresh);
  $("link-newtab").removeAttribute("href");
  $("link-title").textContent = "";
  if (resume) hooks.onClose(); // 掲示板が見えてから災害事例を再開する
}

// onOpen: 開く直前（文書の閲覧を閉じる・災害事例を止める）。onClose: 閉じて掲示板が見えたあと
export function initLinks({ onOpen, onClose }) {
  hooks = { onOpen, onClose };
  $("link-back").addEventListener("click", () => closeLink());
  $("link-continue").addEventListener("click", () => {
    $("link-warn").hidden = true;
    timer.restart();
  });
}
