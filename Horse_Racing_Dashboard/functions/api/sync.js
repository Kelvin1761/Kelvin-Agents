export async function onRequestGet(context) {
  try {
    const value = await context.env.WC_STATE.get("GLOBAL_BETS");
    if (!value) return new Response(JSON.stringify({}), { headers: { 'Content-Type': 'application/json' } });
    return new Response(value, { headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' } });
  } catch (e) {
    return new Response(JSON.stringify({ error: e.message }), { status: 500 });
  }
}

export async function onRequestPost(context) {
  try {
    const body = await context.request.text();
    // Validate JSON parsing works
    JSON.parse(body);
    await context.env.WC_STATE.put("GLOBAL_BETS", body);
    return new Response(JSON.stringify({ success: true }), { headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' } });
  } catch (e) {
    return new Response(JSON.stringify({ error: e.message }), { status: 400 });
  }
}

export async function onRequestOptions(context) {
  return new Response(null, {
    headers: {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    }
  });
}
