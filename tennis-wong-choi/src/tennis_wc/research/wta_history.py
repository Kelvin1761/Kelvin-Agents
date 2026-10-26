"""Provenance-aware WTA history overlay for the registered source experiment.

The live serve reader stays unchanged. Historical backfill is opt-in and is
marked as counterfactual whenever the input was captured after the forecast.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import json
import math
import re
import unicodedata

from tennis_wc.features.history_asof import guard_clause, guard_params, ingestion_cutoff
from tennis_wc.features.serve_return import (
    MIN_SAMPLES, ServeReturnProfile, _SERVE_COLUMNS, _RETURN_COLUMNS, profile_from_rows,
)

OVERLAY_FROM = "2026-06-01"


def _name_key(name: str) -> str:
    normal = unicodedata.normalize("NFKD", str(name or ""))
    return " ".join("".join(c for c in normal if not unicodedata.combining(c)).casefold().split())


def _stamp(value) -> datetime | None:
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result.astimezone(timezone.utc) if result.tzinfo is not None else None
    except (TypeError, ValueError):
        return None


def _score_game_range(match, score):
    sets=[]
    for n in range(1,6):
        try:
            a,b=int(match[f'ScoreSet{n}A']),int(match[f'ScoreSet{n}B'])
        except (KeyError,TypeError,ValueError):
            continue
        if a+b:
            sets.append((a,b))
    if len(sets)<2:
        sets=[(int(a),int(b)) for a,b in re.findall(r'\b(\d+)-(\d+)\b',str(score or ''))]
    if len(sets) not in (2,3) or any(
        not ((max(a,b)==6 and 0<=min(a,b)<=4)
             or (max(a,b)==7 and min(a,b) in (5,6))) for a,b in sets):
        return None
    games=sum(a+b for a,b in sets)
    tiebreaks=sum(sorted((a,b))==[6,7] for a,b in sets)
    return games-tiebreaks,games,tiebreaks


@dataclass(frozen=True)
class ObservedProfile:
    profile: ServeReturnProfile
    observation_ids: tuple[str, ...]
    source_counts: dict
    latest_date: str | None
    captured_before_forecast: bool


class WtaHistoryOverlay:
    def __init__(self, conn):
        self.conn = conn
        self.issues = Counter()
        self.official = defaultdict(list)
        self.cache = {}
        # This experiment deliberately starts after the frozen legacy source.
        # A future overlapping provider must be reconciled, not double-counted.
        overlap = conn.execute(
            "SELECT COUNT(*) FROM player_match_history WHERE tour='WTA' "
            "AND hold_rate IS NOT NULL AND match_date>=?", (OVERLAY_FROM,),
        ).fetchone()[0]
        if overlap:
            raise ValueError("WTA serve sources overlap; reconcile event identities before this study")
        self._names = self._player_names()
        exposures={tuple(row[:3]):tuple(row[3:]) for row in conn.execute(
            'SELECT tournament_id,year,wta_match_id,COUNT(service_games_played),'
            'SUM(service_games_played),MIN(service_games_played),'
            'MAX(service_games_played)-MIN(service_games_played) '
            "FROM wta_match_stats WHERE stats_status='OK' GROUP BY 1,2,3")}
        raw_matches = {}
        for row in conn.execute("SELECT * FROM wta_match_stats WHERE stats_status='OK' ORDER BY id"):
            item = dict(row)
            if item["match_date"] < OVERLAY_FROM:
                continue
            raw_id = item["raw_response_id"]
            if raw_id not in raw_matches:
                raw = conn.execute("SELECT response_json FROM raw_api_responses WHERE id=?", (raw_id,)).fetchone()
                body = json.loads(raw[0]) if raw else {}
                raw_matches[raw_id] = {str(m["MatchID"]): m for m in body.get("matches", [])}
            match = raw_matches[raw_id].get(str(item["wta_match_id"]), {})
            timestamp = _stamp(match.get("MatchTimeStamp"))
            if timestamp is None or timestamp.date().isoformat() != item["match_date"]:
                self.issues["missing_or_inconsistent_actual_match_timestamp"] += 1
                continue
            if any(marker in str(item.get("score") or "").upper()
                   for marker in ("RET", "W/O", "WALKOVER", "ABD", "DEF")):
                self.issues["non_completed_match"] += 1
                continue
            invalid = any(
                item.get(key) is not None and not 0 <= float(item[key]) <= 1
                for key in ("hold_rate", "break_rate", "first_serve_points_won_pct",
                            "second_serve_points_won_pct", "return_points_won_pct")
            )
            count_fields = ("service_games_played", "ace_count", "double_fault_count",
                            "break_points_saved", "break_points_faced",
                            "break_points_converted", "break_points_chances")
            invalid = invalid or any(
                item.get(key) is not None and (
                    not math.isfinite(float(item[key])) or float(item[key]) < 0
                    or not float(item[key]).is_integer())
                for key in count_fields
            )
            if (invalid or item.get("hold_rate") is None
                    or not item.get("service_games_played") or item["service_games_played"] <= 0):
                self.issues["invalid_serve_rates_or_exposure"] += 1
                continue
            bounds=_score_game_range(match,item.get('score'))
            count,total,minimum,gap=exposures[(item['tournament_id'],item['year'],item['wta_match_id'])]
            if (bounds is None or count!=2 or minimum<=0
                    or not bounds[0]<=total<=bounds[1] or gap>bounds[2]+1):
                self.issues['inconsistent_service_exposure_with_score'] += 1
                continue
            own = self._resolve(item["player_name"])
            opponent = self._resolve(item["opponent_name"])
            if own is None or opponent is None or own == opponent:
                self.issues["unresolved_or_ambiguous_player_pair"] += 1
                continue
            item.update(player_id=own, opponent_id=opponent, opponent_elo=None,
                        actual_match_timestamp=timestamp.isoformat(),
                        observation_id=(f"wta:{item['tournament_id']}:{item['year']}:"
                                        f"{item['wta_match_id']}:{item['side']}"),
                        captured_at=item["fetched_at"])
            self.official[own].append(item)
        for rows in self.official.values():
            rows.sort(key=lambda r: (r["match_date"], r["id"]), reverse=True)

    def _player_names(self):
        wta_ids = {row[0] for row in self.conn.execute(
            # DISTINCT otherwise walks player/date and fetches every table row
            # randomly just to test tour. Sequential reads matter on the archive disk.
            "SELECT DISTINCT player_id FROM player_match_history NOT INDEXED WHERE tour='WTA'"
        )}
        columns = {r["name"] for r in self.conn.execute("PRAGMA table_info(players)")}
        canonical_column = "canonical_player_id" if "canonical_player_id" in columns else "NULL"
        players = {r["id"]: dict(r) for r in self.conn.execute(
            f"SELECT id,name,tour,{canonical_column} AS canonical_player_id FROM players"
        )}
        names = defaultdict(set)
        for pid, player in players.items():
            if player["tour"] != "WTA" and pid not in wta_ids:
                continue
            seen = set()
            current = pid
            while players.get(current, {}).get("canonical_player_id") is not None:
                if current in seen:
                    current = None
                    break
                seen.add(current)
                current = int(players[current]["canonical_player_id"])
            if current in players:
                names[_name_key(player["name"])].add(current)
        return names

    def _resolve(self, name):
        ids = self._names.get(_name_key(name), set())
        return next(iter(ids)) if len(ids) == 1 else None

    def profile(self, player_id, as_of_date, *, surface=None, start_time=None,
                max_age_days=None, allow_historical_backfill=False, window=25):
        key = (player_id, as_of_date, surface, start_time, max_age_days,
               allow_historical_backfill, window)
        if key in self.cache:
            return self.cache[key]
        columns = ",".join((*_SERVE_COLUMNS, *_RETURN_COLUMNS, "opponent_elo"))
        where = ""
        params = [player_id, as_of_date, *guard_params(as_of_date, start_time)]
        earliest = (date.fromisoformat(as_of_date)-timedelta(days=max_age_days)).isoformat() if max_age_days else None
        if earliest:
            where += " AND match_date>=?"
            params.append(earliest)
        if surface:
            where += " AND LOWER(COALESCE(surface,''))=LOWER(?)"
            params.append(surface)
        params.append(window)
        old = [dict(r) for r in self.conn.execute(
            f"SELECT {columns},id,match_date,created_at AS captured_at,source_provider "
            f"FROM player_match_history WHERE player_id=? AND match_date<? "
            f"AND hold_rate IS NOT NULL {guard_clause()} {where} "
            "ORDER BY match_date DESC,id DESC LIMIT ?", tuple(params),
        )]
        for row in old:
            row["observation_id"] = f"legacy:{row['id']}"
        cutoff = _stamp(ingestion_cutoff(as_of_date, start_time))
        if cutoff is None:
            raise ValueError("invalid forecast cutoff")
        fresh = [row for row in self.official.get(player_id, [])
                 if row["match_date"] < as_of_date
                 and _stamp(row["actual_match_timestamp"]) < cutoff
                 and (not earliest or row["match_date"] >= earliest)
                 and (not surface or str(row["surface"] or "").lower() == surface.lower())
                 and (allow_historical_backfill or
                      (_stamp(row["captured_at"]) is not None and _stamp(row["captured_at"]) < cutoff))]
        rows = sorted(old+fresh, key=lambda r: (r["match_date"], r["id"]), reverse=True)[:window]
        if surface and len(rows) < MIN_SAMPLES:
            result = self.profile(player_id, as_of_date, start_time=start_time,
                                  max_age_days=max_age_days,
                                  allow_historical_backfill=allow_historical_backfill, window=window)
        else:
            result = ObservedProfile(
                profile_from_rows(player_id, as_of_date, surface, rows),
                tuple(row["observation_id"] for row in rows),
                dict(Counter(row["source_provider"] for row in rows)),
                max((row["match_date"] for row in rows), default=None),
                all(_stamp(row["captured_at"]) is not None and _stamp(row["captured_at"]) < cutoff for row in rows),
            )
        self.cache[key] = result
        return result
