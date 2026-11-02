import * as pdfjsLib from "/pdfjs/pdf.mjs";
import { api } from "./api.js";
import { pickOption, confirmBox, alertBox } from "./picker.js";
import { createStayTimer } from "./links.js";
import { COLORS, WIDTHS, TEXT_SIZES, ERASER_SCALE, createHistory, normRect, arrowHead, thin, formatStamp } from "./whiteboard-core.mjs";

pdfjsLib.GlobalWorkerOptions.workerSrc = "/pdfjs/pdf.worker.mjs";

const $ = id => document.getElementById(id);
const MAX_RATIO = 2; // 描画用の細かさ（画面の細かさの上限）
const MAX_PIXELS = 16e6;
const JPEG_QUALITY = 0.92;
const SAVE_TIMEOUT_MS = 120000;
const LOAD_TIMEOUT_MS = 20000;
const MAX_PAGES = 50; // サーバー（whiteboard.py）の上限と同じ
const NO_BACKGROUND = "__none__";
const FONT = '"Meiryo", "メイリオ", "Yu Gothic UI", sans-serif';

let idleSeconds = 180;
let isOpen = false;
let busy = false; // 保存中
let hooks = { onOpen() {}, onClose() {} };
let tool = "pen";
let color = COLORS[0];
let widthIdx = 1;
// ページごとの記録。背景は pdf のページ番号（pageNo）か写真（img）。page は PDF のページを読み込んだもの
let pages = [newPage(0, null)];
let cur = 0;
let saved = true; // 開いた直後、または最後の保存のあとに描き足していない
let bgDoc = null;
let bgName = "";
let bgTask = null;
let ratio = 1;
let cssW = 1;
let cssH = 1;
let drag = null; // 描いている最中の指（1本だけ見る）: { id, start, last, points }
let textAt = null; // 文字入力中の場所: { x, y, size, color }
let lastActivity = 0;

function newPage(pageNo, img, history = createHistory()) {
  return { history, pageNo, img, page: null };
}

const H = () => pages[cur].history;
const anyInk = () => pages.some(p => p.history.hasInk());

const stage = $("wb-stage");
const bgCanvas = $("wb-bg-canvas");
const ink = $("wb-ink");
const preview = $("wb-preview");

export function isWhiteboardOpen() {
  return isOpen;
}

export function setWhiteboardIdle(seconds) {
  const n = Number(seconds);
  if (Number.isFinite(n) && n >= 30) idleSeconds = n;
}

// ---- 操作なしで戻る（30秒前に警告 → 描いてあれば自動保存して戻る） ----
const timer = createStayTimer({
  onWarn: () => {
    $("wb-warn").hidden = false;
  },
  onExpire: autoReturn,
});

async function autoReturn() {
  if (!isOpen) return;
  if (busy) {
    timer.start(idleSeconds);
    return;
  }
  commitText();
  if (anyInk() && !saved) {
    try {
      await doSave(true);
    } catch (e) {
      // 保存できないときは戻らない（描いたものを失わない）
      $("wb-warn").hidden = true;
      say("自動保存できませんでした: " + e.message + "。保存先を確かめてください", true);
      timer.start(idleSeconds);
      return;
    }
  }
  closeWhiteboard();
}

function onActivity() {
  if (!isOpen) return;
  lastActivity = Date.now();
  $("wb-warn").hidden = true;
  timer.start(idleSeconds);
}

// ---- 画面の知らせ ----
function say(text, error = false) {
  const box = $("wb-msg");
  box.textContent = text ? (error ? "⚠ " : "") + text : "";
  box.classList.toggle("error", !!text && error);
  box.hidden = !text;
}

// ---- 描画 ----
function ctxOf(canvas) {
  const x = canvas.getContext("2d");
  x.setTransform(ratio, 0, 0, ratio, 0, 0);
  return x;
}

function strokePath(ctx, pts) {
  if (pts.length === 0) return;
  if (pts.length === 1) {
    ctx.beginPath();
    ctx.arc(pts[0][0], pts[0][1], ctx.lineWidth / 2, 0, Math.PI * 2);
    ctx.fill();
    return;
  }
  ctx.beginPath();
  ctx.moveTo(pts[0][0], pts[0][1]);
  for (let i = 1; i < pts.length - 1; i++) {
    const mx = (pts[i][0] + pts[i + 1][0]) / 2;
    const my = (pts[i][1] + pts[i + 1][1]) / 2;
    ctx.quadraticCurveTo(pts[i][0], pts[i][1], mx, my);
  }
  const last = pts[pts.length - 1];
  ctx.lineTo(last[0], last[1]);
  ctx.stroke();
}

function drawOp(ctx, op) {
  if (op.type === "clear") return;
  ctx.save();
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.strokeStyle = op.color;
  ctx.fillStyle = op.color;
  ctx.lineWidth = op.width;
  switch (op.type) {
    case "pen":
      strokePath(ctx, op.points);
      break;
    case "erase":
      ctx.globalCompositeOperation = "destination-out"; // 描いた層だけを消す（背景のPDFは別の層）
      ctx.lineWidth = op.width * ERASER_SCALE;
      strokePath(ctx, op.points);
      break;
    case "line":
    case "arrow":
      ctx.beginPath();
      ctx.moveTo(op.x1, op.y1);
      ctx.lineTo(op.x2, op.y2);
      if (op.type === "arrow") {
        for (const [hx, hy] of arrowHead(op.x1, op.y1, op.x2, op.y2, op.width)) {
          ctx.moveTo(op.x2, op.y2);
          ctx.lineTo(hx, hy);
        }
      }
      ctx.stroke();
      break;
    case "rect":
      ctx.strokeRect(op.x, op.y, op.w, op.h);
      break;
    case "ellipse":
      ctx.beginPath();
      ctx.ellipse(op.x + op.w / 2, op.y + op.h / 2, Math.max(op.w / 2, 0.5), Math.max(op.h / 2, 0.5), 0, 0, Math.PI * 2);
      ctx.stroke();
      break;
    case "text":
      ctx.font = `${op.size}px ${FONT}`;
      ctx.textBaseline = "top";
      ctx.fillText(op.text, op.x, op.y);
      break;
  }
  ctx.restore();
}

function replay() {
  const ctx = ctxOf(ink);
  ctx.clearRect(0, 0, cssW, cssH);
  for (const op of H().visible()) drawOp(ctx, op);
}

function sizeCanvases() {
  cssW = Math.max(1, Math.floor(stage.clientWidth));
  cssH = Math.max(1, Math.floor(stage.clientHeight));
  ratio = Math.min(window.devicePixelRatio || 1, MAX_RATIO, Math.sqrt(MAX_PIXELS / (cssW * cssH)));
  for (const c of [bgCanvas, ink, preview]) {
    c.width = Math.max(1, Math.floor(cssW * ratio));
    c.height = Math.max(1, Math.floor(cssH * ratio));
    c.style.width = cssW + "px";
    c.style.height = cssH + "px";
  }
}

// pg の背景を canvas に描く。track=true は画面用（途中で別のページに替わったら描きかけをやめられる）
async function drawBackground(canvas, pg, track) {
  const ctx = canvas.getContext("2d");
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.fillStyle = "#FFFFFF";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  if (pg.img) {
    const fit = Math.min(canvas.width / pg.img.naturalWidth, canvas.height / pg.img.naturalHeight);
    const w = pg.img.naturalWidth * fit;
    const h = pg.img.naturalHeight * fit;
    ctx.drawImage(pg.img, (canvas.width - w) / 2, (canvas.height - h) / 2, w, h);
    return;
  }
  if (!bgDoc || !pg.pageNo) return;
  if (!pg.page) pg.page = await bgDoc.getPage(pg.pageNo);
  const page = pg.page;
  const base = page.getViewport({ scale: 1 });
  const fit = Math.min(canvas.width / base.width, canvas.height / base.height);
  const vp = page.getViewport({ scale: fit });
  const ox = (canvas.width - vp.width) / 2;
  const oy = (canvas.height - vp.height) / 2;
  const task = page.render({ canvasContext: ctx, viewport: vp, transform: [1, 0, 0, 1, ox, oy] });
  if (track) bgTask = task;
  try {
    await task.promise;
  } catch (e) {
    if (!(e && e.name === "RenderingCancelledException")) throw e;
  } finally {
    if (bgTask === task) bgTask = null;
  }
}

async function renderBackground() {
  if (bgTask) {
    bgTask.cancel();
    bgTask = null;
  }
  await drawBackground(bgCanvas, pages[cur], true);
}

function updatePager() {
  $("wb-pages").hidden = pages.length <= 1;
  $("wb-pageno").textContent = `${cur + 1} / ${pages.length}`;
  $("wb-prev").disabled = cur === 0;
  $("wb-next").disabled = cur === pages.length - 1;
}

function gotoPage(n) {
  if (n < 0 || n >= pages.length || n === cur) return;
  commitText();
  drag = null;
  ctxOf(preview).clearRect(0, 0, cssW, cssH);
  cur = n;
  replay();
  syncButtons();
  updatePager();
  renderBackground().catch(() => say("背景を表示できません", true));
}

function relayout() {
  if (!isOpen) return;
  commitText();
  sizeCanvases();
  replay();
  renderBackground().catch(() => say("背景を表示できません", true));
}

// ---- 道具の選択 ----
function syncButtons() {
  for (const b of document.querySelectorAll(".wb-tool")) b.classList.toggle("current", b.dataset.tool === tool);
  for (const b of document.querySelectorAll(".wb-width")) b.classList.toggle("current", Number(b.dataset.width) === widthIdx);
  for (const b of document.querySelectorAll(".wb-color")) b.classList.toggle("current", b.dataset.color === color);
  $("wb-undo").disabled = !H().canUndo();
  $("wb-redo").disabled = !H().canRedo();
  $("wb-clear").disabled = H().visible().length === 0;
}

function record(op) {
  H().push(op);
  saved = false;
  syncButtons();
}

// ---- 文字 ----
function startText([x, y]) {
  commitText();
  const input = $("wb-text");
  const size = TEXT_SIZES[widthIdx];
  textAt = { x, y, size, color };
  input.style.left = x + "px";
  input.style.top = y + "px";
  input.style.fontSize = size + "px";
  input.style.color = color;
  input.value = "";
  input.hidden = false;
  setTimeout(() => input.focus(), 0);
}

function commitText() {
  const input = $("wb-text");
  if (input.hidden || !textAt) return;
  const at = textAt;
  const text = input.value.trim();
  textAt = null;
  input.hidden = true;
  if (!text) return;
  const op = { type: "text", color: at.color, size: at.size, x: at.x, y: at.y, text };
  record(op);
  drawOp(ctxOf(ink), op);
}

$("wb-text").addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.isComposing) {
    e.preventDefault();
    commitText();
  } else if (e.key === "Escape") {
    textAt = null;
    $("wb-text").hidden = true;
  }
});
$("wb-text").addEventListener("blur", commitText);

// ---- 指・ペンの動き ----
const pos = e => {
  const r = stage.getBoundingClientRect();
  return [e.clientX - r.left, e.clientY - r.top];
};

function currentOp() {
  const w = WIDTHS[widthIdx];
  const [x1, y1] = drag.start;
  const [x2, y2] = drag.last;
  switch (tool) {
    case "pen":
      return { type: "pen", color, width: w, points: thin(drag.points) };
    case "eraser":
      return { type: "erase", color, width: w, points: thin(drag.points) };
    case "line":
    case "arrow":
      return Math.hypot(x2 - x1, y2 - y1) < 3 ? null : { type: tool, color, width: w, x1, y1, x2, y2 };
    case "rect":
    case "ellipse": {
      const r = normRect(x1, y1, x2, y2);
      return r.w < 3 && r.h < 3 ? null : { type: tool, color, width: w, ...r };
    }
  }
  return null;
}

stage.addEventListener("pointerdown", e => {
  if (!isOpen || busy || drag) return; // 2本目の指・保存中は見ない
  if (e.pointerType === "mouse" && e.button !== 0) return;
  const p = pos(e);
  if (tool === "text") {
    e.preventDefault();
    startText(p);
    return;
  }
  if (tool === "date") {
    e.preventDefault();
    commitText();
    const op = { type: "text", color, size: TEXT_SIZES[widthIdx], x: p[0], y: p[1], text: formatStamp(new Date()) };
    record(op);
    drawOp(ctxOf(ink), op);
    return;
  }
  commitText();
  stage.setPointerCapture(e.pointerId);
  drag = { id: e.pointerId, start: p, last: p, points: [p] };
  if (tool === "pen" || tool === "eraser") {
    drawOp(ctxOf(ink), { type: tool === "pen" ? "pen" : "erase", color, width: WIDTHS[widthIdx], points: [p] });
  }
});

stage.addEventListener("pointermove", e => {
  if (!drag || e.pointerId !== drag.id) return;
  if (Date.now() - lastActivity > 1000) onActivity(); // 長い1画の途中で「操作なし」にならないように
  const p = pos(e);
  drag.last = p;
  if (tool === "pen" || tool === "eraser") {
    const prev = drag.points[drag.points.length - 1];
    if (Math.hypot(p[0] - prev[0], p[1] - prev[1]) < 1.5) return;
    drag.points.push(p);
    drawOp(ctxOf(ink), { type: tool === "pen" ? "pen" : "erase", color, width: WIDTHS[widthIdx], points: drag.points.slice(-3) });
  } else {
    const ctx = ctxOf(preview);
    ctx.clearRect(0, 0, cssW, cssH);
    const op = currentOp();
    if (op) drawOp(ctx, op);
  }
});

function endDrag(e, commit) {
  if (!drag || e.pointerId !== drag.id) return;
  const op = commit ? currentOp() : null;
  drag = null;
  ctxOf(preview).clearRect(0, 0, cssW, cssH);
  if (op) record(op);
  replay(); // 画面を記録どおりに描き直す（途中の線の細かな差を消す）
}
stage.addEventListener("pointerup", e => endDrag(e, true));
stage.addEventListener("pointercancel", e => endDrag(e, false));

// ---- 背景のPDF ----
async function loadPdf(url) {
  const task = pdfjsLib.getDocument({ url, cMapUrl: "/pdfjs/cmaps/", cMapPacked: true });
  let tid;
  const timeout = new Promise((_, reject) => {
    tid = setTimeout(() => {
      task.destroy();
      reject(new Error("読み込みがタイムアウトしました"));
    }, LOAD_TIMEOUT_MS);
  });
  try {
    return await Promise.race([task.promise, timeout]);
  } finally {
    clearTimeout(tid);
  }
}

function dropBackground() {
  if (bgTask) {
    bgTask.cancel();
    bgTask = null;
  }
  bgName = "";
  if (bgDoc) {
    bgDoc.destroy();
    bgDoc = null;
  }
}

// 新しい背景に替える。ページ数が変わって描いた内容を捨てることになるときは、確かめる。替えたら true
async function adoptBackground({ doc = null, img = null, name = "", count = 1 }) {
  const keep = count === 1 && pages.length === 1 ? pages[0].history : null; // 1ページ→1ページなら、描いたものは残す
  if (!keep && anyInk() && !saved) {
    const ok = await confirmBox("背景を替えると、描いた内容は消えます。替えますか？", "替える");
    if (!ok) {
      if (doc) doc.destroy();
      return false;
    }
    saved = true;
  }
  if (!keep) saved = true; // 捨てる内容は保存済みか、いま捨てると決めたもの
  commitText();
  dropBackground();
  bgDoc = doc;
  bgName = name;
  pages = Array.from({ length: count }, (_, i) => newPage(doc ? i + 1 : 0, img, i === 0 && keep ? keep : createHistory()));
  cur = 0;
  replay();
  syncButtons();
  updatePager();
  await renderBackground();
  return true;
}

function loadImage(url) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const tid = setTimeout(() => {
      img.src = "";
      reject(new Error("読み込みがタイムアウトしました"));
    }, LOAD_TIMEOUT_MS);
    img.onload = () => {
      clearTimeout(tid);
      resolve(img);
    };
    img.onerror = () => {
      clearTimeout(tid);
      reject(new Error("画像を開けません"));
    };
    img.src = url;
  });
}

const enc = encodeURIComponent;
// kind ごとの一覧・ファイルの場所と、選ぶ窓の文言
const SOURCES = {
  pdf: { list: "/api/whiteboard/pdfs", file: n => `/api/whiteboard/pdf/${enc(n)}`, title: "背景にするPDF", empty: "背景用のフォルダにPDFがありません" },
  photo: { list: "/api/whiteboard/images", file: n => `/api/whiteboard/image/${enc(n)}`, title: "背景にする写真", empty: "背景用のフォルダに写真（jpg・png）がありません", image: true },
  saved: { list: "/api/whiteboard/saved", file: n => `/api/whiteboard/saved/${enc(n)}`, title: "続きを書く保存済みの内容（新しい順）", empty: "保存済みの内容がありません" },
};

async function chooseBackground() {
  const kind = await pickOption({
    title: "背景",
    options: [
      { value: NO_BACKGROUND, label: "背景なし（白紙）" },
      { value: "pdf", label: "PDF" },
      { value: "photo", label: "写真" },
      { value: "saved", label: "保存した内容の続きを書く" },
    ],
    current: bgName ? undefined : NO_BACKGROUND,
    allowClear: false,
  });
  if (kind === undefined) return;
  if (kind === NO_BACKGROUND) {
    await adoptBackground({});
    return;
  }
  const src = SOURCES[kind];
  let names;
  try {
    names = await api("GET", src.list);
  } catch (e) {
    say("一覧を読み込めません: " + e.message, true);
    return;
  }
  if (!names.length) {
    await alertBox(src.empty);
    return;
  }
  const name = await pickOption({
    title: src.title,
    options: names.map(n => ({ value: n, label: n.replace(/\.(pdf|jpe?g|png)$/i, "") })),
    current: bgName,
    allowClear: false,
  });
  if (name === undefined) return;
  say("読み込んでいます…");
  let doc = null;
  try {
    if (src.image) {
      const img = await loadImage(src.file(name));
      await adoptBackground({ img, name });
    } else {
      doc = await loadPdf(src.file(name));
      const count = doc.numPages;
      if (count > MAX_PAGES) {
        doc.destroy();
        say("");
        await alertBox(`ページが多すぎます（${MAX_PAGES}ページまで。このPDFは${count}ページ）`);
        return;
      }
      const d = doc;
      doc = null; // 以降の後始末は adoptBackground に任せる
      await adoptBackground({ doc: d, name, count });
    }
    say("");
  } catch (e) {
    if (doc) doc.destroy();
    say("背景を読み込めません: " + e.message, true);
  }
}

// ---- 保存 ----
// 全ページを、背景＋描いた内容の JPEG（base64）にして、順に返す
async function compositeAll() {
  const out = [];
  const comp = document.createElement("canvas");
  const layer = document.createElement("canvas");
  comp.width = layer.width = bgCanvas.width;
  comp.height = layer.height = bgCanvas.height;
  for (const pg of pages) {
    await drawBackground(comp, pg, false);
    const lctx = layer.getContext("2d");
    lctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    lctx.clearRect(0, 0, cssW, cssH);
    for (const op of pg.history.visible()) drawOp(lctx, op);
    comp.getContext("2d").drawImage(layer, 0, 0);
    out.push(comp.toDataURL("image/jpeg", JPEG_QUALITY).split(",")[1]);
  }
  return out;
}

async function doSave(auto) {
  commitText();
  busy = true;
  $("wb-save").disabled = true;
  try {
    const r = await api("POST", "/api/whiteboard/save", { images: await compositeAll(), auto }, SAVE_TIMEOUT_MS);
    saved = true;
    return r;
  } finally {
    busy = false;
    $("wb-save").disabled = false;
  }
}

// ---- 開く・閉じる ----
function openWhiteboard() {
  if (isOpen) return;
  isOpen = true;
  hooks.onOpen();
  pages = [newPage(0, null)];
  cur = 0;
  updatePager();
  saved = true;
  drag = null;
  textAt = null;
  $("wb-text").hidden = true;
  say("");
  $("wb-warn").hidden = true;
  $("whiteboard").hidden = false;
  sizeCanvases();
  replay();
  syncButtons();
  renderBackground().catch(() => {});
  lastActivity = Date.now();
  timer.start(idleSeconds);
}

export function closeWhiteboard(resume = true) {
  if (!isOpen) return;
  isOpen = false;
  timer.stop();
  drag = null;
  textAt = null;
  $("wb-text").hidden = true;
  $("wb-warn").hidden = true;
  $("whiteboard").hidden = true;
  dropBackground();
  pages = [newPage(0, null)];
  cur = 0;
  for (const c of [bgCanvas, ink, preview]) {
    c.width = 0;
    c.height = 0;
  }
  if (resume) hooks.onClose();
}

async function requestClose() {
  commitText();
  if (anyInk() && !saved) {
    const ok = await confirmBox("保存しないで閉じますか？ 描いた内容は消えます。", "閉じる");
    if (!ok) return;
  }
  closeWhiteboard();
}

export function initWhiteboard({ onOpen, onClose }) {
  hooks = { onOpen, onClose };
  const box = $("wb-colors");
  for (const c of COLORS) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "wb-color";
    b.dataset.color = c;
    b.style.background = c;
    b.setAttribute("aria-label", "色 " + c);
    b.addEventListener("click", () => {
      color = c;
      syncButtons();
    });
    box.appendChild(b);
  }
  for (const b of document.querySelectorAll(".wb-tool")) {
    b.addEventListener("click", () => {
      commitText();
      tool = b.dataset.tool;
      syncButtons();
    });
  }
  for (const b of document.querySelectorAll(".wb-width")) {
    b.addEventListener("click", () => {
      widthIdx = Number(b.dataset.width);
      syncButtons();
    });
  }
  const history_ = fn => () => {
    commitText();
    if (fn()) {
      saved = false;
      replay();
      syncButtons();
    }
  };
  $("wb-undo").addEventListener("click", history_(() => H().undo()));
  $("wb-redo").addEventListener("click", history_(() => H().redo()));
  $("wb-clear").addEventListener("click", history_(() => H().clear()));
  $("wb-bg").addEventListener("click", chooseBackground);
  $("wb-prev").addEventListener("click", () => gotoPage(cur - 1));
  $("wb-next").addEventListener("click", () => gotoPage(cur + 1));
  $("wb-save").addEventListener("click", async () => {
    if (busy) return;
    say("保存しています…");
    try {
      const r = await doSave(false);
      say(`保存しました（${r.name}）`);
    } catch (e) {
      say("保存できませんでした: " + e.message, true);
    }
  });
  $("wb-close").addEventListener("click", requestClose);
  $("wb-continue").addEventListener("click", onActivity);
  $("wb-open").addEventListener("click", openWhiteboard);
  for (const ev of ["pointerdown", "keydown", "touchstart"]) {
    document.addEventListener(ev, onActivity, { capture: true, passive: true });
  }
  let resizeTimer = null;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(relayout, 200);
  });
}
