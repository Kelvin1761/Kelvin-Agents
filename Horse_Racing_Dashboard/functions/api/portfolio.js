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

export function horseRegion(record) {
  let snapshot = record?.analysis_snapshot || {};
  if (typeof snapshot === "string") {
    try { snapshot = JSON.parse(snapshot); } catch { snapshot = {}; }
  }
  const region = String(snapshot?.region || "").trim().toLowerCase();
  return region === "hkjc" || region === "au" ? region : "unknown";
}

// Per-day rows in the unified ROI board's shape ({bets, hits, stake, pnl}) so the
// Portfolio page can bucket HKJC by day / week / month next to the board's AU,
// NBA and tennis rows. Settled won/lost only (voids return the stake and are
// not a bet on the board), keyed by event_date.
function boardKey(record) {
  if (record.sport === "horses") {
    const region = horseRegion(record);
    return region === "unknown" ? null : region;
  }
  return record.sport === "nba" || record.sport === "tennis" ? record.sport : null;
}

export function buildDailyBoard(records) {
  const days = { hkjc: {}, au: {}, nba: {}, tennis: {} };
  for (const record of Object.values(records || {})) {
    if (!record || record._deleted) continue;
    if (record.status !== "won" && record.status !== "lost") continue;
    const key = boardKey(record);
    const day = String(record.event_date || "").slice(0, 10);
    if (!key || !/^\d{4}-\d{2}-\d{2}$/.test(day)) continue;
    const cell = days[key][day] || (days[key][day] = { bets: 0, hits: 0, stake: 0, pnl: 0 });
    cell.bets += 1;
    if (record.status === "won") cell.hits += 1;
    cell.stake += Number(record.stake || 0);
    cell.pnl += Number(record.profit || 0);
  }
  for (const byDay of Object.values(days)) {
    for (const cell of Object.values(byDay)) {
      cell.stake = Number(cell.stake.toFixed(4));
      cell.pnl = Number(cell.pnl.toFixed(4));
    }
  }
  return days;
}

export function buildPortfolio(records) {
  const bySport = {
    horses: emptyBucket(),
    nba: emptyBucket(),
    tennis: emptyBucket(),
  };
  // HKJC and AU are separate dashboard tabs (2026-10-10). D1 has no region
  // column; horse bets carry it inside analysis_snapshot.
  const horsesByRegion = { hkjc: emptyBucket(), au: emptyBucket(), unknown: emptyBucket() };
  const total = emptyBucket();
  for (const record of Object.values(records || {})) {
    if (!record || record._deleted || !bySport[record.sport]) continue;
    addRecord(bySport[record.sport], record);
    addRecord(total, record);
    if (record.sport === "horses") addRecord(horsesByRegion[horseRegion(record)], record);
  }
  for (const bucket of Object.values(bySport)) finishBucket(bucket);
  for (const bucket of Object.values(horsesByRegion)) finishBucket(bucket);
  finishBucket(total);
  return {
    generated_at: new Date().toISOString(),
    total,
    by_sport: bySport,
    horses_by_region: horsesByRegion,
    days: buildDailyBoard(records),
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
