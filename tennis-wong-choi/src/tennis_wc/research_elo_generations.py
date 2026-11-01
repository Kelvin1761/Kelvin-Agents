"""Memory-only generation experiment. Never an approved source or live reader.

A generation freezes its inputs and all four Elo outputs together. Selection
uses actual activation knowledge time AND a strict event-date cutoff. Missing
versions never fall back to mutable player ratings or to shadow v2.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from tennis_wc.modelling.elo_builder import ELO_PROVIDERS
from tennis_wc.modelling.elo_replay import replay_elo

QUALIFICATION = 'UNQUALIFIED_RESEARCH_ONLY'


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def _clock(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('knowledge/source clocks require a UTC offset')
    return parsed.astimezone(timezone.utc).isoformat(timespec='microseconds')


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(',', ':'))


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _model_hash() -> str:
    root = Path(__file__).parent
    paths = ['modelling/elo_builder.py', 'modelling/elo_replay.py',
             'modelling/calibration.py', 'features/elo.py']
    return _hash(_json({p: hashlib.sha256((root / p).read_bytes()).hexdigest()
                        for p in paths}))


def _key(row) -> tuple:
    return row['source_provider'], row['provider_match_id'], row['player_id']


def _eligible(row) -> bool:
    return (row['source_provider'] in ELO_PROVIDERS and row['won'] == 1
            and row.get('history_status', 'ACTIVE') == 'ACTIVE'
            and row['player_id'] != row['opponent_id'])


class ResearchEloGenerations:
    def __init__(self, conn=None):
        if conn is not None:
            raise ValueError('research generations own their :memory: connection; external connections forbidden')
        self._conn = sqlite3.connect(':memory:')
        conn = self._conn
        self._guard()
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS research_elo_generations (
                id INTEGER PRIMARY KEY, input_hash TEXT NOT NULL UNIQUE,
                input_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
                payload_json TEXT NOT NULL, available_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS research_elo_activations (
                id INTEGER PRIMARY KEY, generation_id INTEGER NOT NULL,
                observed_at TEXT NOT NULL, reason TEXT NOT NULL);
        ''')
        for table in ('research_elo_generations', 'research_elo_activations'):
            for action in ('UPDATE', 'DELETE'):
                conn.execute(f'''CREATE TRIGGER IF NOT EXISTS {table}_no_{action.lower()}
                    BEFORE {action} ON {table} BEGIN
                    SELECT RAISE(ABORT, 'research generations are append-only'); END''')
        conn.commit()

    @property
    def conn(self):
        return self._conn

    def _guard(self):
        if any(name != 'main' or path for _, name, path in
               self.conn.execute('PRAGMA database_list')):
            raise ValueError('research generations require unattached :memory: main')
        if self.conn.execute('PRAGMA main.journal_mode').fetchone()[0] != 'memory':
            raise ValueError('temporary on-disk databases are not memory-only')
        if self.conn.in_transaction:
            raise ValueError('caller transaction must finish before generation operations')

    def _load(self, generation_id):
        row = self.conn.execute('''SELECT input_hash,input_json,payload_hash,payload_json,
                                  available_at FROM research_elo_generations WHERE id=?''',
                                (generation_id,)).fetchone()
        if row is None:
            raise ValueError('unknown generation')
        if _hash(row[1]) != row[0] or _hash(row[3]) != row[2]:
            raise ValueError('generation digest mismatch')
        return json.loads(row[3]), row[4]

    def build(self, *, history: list[dict], players: list[dict], winner_keys: list,
              mappings: list[dict], source_receipts: list[dict]) -> int:
        """winner_keys must come from read_elo_inputs on the fixed source DB.

        Source receipts are retained claims, never qualification. Rebuilding
        identical input is idempotent; changing facts, mapping, references,
        receipts or algorithm produces a new generation with a new actual clock.
        """
        self._guard()
        now = _clock(utc_now())
        if not source_receipts:
            raise ValueError('explicit source receipts required, even for synthetic inputs')
        for receipt in source_receipts:
            if not re.fullmatch(r'[0-9a-f]{64}', receipt['sha256']):
                raise ValueError('invalid receipt digest')
            if _clock(receipt['captured_at']) > now:
                raise ValueError('source receipt is in the future')
        # JSON roundtrip detaches caller-owned objects and rejects non-finite values.
        inputs = json.loads(_json(dict(history=history, players=players,
                                      winner_keys=winner_keys, mappings=mappings,
                                      source_receipts=source_receipts,
                                      qualification=QUALIFICATION,
                                      model_hash=_model_hash(), initial_rating=1500.0,
                                      k_factor=None)))
        history, players = inputs['history'], inputs['players']
        player_ids = {p['id'] for p in players}
        if len(player_ids) != len(players):
            raise ValueError('duplicate player identity')
        for row in history:
            date.fromisoformat(row['match_date'])
            if any(type(row[k]) is not int or row[k] not in player_ids
                   for k in ('player_id', 'opponent_id')):
                raise ValueError('history identity missing from frozen players')
        winners = [r for r in history if _eligible(r)]
        by_key = {_key(r): r for r in winners}
        order = [tuple(k) for k in inputs['winner_keys']]
        if (len(by_key) != len(winners) or len(set(order)) != len(order)
                or set(order) != set(by_key)):
            raise ValueError('winner order must cover every eligible winner exactly once')
        rows = [by_key[k] for k in order]
        sort_keys = [(r['match_date'], r.get('source_match_ref')
                      if r.get('source_match_ref') is not None else r['provider_match_id'])
                     for r in rows]
        if sort_keys != sorted(sort_keys):
            raise ValueError('winner order contradicts native date/source ordering')
        input_json = _json(inputs)
        input_hash = _hash(input_json)
        existing = self.conn.execute('SELECT id FROM research_elo_generations WHERE input_hash=?',
                                     (input_hash,)).fetchone()
        if existing:
            self._load(existing[0])
            return existing[0]

        calculated = replay_elo(rows)
        legacy, shadow = {}, {}
        for row in calculated.history_rows:
            legacy.setdefault(tuple(row[:3]), row)
        for row in calculated.post_rows:
            shadow[tuple(row[:3])] = row
        updates = {(p, ref): rating for p, ref, rating in calculated.opponent_updates}
        output_history = [dict(r, opponent_elo=updates.get(
            (r['source_provider'], r['provider_match_id']), r.get('opponent_elo')))
            for r in history]
        current_players = []
        for player in players:
            pid = player['id']
            # Do not carry a mutable original current Elo into a new generation.
            rating = calculated.overall.get(pid)
            surfaces = calculated.surface_ratings.get(pid, {})
            current_players.append([pid, round(rating, 3) if rating is not None else None,
                                    json.dumps({s: round(v, 3) for s, v in sorted(surfaces.items())},
                                               sort_keys=True) if rating is not None else None])
        payload_json = _json(dict(qualification=QUALIFICATION, input_hash=input_hash,
                                 model_hash=inputs['model_hash'],
                                 source_receipts=inputs['source_receipts'], history=output_history,
                                 players=sorted(current_players), mappings=inputs['mappings'],
                                 legacy=[legacy[k] for k in sorted(legacy)],
                                 shadow_v2=[shadow[k] for k in sorted(shadow)]))
        available = _clock(utc_now())
        if available < now:
            raise ValueError('clock moved backwards during build')
        # The active version is untouched by building, or by any build failure.
        with self.conn:
            cursor = self.conn.execute('''INSERT INTO research_elo_generations
                (input_hash,input_json,payload_hash,payload_json,available_at)
                VALUES (?,?,?,?,?)''',
                (input_hash, input_json, _hash(payload_json), payload_json, available))
        return cursor.lastrowid

    def activate(self, generation_id: int, *, reason: str) -> None:
        """Rollback uses this same append-only operation at its actual new clock."""
        self._guard()
        _, available = self._load(generation_id)
        now = _clock(utc_now())
        last = self.conn.execute('SELECT MAX(observed_at) FROM research_elo_activations').fetchone()[0]
        if not reason.strip() or now < available or (last and now < last):
            raise ValueError('activation requires a reason and monotonic actual clock')
        with self.conn:
            self.conn.execute('''INSERT INTO research_elo_activations
                (generation_id,observed_at,reason) VALUES (?,?,?)''',
                (generation_id, now, reason))

    def snapshot_as_of(self, *, knowledge_at: str) -> dict | None:
        """Full diagnostic snapshot, not a historical feature matrix."""
        self._guard()
        stamp = _clock(knowledge_at)
        if stamp > _clock(utc_now()):
            raise ValueError('cannot assert future knowledge')
        row = self.conn.execute('''SELECT generation_id FROM research_elo_activations
            WHERE observed_at<=? ORDER BY observed_at DESC,id DESC LIMIT 1''',
                                (stamp,)).fetchone()
        if row is None:
            return None
        payload, available = self._load(row[0])
        if available > stamp:
            raise ValueError('activation precedes generation availability')
        return dict(generation_id=row[0], available_at=available, **payload)

    def history_as_of(self, player_id: int, *, event_before: str,
                      knowledge_at: str) -> list[dict]:
        date.fromisoformat(event_before)
        snapshot = self.snapshot_as_of(knowledge_at=knowledge_at)
        if snapshot is None:
            return []
        return [r for r in snapshot['history'] if r['player_id'] == player_id
                and r['match_date'] < event_before
                and r.get('history_status', 'ACTIVE') == 'ACTIVE'
                and r['player_id'] != r['opponent_id']]

    def rating_as_of(self, player_id: int, *, event_before: str,
                     knowledge_at: str, surface: str | None = None) -> float | None:
        date.fromisoformat(event_before)
        snapshot = self.snapshot_as_of(knowledge_at=knowledge_at)
        if snapshot is None:
            return None
        surface = (surface or '').strip().lower()
        rows = [r for r in snapshot['legacy'] if r[0] == player_id
                and r[1] < event_before and r[2] == surface]
        if not rows and surface:
            rows = [r for r in snapshot['legacy'] if r[0] == player_id
                    and r[1] < event_before and r[2] == '']
        return max(rows, key=lambda r: r[1])[3] if rows else None
