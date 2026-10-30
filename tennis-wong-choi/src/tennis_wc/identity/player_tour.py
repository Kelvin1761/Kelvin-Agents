"""Each player's tour from evidence that can carry it, not from row labels.

``players.tour`` used to be whatever the last ingest row said. Two feeds label
rows wrongly: ESPN by the scoreboard a match was listed on (women's matches at
joint events come back from the ``atp`` scoreboard too) and TennisExplorer by a
default of ATP for any tournament name without "WTA" in it -- every women's ITF
event. ``get_or_create_player`` copied the row label onto the player on every
ingest. Measured 2026-10-30: 3,220 players stored ATP whose opponents with a
known tour are 100% WTA, and 19 WTA ranking rows held every day because a merge
target said ATP while its WTA-ranked duplicate said WTA.

Evidence, strongest first:

* ``authoritative`` -- the player is in a tour's own record: an ATP/WTA ranking
  row, or a provider id that only one tour issues (``wta:`` from the WTA
  rankings API, ``uts:`` from the ATP rankings, a TennisMyLife id -- TML
  publishes ATP only). Disagreement inside this evidence is reported as a
  conflict, never resolved by vote.
* ``opponents`` -- singles is never mixed, so a player's opponents share their
  tour. Labels spread from authoritative players through the match graph, and
  only where the vote is clear. On players that have both, the opponent vote
  agrees with the authoritative tour for 3,585 of 3,622 (2026-10-30).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
import re

from tennis_wc.database.history_observations import history_active_clause

TOURS = ("ATP", "WTA")
# Share of a player's ranking rows that must agree. Sackmann reuses one id
# space for tennis_atp and tennis_wta, so a handful of stray rows exist
# (Badosa: 2 ATP of 121); a real two-tour record does not look like that.
AUTHORITATIVE_PURITY = 0.9
INFER_MIN_MATCHES = 3
INFER_PURITY = 0.9
INFER_MAX_ROUNDS = 12
# A ranked player whose own record is mostly the other tour's opponents holds
# someone else's matches (Marko Stakusic carries "Stakusic M." women's ITF).
MIXED_RECORD_MIN_MATCHES = 5
MIXED_RECORD_MAX_AGREEMENT = 0.5

_WTA_OFFICIAL_ID = re.compile(r"^wta:\d+$")


def provider_id_tour(provider_name: str | None, provider_entity_id: str | None) -> str | None:
    """The tour a provider id proves on its own, or None."""
    provider = str(provider_name or "")
    entity = str(provider_entity_id or "")
    if provider == "composite":
        if entity.startswith("wta:"):
            return "WTA"
        if entity.startswith("uts:"):
            return "ATP"
    if provider == "tennismylife_history":
        return "ATP"
    return None


def is_official_wta_id(provider_name: str | None, provider_entity_id: str | None) -> bool:
    """A numeric id from the WTA's own API (``wta:<digits>``), not a name key."""
    return provider_name == "composite" and bool(_WTA_OFFICIAL_ID.match(str(provider_entity_id or "")))


@dataclass
class TourDecision:
    player_id: int
    tour: str | None
    basis: str | None  # "authoritative" | "opponents" | None
    support: int = 0
    purity: float = 0.0
    evidence: dict = field(default_factory=dict)
    conflict: str | None = None


def terminal_ids(conn) -> dict[int, int]:
    """player id -> terminal canonical id, for every row, in one pass."""
    parent = {int(r[0]): (int(r[1]) if r[1] is not None else None)
              for r in conn.execute("SELECT id, canonical_player_id FROM players")}
    resolved: dict[int, int] = {}
    for start in parent:
        current, seen = start, set()
        while parent.get(current) is not None and current not in seen and len(seen) < 16:
            seen.add(current)
            current = parent[current]
        resolved[start] = current
    return resolved


def authoritative_evidence(conn, terminal: dict[int, int]) -> dict[int, dict]:
    """terminal id -> {"rankings": Counter, "ids": Counter} over it and its merged rows."""
    evidence: dict[int, dict] = defaultdict(lambda: {"rankings": Counter(), "ids": Counter()})
    for provider, entity, internal in conn.execute(
        "SELECT provider_name, provider_entity_id, internal_entity_id FROM provider_entities "
        "WHERE entity_type = 'player'"
    ):
        tour = provider_id_tour(provider, entity)
        if tour and internal is not None and int(internal) in terminal:
            evidence[terminal[int(internal)]]["ids"][tour] += 1
    for player_id, tour, count in conn.execute(
        "SELECT player_id, UPPER(tour), COUNT(*) FROM rankings_history "
        "WHERE source_provider != 'mock' AND UPPER(tour) IN ('ATP', 'WTA') GROUP BY 1, 2"
    ):
        if int(player_id) in terminal:
            evidence[terminal[int(player_id)]]["rankings"][tour] += int(count)
    return dict(evidence)


def _authoritative_decision(player_id: int, evidence: dict) -> TourDecision:
    rankings: Counter = evidence["rankings"]
    ids: Counter = evidence["ids"]
    detail = {"rankings": dict(rankings), "ids": dict(ids)}
    rank_tour = None
    rank_total = sum(rankings.values())
    if rank_total:
        rank_tour, top = rankings.most_common(1)[0]
        if top / rank_total < AUTHORITATIVE_PURITY:
            return TourDecision(player_id, None, None, rank_total, top / rank_total, detail,
                                conflict="ranked on both tours")
    id_tours = set(ids)
    if len(id_tours) > 1:
        return TourDecision(player_id, None, None, sum(ids.values()), 0.0, detail,
                            conflict="provider ids from both tours")
    if rank_tour and id_tours and rank_tour not in id_tours:
        return TourDecision(player_id, None, None, rank_total, 0.0, detail,
                            conflict="ranking tour disagrees with provider id")
    tour = rank_tour or next(iter(id_tours))
    support = rank_total + sum(ids.values())
    purity = (rankings[tour] / rank_total) if rank_total else 1.0
    return TourDecision(player_id, tour, "authoritative", support, purity, detail)


def _opponent_graph(conn, terminal: dict[int, int]) -> dict[int, Counter]:
    graph: dict[int, Counter] = defaultdict(Counter)
    for player_id, opponent_id, count in conn.execute(
        f"""SELECT player_id, opponent_id, COUNT(*) FROM player_match_history
            WHERE {history_active_clause(conn)} GROUP BY 1, 2"""
    ):
        a = terminal.get(int(player_id))
        b = terminal.get(int(opponent_id))
        if a is None or b is None or a == b:
            continue
        # Each match is stored once per side; counting both directions keeps
        # the edge symmetric even where one side's row is missing.
        graph[a][b] += int(count)
        graph[b][a] += int(count)
    return graph


def _vote(neighbours: Counter, labels: dict[int, str]) -> Counter:
    votes: Counter = Counter()
    for other, weight in neighbours.items():
        tour = labels.get(other)
        if tour:
            votes[tour] += weight
    return votes


def resolve_tours(conn) -> dict:
    """Decide a tour for every terminal player, and list what cannot be decided.

    Returns ``{"terminal": {id: terminal}, "decisions": {terminal: TourDecision},
    "conflicts": [TourDecision], "mixed_records": [dict]}``.
    """
    terminal = terminal_ids(conn)
    terminals = sorted(set(terminal.values()))
    evidence = authoritative_evidence(conn, terminal)
    decisions: dict[int, TourDecision] = {}
    conflicts: list[TourDecision] = []
    for player_id in terminals:
        if player_id not in evidence:
            continue
        decision = _authoritative_decision(player_id, evidence[player_id])
        if decision.conflict:
            conflicts.append(decision)
        else:
            decisions[player_id] = decision

    graph = _opponent_graph(conn, terminal)
    conflicted = {d.player_id for d in conflicts}
    labels = {pid: d.tour for pid, d in decisions.items()}
    for round_number in range(1, INFER_MAX_ROUNDS + 1):
        new: dict[int, TourDecision] = {}
        for player_id in terminals:
            if player_id in labels or player_id in conflicted or player_id not in graph:
                continue
            votes = _vote(graph[player_id], labels)
            total = sum(votes.values())
            if total < INFER_MIN_MATCHES:
                continue
            tour, top = votes.most_common(1)[0]
            if top / total >= INFER_PURITY:
                new[player_id] = TourDecision(
                    player_id, tour, "opponents", total, top / total,
                    {"opponent_votes": dict(votes), "round": round_number})
        if not new:
            break
        # Simultaneous per round: a label must not vote in the round that made it.
        decisions.update(new)
        labels.update({pid: d.tour for pid, d in new.items()})

    mixed: list[dict] = []
    for player_id, decision in decisions.items():
        if decision.basis != "authoritative":
            continue
        votes = _vote(graph.get(player_id, Counter()), labels)
        total = sum(votes.values())
        if total >= MIXED_RECORD_MIN_MATCHES and votes[decision.tour] / total < MIXED_RECORD_MAX_AGREEMENT:
            mixed.append({"player_id": player_id, "tour": decision.tour,
                          "opponent_votes": dict(votes)})
    return {"terminal": terminal, "decisions": decisions,
            "conflicts": conflicts, "mixed_records": mixed}


# --------------------------------------------------------------------------
# Repair: plan (read-only), apply (audited), revert.
# --------------------------------------------------------------------------

REPAIR_TABLE = "player_tour_repairs"


def ensure_repair_schema(conn) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {REPAIR_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            applied_at TEXT NOT NULL,
            player_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT,
            basis TEXT,
            evidence_json TEXT,
            reverted_at TEXT
        )
        """
    )


def _feed_names_for_wta_ids(conn, wanted: set[str]) -> dict[str, list[tuple[str, str]]]:
    """wta id -> [(first_seen_date, name)] in the order the ranking feed used them."""
    import json

    seen: dict[str, dict[str, str]] = defaultdict(dict)
    if not wanted:
        return {}
    for fetched_at, payload in conn.execute(
        "SELECT fetched_at, response_json FROM raw_api_responses "
        "WHERE entity_type = 'ranking' AND entity_external_id = 'WTA' AND endpoint = '/rankings' "
        "ORDER BY id"
    ):
        try:
            rows = json.loads(payload)
        except (TypeError, ValueError):
            continue
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict) or row.get("player_id") not in wanted:
                continue
            name = str(row.get("player_name") or row.get("name") or "").strip()
            if name:
                seen[row["player_id"]].setdefault(name, str(fetched_at)[:10])
    return {pid: sorted(((d, n) for n, d in names.items())) for pid, names in seen.items()}


def _official_renames(conn, terminal: dict[int, int]) -> tuple[list[dict], list[dict]]:
    """Merged rows the WTA feed renamed after the merge.

    `wta:323403` was "Sunam Jeong" until 2026-09-14 and "Hyojoo Jeong" since;
    `wta:331329` went "Maria Kalyakina" -> "Maria Pankratova" on 2026-10-18.
    The ranking ingest renamed the merged row, the merge target kept the old
    name, and `_terminal_player_id` has held the ranking ever since. Only the
    WTA's numeric ids qualify: a UTS id has been seen moving between two
    different men (uts:45169 Martin Krumich -> Mats Rosenkranz).
    """
    from tennis_wc.ingestion.entity_mapping import _identity_agrees
    from tennis_wc.ingestion.name_matching import normalise_player_name

    players = {int(r[0]): (r[1], r[2]) for r in conn.execute("SELECT id, name, tour FROM players")}
    candidates: list[tuple[int, int, str]] = []
    for provider, entity, internal in conn.execute(
        "SELECT provider_name, provider_entity_id, internal_entity_id FROM provider_entities "
        "WHERE entity_type = 'player' AND provider_name = 'composite' AND provider_entity_id LIKE 'wta:%'"
    ):
        if internal is None or not is_official_wta_id(provider, entity):
            continue
        child = int(internal)
        target = terminal.get(child, child)
        if target == child or child not in players or target not in players:
            continue
        if _identity_agrees({"name": players[target][0], "tour": "UNKNOWN"}, players[child][0],
                            "UNKNOWN", allow_middle_omission=True):
            continue
        candidates.append((child, target, entity))
    history = _feed_names_for_wta_ids(conn, {entity for _c, _t, entity in candidates})
    renames: list[dict] = []
    unresolved: list[dict] = []
    for child, target, entity in candidates:
        names = history.get(entity, [])
        ordered = [normalise_player_name(n) for _d, n in names]
        old, new = players[target][0], players[child][0]
        item = {"player_id": target, "merged_row": child, "provider_id": entity,
                "old_name": old, "new_name": new, "feed_names": names}
        # The target's name must be an EARLIER name of this same official id,
        # and the merged row's name the latest one.
        if (normalise_player_name(old) in ordered[:-1] and ordered
                and ordered[-1] == normalise_player_name(new)):
            renames.append(item)
        else:
            unresolved.append(item)
    return renames, unresolved


def plan_tour_repairs(conn) -> dict:
    """Everything a repair would change, and everything it would not touch."""
    resolved = resolve_tours(conn)
    terminal = resolved["terminal"]
    decisions: dict[int, TourDecision] = resolved["decisions"]
    stored = {int(r[0]): (str(r[1] or "UNKNOWN").upper(), r[2]) for r in
              conn.execute("SELECT id, tour, name FROM players")}
    changes: list[dict] = []
    for player_id, target in sorted(terminal.items()):
        decision = decisions.get(target)
        if decision is None or player_id not in stored:
            continue
        old = stored[player_id][0]
        if old == decision.tour:
            continue
        changes.append({
            "player_id": player_id, "name": stored[player_id][1], "terminal_id": target,
            "old_tour": old, "new_tour": decision.tour, "basis": decision.basis,
            "support": decision.support, "purity": round(decision.purity, 4),
            "evidence": decision.evidence,
        })
    renames, unresolved = _official_renames(conn, terminal)
    undecided = Counter(
        stored[pid][0] for pid in set(terminal.values())
        if pid in stored and pid not in decisions
    )
    summary = {
        "terminal_players": len(set(terminal.values())),
        "decided": Counter(d.basis for d in decisions.values()),
        "tour_changes": Counter(f"{c['old_tour']}->{c['new_tour']} ({c['basis']}, "
                                f"{'merged row' if c['player_id'] != c['terminal_id'] else 'canonical'})"
                                for c in changes),
        "undecided_by_stored_tour": undecided,
        "conflicts": len(resolved["conflicts"]),
        "mixed_records": len(resolved["mixed_records"]),
        "renames": len(renames),
        "unresolved_name_mismatches": len(unresolved),
    }
    return {
        "summary": {k: dict(v) if isinstance(v, Counter) else v for k, v in summary.items()},
        "changes": changes,
        "renames": renames,
        "unresolved_name_mismatches": unresolved,
        "conflicts": [{"player_id": d.player_id, "name": stored.get(d.player_id, ("", ""))[1],
                       "conflict": d.conflict, "evidence": d.evidence} for d in resolved["conflicts"]],
        "mixed_records": [{**m, "name": stored.get(m["player_id"], ("", ""))[1]}
                          for m in resolved["mixed_records"]],
    }


def apply_tour_repairs(conn, plan: dict, run_id: str) -> dict:
    """Write a plan in one transaction, logging every old value for `revert`."""
    import json
    from tennis_wc.identity.player_identity import ensure_identity_schema
    from tennis_wc.ingestion.name_matching import normalise_player_name

    ensure_repair_schema(conn)
    ensure_identity_schema(conn)
    now = conn.execute("SELECT strftime('%Y-%m-%dT%H:%M:%SZ', 'now')").fetchone()[0]
    applied = {"tour": 0, "rename": 0, "alias": 0}
    with conn:
        for change in plan["changes"]:
            cursor = conn.execute(
                "UPDATE players SET tour = ?, updated_at = ? WHERE id = ? AND UPPER(tour) = ?",
                (change["new_tour"], now, change["player_id"], change["old_tour"]),
            )
            if cursor.rowcount:
                applied["tour"] += 1
                conn.execute(
                    f"INSERT INTO {REPAIR_TABLE} (run_id, applied_at, player_id, action, old_value, "
                    "new_value, basis, evidence_json) VALUES (?, ?, ?, 'tour', ?, ?, ?, ?)",
                    (run_id, now, change["player_id"], change["old_tour"], change["new_tour"],
                     change["basis"], json.dumps({"support": change["support"],
                                                  "purity": change["purity"], **change["evidence"]},
                                                 sort_keys=True)),
                )
        for rename in plan["renames"]:
            cursor = conn.execute(
                "UPDATE players SET name = ?, updated_at = ? WHERE id = ? AND name = ?",
                (rename["new_name"], now, rename["player_id"], rename["old_name"]),
            )
            if not cursor.rowcount:
                continue
            applied["rename"] += 1
            conn.execute(
                f"INSERT INTO {REPAIR_TABLE} (run_id, applied_at, player_id, action, old_value, "
                "new_value, basis, evidence_json) VALUES (?, ?, ?, 'rename', ?, ?, 'official_wta_id', ?)",
                (run_id, now, rename["player_id"], rename["old_name"], rename["new_name"],
                 json.dumps({"provider_id": rename["provider_id"], "merged_row": rename["merged_row"],
                             "feed_names": rename["feed_names"]})),
            )
            # Both spellings resolve to the player; the old one is what Sportsbet
            # and the history feeds still send.
            for name in (rename["old_name"], rename["new_name"]):
                alias = normalise_player_name(name)
                existing = conn.execute(
                    "SELECT canonical_player_id FROM player_aliases WHERE alias_norm = ?", (alias,)
                ).fetchone()
                if existing is None:
                    conn.execute(
                        "INSERT INTO player_aliases (alias_norm, canonical_player_id, source, created_at) "
                        "VALUES (?, ?, 'tour_repair_rename', ?)", (alias, rename["player_id"], now))
                    conn.execute(
                        f"INSERT INTO {REPAIR_TABLE} (run_id, applied_at, player_id, action, old_value, "
                        "new_value, basis) VALUES (?, ?, ?, 'alias', NULL, ?, 'official_wta_id')",
                        (run_id, now, rename["player_id"], alias))
                    applied["alias"] += 1
    return applied


def revert_tour_repairs(conn, run_id: str) -> dict:
    """Undo one applied run, newest change first. Only rows still at the new value move."""
    ensure_repair_schema(conn)
    now = conn.execute("SELECT strftime('%Y-%m-%dT%H:%M:%SZ', 'now')").fetchone()[0]
    reverted = Counter()
    with conn:
        for row_id, player_id, action, old, new in conn.execute(
            f"SELECT id, player_id, action, old_value, new_value FROM {REPAIR_TABLE} "
            "WHERE run_id = ? AND reverted_at IS NULL ORDER BY id DESC", (run_id,)
        ).fetchall():
            if action == "tour":
                cursor = conn.execute("UPDATE players SET tour = ? WHERE id = ? AND tour = ?",
                                      (old, player_id, new))
            elif action == "rename":
                cursor = conn.execute("UPDATE players SET name = ? WHERE id = ? AND name = ?",
                                      (old, player_id, new))
            elif action == "alias":
                cursor = conn.execute(
                    "DELETE FROM player_aliases WHERE alias_norm = ? AND canonical_player_id = ? "
                    "AND source = 'tour_repair_rename'", (new, player_id))
            else:
                continue
            if cursor.rowcount:
                reverted[action] += 1
                conn.execute(f"UPDATE {REPAIR_TABLE} SET reverted_at = ? WHERE id = ?", (now, row_id))
    return dict(reverted)
