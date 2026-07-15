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
  return true;
}

function recKey(b) {
  return `${b.date}|${b.venue}|${b.race_number}|${b.horse_number}`;
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
        cur[recKey(b)] = b;
      }
    }
    await context.env.WC_STATE.put(KEY, JSON.stringify(cur));
    return jsonResponse({ success: true, total: Object.keys(cur).length });
  } catch (e) {
    return jsonResponse({ error: e.message }, 400);
  }
}

export async function onRequestOptions(context) {
  if (!isSameOrigin(context.request)) return new Response(null, { status: 403 });
  return new Response(null, {
    status: 204,
    headers: {
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, Authorization",
      "Access-Control-Max-Age": "86400",
    },
  });
}
