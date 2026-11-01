import test from "node:test";
import assert from "node:assert/strict";
import { api } from "../../static/js/api.js";

const realFetch = globalThis.fetch;
test.afterEach(() => {
  globalThis.fetch = realFetch;
});

test("extra headers are sent together with the JSON content type", async () => {
  let seen;
  globalThis.fetch = async (_url, opts) => {
    seen = opts.headers;
    return { ok: true, json: async () => ({ ok: true }) };
  };
  await api("POST", "/api/admin-settings", { a: 1 }, undefined, { "X-Admin-Key": "k" });
  assert.deepEqual(seen, { "Content-Type": "application/json", "X-Admin-Key": "k" });
});

test("without extra headers nothing else is added", async () => {
  let seen;
  globalThis.fetch = async (_url, opts) => {
    seen = opts.headers;
    return { ok: true, json: async () => ({}) };
  };
  await api("POST", "/x", {});
  assert.deepEqual(seen, { "Content-Type": "application/json" });
  await api("GET", "/x");
  assert.deepEqual(seen, {});
});

test("an error carries the HTTP status and the server message", async () => {
  globalThis.fetch = async () => ({ ok: false, status: 403, statusText: "Forbidden", json: async () => ({ error: "管理者キーが違います" }) });
  await assert.rejects(api("POST", "/x", {}), (e) => e.message === "管理者キーが違います" && e.status === 403);
});

import { isAsciiKey } from "../../static/js/api.js";

test("isAsciiKey: printable ASCII only (a header value with other characters makes fetch throw)", () => {
  for (const ok of ["abc-DEF_123", "Zx9~!", "a b"]) assert.equal(isAsciiKey(ok), true, ok);
  for (const bad of ["管理者キー", "ａｂｃ", "key\n", "kéy", "a\tb", "\u007f"]) assert.equal(isAsciiKey(bad), false, JSON.stringify(bad));
  for (const v of [null, undefined, 5, {}]) assert.equal(isAsciiKey(v), false, String(v));
});
