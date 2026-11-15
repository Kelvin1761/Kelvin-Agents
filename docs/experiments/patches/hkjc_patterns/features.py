"""EXP-20261115-10 特徵表：每匹馬每仗嘅 pattern flag（只用日期早過今仗嘅 HKJC 馬匹頁＋賽果）。
key = (日期, 場次, 名次) → {flag: 0/1}。"""
import gzip
import json
import sys
from collections import defaultdict
from datetime import date

sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")


def iso(dmy):
    d, m, y = dmy.split("/")
    return f"{y}-{m}-{d}"


def num(x):
    try:
        return float(str(x).strip())
    except ValueError:
        return None


def pos(x):
    s = str(x or "").strip()
    return int(s) if s.isdigit() else None


def load():
    runs, prof = defaultdict(list), {}
    for line in gzip.open("/Volumes/Kelvin Hardisk 1/WongChoi-Archive/hkjc-history/parsed/horses.jsonl.gz", "rt", encoding="utf-8"):
        r = json.loads(line)
        code = r["horse_id"].rsplit("_", 1)[-1]
        prof[code] = r.get("profile") or {}
        for x in r.get("runs") or []:
            try:
                x["d"] = iso(x["date"])
            except Exception:
                continue
            runs[code].append(x)
    for v in runs.values():
        v.sort(key=lambda x: x["d"])
    return runs, prof


def build():
    import hkjc_history_replay_pit as p
    df = p.load_all_rows_extended()
    df = df[df["Rank"].notna()]
    runs, prof = load()
    combos = defaultdict(int)    # (trainer, jockey) 之前合作次數 —— 按日期順序累積
    out = {}
    df = df.assign(d=df["Date"].astype(str).str[:10]).sort_values(["d", "RaceNo"])
    ratings = defaultdict(dict)  # (d, race) -> {hid: rating}
    for hid, rr in runs.items():
        for q in rr:
            pass
    pending = []
    for d, g in df.groupby("d", sort=True):
        for r in g.itertuples():
            hid = r.HorseID
            past = [q for q in runs.get(hid, []) if q["d"] < d]
            today = next((q for q in runs.get(hid, []) if q["d"] == d), None)
            f = {}
            if not past:
                imp = str(prof.get(hid, {}).get("進口類別", ""))
                f["pp_import_debut"] = int(imp == "自購馬")
                f["griffin_debut"] = int(imp == "自購新馬")
            elif today:
                last = past[-1]
                gap = (date.fromisoformat(d) - date.fromisoformat(last["d"])).days
                lo = num(last.get("win_odds"))
                lv, tv = str(last.get("venue_track", ""))[:2], str(today.get("venue_track", ""))[:2]
                tc, lc = num(today.get("class")), num(last.get("class"))
                tj, lj = today.get("jockey"), last.get("jockey")
                tg = [x for x in str(today.get("gear") or "").split("/") if x]
                f["prevfav_layoff90"] = int(lo is not None and lo <= 5 and gap >= 90)
                f["prevfav_venue"] = int(lo is not None and lo <= 5 and bool(lv) and bool(tv) and lv != tv)
                f["prevlong_placed"] = int(lo is not None and lo >= 20 and (pos(last.get("pos")) or 99) <= 3)
                f["classdrop_jchange"] = int(bool(tc and lc and tc > lc and tj and lj and tj != lj))
                f["stable_switch"] = int(bool(today.get("trainer") and last.get("trainer") and today["trainer"] != last["trainer"]))
                f["gear_removed"] = int(any(x.endswith("-") for x in tg))
                f["gear_first"] = int(any(x.endswith("1") for x in tg))
                # 深挖
                bw, lbw = num(today.get("body_wt")), num(last.get("body_wt"))
                f["bodywt_big_change"] = int(bw is not None and lbw is not None and abs(bw - lbw) >= 15)
                f["quick_backup14"] = int(gap <= 14)
                f["layoff90"] = int(gap >= 90)
                prep = 1
                for a, b in zip(reversed(past[:-1]), reversed(past)):
                    if (date.fromisoformat(b["d"]) - date.fromisoformat(a["d"])).days >= 90:
                        break
                    prep += 1
                f["third_up"] = int(gap < 90 and prep == 2)
                ld, td = num(last.get("distance")), num(today.get("distance"))
                f["dist_up200"] = int(bool(ld and td and td - ld >= 200))
                f["dist_down200"] = int(bool(ld and td and ld - td >= 200))
                f["first_awt"] = int("全天候" in str(today.get("venue_track")) and not any("全天候" in str(q.get("venue_track")) for q in past))
                f["first_venue"] = int(bool(tv) and not any(str(q.get("venue_track", ""))[:2] == tv for q in past))
                f["two_placed"] = int(len(past) >= 2 and all((pos(q.get("pos")) or 99) <= 3 for q in past[-2:]))
                lbw_ = str(last.get("lbw") or "").strip()
                f["last_close_2nd_3rd"] = int((pos(last.get("pos")) or 99) in (2, 3) and lbw_ in ("頸", "短頭", "頭", "1/2", "3/4", "1", "1-1/4"))
                f["new_tj_combo"] = int(combos[(r.Trainer, r.Jockey)] == 0)
                tr = num(today.get("rating"))
                if tr is not None:
                    ratings[(d, int(r.RaceNo))][(int(r.Rank))] = tr
            out.setdefault((d, int(r.RaceNo), int(r.Rank)), []).append(f)
        for r in g.itertuples():
            combos[(r.Trainer, r.Jockey)] += 1
    for (d, rn), rk in ratings.items():
        if len(rk) >= 6:
            top = max(rk.values())
            for rank, v in rk.items():
                fs = out.get((d, rn, rank))
                if fs and len(fs) == 1:
                    fs[0]["top_rated"] = int(v == top)
    return out
