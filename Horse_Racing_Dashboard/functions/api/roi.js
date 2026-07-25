// Permanent ROI ledger (separate from the editable betting panel GLOBAL_BETS).
// Records committed here survive panel edits/clears and feed the ROI tab.
// Stored in KV WC_STATE under key "ROI_LEDGER" as a dict keyed by
// date|venue|race_number|horse_number (so re-committing a meeting updates,
// not duplicates).
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

export async function onRequestGet(context) {
  if (!isAuthorized(context)) return jsonResponse({ error: "unauthorized" }, 401);
  try {
    const v = await context.env.WC_STATE.get(KEY);
    return new Response(v || "{}", { headers: CORS });
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
    const cur = JSON.parse((await context.env.WC_STATE.get(KEY)) || "{}");
    for (const b of incoming) {
      if (b && b.date && b.venue && b.race_number != null && b.horse_number != null) {
        const normalized = normalizeRecord(b);
        cur[recKey(normalized)] = normalized;
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

    const cur = JSON.parse((await context.env.WC_STATE.get(KEY)) || "{}");
    const existing = cur[key] && !cur[key]._deleted ? cur[key] : payload?.base_record;
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

    const cur = JSON.parse((await context.env.WC_STATE.get(KEY)) || "{}");
    const existing = cur[key] || payload?.record;
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
