// Permanent ROI ledger (separate from the editable betting panel GLOBAL_BETS).
// Records committed here survive panel edits/clears and feed the ROI tab.
// Stored in KV WC_STATE under key "ROI_LEDGER" as a dict keyed by
// date|venue|race_number|horse_number (so re-committing a meeting updates,
// not duplicates).
import {
  deleteD1Bet,
  getD1Bet,
  hasD1,
  listD1Bets,
  putD1Bet,
} from "../_lib/d1-ledger.js";

const KEY = "ROI_LEDGER";
const CORS = {
  "Content-Type": "application/json; charset=utf-8",
  "Cache-Control": "no-store",
  "X-Content-Type-Options": "nosniff",
};

function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload), { status, headers: CORS });
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

function validRecord(bet) {
  if (!bet || typeof bet !== "object" || Array.isArray(bet)) return false;
  if (!bet.date || !bet.venue || bet.race_number == null || bet.horse_number == null) return false;
  for (const field of ["race_number", "horse_number", "stake", "odds", "payout", "net_profit"]) {
    if (bet[field] != null && !Number.isFinite(Number(bet[field]))) return false;
  }
  if (bet.stake != null && Number(bet.stake) <= 0) return false;
  if (bet.odds != null && Number(bet.odds) < 0) return false;
  return true;
}

function recKey(b) {
  return `${b.date}|${b.venue}|${b.race_number}|${b.horse_number}`;
}

function normalizeRecord(record) {
  const normalized = { ...record };
  delete normalized._deleted;
  delete normalized._ledger_key;
  delete normalized.deleted_at;

  normalized.date = String(normalized.date).trim();
  normalized.venue = String(normalized.venue).trim();
  normalized.region = String(normalized.region || "").trim();
  normalized.race_number = Number(normalized.race_number);
  normalized.horse_number = Number(normalized.horse_number);
  normalized.horse_name = String(normalized.horse_name || "").trim();
  normalized.stake = Number(normalized.stake) > 0 ? Number(normalized.stake) : 1;
  normalized.odds = Number(normalized.odds) >= 0 ? Number(normalized.odds) : 0;

  const rawPosition = normalized.result_position;
  const position =
    rawPosition === null || rawPosition === undefined || rawPosition === ""
      ? null
      : Number(rawPosition);
  normalized.result_position = Number.isFinite(position) ? position : null;

  if (normalized.result_position === null) {
    normalized.status = "pending";
    normalized.payout = 0;
    normalized.net_profit = 0;
  } else if (normalized.result_position >= 1 && normalized.result_position <= 3) {
    normalized.status = "won";
    normalized.payout = normalized.odds;
    normalized.net_profit = Number((normalized.payout - normalized.stake).toFixed(2));
  } else {
    normalized.status = "lost";
    normalized.payout = 0;
    normalized.net_profit = Number((-normalized.stake).toFixed(2));
  }
  normalized._updated_at = Date.now();
  return normalized;
}

function validLedgerKey(key) {
  return typeof key === "string" && key.length > 0 && key.length <= 320;
}

function recordMatchesKey(record, key) {
  return validRecord(record) && recKey(record) === key;
}

function horseBetId(key) {
  return `horse:${key}`;
}

function horseToD1Bet(record, key, previous = null) {
  const now = Number(record._updated_at || Date.now());
  return {
    id: horseBetId(key),
    sport: "horses",
    source_id: key,
    event_date: record.date,
    event_name: `${record.venue} R${record.race_number}`,
    market: "Place",
    selection: `#${record.horse_number} ${record.horse_name || ""}`.trim(),
    bet_type: "single",
    odds: Number(record.odds || 0),
    settlement_odds: record.status === "won" ? Number(record.odds || 0) : null,
    stake: Number(record.stake || 1),
    status: record.status,
    payout: Number(record.payout || 0),
    profit: Number(record.net_profit || 0),
    bookmaker: "Horse Racing",
    note: "",
    legs: [],
    analysis_snapshot: {
      region: record.region || "",
      venue: record.venue,
      race_number: Number(record.race_number),
      horse_number: Number(record.horse_number),
      horse_name: record.horse_name || "",
      result_position: record.result_position,
    },
    settlement_source: record.status === "pending" ? "" : "horse-result",
    settlement_ref: `${record.date}|${record.venue}|R${record.race_number}`,
    settlement_reason: "",
    idempotency_key: previous?.idempotency_key || "",
    version: Number(previous?.version || 0) + 1,
    created_at: previous?.created_at || now,
    updated_at: now,
    settled_at: record.status === "pending" ? null : (previous?.settled_at || now),
  };
}

function d1BetToHorse(record) {
  const snapshot = record.analysis_snapshot || {};
  return {
    date: record.event_date,
    venue: snapshot.venue || String(record.event_name || "").replace(/\s+R\d+$/, ""),
    region: snapshot.region || "",
    race_number: Number(snapshot.race_number),
    horse_number: Number(snapshot.horse_number),
    horse_name: snapshot.horse_name || String(record.selection || "").replace(/^#\d+\s*/, ""),
    stake: Number(record.stake),
    odds: Number(record.odds),
    result_position: snapshot.result_position ?? null,
    payout: Number(record.payout || 0),
    net_profit: Number(record.profit || 0),
    status: record.status,
    _updated_at: Number(record.updated_at),
  };
}

async function readKvLedger(context) {
  const raw = await context.env.WC_STATE.get(KEY);
  return JSON.parse(raw || "{}");
}

async function readHorseLedger(context) {
  if (hasD1(context.env)) {
    const d1 = await listD1Bets(context.env.WC_LEDGER, "horses");
    if (d1.total > 0) {
      const records = {};
      for (const record of Object.values(d1.records)) {
        const horse = d1BetToHorse(record);
        records[record.source_id || recKey(horse)] = horse;
      }
      return records;
    }
  }
  return readKvLedger(context);
}

export async function onRequestGet(context) {
  if (!isAuthorized(context)) return jsonResponse({ error: "unauthorized" }, 401);
  try {
    return jsonResponse(await readHorseLedger(context));
  } catch (e) {
    return jsonResponse({ error: e.message }, 500);
  }
}

export async function onRequestPost(context) {
  if (!isAuthorized(context)) return jsonResponse({ error: "unauthorized" }, 401);
  try {
    const incoming = await context.request.json(); // array of bet records
    if (!Array.isArray(incoming)) {
      return jsonResponse({ error: "expected an array of records" }, 400);
    }
    if (incoming.length > 500) return jsonResponse({ error: "too many records" }, 413);
    if (!incoming.every(validRecord)) return jsonResponse({ error: "invalid bet record" }, 422);
    const cur = await readHorseLedger(context);
    for (const b of incoming) {
      if (b && b.date && b.venue && b.race_number != null && b.horse_number != null) {
        const normalized = normalizeRecord(b);
        const key = recKey(normalized);
        const previousD1 = hasD1(context.env)
          ? await getD1Bet(context.env.WC_LEDGER, horseBetId(key))
          : null;
        cur[key] = normalized;
        if (hasD1(context.env)) {
          const bet = horseToD1Bet(normalized, key, previousD1);
          const idempotencyKey = `roi-import:${key}:${normalized.status}:${normalized.result_position}:${normalized.odds}`;
          bet.idempotency_key = previousD1?.idempotency_key || idempotencyKey;
          await putD1Bet(context.env.WC_LEDGER, bet, {
            before: previousD1,
            action: previousD1 ? "import-update" : "import-create",
            idempotencyKey,
            actor: "horse-roi-import",
          });
        }
      }
    }
    await context.env.WC_STATE.put(KEY, JSON.stringify(cur));
    const total = Object.values(cur).filter((record) => !record?._deleted).length;
    return jsonResponse({ success: true, total });
  } catch (e) {
    return jsonResponse({ error: e.message }, 400);
  }
}

export async function onRequestPatch(context) {
  if (!isAuthorized(context)) return jsonResponse({ error: "unauthorized" }, 401);
  try {
    const payload = await context.request.json();
    const key = payload?.key;
    const updates = payload?.updates;
    if (!validLedgerKey(key)) return jsonResponse({ error: "invalid record key" }, 422);
    if (!updates || typeof updates !== "object" || Array.isArray(updates)) {
      return jsonResponse({ error: "updates must be an object" }, 422);
    }

    const cur = await readHorseLedger(context);
    const existingD1 = hasD1(context.env)
      ? await getD1Bet(context.env.WC_LEDGER, horseBetId(key))
      : null;
    const existing = existingD1
      ? d1BetToHorse(existingD1)
      : (cur[key] && !cur[key]._deleted ? cur[key] : payload?.base_record);
    if (!recordMatchesKey(existing, key)) {
      return jsonResponse({ error: "record not found" }, 404);
    }

    const editable = {};
    for (const field of ["horse_name", "odds", "result_position"]) {
      if (Object.prototype.hasOwnProperty.call(updates, field)) editable[field] = updates[field];
    }
    const next = normalizeRecord({ ...existing, ...editable });
    if (!validRecord(next)) return jsonResponse({ error: "invalid bet record" }, 422);
    cur[key] = next;
    if (hasD1(context.env)) {
      const idempotencyKey = String(
        context.request.headers.get("Idempotency-Key")
        || payload.idempotency_key
        || `roi-update:${key}:${next._updated_at}`,
      ).slice(0, 200);
      await putD1Bet(context.env.WC_LEDGER, horseToD1Bet(next, key, existingD1), {
        before: existingD1,
        action: next.status !== existing?.status ? "settle" : "update",
        idempotencyKey,
        actor: "horse-roi-editor",
      });
    }
    await context.env.WC_STATE.put(KEY, JSON.stringify(cur));
    return jsonResponse({ success: true, key, record: next });
  } catch (e) {
    return jsonResponse({ error: e.message }, 400);
  }
}

export async function onRequestDelete(context) {
  if (!isAuthorized(context)) return jsonResponse({ error: "unauthorized" }, 401);
  try {
    const payload = await context.request.json();
    const key = payload?.key;
    if (!validLedgerKey(key)) return jsonResponse({ error: "invalid record key" }, 422);

    const cur = await readHorseLedger(context);
    const existingD1 = hasD1(context.env)
      ? await getD1Bet(context.env.WC_LEDGER, horseBetId(key))
      : null;
    const existing = existingD1 ? d1BetToHorse(existingD1) : (cur[key] || payload?.record);
    if (!recordMatchesKey(existing, key)) {
      return jsonResponse({ error: "record not found" }, 404);
    }

    // Keep a small tombstone.  The generated dashboard contains a pre-baked
    // snapshot, so a hard delete would make that old record reappear.
    cur[key] = {
      date: existing.date,
      venue: existing.venue,
      region: existing.region,
      race_number: existing.race_number,
      horse_number: existing.horse_number,
      _deleted: true,
      deleted_at: Date.now(),
    };
    if (hasD1(context.env)) {
      await deleteD1Bet(context.env.WC_LEDGER, existingD1 || horseToD1Bet(existing, key), {
        idempotencyKey: String(
          context.request.headers.get("Idempotency-Key")
          || payload.idempotency_key
          || `roi-delete:${key}:${cur[key].deleted_at}`,
        ).slice(0, 200),
        actor: "horse-roi-editor",
      });
    }
    await context.env.WC_STATE.put(KEY, JSON.stringify(cur));
    return jsonResponse({ success: true, key });
  } catch (e) {
    return jsonResponse({ error: e.message }, 400);
  }
}

export async function onRequestOptions(context) {
  if (!isSameOrigin(context.request)) return new Response(null, { status: 403 });
  return new Response(null, {
    status: 204,
    headers: {
      "Access-Control-Allow-Methods": "GET, POST, PATCH, DELETE, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, Authorization",
      "Access-Control-Max-Age": "86400",
    },
  });
}
