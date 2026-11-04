#!/usr/bin/env python3
"""EXP-20261104-10 數據集：儲存咗嘅賽前預測 × 落注時見到嘅 Sportsbet 價 × Betfair BSP × 賽果。

    python3 scratch/au_betting_edge_dataset_20261104.py BSP_DIR OUT.json

模型同賽果規則照 `au_window_review.build_dataset`（開跑前最後一個預測快照；退出馬剔走）。
另砌「晚更」版本（賽日之前最後一個快照）。Sportsbet 價：`Odds.json` 入面 captured_at 早過開跑、
唔早過所用預測快照嘅第一個快照（冇就用開跑前最後一個，標 `stale`）。BSP 只作價，唔入模型。
"""
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

W = Path(__file__).resolve().parents[1]
S = W / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(S))
import au_window_review as wr  # noqa: E402

SCHED = Path("/Users/imac/wongchoi-scheduler/.agents/skills/au_racing/data/sb_archive_meeting_ids.json")
CACHE = Path("/Users/imac/Antigravity-repo/.agents/skills/au_racing/.sportsbet_cache")
SINCE, UNTIL = "2026-08-05", "2026-11-03"
MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                                      "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def norm(text):
    return re.sub(r"[^a-z0-9]", "", re.sub(r"^\s*\d+\.\s*", "", str(text or "")).lower())


def load_bsp(bsp_dir):
    """→ {(date, horse_norm): [row…]} 同 {(date, venue_norm, race, horse_norm): row}；row = {win, place, won, placed}。"""
    by_key, by_horse = {}, defaultdict(list)
    race_at = {}   # (場地, event_dt) → 場次號：位市場個 event_name 係「To Be Placed」，冇場次號，要由贏市場對返
    for kind in ("win", "place"):
        for path in sorted(Path(bsp_dir).glob(f"dwbfpricesaus{kind}*.csv")):
            with open(path, newline="", encoding="utf-8", errors="replace") as fh:
                for r in csv.DictReader(fh):
                    m = re.match(r"(.+?) \(AUS\) (\d+)\w* (\w{3})", r.get("menu_hint") or "")
                    rn = re.match(r"R(\d+)\b", r.get("event_name") or "")
                    if not m or m.group(3) not in MONTHS:
                        continue
                    slot = (norm(m.group(1)), r.get("event_dt"))
                    if kind == "win" and rn:
                        race_at[slot] = int(rn.group(1))
                    race_no = int(rn.group(1)) if rn else race_at.get(slot)
                    if race_no is None:
                        continue
                    date = f"2026-{MONTHS[m.group(3)]:02d}-{int(m.group(2)):02d}"
                    key = (date, norm(m.group(1)), race_no, norm(r.get("selection_name")))
                    rec = by_key.setdefault(key, {"venue_bf": m.group(1)})
                    try:
                        price = float(r.get("bsp") or 0) or None
                    except ValueError:
                        price = None
                    rec[kind] = price
                    rec["won" if kind == "win" else "placed"] = r.get("win_lose") == "1"
    for key, rec in by_key.items():
        by_horse[(key[0], key[3])].append((key, rec))
    return by_key, by_horse


def odds_snapshots(meeting):
    try:
        snaps = json.loads((meeting / "Odds.json").read_text(encoding="utf-8")).get("snapshots") or []
    except (OSError, ValueError):
        return []
    out = []
    for s in snaps:
        try:
            out.append((datetime.fromisoformat(s["captured_at"]), s.get("races") or {}))
        except (KeyError, ValueError):
            continue
    return sorted(out, key=lambda x: x[0])


def pick_price(snaps, race_no, model_time, start):
    """第一個 model_time ≤ captured < start 嘅快照；冇就 start 之前最後一個（stale）。"""
    usable = [(t, r) for t, r in snaps if (start is None or t < start) and str(race_no) in r]
    if not usable:
        return None, None, ""
    after = [(t, r) for t, r in usable if model_time is None or t >= model_time]
    t, r = (after[0], "fresh") if after else (usable[-1], "stale")
    return t[1][str(race_no)], t[0].isoformat(), r


def main():
    bsp_dir, out = Path(sys.argv[1]), Path(sys.argv[2])
    by_key, by_horse = load_bsp(bsp_dir)
    starts = wr.load_start_times(SCHED, CACHE)
    root = wr.AU_RACING
    csv_idx = wr.load_results_csv(wr.au_historical_results_csv(root), SINCE, UNTIL)
    lag = timedelta(minutes=30)   # 同一轉 run 先抓價後評分：價最多遲預測 30 分鐘都當係落注嗰刻見到
    scen = {k: {"stats": Counter(), "races": []} for k in ("early", "late")}

    def bsp_for(r, x, stats):
        bf = by_key.get((r["date"], norm(r["venue"]), r["race"], norm(x["name"])))
        if bf is None:
            cands = [rec for k, rec in by_horse.get((r["date"], norm(x["name"])), []) if k[2] == r["race"]]
            bf = cands[0] if len(cands) == 1 else None
            stats["bsp_fallback" if bf else "bsp_miss"] += 1
        else:
            stats["bsp_exact"] += 1
        return bf or {}

    for meeting in wr.meeting_dirs(root):
        day = meeting.name[:10]
        if not (SINCE <= day <= UNTIL):
            continue
        stamped = wr.stamped_snapshots(meeting)
        real = starts(meeting.name)
        odds = odds_snapshots(meeting)
        results = wr.parse_reflector_results(meeting / "Race_Results_Reflector.md")
        numbers = sorted({int(m.group(1)) for _, snap in stamped for q in snap.glob("Race_*_Logic.json")
                          if (m := re.match(r"Race_(\d+)_Logic", q.name))})
        for race_no in numbers:
            start = real.get(race_no)
            rule = "start_time" if start else "cutoff_11"
            start = start or datetime.fromisoformat(day + "T11:00:00").replace(tzinfo=wr.SYD)
            pre = [(t, p) for t, p in stamped if t < start]
            for kind, pick in (("early", pre[:1]), ("late", pre[-1:])):
                st = scen[kind]["stats"]
                if not pick:
                    st["no_snapshot"] += 1
                    continue
                t_model, snap = pick[0]
                caps = [(t, rs) for t, rs in odds if t <= t_model + lag and t < start and str(race_no) in rs]
                price_t, prices = (caps[-1][0], caps[-1][1][str(race_no)]) if caps else (None, {})
                st["price_ok" if caps else "price_none"] += 1
                r = wr.build_race(meeting, snap, race_no, day, results, csv_idx)
                if not r or "skip" in r:
                    st["skip_" + ((r or {}).get("skip") or "bad_logic")] += 1
                    continue
                rows = []
                for x in r["rows"]:
                    bf = bsp_for(r, x, st)
                    sb = prices.get(str(x["n"])) or {}
                    rows.append({"n": x["n"], "name": x["name"], "rank": x["rank"], "score": x["score"],
                                 "pos": x["pos"], "sp": x["sp"], "sb_win": sb.get("Sportsbet-FixedWin"),
                                 "sb_place": sb.get("Sportsbet-FixedPlace"), "bsp_win": bf.get("win"),
                                 "bsp_place": bf.get("place"), "bf_placed": bf.get("placed")})
                ran = {str(x["n"]) for x in r["rows"]}
                scr = [v for hn, v in prices.items() if hn not in ran]
                st["races"] += 1
                scen[kind]["races"].append(
                    {k: r[k] for k in ("meeting", "date", "venue", "race", "state", "tier", "class", "distance",
                                       "going_family", "field")}
                    | {"start": start.isoformat(), "start_rule": rule, "model_time": t_model.isoformat(),
                       "snapshot": snap.name, "price_time": price_t.isoformat() if price_t else None,
                       # 落注之後先退出嘅馬嘅價 —— 澳洲定額注中咗要按佢扣減（scratching deduction）
                       "scratched_win": [v.get("Sportsbet-FixedWin") for v in scr if v.get("Sportsbet-FixedWin")],
                       "scratched_place": [v.get("Sportsbet-FixedPlace") for v in scr if v.get("Sportsbet-FixedPlace")],
                       "rows": rows})
    for kind, v in scen.items():
        v["stats"] = dict(v["stats"])
        print(kind, json.dumps(v["stats"]))
    out.write_text(json.dumps({"since": SINCE, "until": UNTIL, "lag_minutes": 30, "scenarios": scen},
                              ensure_ascii=False))


if __name__ == "__main__":
    main()
