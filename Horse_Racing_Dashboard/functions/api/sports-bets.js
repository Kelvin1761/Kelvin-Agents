// Cross-sport bet ledger for NBA and Tennis.
//
// Recommendation data is copied into `analysis_snapshot` when a bet is
// created.  Later analysis refreshes therefore cannot rewrite the historical
// reason for a bet.  Records live in the existing WC_STATE KV binding.
import {
  deleteD1Bet,
  getD1Bet,
  hasD1,
  listD1Bets,
  putD1Bet,
} from "../_lib/d1-ledger.js";

const KEY = "SPORTS_BET_LEDGER";
const JSON_HEADERS = {
  "Content-Type": "application/json; charset=utf-8",
  "Cache-Control": "no-store",
  "X-Content-Type-Options": "nosniff",
};
const SPORTS = new Set(["nba", "tennis"]);
const STATUSES = new Set(["pending", "won", "lost", "void"]);

function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload), { status, headers: JSON_HEADERS });
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function isSameOrigin(request) {
  const origin = request.headers.get("Origin");
  const fetchSite = request.headers.get("Sec-Fetch-Site");
  if (fetchSite && !["same-origin", "same-site", "none"].includes(fetchSite)) return false;
  return !origin || origin === new URL(request.url).origin;
}

function isAuthorized(context) {
  const configuredToken = context.env.WC_SYNC_TOKEN;
  if (!configuredToken) return isSameOrigin(context.request);
  return context.request.headers.get("Authorization") === `Bearer ${configuredToken}`;
}

function cleanText(value, maxLength = 240) {
  return String(value ?? "").trim().slice(0, maxLength);
}

function finiteNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function validId(value) {
  return typeof value === "string" && /^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,159}$/.test(value);
}

function validBaseRecord(record) {
  if (!isPlainObject(record) || !validId(record.id)) return false;
  if (!SPORTS.has(record.sport) || !STATUSES.has(record.status || "pending")) return false;
  if (!record.event_date || !record.event_name || !record.market || !record.selection) return false;
  const stake = finiteNumber(record.stake);
  const odds = finiteNumber(record.odds);
  if (stake === null || stake <= 0 || stake > 1000000) return false;
  if (odds === null || odds <= 1 || odds > 10000) return false;
  if (record.bet_type === "combo") {
    if (!Array.isArray(record.legs) || record.legs.length < 1 || record.legs.length > 20) return false;
    if (record.legs.some((leg) => !isPlainObject(leg) || !cleanText(leg.selection))) return false;
  }
  return !record.analysis_snapshot || isPlainObject(record.analysis_snapshot);
}

function normalizeLegs(value) {
  if (!Array.isArray(value)) return [];
  return value.slice(0, 20).filter(isPlainObject).map((leg) => {
    const normalized = { ...leg };
    normalized.selection = cleanText(leg.selection);
    if (Object.prototype.hasOwnProperty.call(leg, "market")) normalized.market = cleanText(leg.market);
    if (Object.prototype.hasOwnProperty.call(leg, "event_name")) normalized.event_name = cleanText(leg.event_name);
    if (Object.prototype.hasOwnProperty.call(leg, "odds")) normalized.odds = finiteNumber(leg.odds);
    if (Object.prototype.hasOwnProperty.call(leg, "line")) normalized.line = finiteNumber(leg.line);
    if (Object.prototype.hasOwnProperty.call(leg, "result_value")) normalized.result_value = finiteNumber(leg.result_value);
    normalized.status = STATUSES.has(cleanText(leg.status || "pending", 24).toLowerCase())
      ? cleanText(leg.status || "pending", 24).toLowerCase()
      : "pending";
    if (Object.prototype.hasOwnProperty.call(leg, "settlement_source")) {
      normalized.settlement_source = cleanText(leg.settlement_source, 120);
    }
    if (Object.prototype.hasOwnProperty.call(leg, "settlement_ref")) {
      normalized.settlement_ref = cleanText(leg.settlement_ref, 240);
    }
    return normalized;
  });
}

function deriveComboSettlement(legs) {
  if (!Array.isArray(legs) || !legs.length) {
    return { status: "pending", settlement_odds: null };
  }
  const statuses = legs.map((leg) => cleanText(leg.status || "pending", 24).toLowerCase());
  if (statuses.includes("lost")) return { status: "lost", settlement_odds: 0 };
  if (statuses.includes("pending")) return { status: "pending", settlement_odds: null };
  const wonLegs = legs.filter((leg) => cleanText(leg.status, 24).toLowerCase() === "won");
  if (!wonLegs.length) return { status: "void", settlement_odds: 1 };
  const effectiveOdds = wonLegs.reduce((product, leg) => {
    const odds = finiteNumber(leg.odds);
    return odds && odds > 1 ? product * odds : product;
  }, 1);
  return {
    status: "won",
    settlement_odds: Number(effectiveOdds.toFixed(4)),
  };
}

function deriveFinancials(record) {
  const stake = Number(record.stake);
  const odds = Number(record.settlement_odds ?? record.odds);
  if (record.status === "won") {
    record.payout = Number((stake * odds).toFixed(2));
    record.profit = Number((record.payout - stake).toFixed(2));
  } else if (record.status === "lost") {
    record.payout = 0;
    record.profit = Number((-stake).toFixed(2));
  } else if (record.status === "void") {
    record.payout = Number(stake.toFixed(2));
    record.profit = 0;
  } else {
    record.payout = 0;
    record.profit = 0;
  }
  return record;
}

function normalizeRecord(record, previous = null) {
  const now = Date.now();
  const legs = normalizeLegs(record.legs);
  const normalized = {
    id: cleanText(record.id, 160),
    sport: cleanText(record.sport, 16).toLowerCase(),
    source_id: cleanText(record.source_id, 200),
    event_date: cleanText(record.event_date, 32),
    event_name: cleanText(record.event_name),
    market: cleanText(record.market),
    selection: cleanText(record.selection),
    bet_type: cleanText(record.bet_type || "single", 24),
    odds: finiteNumber(record.odds),
    stake: finiteNumber(record.stake),
    status: cleanText(record.status || "pending", 24).toLowerCase(),
    bookmaker: cleanText(record.bookmaker, 120),
    note: cleanText(record.note, 1000),
    legs,
    // Immutable after creation: this is the audit snapshot of why the bet
    // existed, not a live reference to an analysis card.
    analysis_snapshot: previous?.analysis_snapshot ?? (
      isPlainObject(record.analysis_snapshot)
        ? JSON.parse(JSON.stringify(record.analysis_snapshot))
        : {}
    ),
    settlement_odds: finiteNumber(record.settlement_odds),
    settlement_source: cleanText(record.settlement_source, 120),
    settlement_ref: cleanText(record.settlement_ref, 240),
    settlement_reason: cleanText(record.settlement_reason, 1000),
    idempotency_key: cleanText(previous?.idempotency_key || record.idempotency_key, 200),
    last_idempotency_key: cleanText(record.last_idempotency_key || previous?.last_idempotency_key, 200),
    version: Number(previous?.version || 0) + 1,
    created_at: previous?.created_at || now,
    updated_at: now,
    settled_at: previous?.settled_at || null,
  };
  if (normalized.bet_type === "combo" && legs.some((leg) => leg.status !== "pending")) {
    const combo = deriveComboSettlement(legs);
    normalized.status = combo.status;
    normalized.settlement_odds = combo.settlement_odds;
  }
  if (normalized.status !== "pending") normalized.settled_at = previous?.settled_at || now;
  else normalized.settled_at = null;
  return deriveFinancials(normalized);
}

async function readKvLedger(context) {
  const raw = await context.env.WC_STATE.get(KEY);
  if (!raw) return {};
  const parsed = JSON.parse(raw);
  return isPlainObject(parsed) ? parsed : {};
}

async function readLedger(context) {
  if (hasD1(context.env)) {
    const [nba, tennis] = await Promise.all([
      listD1Bets(context.env.WC_LEDGER, "nba"),
      listD1Bets(context.env.WC_LEDGER, "tennis"),
    ]);
    if (nba.total + tennis.total > 0) return { ...nba.records, ...tennis.records };
  }
  return readKvLedger(context);
}

async function shadowWriteKv(context, ledger) {
  await context.env.WC_STATE.put(KEY, JSON.stringify(ledger));
}

export async function onRequestGet(context) {
  if (!isAuthorized(context)) return jsonResponse({ error: "unauthorized" }, 401);
  try {
    return jsonResponse(await readLedger(context));
  } catch (error) {
    return jsonResponse({ error: error.message }, 500);
  }
}

export async function onRequestPost(context) {
  if (!isAuthorized(context)) return jsonResponse({ error: "unauthorized" }, 401);
  try {
    const incoming = await context.request.json();
    if (!validBaseRecord(incoming)) return jsonResponse({ error: "invalid bet record" }, 422);
    const ledger = await readLedger(context);
    const existing = hasD1(context.env)
      ? (await getD1Bet(context.env.WC_LEDGER, incoming.id)) || ledger[incoming.id]
      : ledger[incoming.id];
    const idempotencyKey = cleanText(
      context.request.headers.get("Idempotency-Key") || incoming.idempotency_key || incoming.id,
      200,
    );
    if (existing && !existing._deleted) {
      if (existing.idempotency_key === idempotencyKey) {
        return jsonResponse({ success: true, idempotent: true, record: existing });
      }
      return jsonResponse({ error: "record already exists" }, 409);
    }
    const record = normalizeRecord({ ...incoming, idempotency_key: idempotencyKey });
    ledger[record.id] = record;
    let d1Result = null;
    if (hasD1(context.env)) {
      d1Result = await putD1Bet(context.env.WC_LEDGER, record, {
        action: "create",
        idempotencyKey,
        actor: "dashboard",
      });
    }
    await shadowWriteKv(context, ledger);
    return jsonResponse({
      success: true,
      idempotent: Boolean(d1Result?.idempotent),
      storage: hasD1(context.env) ? "d1+kv-shadow" : "kv",
      record: d1Result?.record || record,
    });
  } catch (error) {
    return jsonResponse({ error: error.message }, 400);
  }
}

export async function onRequestPatch(context) {
  if (!isAuthorized(context)) return jsonResponse({ error: "unauthorized" }, 401);
  try {
    const payload = await context.request.json();
    if (!validId(payload?.id) || !isPlainObject(payload?.updates)) {
      return jsonResponse({ error: "invalid edit payload" }, 422);
    }
    const ledger = await readLedger(context);
    const existing = hasD1(context.env)
      ? (await getD1Bet(context.env.WC_LEDGER, payload.id)) || ledger[payload.id]
      : ledger[payload.id];
    if (!existing || existing._deleted) return jsonResponse({ error: "record not found" }, 404);
    const idempotencyKey = cleanText(
      context.request.headers.get("Idempotency-Key") || payload.idempotency_key || "",
      200,
    );
    if (idempotencyKey && existing.last_idempotency_key === idempotencyKey) {
      return jsonResponse({ success: true, idempotent: true, record: existing });
    }

    const editable = {};
    for (const field of [
      "event_date", "event_name", "market", "selection", "bet_type", "legs",
      "odds", "stake", "status", "bookmaker", "note", "settlement_odds",
      "settlement_source", "settlement_ref", "settlement_reason",
    ]) {
      if (Object.prototype.hasOwnProperty.call(payload.updates, field)) editable[field] = payload.updates[field];
    }
    const candidate = { ...existing, ...editable };
    if (!validBaseRecord(candidate)) return jsonResponse({ error: "invalid bet record" }, 422);
    const record = normalizeRecord(
      { ...candidate, last_idempotency_key: idempotencyKey || existing.last_idempotency_key },
      existing,
    );
    ledger[payload.id] = record;
    let d1Result = null;
    if (hasD1(context.env)) {
      d1Result = await putD1Bet(context.env.WC_LEDGER, record, {
        before: existing,
        action: record.status !== existing.status ? "settle" : "update",
        idempotencyKey: idempotencyKey || `update:${record.id}:${record.updated_at}`,
        actor: cleanText(payload.actor || "dashboard", 80),
      });
    }
    await shadowWriteKv(context, ledger);
    return jsonResponse({
      success: true,
      idempotent: Boolean(d1Result?.idempotent),
      storage: hasD1(context.env) ? "d1+kv-shadow" : "kv",
      record: d1Result?.record || record,
    });
  } catch (error) {
    return jsonResponse({ error: error.message }, 400);
  }
}

export async function onRequestDelete(context) {
  if (!isAuthorized(context)) return jsonResponse({ error: "unauthorized" }, 401);
  try {
    const payload = await context.request.json();
    if (!validId(payload?.id)) return jsonResponse({ error: "invalid record id" }, 422);
    const ledger = await readLedger(context);
    const existing = hasD1(context.env)
      ? (await getD1Bet(context.env.WC_LEDGER, payload.id)) || ledger[payload.id]
      : ledger[payload.id];
    if (!existing || existing._deleted) return jsonResponse({ error: "record not found" }, 404);
    const idempotencyKey = cleanText(
      context.request.headers.get("Idempotency-Key")
      || payload.idempotency_key
      || `delete:${payload.id}:${Date.now()}`,
      200,
    );
    let d1Result = null;
    if (hasD1(context.env)) {
      d1Result = await deleteD1Bet(context.env.WC_LEDGER, existing, {
        idempotencyKey,
        actor: cleanText(payload.actor || "dashboard", 80),
      });
    }
    ledger[payload.id] = {
      id: existing.id,
      sport: existing.sport,
      event_date: existing.event_date,
      _deleted: true,
      deleted_at: Date.now(),
    };
    await shadowWriteKv(context, ledger);
    return jsonResponse({
      success: true,
      idempotent: Boolean(d1Result?.idempotent),
      storage: hasD1(context.env) ? "d1+kv-shadow" : "kv",
      id: payload.id,
    });
  } catch (error) {
    return jsonResponse({ error: error.message }, 400);
  }
}

export async function onRequestOptions(context) {
  if (!isSameOrigin(context.request)) return new Response(null, { status: 403 });
  return new Response(null, {
    status: 204,
    headers: {
      "Access-Control-Allow-Methods": "GET, POST, PATCH, DELETE, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, Authorization, Idempotency-Key",
      "Access-Control-Max-Age": "86400",
    },
  });
}
