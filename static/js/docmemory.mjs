// 文書（PDF）ごとに、最後に見ていたページ・拡大率・位置を覚える（この端末だけ。documents.js が localStorage に入れる）。
// fp は PDF の指紋（PDF.js の fingerprints[0]）。同じ名前で差し替えられた PDF は指紋が変わるので、1ページ目から始める。
export const MAX_REMEMBERED = 100; // 覚える文書の数の上限。古いものから忘れる

const num = (v, fallback) => (typeof v === "number" && Number.isFinite(v) ? v : fallback);

export function rememberPos(store, key, { fp, page, zoom, sx, sy }) {
  const out = { ...(store || {}) };
  delete out[key]; // 覚え直したものを、いちばん新しい扱いにする（キーの並び順が古い順）
  out[key] = { fp, page, zoom, sx, sy };
  const keys = Object.keys(out);
  for (let i = 0; i < keys.length - MAX_REMEMBERED; i++) delete out[keys[i]];
  return out;
}

export function recallPos(store, key, fp, numPages) {
  const r = store && store[key];
  if (!r || r.fp !== fp) return null;
  return {
    page: Math.min(Math.max(1, Math.round(num(r.page, 1))), Math.max(1, numPages)),
    zoom: Math.min(5, Math.max(0.5, num(r.zoom, 1))),
    sx: Math.max(0, num(r.sx, 0)),
    sy: Math.max(0, num(r.sy, 0)),
  };
}
