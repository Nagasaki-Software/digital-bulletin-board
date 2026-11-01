import { formatClock } from "./timeutil.mjs";

// 日付の右に「HH:MM」を出す。このパソコンの時計を読むだけで、サーバーには問い合わせない
export function initClock() {
  const box = document.getElementById("clock");
  if (!box) return;
  function tick() {
    const now = new Date();
    const text = formatClock(now);
    if (box.textContent !== text) box.textContent = text;
    // 次の「分」の切り替わりに合わせる。スリープ復帰などでずれても、次の回で直る
    setTimeout(tick, 60000 - (now.getSeconds() * 1000 + now.getMilliseconds()) + 50);
  }
  tick();
}
