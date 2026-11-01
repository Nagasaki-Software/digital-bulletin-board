import * as pdfjsLib from "/pdfjs/pdf.mjs";
import { api } from "./api.js";

pdfjsLib.GlobalWorkerOptions.workerSrc = "/pdfjs/pdf.worker.mjs";

const $ = id => document.getElementById(id);
const DOC_ICON =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M16 13H8"/><path d="M16 17H8"/></svg>';
const LOAD_TIMEOUT_MS = 20000;
const MAX_CANVAS_PIXELS = 16e6; // 拡大しすぎても描画用メモリが際限なく増えないようにする上限
const FAIL_NOTICE = "表示できません";
let idleSeconds = 120;
let idleTimer = null;
let doc = null;
let loadTask = null;
let renderTask = null;
let retryTimer = null;
let token = 0; // フォルダ・ファイルを切り替えるたびに増やし、古い読み込みの結果を捨てる
let pageNum = 1;
let zoom = 1;
let rendering = false;
let pending = false;
let currentIndex = 0;
let currentLabel = "";
let pinch = null;

const wrap = $("doc-canvas-wrap");
const msg = document.createElement("div");
msg.style.cssText = "display:none;padding:3rem 2rem;font-size:2rem;color:#FFFFFF";
wrap.appendChild(msg);

function showMsg(text) {
  msg.textContent = text;
  msg.style.display = text ? "block" : "none";
  $("doc-canvas").hidden = !!text;
}

function resetIdle() {
  if ($("documents").hidden) return;
  clearTimeout(idleTimer);
  idleTimer = setTimeout(closeDocuments, idleSeconds * 1000);
}

// 読み込み中の PDF.js の作業（ワーカー）を止める。getDocument は失敗しても自分では片付けない
function cancelLoad() {
  if (loadTask) {
    loadTask.destroy();
    loadTask = null;
  }
}

function dropDoc() {
  clearTimeout(retryTimer);
  if (renderTask) {
    renderTask.cancel();
    renderTask = null;
  }
  pending = false;
  if (doc) {
    doc.destroy();
    doc = null;
  }
  // 前の文書の絵を残さず、描画用メモリも手放す
  const c = $("doc-canvas");
  c.width = 0;
  c.height = 0;
  c.style.width = "0px";
  c.style.height = "0px";
  wrap.scrollTop = 0;
  wrap.scrollLeft = 0;
}

function loadDoc(url) {
  const task = pdfjsLib.getDocument({ url, cMapUrl: "/pdfjs/cmaps/", cMapPacked: true });
  loadTask = task;
  let tid;
  const timeout = new Promise((_, reject) => {
    tid = setTimeout(() => reject(new Error("読み込みがタイムアウトしました")), LOAD_TIMEOUT_MS);
  });
  return Promise.race([task.promise, timeout]).finally(() => clearTimeout(tid));
}

export function closeDocuments() {
  clearTimeout(idleTimer);
  token++;
  cancelLoad();
  dropDoc();
  pinch = null;
  $("documents").hidden = true;
}

export function renderDocButtons(buttons, idle) {
  if (Number(idle) > 0) idleSeconds = Number(idle);
  const box = $("doc-buttons");
  const key = JSON.stringify(buttons);
  if (box.dataset.key === key) return;
  box.dataset.key = key;
  box.innerHTML = "";
  box.classList.toggle("many", buttons.length > 3);
  for (const b of buttons) {
    const e = document.createElement("button");
    e.type = "button";
    e.className = "doc-btn";
    e.insertAdjacentHTML("beforeend", DOC_ICON);
    const t = document.createElement("span");
    t.className = "doc-label";
    t.textContent = b.label;
    e.appendChild(t);
    e.addEventListener("click", () => openFolder(b.index, b.label));
    box.appendChild(e);
  }
}

async function openFolder(index, label) {
  const my = ++token;
  currentIndex = index;
  currentLabel = label;
  cancelLoad();
  dropDoc();
  pinch = null;
  $("documents").hidden = false;
  $("docs-title").textContent = label;
  $("docs-back").hidden = true;
  $("doc-viewer").hidden = true;
  const list = $("doc-list");
  list.hidden = false;
  list.innerHTML = "";
  resetIdle();
  let files = [];
  let failed = false;
  try {
    files = await api("GET", `/api/documents/${index}/files`);
  } catch (e) {
    console.error("文書の一覧を取得できませんでした", e);
    failed = true;
  }
  if (my !== token) return;
  if (!files.length) {
    list.textContent = failed ? "文書の一覧を読み込めません" : "文書がありません";
    return;
  }
  for (const name of files) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "opt doc-item";
    b.textContent = name.replace(/\.pdf$/i, "");
    b.addEventListener("click", () => openFile(name));
    list.appendChild(b);
  }
}

async function openFile(name) {
  const my = ++token;
  $("doc-list").hidden = true;
  $("doc-viewer").hidden = false;
  $("docs-back").hidden = false;
  $("docs-title").textContent = name.replace(/\.pdf$/i, "");
  $("doc-page").textContent = "読み込み中…";
  showMsg("");
  zoom = 1;
  pageNum = 1;
  pinch = null;
  cancelLoad();
  dropDoc();
  resetIdle();
  try {
    const loaded = await loadDoc(`/api/documents/${currentIndex}/pdf/${encodeURIComponent(name)}`);
    if (my !== token) {
      // 読み込み中に別の表示へ切り替わった・閉じられた。後から届いた分は捨てる（失敗側は切替時の cancelLoad で止まっている）
      loaded.destroy();
      return;
    }
    loadTask = null;
    doc = loaded;
    await renderPage();
  } catch (e) {
    if (my !== token) return;
    console.error("文書の表示に失敗しました", e);
    cancelLoad();
    dropDoc();
    $("doc-page").textContent = "";
    showMsg(FAIL_NOTICE);
  }
}

async function renderPage() {
  const d = doc;
  if (!d) return;
  if (rendering) {
    pending = true;
    if (renderTask) renderTask.cancel(); // 古い大きさの描画は待たずに捨て、最新の大きさで描き直す
    return;
  }
  const my = token;
  rendering = true;
  try {
    const p = await d.getPage(pageNum);
    if (d !== doc) return;
    const base = p.getViewport({ scale: 1 });
    if (!wrap.clientWidth || !wrap.clientHeight) {
      // 枠がまだ見えていない（大きさ0）。少し待って出し直す
      clearTimeout(retryTimer);
      retryTimer = setTimeout(redraw, 500);
      return;
    }
    const fit = Math.min(wrap.clientWidth / base.width, wrap.clientHeight / base.height) * 0.97;
    const vp = p.getViewport({ scale: fit * zoom });
    const ratio = Math.min(window.devicePixelRatio || 1, Math.sqrt(MAX_CANVAS_PIXELS / (vp.width * vp.height)));
    const c = $("doc-canvas");
    c.width = Math.max(1, Math.floor(vp.width * ratio));
    c.height = Math.max(1, Math.floor(vp.height * ratio));
    c.style.width = vp.width + "px";
    c.style.height = vp.height + "px";
    const ctx = c.getContext("2d");
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    renderTask = p.render({ canvasContext: ctx, viewport: vp });
    await renderTask.promise;
    renderTask = null;
    if (d !== doc) return;
    showMsg("");
    $("doc-page").textContent = `${pageNum} / ${d.numPages}`;
  } catch (e) {
    if (e && e.name === "RenderingCancelledException") return;
    if (d !== doc || my !== token) return;
    throw e;
  } finally {
    rendering = false;
    if (pending) {
      pending = false;
      if (doc) redraw();
    }
  }
}

function onRenderError(e) {
  console.error("文書の表示に失敗しました", e);
  $("doc-page").textContent = "";
  showMsg(FAIL_NOTICE);
}

// ボタン・ピンチからの描き直し。失敗しても未処理の例外にせず、画面に出す
function redraw() {
  renderPage().catch(onRenderError);
}

function clampZoom(z) {
  return Math.min(5, Math.max(0.5, z));
}

$("docs-close").addEventListener("click", closeDocuments);
$("docs-back").addEventListener("click", () => openFolder(currentIndex, currentLabel));
$("doc-prev").addEventListener("click", () => {
  if (doc && pageNum > 1) {
    pageNum--;
    wrap.scrollTop = 0;
    wrap.scrollLeft = 0;
    redraw();
  }
});
$("doc-next").addEventListener("click", () => {
  if (doc && pageNum < doc.numPages) {
    pageNum++;
    wrap.scrollTop = 0;
    wrap.scrollLeft = 0;
    redraw();
  }
});
$("doc-zoom-in").addEventListener("click", () => {
  zoom = clampZoom(zoom * 1.25);
  redraw();
});
$("doc-zoom-out").addEventListener("click", () => {
  zoom = clampZoom(zoom / 1.25);
  redraw();
});

// ピンチ（2本指）とホイールでの拡大縮小。指を離す・取り消される（touchcancel）・閉じるで状態を捨てる
const dist = t => Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY);
wrap.addEventListener("touchstart", e => {
  if (e.touches.length === 2) {
    const d = dist(e.touches);
    pinch = d > 0 ? { d, z: zoom } : null;
  } else {
    pinch = null;
  }
}, { passive: true });
wrap.addEventListener("touchmove", e => {
  if (pinch && e.touches.length === 2 && doc) {
    zoom = clampZoom(pinch.z * (dist(e.touches) / pinch.d));
    redraw();
  }
}, { passive: true });
const endPinch = e => {
  if (e.touches.length < 2) pinch = null;
};
wrap.addEventListener("touchend", endPinch, { passive: true });
wrap.addEventListener("touchcancel", () => {
  pinch = null;
}, { passive: true });
wrap.addEventListener("wheel", e => {
  if (e.ctrlKey) {
    e.preventDefault();
    if (!doc) return;
    zoom = clampZoom(zoom * (e.deltaY < 0 ? 1.1 : 1 / 1.1));
    redraw();
  }
}, { passive: false });

// 何か操作するたびに「一定時間操作なしで戻る」を数え直す
for (const ev of ["pointerdown", "touchstart", "touchmove", "wheel", "scroll", "keydown"]) {
  $("documents").addEventListener(ev, resetIdle, { capture: true, passive: true });
}
