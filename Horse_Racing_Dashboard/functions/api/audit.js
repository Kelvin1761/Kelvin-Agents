import { hasD1, listD1Audit } from "../_lib/d1-ledger.js";

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

export async function onRequestGet(context) {
  if (!isAuthorized(context)) return jsonResponse({ error: "unauthorized" }, 401);
  if (!hasD1(context.env)) return jsonResponse({ error: "d1 ledger unavailable" }, 503);
  try {
    const url = new URL(context.request.url);
    const entityId = String(url.searchParams.get("id") || "").slice(0, 200);
    const limit = Number(url.searchParams.get("limit") || 100);
    const audit = await listD1Audit(context.env.WC_LEDGER, entityId, limit);
    return jsonResponse({ success: true, storage: "d1", audit });
  } catch (error) {
    return jsonResponse({ error: error.message }, 500);
  }
}
