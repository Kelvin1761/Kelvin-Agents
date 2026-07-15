import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";


async function loadModule(relativePath) {
  const source = fs.readFileSync(new URL(relativePath, import.meta.url), "utf8");
  const url = `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`;
  return import(url);
}


function memoryKv(initial = {}) {
  const values = new Map(Object.entries(initial));
  return {
    get: async (key) => values.get(key) ?? null,
    put: async (key, value) => values.set(key, String(value)),
    read: (key) => values.get(key),
  };
}


test("sync API rejects a cross-origin browser request", async () => {
  const sync = await loadModule("../functions/api/sync.js");
  const response = await sync.onRequestGet({
    request: new Request("https://dashboard.example/api/sync", {
      headers: { Origin: "https://attacker.example", "Sec-Fetch-Site": "cross-site" },
    }),
    env: { WC_STATE: memoryKv() },
  });

  assert.equal(response.status, 401);
});


test("sync API merges bet records by updatedAt", async () => {
  const sync = await loadModule("../functions/api/sync.js");
  const meeting = "betting_state_2026-07-15_HappyValley";
  const betKey = "bet|2026-07-15|HappyValley|1|3";
  const kv = memoryKv({
    GLOBAL_BETS: JSON.stringify({ [meeting]: { [betKey]: { odds: 2, updatedAt: 200 } } }),
  });
  const response = await sync.onRequestPost({
    request: new Request("https://dashboard.example/api/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Sec-Fetch-Site": "same-origin" },
      body: JSON.stringify({ [meeting]: { [betKey]: { odds: null, updatedAt: 100 } } }),
    }),
    env: { WC_STATE: kv },
  });

  assert.equal(response.status, 200);
  const body = await response.json();
  assert.equal(body.state[meeting][betKey].odds, 2);
  assert.equal(JSON.parse(kv.read("GLOBAL_BETS"))[meeting][betKey].odds, 2);
});


test("configured sync token is required for writes", async () => {
  const sync = await loadModule("../functions/api/sync.js");
  const kv = memoryKv();
  const request = (authorization) => new Request("https://dashboard.example/api/sync", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(authorization ? { Authorization: authorization } : {}),
    },
    body: "{}",
  });

  const rejected = await sync.onRequestPost({
    request: request(),
    env: { WC_STATE: kv, WC_SYNC_TOKEN: "internal-secret" },
  });
  assert.equal(rejected.status, 401);

  const accepted = await sync.onRequestPost({
    request: request("Bearer internal-secret"),
    env: { WC_STATE: kv, WC_SYNC_TOKEN: "internal-secret" },
  });
  assert.equal(accepted.status, 200);
});
