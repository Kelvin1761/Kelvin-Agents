import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";


async function loadModule(relativePath) {
  const url = new URL(relativePath, import.meta.url);
  url.searchParams.set("testRun", `${Date.now()}-${Math.random()}`);
  return import(url.href);
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


test("ROI API edits a settled result and recalculates financial fields", async () => {
  const roi = await loadModule("../functions/api/roi.js");
  const key = "2026-07-15|HappyValley|1|3";
  const kv = memoryKv({
    ROI_LEDGER: JSON.stringify({
      [key]: {
        date: "2026-07-15",
        venue: "HappyValley",
        region: "hkjc",
        race_number: 1,
        horse_number: 3,
        horse_name: "Test Horse",
        stake: 1,
        odds: 2.5,
        result_position: null,
        payout: 0,
        net_profit: 0,
        status: "pending",
      },
    }),
  });

  const response = await roi.onRequestPatch({
    request: new Request("https://dashboard.example/api/roi", {
      method: "PATCH",
      headers: { "Content-Type": "application/json", "Sec-Fetch-Site": "same-origin" },
      body: JSON.stringify({
        key,
        updates: { odds: 2.5, result_position: 2, horse_name: "Test Horse" },
      }),
    }),
    env: { WC_STATE: kv },
  });

  assert.equal(response.status, 200);
  const body = await response.json();
  assert.equal(body.record.status, "won");
  assert.equal(body.record.payout, 2.5);
  assert.equal(body.record.net_profit, 1.5);
  assert.equal(JSON.parse(kv.read("ROI_LEDGER"))[key].result_position, 2);
});


test("ROI API delete writes a tombstone so snapshot records stay hidden", async () => {
  const roi = await loadModule("../functions/api/roi.js");
  const key = "2026-07-15|HappyValley|1|3";
  const kv = memoryKv({
    ROI_LEDGER: JSON.stringify({
      [key]: {
        date: "2026-07-15",
        venue: "HappyValley",
        region: "hkjc",
        race_number: 1,
        horse_number: 3,
        horse_name: "Test Horse",
        stake: 1,
        odds: 2.5,
        result_position: 2,
        payout: 2.5,
        net_profit: 1.5,
        status: "won",
      },
    }),
  });

  const response = await roi.onRequestDelete({
    request: new Request("https://dashboard.example/api/roi", {
      method: "DELETE",
      headers: { "Content-Type": "application/json", "Sec-Fetch-Site": "same-origin" },
      body: JSON.stringify({ key }),
    }),
    env: { WC_STATE: kv },
  });

  assert.equal(response.status, 200);
  const stored = JSON.parse(kv.read("ROI_LEDGER"));
  assert.equal(stored[key]._deleted, true);
  assert.equal(stored[key].date, "2026-07-15");
});


test("ROI API can adopt and edit a pre-baked snapshot record", async () => {
  const roi = await loadModule("../functions/api/roi.js");
  const key = "2026-07-15|HappyValley|1|3";
  const baseRecord = {
    date: "2026-07-15",
    venue: "HappyValley",
    region: "hkjc",
    race_number: 1,
    horse_number: 3,
    horse_name: "Snapshot Horse",
    stake: 1,
    odds: 2.5,
    result_position: null,
  };
  const kv = memoryKv();

  const response = await roi.onRequestPatch({
    request: new Request("https://dashboard.example/api/roi", {
      method: "PATCH",
      headers: { "Content-Type": "application/json", "Sec-Fetch-Site": "same-origin" },
      body: JSON.stringify({
        key,
        base_record: baseRecord,
        updates: { result_position: 1 },
      }),
    }),
    env: { WC_STATE: kv },
  });

  assert.equal(response.status, 200);
  const stored = JSON.parse(kv.read("ROI_LEDGER"));
  assert.equal(stored[key].horse_name, "Snapshot Horse");
  assert.equal(stored[key].status, "won");
  assert.equal(stored[key].net_profit, 1.5);
});

test("sports bet API snapshots a recommendation and derives settled profit", async () => {
  const sports = await loadModule("../functions/api/sports-bets.js");
  const kv = memoryKv();
  const response = await sports.onRequestPost({
    request: new Request("https://dashboard.example/api/sports-bets", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Sec-Fetch-Site": "same-origin" },
      body: JSON.stringify({
        id: "tennis-halys-navone-aces",
        sport: "tennis",
        source_id: "tennis-2026-07-23-halys-navone-aces",
        event_date: "2026-07-23",
        event_name: "Quentin Halys vs Mariano Navone",
        market: "Total Aces",
        selection: "Over 5.5",
        odds: 1.7,
        stake: 2,
        status: "won",
        analysis_snapshot: {
          model_probability: 0.7484,
          edge: 0.1531,
        },
      }),
    }),
    env: { WC_STATE: kv },
  });

  assert.equal(response.status, 200);
  const body = await response.json();
  assert.equal(body.record.payout, 3.4);
  assert.equal(body.record.profit, 1.4);
  assert.equal(body.record.analysis_snapshot.edge, 0.1531);
  assert.equal(JSON.parse(kv.read("SPORTS_BET_LEDGER"))[body.record.id].selection, "Over 5.5");
});

test("sports bet API edits and tombstones a record without changing its analysis snapshot", async () => {
  const sports = await loadModule("../functions/api/sports-bets.js");
  const id = "nba-brunson-25";
  const original = {
    id,
    sport: "nba",
    source_id: "nba-nyk-atl-brunson-25",
    event_date: "2026-04-24",
    event_name: "NYK @ ATL",
    market: "Player Points",
    selection: "Jalen Brunson 25+",
    odds: 1.9,
    stake: 1,
    status: "pending",
    analysis_snapshot: { monte_carlo: 0.229, factor_model: 0.81 },
  };
  const kv = memoryKv({ SPORTS_BET_LEDGER: JSON.stringify({ [id]: original }) });
  const edited = await sports.onRequestPatch({
    request: new Request("https://dashboard.example/api/sports-bets", {
      method: "PATCH",
      headers: { "Content-Type": "application/json", "Sec-Fetch-Site": "same-origin" },
      body: JSON.stringify({ id, updates: { status: "lost", odds: 2.1, note: "manual settlement" } }),
    }),
    env: { WC_STATE: kv },
  });

  assert.equal(edited.status, 200);
  const editedBody = await edited.json();
  assert.equal(editedBody.record.profit, -1);
  assert.deepEqual(editedBody.record.analysis_snapshot, original.analysis_snapshot);

  const removed = await sports.onRequestDelete({
    request: new Request("https://dashboard.example/api/sports-bets", {
      method: "DELETE",
      headers: { "Content-Type": "application/json", "Sec-Fetch-Site": "same-origin" },
      body: JSON.stringify({ id }),
    }),
    env: { WC_STATE: kv },
  });
  assert.equal(removed.status, 200);
  assert.equal(JSON.parse(kv.read("SPORTS_BET_LEDGER"))[id]._deleted, true);
});

test("sports bet API edits combo legs while preserving the original recommendation snapshot", async () => {
  const sports = await loadModule("../functions/api/sports-bets.js");
  const id = "tennis-combo-live";
  const original = {
    id,
    sport: "tennis",
    source_id: "tennis:combo:live",
    event_date: "2026-07-25",
    event_name: "2-match Combo",
    market: "Tennis Multi",
    selection: "A + B",
    bet_type: "combo",
    legs: [
      { selection: "A", market: "Match Betting", odds: 1.5 },
      { selection: "B", market: "Match Betting", odds: 1.6 },
    ],
    odds: 2.4,
    stake: 1,
    status: "pending",
    analysis_snapshot: {
      legs: [
        { selection: "A", odds: 1.5 },
        { selection: "B", odds: 1.6 },
      ],
    },
  };
  const kv = memoryKv({ SPORTS_BET_LEDGER: JSON.stringify({ [id]: original }) });
  const updatedLegs = [
    { selection: "A Over", market: "Match Betting", odds: 1.55 },
    { selection: "B", market: "Match Betting", odds: 1.65 },
  ];

  const response = await sports.onRequestPatch({
    request: new Request("https://dashboard.example/api/sports-bets", {
      method: "PATCH",
      headers: { "Content-Type": "application/json", "Sec-Fetch-Site": "same-origin" },
      body: JSON.stringify({
        id,
        updates: { legs: updatedLegs, selection: "A Over + B", odds: 2.55 },
      }),
    }),
    env: { WC_STATE: kv },
  });

  assert.equal(response.status, 200);
  const body = await response.json();
  assert.deepEqual(
    body.record.legs,
    updatedLegs.map((leg) => ({ ...leg, status: "pending" })),
  );
  assert.equal(body.record.analysis_snapshot.legs[0].selection, "A");
});

test("sports bet create is idempotent when the same idempotency key is retried", async () => {
  const sports = await loadModule("../functions/api/sports-bets.js");
  const kv = memoryKv();
  const payload = {
    id: "tennis-idempotent-create",
    sport: "tennis",
    source_id: "tennis:market:42",
    event_date: "2026-07-25",
    event_name: "A vs B",
    market: "Match Betting",
    selection: "A",
    odds: 2.1,
    stake: 1,
    status: "pending",
  };
  const request = () => new Request("https://dashboard.example/api/sports-bets", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Sec-Fetch-Site": "same-origin",
      "Idempotency-Key": "create-tennis-42",
    },
    body: JSON.stringify(payload),
  });

  const first = await sports.onRequestPost({ request: request(), env: { WC_STATE: kv } });
  const second = await sports.onRequestPost({ request: request(), env: { WC_STATE: kv } });

  assert.equal(first.status, 200);
  assert.equal(second.status, 200);
  assert.equal((await second.json()).idempotent, true);
});

test("combo settlement supports a won leg plus a void leg using effective odds", async () => {
  const sports = await loadModule("../functions/api/sports-bets.js");
  const id = "tennis-partial-void";
  const original = {
    id,
    sport: "tennis",
    source_id: "tennis:combo:partial-void",
    event_date: "2026-07-25",
    event_name: "2-match Combo",
    market: "Tennis Multi",
    selection: "A + B",
    bet_type: "combo",
    legs: [
      { selection: "A", market: "Match Betting", odds: 2.0, status: "pending" },
      { selection: "B", market: "Match Betting", odds: 1.5, status: "pending" },
    ],
    odds: 3.0,
    stake: 2,
    status: "pending",
    analysis_snapshot: {},
  };
  const kv = memoryKv({ SPORTS_BET_LEDGER: JSON.stringify({ [id]: original }) });

  const response = await sports.onRequestPatch({
    request: new Request("https://dashboard.example/api/sports-bets", {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        "Sec-Fetch-Site": "same-origin",
        "Idempotency-Key": "settle-partial-void",
      },
      body: JSON.stringify({
        id,
        updates: {
          legs: [
            { selection: "A", market: "Match Betting", odds: 2.0, status: "won" },
            { selection: "B", market: "Match Betting", odds: 1.5, status: "void" },
          ],
          settlement_source: "tennis_wc.db",
          settlement_ref: "combo_tracker#partial-void",
        },
      }),
    }),
    env: { WC_STATE: kv },
  });

  assert.equal(response.status, 200);
  const body = await response.json();
  assert.equal(body.record.status, "won");
  assert.equal(body.record.settlement_odds, 2);
  assert.equal(body.record.payout, 4);
  assert.equal(body.record.profit, 2);
});

test("D1 migration defines the unified ledger, leg, settlement and audit contracts", () => {
  const schema = fs.readFileSync(
    new URL("../migrations/0001_unified_bet_ledger.sql", import.meta.url),
    "utf8",
  );
  for (const table of ["analysis_runs", "recommendations", "bets", "bet_legs", "settlements", "audit_log"]) {
    assert.match(schema, new RegExp(`CREATE TABLE IF NOT EXISTS ${table}`));
  }
  assert.match(schema, /UNIQUE \(bet_id, leg_index\)/);
  assert.match(schema, /idempotency_key TEXT NOT NULL UNIQUE/);
});

test("portfolio summary separates realised ROI from pending exposure by sport", async () => {
  const portfolio = await loadModule("../functions/api/portfolio.js");
  const summary = portfolio.buildPortfolio({
    horseWon: { sport: "horses", status: "won", stake: 1, profit: 1.5 },
    nbaLost: { sport: "nba", status: "lost", stake: 2, profit: -2 },
    tennisVoid: { sport: "tennis", status: "void", stake: 1, profit: 0 },
    tennisPending: { sport: "tennis", status: "pending", stake: 3, profit: 0 },
  });

  assert.equal(summary.total.pending_exposure, 3);
  assert.equal(summary.total.realised_stake, 4);
  assert.equal(summary.total.profit, -0.5);
  assert.equal(summary.total.roi, -0.125);
  assert.equal(summary.by_sport.tennis.pending, 1);
  assert.equal(summary.by_sport.horses.wins, 1);
});

test("results-backed settlement preserves actual odds and stake while grading a single", async () => {
  const settlements = await loadModule("../functions/api/settlements.js");
  const existing = {
    id: "nba-user-bet-1",
    sport: "nba",
    source_id: "nba:2026-04-15:chi-was:banker",
    event_date: "2026-04-15",
    event_name: "CHI @ WAS",
    market: "Player PTS",
    selection: "Zach LaVine 24+ PTS",
    bet_type: "single",
    odds: 1.85,
    stake: 3,
    status: "pending",
    payout: 0,
    profit: 0,
    analysis_snapshot: { edge: 0.051 },
    version: 1,
    created_at: 100,
    updated_at: 100,
    legs: [],
  };
  const proposal = {
    source_id: existing.source_id,
    sport: "nba",
    status: "won",
    source: "nba_reflector",
    source_ref: "Results_Brief_2026-04-15.json",
    reason: "box score",
    idempotency_key: "nba-result-1",
  };

  const record = settlements.applySettlementProposal(existing, proposal, 200);

  assert.equal(record.odds, 1.85);
  assert.equal(record.stake, 3);
  assert.equal(record.payout, 5.55);
  assert.equal(record.profit, 2.55);
  assert.equal(record.analysis_snapshot.edge, 0.051);
  assert.equal(record.settlement_source, "nba_reflector");
});

test("results-backed combo settlement preserves leg prices and supports partial void", async () => {
  const settlements = await loadModule("../functions/api/settlements.js");
  const existing = {
    id: "tennis-user-combo-1",
    sport: "tennis",
    source_id: "tennis:combo:42",
    event_date: "2026-07-25",
    event_name: "A + B",
    market: "Tennis Multi",
    selection: "A + B",
    bet_type: "combo",
    odds: 3,
    stake: 2,
    status: "pending",
    payout: 0,
    profit: 0,
    analysis_snapshot: {},
    version: 1,
    created_at: 100,
    updated_at: 100,
    legs: [
      { selection: "A", odds: 2, status: "pending" },
      { selection: "B", odds: 1.5, status: "pending" },
    ],
  };
  const proposal = {
    source_id: existing.source_id,
    sport: "tennis",
    status: "won",
    source: "tennis_wc.db",
    source_ref: "combo_tracker#42",
    reason: "per-leg results",
    idempotency_key: "tennis-result-42",
    legs: [
      { selection: "ignored", odds: 99, status: "won", result_value: 2 },
      { selection: "ignored", odds: 99, status: "void" },
    ],
  };

  const record = settlements.applySettlementProposal(existing, proposal, 200);

  assert.equal(record.status, "won");
  assert.equal(record.settlement_odds, 2);
  assert.equal(record.payout, 4);
  assert.equal(record.profit, 2);
  assert.equal(record.legs[0].odds, 2);
  assert.equal(record.legs[1].odds, 1.5);
  assert.deepEqual(record.legs.map((leg) => leg.status), ["won", "void"]);
});

test("settlement endpoint contract only trusts native tennis and NBA reflector sources", async () => {
  const settlements = await loadModule("../functions/api/settlements.js");
  const base = {
    source_id: "source:1",
    sport: "tennis",
    status: "won",
    source: "tennis_wc.db",
    source_ref: "clv_tracker#1",
    idempotency_key: "result:1",
  };
  assert.equal(settlements.validateSettlementProposal(base), "");
  assert.equal(
    settlements.validateSettlementProposal({ ...base, source: "browser_form" }),
    "untrusted settlement source",
  );
});
