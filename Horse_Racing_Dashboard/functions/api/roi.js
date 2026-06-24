// Permanent ROI ledger (separate from the editable betting panel GLOBAL_BETS).
// Records committed here survive panel edits/clears and feed the ROI tab.
// Stored in KV WC_STATE under key "ROI_LEDGER" as a dict keyed by
// date|venue|race_number|horse_number (so re-committing a meeting updates,
// not duplicates).
const KEY = "ROI_LEDGER";
const CORS = {
  "Content-Type": "application/json",
  "Access-Control-Allow-Origin": "*",
};

function recKey(b) {
  return `${b.date}|${b.venue}|${b.race_number}|${b.horse_number}`;
}

export async function onRequestGet(context) {
  try {
    const v = await context.env.WC_STATE.get(KEY);
    return new Response(v || "{}", { headers: CORS });
  } catch (e) {
    return new Response(JSON.stringify({ error: e.message }), { status: 500, headers: CORS });
  }
}

export async function onRequestPost(context) {
  try {
    const incoming = await context.request.json(); // array of bet records
    if (!Array.isArray(incoming)) {
      return new Response(JSON.stringify({ error: "expected an array of records" }), { status: 400, headers: CORS });
    }
    const cur = JSON.parse((await context.env.WC_STATE.get(KEY)) || "{}");
    for (const b of incoming) {
      if (b && b.date && b.venue && b.race_number != null && b.horse_number != null) {
        cur[recKey(b)] = b;
      }
    }
    await context.env.WC_STATE.put(KEY, JSON.stringify(cur));
    return new Response(JSON.stringify({ success: true, total: Object.keys(cur).length }), { headers: CORS });
  } catch (e) {
    return new Response(JSON.stringify({ error: e.message }), { status: 400, headers: CORS });
  }
}

export async function onRequestOptions() {
  return new Response(null, {
    headers: {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    },
  });
}
