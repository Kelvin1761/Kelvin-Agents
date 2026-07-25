const SETTLED = new Set(["won", "lost", "void"]);

export function hasD1(env) {
  return Boolean(env?.WC_LEDGER && typeof env.WC_LEDGER.prepare === "function");
}

function parseJson(value, fallback) {
  try {
    const parsed = JSON.parse(value || "");
    return parsed ?? fallback;
  } catch {
    return fallback;
  }
}

function rowsFromResult(result) {
  return Array.isArray(result?.results) ? result.results : [];
}

function uuid(prefix) {
  const id = globalThis.crypto?.randomUUID
    ? globalThis.crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}:${id}`;
}

function rowToRecord(row, legs = []) {
  if (!row) return null;
  return {
    id: row.id,
    sport: row.sport,
    source_id: row.source_id || "",
    event_date: row.event_date,
    event_name: row.event_name,
    market: row.market,
    selection: row.selection,
    bet_type: row.bet_type || "single",
    odds: Number(row.odds),
    settlement_odds: row.settlement_odds === null ? null : Number(row.settlement_odds),
    stake: Number(row.stake),
    status: row.status,
    payout: Number(row.payout || 0),
    profit: Number(row.profit || 0),
    bookmaker: row.bookmaker || "",
    note: row.note || "",
    analysis_snapshot: parseJson(row.analysis_snapshot, {}),
    settlement_source: row.settlement_source || "",
    settlement_ref: row.settlement_ref || "",
    settlement_reason: row.settlement_reason || "",
    idempotency_key: row.idempotency_key || "",
    version: Number(row.version || 1),
    created_at: Number(row.created_at),
    updated_at: Number(row.updated_at),
    settled_at: row.settled_at === null ? null : Number(row.settled_at),
    legs,
  };
}

function legRowToRecord(row) {
  return {
    event_name: row.event_name || "",
    market: row.market || "",
    selection: row.selection,
    line: row.line === null ? null : Number(row.line),
    odds: row.odds === null ? null : Number(row.odds),
    status: row.status || "pending",
    result_value: row.result_value === null ? null : Number(row.result_value),
    settlement_source: row.settlement_source || "",
    settlement_ref: row.settlement_ref || "",
    settled_at: row.settled_at === null ? null : Number(row.settled_at),
  };
}

async function readLegs(db, betId = "") {
  const statement = betId
    ? db.prepare(
      `SELECT bet_id, leg_index, event_name, market, selection, line, odds, status,
              result_value, settlement_source, settlement_ref, settled_at
       FROM bet_legs WHERE bet_id = ? ORDER BY leg_index`,
    ).bind(betId)
    : db.prepare(
      `SELECT bet_id, leg_index, event_name, market, selection, line, odds, status,
              result_value, settlement_source, settlement_ref, settled_at
       FROM bet_legs ORDER BY bet_id, leg_index`,
    );
  const result = await statement.all();
  const grouped = new Map();
  for (const row of rowsFromResult(result)) {
    if (!grouped.has(row.bet_id)) grouped.set(row.bet_id, []);
    grouped.get(row.bet_id).push(legRowToRecord(row));
  }
  return grouped;
}

export async function listD1Bets(db, sport = "") {
  const statement = sport
    ? db.prepare(
      `SELECT * FROM bets
       WHERE deleted_at IS NULL AND sport = ?
       ORDER BY event_date DESC, updated_at DESC`,
    ).bind(sport)
    : db.prepare(
      `SELECT * FROM bets
       WHERE deleted_at IS NULL
       ORDER BY event_date DESC, updated_at DESC`,
    );
  const countStatement = sport
    ? db.prepare("SELECT COUNT(*) AS total FROM bets WHERE sport = ?").bind(sport)
    : db.prepare("SELECT COUNT(*) AS total FROM bets");
  const [rowsResult, countRow, legs] = await Promise.all([
    statement.all(),
    countStatement.first(),
    readLegs(db),
  ]);
  const records = {};
  for (const row of rowsFromResult(rowsResult)) {
    records[row.id] = rowToRecord(row, legs.get(row.id) || []);
  }
  return { records, total: Number(countRow?.total || 0) };
}

export async function getD1Bet(db, id) {
  const row = await db.prepare("SELECT * FROM bets WHERE id = ? AND deleted_at IS NULL").bind(id).first();
  if (!row) return null;
  const legs = await readLegs(db, id);
  return rowToRecord(row, legs.get(id) || []);
}

export async function getD1BetIncludingDeleted(db, id) {
  const row = await db.prepare("SELECT * FROM bets WHERE id = ?").bind(id).first();
  if (!row) return null;
  if (row.deleted_at !== null) return { id: row.id, _deleted: true, deleted_at: Number(row.deleted_at) };
  const legs = await readLegs(db, id);
  return rowToRecord(row, legs.get(id) || []);
}

export async function findD1BetsBySourceId(db, sourceId, sport = "") {
  const statement = sport
    ? db.prepare(
      `SELECT * FROM bets
       WHERE deleted_at IS NULL AND source_id = ? AND sport = ?
       ORDER BY created_at`,
    ).bind(sourceId, sport)
    : db.prepare(
      `SELECT * FROM bets
       WHERE deleted_at IS NULL AND source_id = ?
       ORDER BY created_at`,
    ).bind(sourceId);
  const result = await statement.all();
  const rows = rowsFromResult(result);
  if (!rows.length) return [];
  const legs = await readLegs(db);
  return rows.map((row) => rowToRecord(row, legs.get(row.id) || []));
}

async function idempotentAudit(db, idempotencyKey) {
  if (!idempotencyKey) return null;
  return db.prepare(
    "SELECT entity_id, action FROM audit_log WHERE idempotency_key = ?",
  ).bind(idempotencyKey).first();
}

function betUpsertStatement(db, record) {
  return db.prepare(
    `INSERT INTO bets (
       id, sport, source_id, event_date, event_name, market, selection, bet_type,
       odds, settlement_odds, stake, status, payout, profit, bookmaker, note,
       analysis_snapshot, settlement_source, settlement_ref, settlement_reason,
       idempotency_key, version, created_at, updated_at, settled_at, deleted_at
     ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
     ON CONFLICT(id) DO UPDATE SET
       event_date=excluded.event_date,
       event_name=excluded.event_name,
       market=excluded.market,
       selection=excluded.selection,
       bet_type=excluded.bet_type,
       odds=excluded.odds,
       settlement_odds=excluded.settlement_odds,
       stake=excluded.stake,
       status=excluded.status,
       payout=excluded.payout,
       profit=excluded.profit,
       bookmaker=excluded.bookmaker,
       note=excluded.note,
       settlement_source=excluded.settlement_source,
       settlement_ref=excluded.settlement_ref,
       settlement_reason=excluded.settlement_reason,
       version=excluded.version,
       updated_at=excluded.updated_at,
       settled_at=excluded.settled_at,
       deleted_at=NULL`,
  ).bind(
    record.id,
    record.sport,
    record.source_id || null,
    record.event_date,
    record.event_name,
    record.market,
    record.selection,
    record.bet_type || "single",
    record.odds,
    record.settlement_odds ?? null,
    record.stake,
    record.status,
    record.payout || 0,
    record.profit || 0,
    record.bookmaker || null,
    record.note || null,
    JSON.stringify(record.analysis_snapshot || {}),
    record.settlement_source || null,
    record.settlement_ref || null,
    record.settlement_reason || null,
    record.idempotency_key || null,
    record.version || 1,
    record.created_at,
    record.updated_at,
    record.settled_at ?? null,
  );
}

function legStatements(db, record) {
  const statements = [db.prepare("DELETE FROM bet_legs WHERE bet_id = ?").bind(record.id)];
  for (const [index, leg] of (record.legs || []).entries()) {
    statements.push(
      db.prepare(
        `INSERT INTO bet_legs (
           bet_id, leg_index, event_name, market, selection, line, odds, status,
           result_value, settlement_source, settlement_ref, settled_at
         ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      ).bind(
        record.id,
        index,
        leg.event_name || null,
        leg.market || null,
        leg.selection,
        leg.line ?? null,
        leg.odds ?? null,
        leg.status || "pending",
        leg.result_value ?? null,
        leg.settlement_source || null,
        leg.settlement_ref || null,
        leg.status && leg.status !== "pending" ? (leg.settled_at || record.updated_at) : null,
      ),
    );
  }
  return statements;
}

function auditStatement(db, record, before, action, idempotencyKey, actor) {
  return db.prepare(
    `INSERT INTO audit_log (
       id, entity_type, entity_id, action, before_json, after_json,
       actor, idempotency_key, created_at
     ) VALUES (?, 'bet', ?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT(idempotency_key) DO NOTHING`,
  ).bind(
    uuid("audit"),
    record.id,
    action,
    before ? JSON.stringify(before) : null,
    JSON.stringify(record),
    actor || "dashboard",
    idempotencyKey,
    record.updated_at,
  );
}

function settlementStatement(db, record, before, idempotencyKey) {
  if (!SETTLED.has(record.status) || before?.status === record.status) return null;
  return db.prepare(
    `INSERT INTO settlements (
       id, bet_id, previous_status, status, payout, profit, effective_odds,
       source, source_ref, reason, payload_json, created_at
     ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT(id) DO NOTHING`,
  ).bind(
    `settlement:${idempotencyKey}`,
    record.id,
    before?.status || "pending",
    record.status,
    record.payout || 0,
    record.profit || 0,
    record.settlement_odds ?? record.odds,
    record.settlement_source || "manual",
    record.settlement_ref || null,
    record.settlement_reason || null,
    JSON.stringify({ legs: record.legs || [] }),
    record.updated_at,
  );
}

export async function putD1Bet(
  db,
  record,
  { before = null, action = "create", idempotencyKey, actor = "dashboard" } = {},
) {
  const previousAudit = await idempotentAudit(db, idempotencyKey);
  if (previousAudit) {
    return { record: await getD1Bet(db, record.id), idempotent: true };
  }
  const statements = [
    betUpsertStatement(db, record),
    ...legStatements(db, record),
    auditStatement(db, record, before, action, idempotencyKey, actor),
  ];
  const settlement = settlementStatement(db, record, before, idempotencyKey);
  if (settlement) statements.push(settlement);
  await db.batch(statements);
  return { record, idempotent: false };
}

export async function deleteD1Bet(
  db,
  record,
  { idempotencyKey, actor = "dashboard", now = Date.now() } = {},
) {
  const previousAudit = await idempotentAudit(db, idempotencyKey);
  if (previousAudit) return { id: record.id, idempotent: true };
  await db.batch([
    db.prepare(
      "UPDATE bets SET deleted_at = ?, updated_at = ?, version = version + 1 WHERE id = ?",
    ).bind(now, now, record.id),
    db.prepare(
      `INSERT INTO audit_log (
         id, entity_type, entity_id, action, before_json, after_json,
         actor, idempotency_key, created_at
       ) VALUES (?, 'bet', ?, 'delete', ?, ?, ?, ?, ?)`,
    ).bind(
      uuid("audit"),
      record.id,
      JSON.stringify(record),
      JSON.stringify({ id: record.id, _deleted: true, deleted_at: now }),
      actor,
      idempotencyKey,
      now,
    ),
  ]);
  return { id: record.id, idempotent: false };
}

export async function listD1Audit(db, entityId = "", limit = 100) {
  const safeLimit = Math.max(1, Math.min(Number(limit) || 100, 500));
  const statement = entityId
    ? db.prepare(
      `SELECT id, entity_type, entity_id, action, before_json, after_json,
              actor, idempotency_key, created_at
       FROM audit_log WHERE entity_id = ?
       ORDER BY created_at DESC LIMIT ?`,
    ).bind(entityId, safeLimit)
    : db.prepare(
      `SELECT id, entity_type, entity_id, action, before_json, after_json,
              actor, idempotency_key, created_at
       FROM audit_log ORDER BY created_at DESC LIMIT ?`,
    ).bind(safeLimit);
  const result = await statement.all();
  return rowsFromResult(result).map((row) => ({
    ...row,
    before: parseJson(row.before_json, null),
    after: parseJson(row.after_json, null),
    before_json: undefined,
    after_json: undefined,
  }));
}
