"""Price every supported player prop for one date.

``price_date`` returns the rows to write to ``prop_tracker``; ``record_rows``
writes them. Families priced (Kelvin 2026-11-05 paused aces, double faults and
exact set score; match total games was never bettable):

  player_total_games            simulator, closed form as unstaked fallback
  player_win_a_set              set table from the match probability ("yes" only)
  first_set_winner              hand-set holds -> simulator, closed form unstaked
  player_first_set_match        simulator, four outcomes, only win-first staked
  player_first_set_game_handicap  simulator
  player_game_handicap          simulator, closed form unstaked
  player_set_handicap           set table

A side is value when the odds-blind model beats the de-vigged market by the
family's minimum edge (``families.is_value_selection``). The blended
probability (market + family weight x (model - market)) is stored for sizing.
Value is removed when the match's feature quality is under 0.65, the event is
not TOUR/CHALLENGER, or the price came from a closed-form fallback.

One pricing context (fixture, feature quality, quotes, serve profiles) is
captured per match and frozen onto each row as it is written; serve profiles
appear from the first hold estimate onward, so the order of families matters.
"""
from __future__ import annotations

import math
import re
from dataclasses import asdict

from tennis_wc.model import market, sets
from tennis_wc.model.serve import (
    combined_hold, estimate_hold, estimate_hold_fitted, predict_total_games,
    serve_return_profile,
)
from tennis_wc.model.simulate import FITTED_HOLD_GAP_DISPERSION, simulate_match
from tennis_wc.pricing import quotes as q
from tennis_wc.pricing.families import family_for_market, is_value_selection, value_profile, value_profile_for_family
from tennis_wc.store.evidence import capture_context, freeze_context
from tennis_wc.store.results import conflicting_result_matches

TRIALS = 1500
MIN_DATA_QUALITY = 0.65
BETTABLE_TIERS = frozenset({"TOUR", "CHALLENGER"})
# A best-of-three player wins at most ~20 games; a higher "player" line is a
# match total wearing a player's name.
MAX_PLAYER_GAMES_LINE = 15.5
# Closed-form share model for games (fallback when serve history is thin).
_PLAYER_GAMES_MEAN_BIAS = 0.75
_PLAYER_GAMES_SD = 4.50
_GAME_MARGIN_RESIDUAL_SD = 5.2
_GAME_MARGIN_SLOPE = 11.26
_GAME_HANDICAP_RAW_SHRINK = 0.65

_UNINFORMATIVE_NAME = re.compile(r"^\s*\d+\s*-\s*\d{4}\s*$")
_PLAYER_NAME_IN_MARKET = {
    "player_total_games": r"^(.*?)\s+total games(?:\s+\d|$)",
    "player_win_a_set": r"^(.*?)\s+to win at least (?:one|1) set",
}


# --------------------------------------------------------------------------- match context

def _match_meta(conn, match_id: int) -> dict | None:
    row = conn.execute("""
        SELECT m.id, m.player_a_id, m.player_b_id, m.match_date, m.tour,
               m.start_time_utc, m.round,
               pa.tour AS player_a_tour, pb.tour AS player_b_tour,
               pa.name AS a_name, pb.name AS b_name,
               (SELECT t.name FROM tournaments t WHERE t.id = m.tournament_id) AS tournament_name,
               (SELECT tl.level FROM tournament_levels tl
                 WHERE tl.tournament_id = m.tournament_id ORDER BY tl.id DESC LIMIT 1) AS tournament_level,
               (SELECT tl.surface FROM tournament_levels tl
                 WHERE tl.tournament_id = m.tournament_id AND tl.surface IS NOT NULL
                 ORDER BY tl.id DESC LIMIT 1) AS surface
        FROM matches m JOIN players pa ON pa.id = m.player_a_id
                       JOIN players pb ON pb.id = m.player_b_id
        WHERE m.id = ?""", (match_id,)).fetchone()
    return dict(row) if row else None


def tier_of(tournament_name: str | None, level: str | None = None) -> str:
    resolved = str(level or "").strip().upper()
    if resolved and resolved != "UNKNOWN":
        if "ITF" in resolved or "FUTURE" in resolved:
            return "ITF"
        if "UTR" in resolved:
            return "UTR"
        if "CHALLENGER" in resolved:
            return "CHALLENGER"
        return "TOUR"
    name = str(tournament_name or "").strip().upper()
    if not name:
        return "UNKNOWN"
    if "ITF" in name or "FUTURES" in name:
        return "ITF"
    if "UTR" in name:
        return "UTR"
    if "CHALLENGER" in name:
        return "CHALLENGER"
    if _UNINFORMATIVE_NAME.match(name):
        return "UNKNOWN"
    return "TOUR"


def _is_best_of_three(meta: dict) -> bool:
    tour = meta["tour"]
    if tour == "UNKNOWN" and meta["player_a_tour"] == meta["player_b_tour"]:
        tour = meta["player_a_tour"]
    level = str(meta["tournament_level"] or "").upper()
    if level == "GRAND_SLAM" and tour not in {"ATP", "WTA"}:
        return False  # unverified slam format
    round_name = str(meta["round"] or "").strip().upper()
    qualifying = round_name in {"Q", "Q1", "Q2", "Q3", "QR1", "QR2", "QR3"} or "QUAL" in round_name
    return not (str(tour or "").upper() == "ATP" and level == "GRAND_SLAM" and not qualifying)


def _feature_quality(conn, match_id: int) -> float:
    row = conn.execute("""
        SELECT MIN(fs.data_quality_score) FROM feature_snapshots fs
        WHERE fs.match_id = ? AND fs.id = (
            SELECT MAX(x.id) FROM feature_snapshots x
            WHERE x.match_id = fs.match_id AND x.player_id = fs.player_id)""", (match_id,)).fetchone()
    try:
        quality = float(row[0])
    except (TypeError, ValueError):
        return 0.0
    if quality > 1.0:
        quality /= 100.0
    return max(0.0, min(1.0, quality))


def match_probabilities(conn, match_date: str) -> dict[int, float]:
    """P(player A wins) from each match's latest prediction (exactly 0.5 = no model)."""
    rows = conn.execute("""
        SELECT p.match_id,
               CASE WHEN p.selection_player_id = m.player_a_id
                    THEN p.model_probability ELSE 1.0 - p.model_probability END AS p_a
        FROM predictions p JOIN matches m ON m.id = p.match_id
        WHERE m.match_date = ? AND p.id IN (SELECT MAX(id) FROM predictions GROUP BY match_id)
        """, (match_date,)).fetchall()
    return {r["match_id"]: r["p_a"] for r in rows
            if r["p_a"] is not None and abs(float(r["p_a"]) - 0.5) > 1e-12}


class _Match:
    """One fixture being priced: its meta, evidence context and hold estimates."""

    def __init__(self, conn, meta: dict, quotes: list, now: str):
        self.conn = conn
        self.meta = meta
        self.start = meta["start_time_utc"] or None
        self.label = f"{meta['a_name']} vs {meta['b_name']}"
        self.evidence = capture_context(conn, meta["id"], now, quotes)

    def holds(self, subject_id: int, *, fitted: bool) -> tuple[float, float] | None:
        """(subject hold, opponent hold); records both serve profiles in the evidence."""
        m = self.meta
        opponent_id = m["player_b_id"] if subject_id == m["player_a_id"] else m["player_a_id"]
        server = serve_return_profile(self.conn, subject_id, m["match_date"],
                                      surface=m["surface"], start_time=self.start)
        returner = serve_return_profile(self.conn, opponent_id, m["match_date"],
                                        surface=m["surface"], start_time=self.start)
        self.evidence["profiles"].setdefault("serve_return", {}).update(
            {str(p.player_id): asdict(p) for p in (server, returner)})
        if fitted:
            subject, opponent = estimate_hold_fitted(server, returner), estimate_hold_fitted(returner, server)
        else:
            subject = estimate_hold(server, returner, return_weight=0.35, elo_weight=0.04)
            opponent = estimate_hold(returner, server, return_weight=0.35, elo_weight=0.04)
        if not (subject.is_usable and opponent.is_usable):
            return None
        return round(subject.probability, 3), round(opponent.probability, 3)

    def simulate(self, subject_id: int):
        """Simulated match from the subject's side (subject = player 'a')."""
        holds = self.holds(subject_id, fitted=True)
        if holds is None:
            return None
        return simulate_match(holds[0], holds[1], trials=TRIALS, dispersion=FITTED_HOLD_GAP_DISPERSION)

    def named_player(self, market_name: str, family: str) -> tuple[int | None, str]:
        from tennis_wc.ingestion.ingest_odds import selection_side_for

        match = re.search(_PLAYER_NAME_IN_MARKET[family], market_name.strip(), re.I)
        who = match.group(1).strip() if match else ""
        if not who:
            return None, ""
        side = selection_side_for(self.meta["a_name"], self.meta["b_name"], who)
        if side == "player_a":
            return self.meta["player_a_id"], self.meta["a_name"]
        if side == "player_b":
            return self.meta["player_b_id"], self.meta["b_name"]
        return None, ""


# --------------------------------------------------------------------------- one priced market

class _Side:
    """Two-way price from side A's raw probability. Value is checked A first."""

    def __init__(self, raw_a: float, odds_a: float, odds_b: float, weight: float, profile):
        self.raw_a = raw_a
        self.odds_a, self.odds_b = odds_a, odds_b
        self.fair_a = market.devig(odds_a, odds_b)
        self.blended_a = market.blend(raw_a, self.fair_a, weight)
        self.strength = 1.0 - max(0.0, min(1.0, float(weight)))
        self.value = None
        if is_value_selection(raw_a, self.fair_a, odds_a, profile):
            self.value = "a"
        elif is_value_selection(1 - raw_a, 1 - self.fair_a, odds_b, profile):
            self.value = "b"

    def strip(self) -> None:
        self.value = None

    def rows(self, base: dict, a: dict, b: dict) -> list[dict]:
        """``a`` is always written (the scorecard row); ``b`` only when it is the value side."""
        raw_a, fair_a = round(self.raw_a, 4), round(self.fair_a, 4)
        blended_a = round(self.blended_a, 4)
        common = {"temper_strength": round(self.strength, 4)}
        a_value = self.value == "a"
        out = [{**base, **common, **a, "decimal_odds": round(self.odds_a, 3),
                "model_prob": blended_a, "model_prob_raw": raw_a, "market_prob_fair": fair_a,
                "blended_prob": blended_a,
                "edge": round(self.raw_a - self.fair_a, 4) if a_value else 0.0,
                "ev": round(self.raw_a * self.odds_a - 1, 4) if a_value else 0.0,
                "stake_units": 1.0 if a_value else 0.0, "is_value": a_value}]
        if self.value == "b":
            raw_b, fair_b = 1 - self.raw_a, 1 - self.fair_a
            out.append({**base, **common, **b, "decimal_odds": round(self.odds_b, 3),
                        "model_prob": round(1 - blended_a, 4),
                        "model_prob_raw": round(1 - raw_a, 4),
                        "market_prob_fair": round(1 - fair_a, 4),
                        "blended_prob": round(1 - self.blended_a, 4),
                        "edge": round(raw_b - fair_b, 4), "ev": round(raw_b * self.odds_b - 1, 4),
                        "stake_units": 1.0, "is_value": True})
        return out


def _feed(quote: dict, market_key, side_key: str, line=None) -> dict:
    """The bookmaker's own market/selection, so the row can be found again at the close."""
    name = quote.get(f"{side_key}_name") if side_key else None
    if not market_key or not name:
        return {"feed_market_key": None, "feed_market_name": None,
                "feed_selection_name": None, "feed_line": None}
    return {"feed_market_key": str(market_key), "feed_market_name": quote.get("market_name"),
            "feed_selection_name": str(name), "feed_line": float(line) if line is not None else None}


# --------------------------------------------------------------------------- closed-form fallbacks

def _player_games_closed_form(line: float, total_games: float, p_side: float) -> tuple[float, float]:
    share = max(0.34, min(0.66, 0.4187 + 0.1465 * p_side))
    mean = max(1.0, total_games * share + _PLAYER_GAMES_MEAN_BIAS)
    cdf = 0.5 * (1 + math.erf(((line + 0.5) - mean) / (_PLAYER_GAMES_SD * math.sqrt(2))))
    return max(0.03, min(0.97, 1 - cdf)), round(mean, 3)


def _game_handicap_closed_form(a_handicap: float, total_games: float, p_a: float) -> tuple[float, float]:
    total = max(1.0, float(total_games))
    share = max(0.34, min(0.66, 0.5 + (_GAME_MARGIN_SLOPE / (2.0 * total)) * (float(p_a) - 0.5)))
    margin = 2.0 * max(1.0, total * share) - total
    z = (-float(a_handicap) - margin) / _GAME_MARGIN_RESIDUAL_SD
    cover = 1.0 - 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
    cover = 0.5 + (cover - 0.5) * _GAME_HANDICAP_RAW_SHRINK
    return max(0.03, min(0.97, cover)), round(margin, 3)


# --------------------------------------------------------------------------- the date

def price_date(conn, match_date: str, now: str) -> list[dict]:
    """Rows for every priced prop on ``match_date`` (``now`` stamps the evidence)."""
    rows = q.rows_for_date(conn, match_date)
    by_match: dict[int, list] = {}
    for row in rows:
        by_match.setdefault(int(row["match_id"]), []).append(row)
    p_match = match_probabilities(conn, match_date)
    conflicts = conflicting_result_matches(conn)
    weights: dict[str, float] = {}

    def weight(family: str) -> float:
        if family not in weights:
            weights[family] = market.family_weight(conn, family, match_date)
        return weights[family]

    out: list[dict] = []
    for match_id, match_rows in by_match.items():
        meta = _match_meta(conn, match_id)
        if (not meta or "/" in str(meta["a_name"] or "") or "/" in str(meta["b_name"] or "")
                or match_id in conflicts or not _is_best_of_three(meta)):
            continue  # doubles, disputed results, or not a verified best-of-three
        if len({(str(r["bookmaker"]).strip().lower(), r["source_provider"]) for r in match_rows}) > 1:
            continue  # quotes from more than one source
        out.extend(_price_match(conn, _Match(conn, meta, match_rows, now), match_rows,
                                match_date, p_match.get(match_id), weight))
    return out


def _price_match(conn, m: _Match, match_rows, match_date, p_a, weight) -> list[dict]:
    meta = m.meta
    a_id, b_id = meta["player_a_id"], meta["player_b_id"]
    out: list[dict] = []

    def emit(rows: list[dict]) -> None:
        for row in rows:
            row["pricing_evidence_json"] = freeze_context(
                {**m.evidence, "context_captured_at": m.evidence["priced_at"], "priced_at": m.evidence["priced_at"]},
                row["feed_market_key"], row["feed_market_name"], row["feed_selection_name"], row["feed_line"])
            out.append(row)

    def base(market_key, line, scope, subject):
        return {"match_id": meta["id"], "match_date": match_date, "match_label": m.label,
                "market_key": market_key, "line": line, "prop_scope": scope,
                "subject_player_id": subject}

    outcomes = sets.outcome_distribution(float(p_a)) if p_a is not None else None
    fsm_quotes = q.first_set_match(match_rows, meta)
    fs_spreads = q.spreads(match_rows, meta, "player_first_set_game_handicap")
    first_set_sim = m.simulate(a_id) if (fsm_quotes or fs_spreads) else None
    quality_ok = (_feature_quality(conn, meta["id"]) >= MIN_DATA_QUALITY
                  and tier_of(meta["tournament_name"], meta["tournament_level"]) in BETTABLE_TIERS)
    hold_sum = combined_hold(conn, a_id, b_id, meta["match_date"], start_time=m.start)

    # Player total games.
    for (mk, market_name, line), quote in q.two_way(match_rows).items():
        if "over" not in quote or "under" not in quote:
            continue
        if family_for_market(mk, market_name) != "player_total_games":
            continue
        pid, pname = m.named_player(market_name, "player_total_games")
        if pid is None or p_a is None or line > MAX_PLAYER_GAMES_LINE:
            continue
        p_side = p_a if pid == a_id else 1 - p_a
        total_games = predict_total_games(p_a, best_of=3, hold_sum=hold_sum)
        if total_games is None:
            continue
        sim = m.simulate(pid)
        if sim is None:
            raw_over, mean = _player_games_closed_form(line, total_games, p_side)
        else:
            raw_over = max(0.03, min(0.97, sim.player_games_over_a(float(line))))
            mean = round(sum(sim.games_a) / sim.trials, 3)
        if (mean <= 0 or quote["over"] <= 1.0 or quote["under"] <= 1.0
                or line > 9.0 * mean or line < 0.3 * mean):
            continue
        key = f"player_total_games_{pid}_{line:g}"
        side = _Side(raw_over, quote["over"], quote["under"], weight("player_total_games"), value_profile(key))
        if not quality_ok or sim is None:
            side.strip()
        b = base(key, line, "player_games", pid)
        emit(side.rows({**b, "predicted_mean": mean},
                       {"selection": f"Over {line}", "side": "over", **_feed(quote, mk, "over", line)},
                       {"selection": f"Under {line}", "side": "under", **_feed(quote, mk, "under", line)}))

    # Player to win at least one set ("yes" side only).
    for (mk, market_name), quote in q.yes_no(match_rows).items():
        if "yes" not in quote or "no" not in quote or p_a is None:
            continue
        if family_for_market(mk, market_name) != "player_win_a_set":
            continue
        pid, _name = m.named_player(market_name, "player_win_a_set")
        if pid is None or quote["yes"] <= 1 or quote["no"] <= 1:
            continue
        raw_yes = 1.0 - float(outcomes["b20"]) if pid == a_id else 1.0 - float(outcomes["a20"])
        key = f"player_win_a_set_{pid}"
        side = _Side(raw_yes, quote["yes"], quote["no"], weight("player_win_a_set"), value_profile(key))
        if not quality_ok or side.value == "b":
            side.strip()
        b = base(key, 0.5, "player_win_set", pid)
        emit(side.rows({**b, "predicted_mean": round(raw_yes, 4)},
                       {"selection": "Yes", "side": "over", **_feed(quote, mk, "yes")}, {}))

    # First set winner.
    for (mk, _market_name), quote in q.first_set_winner(match_rows, meta).items():
        if "a" not in quote or "b" not in quote or p_a is None:
            continue
        holds = m.holds(a_id, fitted=False)
        if holds is None:
            raw_a = sets.outcome_distribution(p_a)["a_set1"]
        else:
            # Fixed holds (no per-match shift) for this market.
            raw_a = max(0.03, min(0.97, simulate_match(holds[0], holds[1], trials=TRIALS).first_set_winner_a()))
        if quote["a"] <= 1 or quote["b"] <= 1:
            continue
        side = _Side(raw_a, quote["a"], quote["b"], weight("first_set_winner"),
                     value_profile_for_family("first_set_winner"))
        if not quality_ok or holds is None:
            side.strip()
        common = {"line": 0.5, "prop_scope": "player_first_set", "match_id": meta["id"],
                  "match_date": match_date, "match_label": m.label}
        emit(side.rows(common,
                       {"market_key": f"first_set_winner_{a_id}", "selection": meta["a_name"], "side": "over",
                        "subject_player_id": a_id, "predicted_mean": round(raw_a, 4), **_feed(quote, mk, "a")},
                       {"market_key": f"first_set_winner_{b_id}", "selection": meta["b_name"], "side": "over",
                        "subject_player_id": b_id, "predicted_mean": round(1 - round(raw_a, 4), 4),
                        **_feed(quote, mk, "b")}))

    # Win first set and match: four outcomes, only "won the first set" may be staked.
    if fsm_quotes and first_set_sim is not None:
        emit(_first_set_match_rows(meta, m.label, match_date, fsm_quotes,
                                   first_set_sim.first_set_match_outcomes(),
                                   weight("player_first_set_match"), quality_ok))

    # Full-match game handicap.
    for abs_line, quote in q.spreads(match_rows, meta, "player_game_handicap").items():
        if p_a is None:
            continue
        total_games = predict_total_games(p_a, best_of=3, hold_sum=hold_sum)
        if total_games is None:
            continue
        sim = m.simulate(a_id)
        if sim is not None:
            raw_a = max(0.03, min(0.97, sim.game_handicap_cover_a(float(quote["a"]["handicap"]))))
            margin = round(sim.expected_margin(), 3)
        else:
            raw_a, margin = _game_handicap_closed_form(quote["a"]["handicap"], total_games, p_a)
        rows = _spread_rows(meta, m.label, match_date, f"player_game_handicap_{abs_line:g}",
                            "player_game_margin", quote, raw_a, margin, weight("player_game_handicap"),
                            strip=not quality_ok or sim is None)
        emit(rows)

    # First-set game handicap.
    for abs_line, quote in fs_spreads.items():
        if first_set_sim is None:
            continue
        raw_a = max(0.03, min(0.97, first_set_sim.first_set_game_handicap_cover_a(float(quote["a"]["handicap"]))))
        emit(_spread_rows(meta, m.label, match_date, f"player_first_set_game_handicap_{abs_line:g}",
                          "player_first_set_game_margin", quote, raw_a,
                          round(first_set_sim.expected_first_set_margin(), 3),
                          weight("player_first_set_game_handicap"), strip=not quality_ok))

    # Set handicap.
    for abs_line, quote in q.spreads(match_rows, meta, "player_set_handicap").items():
        if p_a is None:
            continue
        raw_a, margin = sets.set_handicap_cover(quote["a"]["handicap"], outcomes)
        emit(_spread_rows(meta, m.label, match_date, f"player_set_handicap_{abs_line:g}",
                          "player_set_margin", quote, raw_a, margin, weight("player_set_handicap"),
                          strip=not quality_ok))
    return out


def _spread_rows(meta, label, match_date, market_key, scope, quote, raw_a_cover, margin, weight, *, strip):
    a_h, b_h = float(quote["a"]["handicap"]), float(quote["b"]["handicap"])
    a_odds, b_odds = quote["a"]["odds"], quote["b"]["odds"]
    if a_odds <= 1 or b_odds <= 1 or abs(a_h + b_h) > 1e-9 or abs(abs(a_h) % 1.0 - 0.5) > 1e-9:
        return []
    raw_a = max(0.001, min(0.999, float(raw_a_cover)))
    side = _Side(raw_a, a_odds, b_odds, weight, value_profile(market_key))
    if strip:
        side.strip()
    a_h, b_h = round(a_h, 3), round(b_h, 3)
    mk = quote.get("market_key")
    # Both rows settle on player A's margin: A covers over -a_h, B on the under.
    base = {"match_id": meta["id"], "match_date": match_date, "match_label": label,
            "market_key": market_key, "line": -a_h, "prop_scope": scope,
            "subject_player_id": meta["player_a_id"], "predicted_mean": round(float(margin), 3)}
    return side.rows(base,
                     {"selection": f"{meta['a_name']} ({a_h:+g})", "side": "over", **_feed(quote, mk, "a", a_h)},
                     {"selection": f"{meta['b_name']} ({b_h:+g})", "side": "under", **_feed(quote, mk, "b", b_h)})


def _first_set_match_rows(meta, label, match_date, quotes, probs, weight, quality_ok) -> list[dict]:
    keys = ("a_win", "a_lose", "b_win", "b_lose")
    try:
        odds = {k: float(quotes[k]["odds"]) for k in keys}
        raw = {k: float(probs[k]) for k in keys}
    except (TypeError, ValueError, KeyError):
        return []
    if (any(v <= 1 for v in odds.values()) or any(v < 0 or v > 1 for v in raw.values())
            or abs(sum(raw.values()) - 1.0) > 1e-6):
        return []
    inverse = sum(1.0 / v for v in odds.values())
    fair = {k: 1.0 / odds[k] / inverse for k in keys}
    blended = {k: market.blend(raw[k], fair[k], weight) for k in keys}
    strength = 1.0 - max(0.0, min(1.0, float(weight)))
    profile = value_profile_for_family("player_first_set_match")
    rows = []
    for k in keys:
        player_id, name = ((meta["player_a_id"], meta["a_name"]) if k[0] == "a"
                           else (meta["player_b_id"], meta["b_name"]))
        won_first = k.endswith("_win")
        is_value = quality_ok and won_first and is_value_selection(raw[k], fair[k], odds[k], profile)
        source = quotes[k]
        rows.append({
            "match_id": meta["id"], "match_date": match_date, "match_label": label,
            "market_key": f"player_first_set_match_{player_id}_{'win_first' if won_first else 'lose_first'}",
            "line": 0.5,
            "selection": f"{name} {'Win' if won_first else 'Lose'} 1st Set & Win Match",
            "side": "over", "prop_scope": "player_first_set_match", "subject_player_id": player_id,
            "decimal_odds": round(odds[k], 3), "model_prob": round(blended[k], 4),
            "model_prob_raw": round(raw[k], 4), "temper_strength": round(strength, 4),
            "market_prob_fair": round(fair[k], 4), "blended_prob": round(blended[k], 4),
            "edge": round(raw[k] - fair[k], 4) if is_value else 0.0,
            "ev": round(raw[k] * odds[k] - 1.0, 4) if is_value else 0.0,
            "predicted_mean": round(raw[k], 4),
            "stake_units": 1.0 if is_value else 0.0, "is_value": is_value,
            "feed_market_key": source["market_key"], "feed_market_name": source["market_name"],
            "feed_selection_name": source["selection_name"], "feed_line": None,
        })
    return rows
