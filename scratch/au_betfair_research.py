#!/usr/bin/env python3
"""AU Betfair offline research harness (Phase 1 — zero live API).

Consumes Betfair's FREE historical BSP CSV files (promotions.betfair.com/
betfairsp/prices/), joins them to our archive by (date, track, horse), and:
  1. re-runs the model's win-bet ROI at Betfair SP (BSP) instead of bookmaker
     SP — the decisive test of whether the tight-tier rank-1 edge (+16.8% at
     SP, CI included zero) is real once the ~15-20% bookmaker margin is gone;
  2. exposes traded-volume / weight-of-money columns as a candidate NEW
     feature source (money flow), the first signal orthogonal to our matrix.

Betfair AUS win-market BSP CSV columns (documented format):
  EVENT_ID, MENU_HINT, EVENT_NAME, SELECTION_ID, SELECTION_NAME, WIN_LOSE,
  BSP, PPWAP, MORNINGWAP, PPMAX, PPMIN, IPMAX, IPMIN,
  MORNINGTRADEDVOL, PPTRADEDVOL, IPTRADEDVOL
  - MENU_HINT e.g. "AUS / Rosehill (AUS) 27th Jun"
  - EVENT_NAME e.g. "R1 1100m Mdn"
  - SELECTION_NAME e.g. "1. Mother Goose" (may carry a number prefix)
  - BSP: exchange starting price (no bookmaker margin)
  - PPWAP: pre-post weighted-avg traded price; *TRADEDVOL: money matched

Usage:
  python3 scratch/au_betfair_research.py --bsp-dir <dir-of-csvs>
  python3 scratch/au_betfair_research.py --selftest   # parser check, no data
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, "/Users/imac/Antigravity-repo")
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/au_racing/au_wong_choi_auto/scripts")
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/shared_racing")

MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def norm_name(name: str) -> str:
    # strip a leading "N. " selection prefix, then match au_archive normalize
    name = re.sub(r"^\s*\d+\.?\s*", "", str(name or ""))
    return re.sub(r"[^a-z0-9]", "", name.lower())


def parse_menu_hint(hint: str) -> tuple[str | None, str | None]:
    """Real format 'Eagle Farm (AUS) 30th May' (older: 'AUS / Rosehill (AUS)
    27th Jun') -> (track_norm, 'MM-DD'). Leading 'AUS /' is optional."""
    m = re.search(r"(?:/\s*)?([A-Za-z][A-Za-z .'-]+?)\s*\(AUS\)\s*(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3})",
                  hint or "")
    if not m:
        return None, None
    track = re.sub(r"[^a-z0-9]", "", m.group(1).lower())
    day, mon = int(m.group(2)), MONTHS.get(m.group(3)[:3].title())
    return (track, f"{mon:02d}-{day:02d}") if mon else (track, None)


def _ci(row: dict, key: str):
    # real files use lowercase headers; be case-insensitive
    return row.get(key) or row.get(key.upper()) or row.get(key.lower())


def load_bsp(bsp_dir: Path) -> tuple[dict, int]:
    """-> {(mmdd, track_norm, horse_norm): row_dict}. Keyed by the menu_hint
    race date (MM-DD), which is robust to Betfair's filename+1 settlement offset."""
    out = {}
    files = sorted(bsp_dir.glob("dwbfprices*win*.csv"))
    for fp in files:
        with fp.open(encoding="utf-8-sig", errors="replace") as f:
            for row in csv.DictReader(f):
                track, mmdd = parse_menu_hint(_ci(row, "menu_hint") or "")
                if not track or not mmdd:
                    continue
                horse = norm_name(_ci(row, "selection_name") or "")
                if horse:
                    out[(mmdd, track, horse)] = row
    return out, len(files)


def _bsp_key(date: str, track: str, horse: str) -> tuple:
    return (date[5:], re.sub(r"[^a-z0-9]", "", track.lower()), horse)


def run(bsp_dir: Path) -> int:
    from au_cached_walkforward_ml import materialize_dataset, group_races, as_float
    from au_archive_calibrator import normalize_horse_name

    bsp, nfiles = load_bsp(bsp_dir)
    print(f"loaded {len(bsp)} BSP selections from {nfiles} files")
    races = group_races(materialize_dataset())

    def tier_gap(race):
        s = sorted((as_float(r["ability_score"], 60) for r in race), reverse=True)
        return (s[0] - s[2]) if len(s) >= 3 else 99.0

    joined = missed = 0
    strat = defaultdict(lambda: {"bets": 0, "sp_ret": 0.0, "bsp_ret": 0.0, "wins": 0})
    overround = []
    for race in races:
        first = race[0]
        track = str(first.get("track") or "")
        gap = tier_gap(race)
        t = "tight" if gap < 2 else ("medium" if gap < 5 else "clear")
        ranked = sorted(race, key=lambda r: (-as_float(r["ability_score"], 60), int(r["horse_number"])))
        # overround proxy: sum(1/BSP) over the field
        inv = []
        for r in race:
            row = bsp.get(_bsp_key(str(first["date"]), track, normalize_horse_name(str(r.get("horse_name") or ""))))
            if row:
                try:
                    inv.append(1.0 / float(row["BSP"]))
                except (ValueError, ZeroDivisionError, KeyError):
                    pass
        if inv:
            overround.append(sum(inv))
        for rank, r in enumerate(ranked[:2], 1):
            row = bsp.get(_bsp_key(str(first["date"]), track, normalize_horse_name(str(r.get("horse_name") or ""))))
            if not row:
                missed += 1
                continue
            joined += 1
            try:
                bsp_price = float(row["BSP"])
                won = str(row.get("WIN_LOSE", "")).strip() in ("1", "1.0")
            except (ValueError, KeyError):
                continue
            for label in (f"{t} rank{rank}", f"ALL rank{rank}"):
                s = strat[label]
                s["bets"] += 1
                if won:
                    s["wins"] += 1
                    s["bsp_ret"] += bsp_price  # Betfair BSP already net of commission? apply below
    print(f"joined {joined} model picks to BSP, missed {missed} "
          f"({100*joined/max(1,joined+missed):.0f}% coverage)")
    if overround:
        import statistics as st
        print(f"median field overround (Σ 1/BSP): {st.median(overround):.3f} "
              f"(1.00 = zero margin; bookmaker SP ~1.20-1.25)")
    COMMISSION = 0.05  # Betfair AU commission on net winnings
    print(f"\nWIN bets at BSP (5% commission on winnings), flat $1:")
    print(f"{'strategy':<16}{'bets':>6}{'strike':>8}{'ROI@BSP':>10}")
    for label in ("tight rank1", "clear rank1", "medium rank1", "ALL rank1", "ALL rank2"):
        s = strat[label]
        if not s["bets"]:
            continue
        gross = s["bsp_ret"] - s["wins"]  # net winnings before stake
        ret = s["wins"] + gross * (1 - COMMISSION)  # returned incl stake, post-commission
        roi = ret / s["bets"] - 1
        print(f"{label:<16}{s['bets']:>6}{100*s['wins']/s['bets']:>7.1f}%{100*roi:>+9.1f}%")
    return 0


def selftest() -> int:
    sample = {
        "MENU_HINT": "AUS / Rosehill (AUS) 27th Jun",
        "EVENT_NAME": "R1 1100m Mdn",
        "SELECTION_NAME": "7. Mother Goose",
        "WIN_LOSE": "0", "BSP": "12.5", "PPWAP": "11.8", "PPTRADEDVOL": "48210",
    }
    track, mmdd = parse_menu_hint(sample["MENU_HINT"])
    assert track == "rosehill" and mmdd == "06-27", (track, mmdd)
    assert norm_name(sample["SELECTION_NAME"]) == "mothergoose"
    assert _bsp_key("2026-06-27", "Rosehill Gardens", "mothergoose")[0] == "06-27"
    # NOTE: 'Rosehill' (BSP) vs 'Rosehill Gardens' (archive) — track join needs
    # an alias map; flagged for the real run.
    print("selftest OK — parser + key logic verified on synthetic row")
    print("KNOWN JOIN CAVEAT: Betfair track names ('Rosehill') differ from archive "
          "('Rosehill Gardens') — an alias map is required before ROI is trusted.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bsp-dir", type=Path)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if args.bsp_dir:
        return run(args.bsp_dir)
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
