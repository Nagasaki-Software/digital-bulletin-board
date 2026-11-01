// 応答が止まったままのリクエストで、更新の確認が永久に止まらないよう、一定時間で打ち切る
const TIMEOUT_MS = 10000;

function timeoutSignal(ms) {
  if (typeof AbortSignal !== "undefined" && typeof AbortSignal.timeout === "function") return AbortSignal.timeout(ms);
  const c = new AbortController();
  setTimeout(() => c.abort(), ms);
  return c.signal;
}

// 管理者キーは HTTP の見出しに載せるので、半角の英数字・記号だけ（それ以外だと fetch が例外になる）
export function isAsciiKey(key) {
  return typeof key === "string" && /^[ -~]*$/.test(key);
}

export async function api(method, url, body, timeoutMs = TIMEOUT_MS, extraHeaders = {}) {
  let res;
  try {
    res = await fetch(url, {
      method,
      headers: { ...(body !== undefined ? { "Content-Type": "application/json" } : {}), ...extraHeaders },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: timeoutSignal(timeoutMs),
    });
  } catch (e) {
    if (e && (e.name === "TimeoutError" || e.name === "AbortError")) throw new Error("サーバーから応答がありません");
    throw e;
  }
  if (!res.ok) {
    let message = res.statusText;
    try {
      message = (await res.json()).error || message;
    } catch (_) {}
    const err = new Error(message);
    err.status = res.status;
    throw err;
  }
  return res.json();
}
