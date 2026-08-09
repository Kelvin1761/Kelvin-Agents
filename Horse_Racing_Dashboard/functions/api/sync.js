const KEY = "GLOBAL_BETS";
const MAX_BODY_BYTES = 512 * 1024;
const JSON_HEADERS = {
  "Content-Type": "application/json; charset=utf-8",
  "Cache-Control": "no-store",
  "X-Content-Type-Options": "nosniff",
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

function stateTimestamp(state) {
  const value = Number(state?.updatedAt ?? state?.updated_at ?? 0);
  return Number.isFinite(value) ? value : 0;
}

function isBetRecord(value) {
  if (!isPlainObject(value)) return false;
  if (value.updatedAt != null && !Number.isFinite(Number(value.updatedAt))) return false;
  if (value.odds != null && (!Number.isFinite(Number(value.odds)) || Number(value.odds) < 0)) return false;
  return true;
}

function validateStore(store) {
  if (!isPlainObject(store)) return "payload must be an object";
  const meetings = Object.entries(store);
  if (meetings.length > 500) return "too many meeting entries";
  for (const [key, value] of meetings) {
    if (key.length > 320) return `invalid meeting entry: ${key}`;
    // Backward compatibility for the original flat ``bet|...`` store.
    if (key.startsWith("bet|")) {
      if (!isBetRecord(value)) return `invalid bet record: ${key}`;
      continue;
    }
    if (!isPlainObject(value)) return `invalid meeting entry: ${key}`;
    const records = Object.entries(value);
    if (records.length > 500) return `too many bet records in ${key}`;
    for (const [recordKey, record] of records) {
      if (recordKey.length > 320 || !isBetRecord(record)) return `invalid bet record: ${recordKey}`;
    }
  }
  return null;
}

function mergeRecordMaps(current, incoming) {
  const merged = { ...(isPlainObject(current) ? current : {}) };
  for (const [key, nextRecord] of Object.entries(incoming || {})) {
    const currentRecord = merged[key];
    if (!isPlainObject(currentRecord) || stateTimestamp(nextRecord) >= stateTimestamp(currentRecord)) {
      merged[key] = nextRecord;
    }
  }
  return merged;
}

function mergeStores(current, incoming) {
  const merged = { ...(isPlainObject(current) ? current : {}) };
  for (const [meetingKey, meetingState] of Object.entries(incoming)) {
    if (meetingKey.startsWith("bet|")) {
      const currentRecord = merged[meetingKey];
      if (!isPlainObject(currentRecord) || stateTimestamp(meetingState) >= stateTimestamp(currentRecord)) {
        merged[meetingKey] = meetingState;
      }
      continue;
    }
    merged[meetingKey] = mergeRecordMaps(merged[meetingKey], meetingState);
  }
  return merged;
}

export async function onRequestGet(context) {
  if (!isAuthorized(context)) return jsonResponse({ error: "unauthorized" }, 401);
  try {
    const value = await context.env.WC_STATE.get(KEY);
    if (!value) return jsonResponse({});
    const parsed = JSON.parse(value);
    return jsonResponse(isPlainObject(parsed) ? parsed : {});
  } catch (error) {
    return jsonResponse({ error: error.message }, 500);
  }
}

export async function onRequestPost(context) {
  if (!isAuthorized(context)) return jsonResponse({ error: "unauthorized" }, 401);
  try {
    const contentLength = Number(context.request.headers.get("Content-Length") || 0);
    if (contentLength > MAX_BODY_BYTES) return jsonResponse({ error: "payload too large" }, 413);

    const body = await context.request.text();
    if (new TextEncoder().encode(body).length > MAX_BODY_BYTES) {
      return jsonResponse({ error: "payload too large" }, 413);
    }
    const incoming = JSON.parse(body);
    const validationError = validateStore(incoming);
    if (validationError) return jsonResponse({ error: validationError }, 422);

    let current = {};
    const currentValue = await context.env.WC_STATE.get(KEY);
    if (currentValue) {
      try {
        current = JSON.parse(currentValue);
      } catch (_) {
        current = {};
      }
    }
    const merged = mergeStores(current, incoming);
    await context.env.WC_STATE.put(KEY, JSON.stringify(merged));
    return jsonResponse({ success: true, state: merged });
  } catch (error) {
    return jsonResponse({ error: error.message }, 400);
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
