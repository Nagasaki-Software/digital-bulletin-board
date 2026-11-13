import * as pdfjsLib from "/pdfjs/pdf.mjs";
import { api } from "./api.js";
import { rememberPos, recallPos } from "./docmemory.mjs";

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
const GRID_SIZE = 6;
let folderFiles = [];
let gridStart = 0;
let fromGrid = false; // 1枚表示を 3×2 から開いたか（「戻る」の行き先）
let gridJobs = []; // 3×2 の各マスの読み込み。切り替え・閉じるときに止める
let gridMode = "files"; // 3×2 に並べているもの。"files"＝フォルダの各PDFの1ページ目、"pages"＝開いているPDFのページ
let pageGridStart = 0;
let currentFile = ""; // 1枚表示で開いている PDF の名前（ページを覚えるときの名前）
let lastScroll = { sx: 0, sy: 0 };

// ---- ページ・拡大率・位置を覚える（この端末だけ。設定の「文書のページを覚える」） ----
const MEMORY_KEY = "dbb.docMemory";
const POS_KEY = "dbb.docPos";

function memoryOn() {
  try {
    return localStorage.getItem(MEMORY_KEY) === "on";
  } catch (_) {
    return false;
  }
}

function readPosStore() {
  try {
    return JSON.parse(localStorage.getItem(POS_KEY) || "{}");
  } catch (_) {
    return {};
  }
}

const posKey = name => `${currentIndex}/${name}`;

// 閉じる・一覧へ戻る・別の文書を開く・操作なしで戻るときに呼ぶ
function saveCurrentPos() {
  if (!memoryOn() || !doc || !currentFile) return;
  try {
    const store = rememberPos(readPosStore(), posKey(currentFile), { fp: doc.fingerprints[0], page: pageNum, zoom, ...lastScroll });
    localStorage.setItem(POS_KEY, JSON.stringify(store));
  } catch (_) {}
}

// 一覧・1枚表示・3×2 の切り替え。下の帯のボタンも、その画面で使うものだけを出す
function setView(view) {
  $("doc-list").hidden = view !== "list";
  $("doc-viewer").hidden = view !== "viewer";
  $("doc-grid-view").hidden = view !== "grid";
  $("doc-nav").hidden = view !== "viewer";
  $("grid-nav").hidden = view !== "grid";
  $("grid-single").hidden = !(view === "grid" && gridMode === "pages");
  $("docs-back").hidden = view === "list" || (view === "viewer" && !fromGrid && folderFiles.length === 1);
  $("docs-back").textContent = fromGrid ? "戻る" : "一覧へ";
}

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

function openPdf(url) {
  const task = pdfjsLib.getDocument({ url, cMapUrl: "/pdfjs/cmaps/", cMapPacked: true });
  let tid;
  const timeout = new Promise((_, reject) => {
    tid = setTimeout(() => reject(new Error("読み込みがタイムアウトしました")), LOAD_TIMEOUT_MS);
  });
  return { task, promise: Promise.race([task.promise, timeout]).finally(() => clearTimeout(tid)) };
}

function loadDoc(url) {
  const { task, promise } = openPdf(url);
  loadTask = task;
  return promise;
}

const pdfUrl = name => `/api/documents/${currentIndex}/pdf/${encodeURIComponent(name)}`;

function cancelGrid() {
  for (const j of gridJobs) {
    if (j.task) j.task.destroy();
    j.task = null;
  }
  gridJobs = [];
  const grid = $("doc-grid");
  for (const c of grid.querySelectorAll("canvas")) {
    c.width = 0;
    c.height = 0;
  }
  grid.innerHTML = "";
}

export function closeDocuments() {
  saveCurrentPos();
  clearTimeout(idleTimer);
  token++;
  currentFile = "";
  cancelLoad();
  dropDoc();
  cancelGrid();
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
  saveCurrentPos();
  const my = ++token;
  currentIndex = index;
  currentLabel = label;
  currentFile = "";
  cancelLoad();
  dropDoc();
  cancelGrid();
  pinch = null;
  fromGrid = false;
  folderFiles = [];
  $("documents").hidden = false;
  $("docs-title").textContent = label;
  setView("list");
  const box = $("doc-list");
  box.innerHTML = "";
  const list = document.createElement("div");
  list.className = "doc-list-inner";
  box.appendChild(list);
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
    box.innerHTML = "";
    const m = document.createElement("div");
    m.className = "doc-list-msg";
    m.textContent = failed ? "文書の一覧を読み込めません" : "文書がありません";
    box.appendChild(m);
    return;
  }
  folderFiles = files;
  if (files.length === 1) {
    openFile(files[0]);
    return;
  }
  if (files.length > 1) {
    const g = document.createElement("button");
    g.type = "button";
    g.className = "opt doc-grid-btn";
    g.textContent = "6枚ずつ表示（3×2）";
    g.addEventListener("click", () => showGrid(0));
    list.appendChild(g);
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

async function openFile(name, viaGrid = false) {
  saveCurrentPos();
  const my = ++token;
  cancelGrid();
  fromGrid = viaGrid;
  currentFile = "";
  setView("viewer");
  $("doc-pages-grid").hidden = true;
  $("docs-title").textContent = name.replace(/\.pdf$/i, "");
  $("doc-page").textContent = "読み込み中…";
  showMsg("");
  zoom = 1;
  pageNum = 1;
  lastScroll = { sx: 0, sy: 0 };
  pinch = null;
  cancelLoad();
  dropDoc();
  resetIdle();
  try {
    const loaded = await loadDoc(pdfUrl(name));
    if (my !== token) {
      // 読み込み中に別の表示へ切り替わった・閉じられた。後から届いた分は捨てる（失敗側は切替時の cancelLoad で止まっている）
      loaded.destroy();
      return;
    }
    loadTask = null;
    doc = loaded;
    currentFile = name;
    $("doc-pages-grid").hidden = doc.numPages < 2;
    // 前に見ていたページ・拡大率・位置から始める（設定で「覚える」のときだけ。PDF が差し替えられていれば1ページ目から）
    const pos = memoryOn() ? recallPos(readPosStore(), posKey(name), doc.fingerprints[0], doc.numPages) : null;
    if (pos) {
      pageNum = pos.page;
      zoom = pos.zoom;
    }
    await renderPage();
    if (pos && my === token) {
      wrap.scrollLeft = pos.sx;
      wrap.scrollTop = pos.sy;
      lastScroll = { sx: wrap.scrollLeft, sy: wrap.scrollTop };
    }
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

// 3×2 表示。フォルダの一覧と同じ順に start 番目から6つを並べ、各ファイルの1ページ目だけを描く
async function showGrid(start) {
  saveCurrentPos();
  const my = ++token;
  cancelLoad();
  dropDoc();
  cancelGrid();
  pinch = null;
  fromGrid = false;
  currentFile = "";
  gridMode = "files";
  gridStart = start;
  setView("grid");
  $("docs-title").textContent = currentLabel;
  const shown = folderFiles.slice(start, start + GRID_SIZE);
  $("grid-range").textContent = `${start + 1}〜${start + shown.length}枚目 / 全${folderFiles.length}枚`;
  $("grid-prev").disabled = start === 0;
  $("grid-next").disabled = start + GRID_SIZE >= folderFiles.length;
  const grid = $("doc-grid");
  const tiles = [];
  for (let i = 0; i < GRID_SIZE; i++) {
    const name = shown[i];
    if (!name) {
      const e = document.createElement("div");
      e.className = "doc-tile empty";
      grid.appendChild(e);
      continue;
    }
    const t = document.createElement("button");
    t.type = "button";
    t.className = "doc-tile";
    const page = document.createElement("div");
    page.className = "tile-page";
    page.textContent = "読み込み中…";
    const cap = document.createElement("div");
    cap.className = "tile-name";
    cap.textContent = name.replace(/\.pdf$/i, "");
    t.append(page, cap);
    t.addEventListener("click", () => openFile(name, true));
    grid.appendChild(t);
    tiles.push([name, page]);
  }
  resetIdle();
  // メモリを抑えるため1つずつ読む。描き終えた文書はすぐ手放し、絵（canvas）だけ残す
  for (const [name, page] of tiles) {
    if (my !== token) return;
    await renderTile(name, page, my);
  }
}

async function renderTile(name, box, my) {
  const { task, promise } = openPdf(pdfUrl(name));
  const job = { task };
  gridJobs.push(job);
  try {
    const d = await promise;
    if (my !== token) return;
    const p = await d.getPage(1);
    if (my !== token) return;
    const base = p.getViewport({ scale: 1 });
    const w = box.clientWidth;
    const h = box.clientHeight;
    if (!w || !h) throw new Error("マスの大きさが0です");
    const vp = p.getViewport({ scale: Math.min(w / base.width, h / base.height) * 0.97 });
    const ratio = Math.min(window.devicePixelRatio || 1,
      Math.sqrt(MAX_CANVAS_PIXELS / GRID_SIZE / (vp.width * vp.height)));
    const c = document.createElement("canvas");
    c.width = Math.max(1, Math.floor(vp.width * ratio));
    c.height = Math.max(1, Math.floor(vp.height * ratio));
    c.style.width = vp.width + "px";
    c.style.height = vp.height + "px";
    const ctx = c.getContext("2d");
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    await p.render({ canvasContext: ctx, viewport: vp }).promise;
    if (my !== token) return;
    box.textContent = "";
    box.appendChild(c);
  } catch (e) {
    if (my !== token) return;
    console.error("文書の表示に失敗しました", name, e);
    box.textContent = FAIL_NOTICE;
  } finally {
    if (job.task) {
      job.task.destroy();
      job.task = null;
    }
  }
}

// 開いている PDF のページを 3×2 で並べる（start 番目のページから6つ）。押したページを1枚で開く
async function showPageGrid(start) {
  if (!doc) return;
  const my = ++token;
  const d = doc;
  cancelGrid();
  pinch = null;
  gridMode = "pages";
  pageGridStart = start;
  setView("grid");
  const end = Math.min(start + GRID_SIZE, d.numPages);
  $("grid-range").textContent = `${start + 1}〜${end}ページ / 全${d.numPages}ページ`;
  $("grid-prev").disabled = start === 0;
  $("grid-next").disabled = end >= d.numPages;
  const grid = $("doc-grid");
  const tiles = [];
  for (let i = 0; i < GRID_SIZE; i++) {
    const n = start + i + 1;
    if (n > d.numPages) {
      const e = document.createElement("div");
      e.className = "doc-tile empty";
      grid.appendChild(e);
      continue;
    }
    const t = document.createElement("button");
    t.type = "button";
    t.className = "doc-tile";
    const page = document.createElement("div");
    page.className = "tile-page";
    page.textContent = "読み込み中…";
    const cap = document.createElement("div");
    cap.className = "tile-name";
    cap.textContent = `${n}ページ`;
    t.append(page, cap);
    t.addEventListener("click", () => showViewerAt(n));
    grid.appendChild(t);
    tiles.push([n, page]);
  }
  resetIdle();
  // 1つずつ描く（読み込み済みの PDF を使うので、サーバーへは取りに行かない）
  for (const [n, page] of tiles) {
    if (my !== token || d !== doc) return;
    await renderPageTile(d, n, page, my);
  }
}

async function renderPageTile(d, n, box, my) {
  try {
    const p = await d.getPage(n);
    if (my !== token) return;
    const base = p.getViewport({ scale: 1 });
    const w = box.clientWidth;
    const h = box.clientHeight;
    if (!w || !h) throw new Error("マスの大きさが0です");
    const vp = p.getViewport({ scale: Math.min(w / base.width, h / base.height) * 0.97 });
    const ratio = Math.min(window.devicePixelRatio || 1,
      Math.sqrt(MAX_CANVAS_PIXELS / GRID_SIZE / (vp.width * vp.height)));
    const c = document.createElement("canvas");
    c.width = Math.max(1, Math.floor(vp.width * ratio));
    c.height = Math.max(1, Math.floor(vp.height * ratio));
    c.style.width = vp.width + "px";
    c.style.height = vp.height + "px";
    const ctx = c.getContext("2d");
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    await p.render({ canvasContext: ctx, viewport: vp }).promise;
    if (my !== token) return;
    box.textContent = "";
    box.appendChild(c);
  } catch (e) {
    if (my !== token) return;
    console.error("文書の表示に失敗しました", n, e);
    box.textContent = FAIL_NOTICE;
  }
}

// 3×2 から、そのページを1枚で開く（読み込み済みの PDF をそのまま使う）
function showViewerAt(n) {
  if (!doc) return;
  token++;
  cancelGrid();
  pageNum = n;
  setView("viewer");
  $("doc-pages-grid").hidden = doc.numPages < 2;
  wrap.scrollTop = 0;
  wrap.scrollLeft = 0;
  lastScroll = { sx: 0, sy: 0 };
  resetIdle();
  redraw();
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
$("docs-back").addEventListener("click", () => {
  if (fromGrid) showGrid(gridStart);
  else openFolder(currentIndex, currentLabel);
});
$("grid-prev").addEventListener("click", () => {
  if (gridMode === "pages") {
    if (pageGridStart > 0) showPageGrid(Math.max(0, pageGridStart - GRID_SIZE));
  } else if (gridStart > 0) showGrid(Math.max(0, gridStart - GRID_SIZE));
});
$("grid-next").addEventListener("click", () => {
  if (gridMode === "pages") {
    if (doc && pageGridStart + GRID_SIZE < doc.numPages) showPageGrid(pageGridStart + GRID_SIZE);
  } else if (gridStart + GRID_SIZE < folderFiles.length) showGrid(gridStart + GRID_SIZE);
});
$("doc-pages-grid").addEventListener("click", () => {
  if (doc) showPageGrid(Math.floor((pageNum - 1) / GRID_SIZE) * GRID_SIZE);
});
$("grid-single").addEventListener("click", () => showViewerAt(pageNum));
wrap.addEventListener("scroll", () => {
  if (!$("doc-viewer").hidden) lastScroll = { sx: wrap.scrollLeft, sy: wrap.scrollTop };
}, { passive: true });

// 設定の「文書のページを覚える」（この端末だけ）
$("btn-gear").addEventListener("click", () => {
  for (const r of document.querySelectorAll('input[name="doc-memory"]')) r.checked = r.value === (memoryOn() ? "on" : "off");
});
for (const r of document.querySelectorAll('input[name="doc-memory"]')) {
  r.addEventListener("change", () => {
    try {
      localStorage.setItem(MEMORY_KEY, r.value === "on" ? "on" : "off");
    } catch (_) {}
  });
}
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
