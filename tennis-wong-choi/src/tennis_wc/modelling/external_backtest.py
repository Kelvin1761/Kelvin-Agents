"""
Clean walk-forward backtest of the match-winner model against REAL Pinnacle
closing odds from tennis-data.co.uk (free, no API key, no trial).

Why this exists: our own scraped market_odds + live predictions are too few and
not temporally aligned for honest validation. tennis-data.co.uk publishes, per
season, every ATP/WTA main-tour match with set scores AND closing odds
(Pinnacle PSW/PSL, Bet365 B365W/B365L). We rebuild Elo walk-forward (same
decayed-K curve the production model uses), devig the closing line, and measure
whether the model's edges actually beat the close (CLV) and turn a profit (ROI)
out of sample.

Everything here is deterministic and self-contained: it does NOT touch the
production DB or our scraped odds, so it is leakage-free by construction (Elo is
built only from matches strictly before each bet, in date order).
"""
from __future__ import annotations

import math
import urllib.request
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from tennis_wc.features.elo import elo_probability
from tennis_wc.features.market import remove_vig_two_way
from tennis_wc.modelling.calibration import elo_k_factor

CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "external"
_ATP_URL = "http://www.tennis-data.co.uk/{year}/{year}.xlsx"
_WTA_URL = "http://www.tennis-data.co.uk/{year}w/{year}.xlsx"


def _download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 tennis-wc-backtest"})
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 (trusted static host)
        data = resp.read()
    dest.write_bytes(data)
    return dest


def _parse_xlsx(path: Path, tour: str) -> list[dict]:
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows = ws.iter_rows(values_only=True)
    header = [str(h).strip() if h is not None else "" for h in next(rows)]
    idx = {name: i for i, name in enumerate(header)}

    def col(row, name):
        i = idx.get(name)
        return row[i] if i is not None and i < len(row) else None

    out: list[dict] = []
    for row in rows:
        if not any(row):
            continue
        winner = col(row, "Winner")
        loser = col(row, "Loser")
        if not winner or not loser:
            continue
        date_raw = col(row, "Date")
        match_date = _to_date(date_raw)
        if match_date is None:
            continue
        psw = _to_float(col(row, "PSW"))
        psl = _to_float(col(row, "PSL"))
        # Bet365 fallback when Pinnacle missing.
        if psw is None or psl is None:
            psw = psw or _to_float(col(row, "B365W"))
            psl = psl or _to_float(col(row, "B365L"))
        comment = str(col(row, "Comment") or "").strip().lower()
        total_games = _total_games(row, col)
        w_sets = _to_float(col(row, "Wsets"))
        l_sets = _to_float(col(row, "Lsets"))
        out.append(
            {
                "tour": tour,
                "date": match_date,
                "surface": str(col(row, "Surface") or "").strip().lower() or None,
                "best_of": int(_to_float(col(row, "Best of")) or 3),
                "winner": str(winner).strip(),
                "loser": str(loser).strip(),
                "winner_odds": psw,
                "loser_odds": psl,
                "completed": comment == "completed",
                "total_games": total_games,
                "set_margin": (int(w_sets) - int(l_sets)) if (w_sets is not None and l_sets is not None) else None,
            }
        )
    out.sort(key=lambda r: r["date"])
    return out


def _total_games(row, col) -> int | None:
    total = 0
    seen = False
    for s in range(1, 6):
        w = _to_float(col(row, f"W{s}"))
        l = _to_float(col(row, f"L{s}"))
        if w is None or l is None:
            continue
        total += int(w) + int(l)
        seen = True
    return total if seen else None


def _to_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_date(value):
    if isinstance(value, datetime):
        return value.date()
    if value is None:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(str(value).strip(), fmt).date()
        except ValueError:
            continue
    return None


def load_matches(years: list[int], tours: tuple[str, ...] = ("ATP", "WTA")) -> list[dict]:
    matches: list[dict] = []
    for year in years:
        for tour in tours:
            url = (_ATP_URL if tour == "ATP" else _WTA_URL).format(year=year)
            dest = CACHE_DIR / f"tennisdata_{tour.lower()}_{year}.xlsx"
            try:
                _download(url, dest)
                matches.extend(_parse_xlsx(dest, tour))
            except Exception as exc:  # noqa: BLE001
                print(f"[warn] {tour} {year}: {exc}")
    matches.sort(key=lambda r: r["date"])
    return matches


def run_match_winner_backtest(
    years: list[int],
    tours: tuple[str, ...] = ("ATP", "WTA"),
    surface_blend: float = 0.65,
    k_factor: float | None = None,
    min_edge: float = 0.03,
    kelly_fraction_value: float = 0.5,
    warmup_matches: int = 1500,
    mov_weight: bool = False,
) -> dict:
    """
    Walk-forward Elo -> devig closing odds -> bet on +edge side, half-Kelly.

    k_factor=None uses the production decayed-K curve; pass a float for a flat-K
    A/B comparison. warmup_matches skips early matches while Elo stabilises.
    """
    matches = load_matches(years, tours)
    overall: dict[str, float] = defaultdict(lambda: 1500.0)
    surface: dict[str, dict[str, float]] = defaultdict(dict)
    o_count: dict[str, int] = defaultdict(int)
    s_count: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def k_for(n: int) -> float:
        return float(k_factor) if k_factor is not None else elo_k_factor(n)

    brier_sum = log_sum = 0.0
    scored = hits = 0
    bets = wins = 0
    staked = pnl = 0.0
    edge_sum = edge_n = 0
    bins: dict[str, list[float]] = defaultdict(list)
    bin_out: dict[str, list[float]] = defaultdict(list)
    processed = 0

    for m in matches:
        w, l, surf = m["winner"], m["loser"], m["surface"]
        wo, lo = overall[w], overall[l]
        ws = surface[w].get(surf, wo) if surf else wo
        ls = surface[l].get(surf, lo) if surf else lo
        p_overall = elo_probability(wo, lo)
        p_surface = elo_probability(ws, ls)
        p_winner = max(0.001, min(0.999, surface_blend * p_surface + (1 - surface_blend) * p_overall))

        if processed >= warmup_matches and m["completed"]:
            # Calibration / accuracy vs the actual outcome (winner always won).
            brier_sum += (1 - p_winner) ** 2
            log_sum += -math.log(p_winner)
            scored += 1
            hits += 1 if p_winner >= 0.5 else 0
            fav_p = max(p_winner, 1 - p_winner)
            key = f"{int(fav_p * 10) / 10:.1f}"
            bins[key].append(fav_p)
            bin_out[key].append(1.0 if p_winner >= 0.5 else 0.0)

            # Betting vs the closing line (devig Pinnacle).
            if m["winner_odds"] and m["loser_odds"] and m["winner_odds"] > 1 and m["loser_odds"] > 1:
                nv_w, nv_l = remove_vig_two_way(1 / m["winner_odds"], 1 / m["loser_odds"])
                edge_w = p_winner - nv_w
                edge_l = (1 - p_winner) - nv_l
                # bet the higher-edge side if it clears the threshold
                if edge_w >= edge_l and edge_w > min_edge:
                    odds, p, won, nv = m["winner_odds"], p_winner, True, nv_w
                elif edge_l > min_edge:
                    odds, p, won, nv = m["loser_odds"], 1 - p_winner, False, nv_l
                else:
                    odds = None
                if odds is not None:
                    b = odds - 1
                    f = max(0.0, (p * b - (1 - p)) / b) * kelly_fraction_value
                    if f > 0:
                        bets += 1
                        staked += f
                        pnl += f * (odds - 1) if won else -f
                        wins += 1 if won else 0
                        edge_sum += (p - nv)
                        edge_n += 1

        # Update Elo (winner beat loser), optionally scaled by margin of victory.
        e = elo_probability(wo, lo)
        mov = 1.0
        if mov_weight and m.get("set_margin"):
            # FiveThirtyEight-style: bigger margin -> bigger update, dampened when
            # a strong favourite wins big (expected).
            mov = math.log(abs(int(m["set_margin"])) + 1) * (2.2 / ((wo - lo) * 0.001 + 2.2))
            mov = max(0.5, min(2.0, mov))
        overall[w] = wo + k_for(o_count[w]) * mov * (1 - e)
        overall[l] = lo + k_for(o_count[l]) * mov * (0 - (1 - e))
        o_count[w] += 1
        o_count[l] += 1
        if surf:
            es = elo_probability(ws, ls)
            surface[w][surf] = ws + k_for(s_count[w][surf]) * (1 - es)
            surface[l][surf] = ls + k_for(s_count[l][surf]) * (0 - (1 - es))
            s_count[w][surf] += 1
            s_count[l][surf] += 1
        processed += 1

    calib = [
        {
            "bin": f"{k}-{round(float(k) + 0.1, 1)}",
            "n": len(v),
            "pred": round(sum(v) / len(v), 4),
            "actual": round(sum(bin_out[k]) / len(bin_out[k]), 4),
        }
        for k, v in sorted(bins.items())
        if v
    ]
    return {
        "years": years,
        "tours": list(tours),
        "k": "decayed" if k_factor is None else f"flat_{k_factor}",
        "total_matches": len(matches),
        "scored_matches": scored,
        "favorite_accuracy": round(hits / scored, 4) if scored else None,
        "brier_score": round(brier_sum / scored, 6) if scored else None,
        "log_loss": round(log_sum / scored, 6) if scored else None,
        "bets": bets,
        "bet_win_rate": round(wins / bets, 4) if bets else None,
        "roi_half_kelly": round(pnl / staked, 4) if staked else None,
        "total_staked_units": round(staked, 2),
        "pnl_units": round(pnl, 2),
        # PERCEIVED edge (model_prob - no_vig_close), NOT realised CLV. Positive
        # here just means we thought we had an edge; the ROI shows whether it was
        # real against the closing line.
        "avg_perceived_edge": round(edge_sum / edge_n, 4) if edge_n else None,
        "min_edge": min_edge,
        "calibration_bins": calib,
    }
