import { setTheme, getTheme } from "./theme.js";
import { resolveEditMode } from "./timeutil.mjs";

const KEY = "dbb.editButton";
const $ = id => document.getElementById(id);

let mode = "off";
let stored = null; // このパソコンで選んだ値（無ければ null）
let serverDefault = "off"; // config.json の default_edit_button
let editing = false;
let timer = null;
let lockSeconds = 60;

function readStored() {
  try {
    const v = localStorage.getItem(KEY);
    return v === "on" || v === "off" ? v : null;
  } catch (_) {
    return null;
  }
}

function writeMode(m) {
  try {
    localStorage.setItem(KEY, m);
  } catch (_) {}
}

export function isEditable() {
  return mode === "off" || editing;
}

// 画面を取得するたびに呼ばれる。このパソコンで選んだ値が無いときだけ、サーバーの既定に従う
export function setDefaultEditButton(v) {
  serverDefault = v;
  const next = resolveEditMode(stored, serverDefault);
  if (next === mode) return;
  mode = next;
  editing = false;
  apply();
}

export function setLockSeconds(s) {
  const n = Number(s);
  if (n > 0) lockSeconds = n;
}

function apply() {
  clearTimeout(timer);
  timer = null;
  document.body.classList.toggle("locked", !isEditable());
  const b = $("btn-edit");
  b.hidden = mode !== "on";
  $("btn-edit-label").textContent = editing ? "完了" : "編集";
  if (editing) {
    timer = setTimeout(() => {
      editing = false;
      apply();
    }, lockSeconds * 1000);
  }
}

function openSettings() {
  for (const r of document.querySelectorAll('input[name="edit-button"]')) r.checked = r.value === mode;
  for (const r of document.querySelectorAll('input[name="theme"]')) r.checked = r.value === getTheme();
  $("settings").hidden = false;
}

export function initLock() {
  stored = readStored();
  mode = resolveEditMode(stored, serverDefault);
  $("btn-edit").addEventListener("click", () => {
    editing = !editing;
    apply();
  });
  // 編集中に画面を触る・キーを打つたびに、自動で閲覧に戻るまでの時間を数え直す
  const touched = () => {
    if (editing) apply();
  };
  document.addEventListener("pointerdown", touched, true);
  document.addEventListener("keydown", touched, true);
  $("btn-gear").addEventListener("click", openSettings);
  $("settings-close").addEventListener("click", () => {
    $("settings").hidden = true;
  });
  for (const r of document.querySelectorAll('input[name="edit-button"]')) {
    r.addEventListener("change", () => {
      mode = r.value === "on" ? "on" : "off";
      stored = mode;
      writeMode(mode);
      editing = false;
      apply();
    });
  }
  for (const r of document.querySelectorAll('input[name="theme"]')) {
    r.addEventListener("change", () => setTheme(r.value));
  }
  apply();
}
