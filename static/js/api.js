// 応答が止まったままのリクエストで、更新の確認が永久に止まらないよう、一定時間で打ち切る
const TIMEOUT_MS = 10000;

function timeoutSignal(ms) {
  if (typeof AbortSignal !== "undefined" && typeof AbortSignal.timeout === "function") return AbortSignal.timeout(ms);
  const c = new AbortController();
  setTimeout(() => c.abort(), ms);
  return c.signal;
}

export async function api(method, url, body, timeoutMs = TIMEOUT_MS) {
  let res;
  try {
    res = await fetch(url, {
      method,
      headers: body !== undefined ? { "Content-Type": "application/json" } : {},
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
    throw new Error(message);
  }
  return res.json();
}
