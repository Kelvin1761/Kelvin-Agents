import {
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
const STATUSES = new Set(["won", "lost", "void"]);
const TRUSTED_SOURCES = {
  nba: new Set(["nba_reflector"]),
  tennis: new Set(["tennis_wc.db"]),
};

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

function comboResult(legs) {
  const statuses = legs.map((leg) => leg.status || "pending");
  if (statuses.includes("lost")) return { status: "lost", settlement_odds: 0 };
  if (statuses.includes("pending")) return { status: "pending", settlement_odds: null };
  const won = legs.filter((leg) => leg.status === "won");
  if (!won.length) return { status: "void", settlement_odds: 1 };
  const effectiveOdds = won.reduce((product, leg) => {
    const odds = finiteNumber(leg.odds);
    return odds && odds > 1 ? product * odds : product;
  }, 1);
  return { status: "won", settlement_odds: Number(effectiveOdds.toFixed(4)) };
}

function financials(record) {
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

export function validateSettlementProposal(proposal) {
  if (!isPlainObject(proposal)) return "invalid proposal";
  const sport = cleanText(proposal.sport, 16).toLowerCase();
  const source = cleanText(proposal.source, 120);
  if (!TRUSTED_SOURCES[sport]?.has(source)) return "untrusted settlement source";
  if (!cleanText(proposal.source_id, 200)) return "missing source_id";
  if (!STATUSES.has(cleanText(proposal.status, 24).toLowerCase())) return "invalid status";
  if (!cleanText(proposal.source_ref, 240)) return "missing source_ref";
  if (!cleanText(proposal.idempotency_key, 200)) return "missing idempotency_key";
  if (proposal.legs !== undefined && !Array.isArray(proposal.legs)) return "invalid legs";
  return "";
}

export function applySettlementProposal(existing, proposal, now = Date.now()) {
  const error = validateSettlementProposal(proposal);
  if (error) throw new Error(error);
  if (!existing || existing._deleted) throw new Error("record not found");
  if (existing.sport !== proposal.sport) throw new Error("sport mismatch");
  if (existing.source_id !== proposal.source_id) throw new Error("source mismatch");

  let legs = Array.isArray(existing.legs)
    ? existing.legs.map((leg) => ({ ...leg }))
    : [];
  if (existing.bet_type === "combo") {
    if (!Array.isArray(proposal.legs) || proposal.legs.length !== legs.length) {
      throw new Error("combo leg count mismatch");
    }
    legs = legs.map((leg, index) => {
      const result = proposal.legs[index] || {};
      const status = cleanText(result.status, 24).toLowerCase();
      if (!STATUSES.has(status)) throw new Error(`invalid combo leg status ${index + 1}`);
      return {
        ...leg,
        status,
        result_value: finiteNumber(result.result_value),
        settlement_source: cleanText(proposal.source, 120),
        settlement_ref: cleanText(result.settlement_ref || proposal.source_ref, 240),
        settled_at: now,
      };
    });
  }

  const derived = existing.bet_type === "combo"
    ? comboResult(legs)
    : {
      status: cleanText(proposal.status, 24).toLowerCase(),
      settlement_odds: existing.status === "void" ? 1 : null,
    };
  if (existing.bet_type === "combo" && derived.status !== cleanText(proposal.status, 24).toLowerCase()) {
    throw new Error("combo status does not match leg results");
  }
  const record = {
    ...existing,
    legs,
    status: derived.status,
    settlement_odds: derived.status === "won"
      ? (derived.settlement_odds ?? existing.odds)
      : derived.status === "void" ? 1 : derived.settlement_odds,
    settlement_source: cleanText(proposal.source, 120),
    settlement_ref: cleanText(proposal.source_ref, 240),
    settlement_reason: cleanText(proposal.reason, 1000),
    version: Number(existing.version || 1) + 1,
    updated_at: now,
    settled_at: now,
  };
  return financials(record);
}

async function readKvLedger(context) {
  const raw = await context.env.WC_STATE?.get(KEY);
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    return isPlainObject(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

export async function onRequestPost(context) {
  if (!isAuthorized(context)) return jsonResponse({ error: "unauthorized" }, 401);
  if (!hasD1(context.env)) return jsonResponse({ error: "d1 ledger unavailable" }, 503);
  try {
    const payload = await context.request.json();
    const proposals = Array.isArray(payload?.settlements) ? payload.settlements : [];
    if (!proposals.length || proposals.length > 500) {
      return jsonResponse({ error: "settlements must contain 1-500 proposals" }, 422);
    }
    const invalid = proposals
      .map((proposal, index) => ({ index, error: validateSettlementProposal(proposal) }))
      .filter((item) => item.error);
    if (invalid.length) return jsonResponse({ error: "invalid settlement proposals", invalid }, 422);

    const kvLedger = await readKvLedger(context);
    const { records } = await listD1Bets(context.env.WC_LEDGER);
    const bySource = new Map();
    for (const record of Object.values(records)) {
      if (!record.source_id || !["nba", "tennis"].includes(record.sport)) continue;
      const key = `${record.sport}\u0000${record.source_id}`;
      if (!bySource.has(key)) bySource.set(key, []);
      bySource.get(key).push(record);
    }
    const applied = [];
    const skipped = [];
    for (const proposal of proposals) {
      const lookupKey = (
        `${cleanText(proposal.sport, 16).toLowerCase()}\u0000${cleanText(proposal.source_id, 200)}`
      );
      const matches = bySource.get(lookupKey) || [];
      if (!matches.length) {
        skipped.push({ source_id: proposal.source_id, reason: "no matching user bet" });
        continue;
      }
      for (const existing of matches) {
        const idempotencyKey = `${cleanText(proposal.idempotency_key, 200)}:${existing.id}`;
        const record = applySettlementProposal(existing, proposal);
        const result = await putD1Bet(context.env.WC_LEDGER, record, {
          before: existing,
          action: "auto_settle",
          idempotencyKey,
          actor: cleanText(proposal.source, 80),
        });
        kvLedger[existing.id] = result.record || record;
        applied.push({
          id: existing.id,
          source_id: proposal.source_id,
          status: (result.record || record).status,
          idempotent: Boolean(result.idempotent),
        });
      }
    }
    if (context.env.WC_STATE?.put) {
      await context.env.WC_STATE.put(KEY, JSON.stringify(kvLedger));
    }
    return jsonResponse({
      success: true,
      storage: "d1+kv-shadow",
      applied,
      skipped,
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
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, Authorization, Idempotency-Key",
      "Access-Control-Max-Age": "86400",
    },
  });
}
