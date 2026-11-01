const KEY = "dbb.theme";
let defaultTheme = "light";

function read() {
  try {
    const v = localStorage.getItem(KEY);
    return v === "dark" || v === "light" ? v : null;
  } catch (_) {
    return null;
  }
}

let chosen = read();

function apply() {
  document.documentElement.dataset.theme = chosen || defaultTheme;
}

export function getTheme() {
  return chosen || defaultTheme;
}

export function setTheme(t) {
  chosen = t === "dark" ? "dark" : "light";
  try {
    localStorage.setItem(KEY, chosen);
  } catch (_) {}
  apply();
}

// 端末で選んでいなければ、サーバーの既定（config.json の default_theme）に従う
export function setDefaultTheme(t) {
  defaultTheme = t === "dark" ? "dark" : "light";
  apply();
}

export function initTheme() {
  apply();
}
