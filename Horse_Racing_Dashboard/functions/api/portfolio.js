import { hasD1, listD1Bets } from "../_lib/d1-ledger.js";

const JSON_HEADERS = {
  "Content-Type": "application/json; charset=utf-8",
  "Cache-Control": "no-store",
  "X-Content-Type-Options": "nosniff",
};

function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload), { status, headers: JSON_HEADERS });
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

function emptyBucket() {
  return {
    bets: 0,
    pending: 0,
    settled: 0,
    wins: 0,
    losses: 0,
    voids: 0,
    pending_exposure: 0,
    realised_stake: 0,
    profit: 0,
    roi: null,
  };
}

function addRecord(bucket, record) {
  const stake = Number(record.stake || 0);
  const profit = Number(record.profit || 0);
  bucket.bets += 1;
  if (record.status === "pending") {
    bucket.pending += 1;
    bucket.pending_exposure += stake;
  } else {
    bucket.settled += 1;
    bucket.realised_stake += stake;
    bucket.profit += profit;
    if (record.status === "won") bucket.wins += 1;
    else if (record.status === "lost") bucket.losses += 1;
    else if (record.status === "void") bucket.voids += 1;
  }
}

function finishBucket(bucket) {
  for (const key of ["pending_exposure", "realised_stake", "profit"]) {
    bucket[key] = Number(bucket[key].toFixed(2));
  }
  bucket.roi = bucket.realised_stake
    ? Number((bucket.profit / bucket.realised_stake).toFixed(6))
    : null;
  return bucket;
}

export function buildPortfolio(records) {
  const bySport = {
    horses: emptyBucket(),
    nba: emptyBucket(),
    tennis: emptyBucket(),
  };
  const total = emptyBucket();
  for (const record of Object.values(records || {})) {
    if (!record || record._deleted || !bySport[record.sport]) continue;
    addRecord(bySport[record.sport], record);
    addRecord(total, record);
  }
  for (const bucket of Object.values(bySport)) finishBucket(bucket);
  finishBucket(total);
  return {
    generated_at: new Date().toISOString(),
    total,
    by_sport: bySport,
  };
}

export async function onRequestGet(context) {
  if (!isAuthorized(context)) return jsonResponse({ error: "unauthorized" }, 401);
  if (!hasD1(context.env)) return jsonResponse({ error: "d1 ledger unavailable" }, 503);
  try {
    const { records } = await listD1Bets(context.env.WC_LEDGER);
    return jsonResponse({
      success: true,
      storage: "d1",
      ...buildPortfolio(records),
    });
  } catch (error) {
    return jsonResponse({ error: error.message }, 500);
  }
}
