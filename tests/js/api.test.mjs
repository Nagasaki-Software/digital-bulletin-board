import test from "node:test";
import assert from "node:assert/strict";
import { api } from "../../static/js/api.js";

const realFetch = globalThis.fetch;
test.afterEach(() => {
  globalThis.fetch = realFetch;
});

// signal が中止されたら失敗する、止まったままのリクエスト
function hangingFetch(_url, opts) {
  return new Promise((_resolve, reject) => {
    opts.signal.addEventListener("abort", () => reject(opts.signal.reason));
  });
}

test("a stalled request fails with a plain Japanese message after the timeout", async () => {
  globalThis.fetch = hangingFetch;
  const t = Date.now();
  await assert.rejects(api("GET", "/api/rev", undefined, 50), /サーバーから応答がありません/);
  assert.ok(Date.now() - t < 2000);
});

test("normal response is returned as JSON", async () => {
  globalThis.fetch = async (_url, opts) => {
    assert.ok(opts.signal, "a timeout signal is passed");
    return { ok: true, json: async () => ({ rev: "1" }) };
  };
  assert.deepEqual(await api("GET", "/api/rev"), { rev: "1" });
});

test("server error message is kept", async () => {
  globalThis.fetch = async () => ({ ok: false, statusText: "Bad", json: async () => ({ error: "登録されていません" }) });
  await assert.rejects(api("POST", "/x", {}), /登録されていません/);
});
