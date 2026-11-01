import * as pdfjsLib from "/pdfjs/pdf.mjs";

pdfjsLib.GlobalWorkerOptions.workerSrc = "/pdfjs/pdf.worker.mjs";

const frame = document.getElementById("accident-frame");
const canvas = document.getElementById("accident-canvas");
const msg = document.getElementById("accident-msg");
const tag = document.getElementById("accident-tag");
const count = document.getElementById("accident-count");
const bar = document.getElementById("accident-bar");
const barFill = document.getElementById("accident-bar-fill");

let list = [];
let listKey = null;
let seconds = 15;
let fileIdx = 0;
let pageNum = 1;
let doc = null;
let timer = null;
let advancing = false; // いまのスライドが「次へ進むまでの秒数」を数えている最中か
let paused = false;
let token = 0;
let renderTask = null;
let loadTask = null;
const LOAD_TIMEOUT_MS = 20000;
const FAIL_NOTICE = "この資料は表示できません";

// 設定の表示秒数が変わったときだけ、表示中のスライドの数え直しをする（長い秒数から短くしても古い秒数を待たない）。同じ値なら何もしない
export function setSeconds(s) {
  const n = Number(s);
  if (!(n > 0) || n === seconds) return;
  seconds = n;
  if (advancing && !paused) {
    clearTimeout(timer);
    restartBar();
    timer = setTimeout(() => step(1), seconds * 1000);
  }
}

export function pause() {
  paused = true;
  advancing = false;
  clearTimeout(timer);
  barFill.style.transition = "none";
  barFill.style.width = "0";
}

export function resume() {
  if (!paused) return;
  paused = false;
  if (list.length) show();
}

// 読み込み中の PDF.js の作業（ワーカー）を止める。getDocument は失敗しても自分では片付けない
function cancelLoad() {
  if (loadTask) {
    loadTask.destroy();
    loadTask = null;
  }
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

function dropDoc() {
  if (doc) {
    doc.destroy();
    doc = null;
  }
}

export function setPlaylist(files, emptyMessage) {
  const key = JSON.stringify(files.map(f => f.name)) + "|" + emptyMessage;
  if (key === listKey) return;
  listKey = key;
  list = files;
  fileIdx = 0;
  pageNum = 1;
  dropDoc();
  cancelLoad();
  clearTimeout(timer);
  advancing = false;
  token++;
  if (!files.length) {
    canvas.hidden = true;
    tag.hidden = true;
    count.hidden = true;
    bar.hidden = true;
    msg.hidden = false;
    msg.textContent = emptyMessage;
    return;
  }
  canvas.hidden = false;
  tag.hidden = false;
  count.hidden = false;
  bar.hidden = false;
  msg.hidden = true;
  if (!paused) show();
}

async function show() {
  clearTimeout(timer);
  advancing = false;
  const my = ++token;
  cancelLoad();
  if (!frame.clientWidth || !frame.clientHeight) {
    // 枠がまだ見えていない（大きさ0）。少し待って出し直す
    if (!paused) timer = setTimeout(show, 1000);
    return;
  }
  try {
    if (!doc) {
      const loaded = await loadDoc(list[fileIdx].url);
      if (my !== token) {
        // 読み込み中に別の表示へ切り替わった。後から届いた分は捨てる（失敗側は切替時の cancelLoad で止まっている）
        loaded.destroy();
        return;
      }
      loadTask = null;
      doc = loaded;
    }
    pageNum = Math.min(Math.max(pageNum, 1), doc.numPages);
    const page = await doc.getPage(pageNum);
    if (my !== token) return;
    const base = page.getViewport({ scale: 1 });
    const scale = Math.min(frame.clientWidth / base.width, frame.clientHeight / base.height);
    const vp = page.getViewport({ scale });
    const dpr = window.devicePixelRatio || 1;
    canvas.width = vp.width * dpr;
    canvas.height = vp.height * dpr;
    canvas.style.width = vp.width + "px";
    canvas.style.height = vp.height + "px";
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (renderTask) renderTask.cancel();
    renderTask = page.render({ canvasContext: ctx, viewport: vp });
    await renderTask.promise;
    if (my === token) {
      msg.hidden = true;
      canvas.hidden = false;
      updateOverlay();
    }
  } catch (e) {
    if (my !== token || (e && e.name === "RenderingCancelledException")) return;
    console.error("災害事例の表示に失敗しました", e);
    cancelLoad();
    dropDoc();
    canvas.hidden = true;
    msg.hidden = false;
    msg.textContent = FAIL_NOTICE;
    updateOverlay();
    if (!paused) timer = setTimeout(() => step(1), 3000);
    return;
  }
  if (my === token && !paused) {
    restartBar();
    advancing = true;
    timer = setTimeout(() => step(1), seconds * 1000);
  }
}

// 枠の左上にジャンル名、右下に「何件目／全部で何件」、下に次へ進むまでの進み具合を出す
function updateOverlay() {
  const f = list[fileIdx];
  tag.textContent = f.name.split("_")[0];
  count.textContent = `${fileIdx + 1} / ${list.length}`;
}

function restartBar() {
  barFill.style.transition = "none";
  barFill.style.width = "0";
  void barFill.offsetWidth;
  barFill.style.transition = `width ${seconds}s linear`;
  barFill.style.width = "100%";
}

function step(dir) {
  if (!list.length) return;
  if (dir > 0) {
    if (doc && pageNum < doc.numPages) {
      pageNum++;
    } else {
      // 一周して同じファイルに戻る場合も読み直す（同名で差し替えられた PDF を反映するため）
      dropDoc();
      fileIdx = (fileIdx + 1) % list.length;
      pageNum = 1;
    }
  } else if (pageNum > 1) {
    pageNum--;
  } else {
    dropDoc();
    fileIdx = (fileIdx - 1 + list.length) % list.length;
    pageNum = Number.MAX_SAFE_INTEGER;
  }
  show();
}

// 操作の判定：左右に60px以上動かしたらスワイプ、ほぼ動かず短く押したらタップ。縦に動いた・長押し・右クリックは無視
const TAP_MOVE = 20;
const TAP_MS = 600;
let down = null;
frame.addEventListener("pointerdown", e => {
  if (!e.isPrimary || e.button !== 0) return;
  down = { x: e.clientX, y: e.clientY, t: Date.now() };
});
frame.addEventListener("pointercancel", () => {
  down = null;
});
frame.addEventListener("pointerup", e => {
  if (!down || !e.isPrimary || e.button !== 0) return;
  const dx = e.clientX - down.x;
  const dy = e.clientY - down.y;
  const dt = Date.now() - down.t;
  down = null;
  if (Math.abs(dy) > Math.abs(dx)) return;
  if (Math.abs(dx) > 60) {
    step(dx < 0 ? 1 : -1);
  } else if (Math.abs(dx) <= TAP_MOVE && Math.abs(dy) <= TAP_MOVE && dt <= TAP_MS) {
    const r = frame.getBoundingClientRect();
    step(e.clientX > r.left + r.width / 2 ? 1 : -1);
  }
});

let resizeTimer = null;
window.addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => {
    if (list.length && !paused) show();
  }, 300);
});
