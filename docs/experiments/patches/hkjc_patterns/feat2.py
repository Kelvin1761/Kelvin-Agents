"""EXP-20261115-15 特徵：老馬贏後、降班＋換騎拆解、評分（只用日期早過今仗嘅 HKJC 馬匹頁＋賽果）。
key = (日期, 場次, 名次) → {flag: 0/1}。"""
import sys
from collections import defaultdict
from datetime import date

sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
sys.path.insert(0, sys.path[0])
import features as F  # noqa: E402

BAND_LOW = {5: 0, 4: 40, 3: 60, 2: 80, 1: 100}
BAND_HIGH = {5: 40, 4: 60, 3: 80, 2: 100, 1: 140}


def build():
    import hkjc_history_replay_pit as p
    df = p.load_all_rows_extended()
    df = df[df["Rank"].notna()].assign(d=lambda x: x["Date"].astype(str).str[:10]).sort_values(["d", "RaceNo"])
    runs, prof = F.load()
    # 騎師一年入位率（as-of，按日期累積）
    jstat = defaultdict(list)      # jockey -> [(d, placed)]
    out = {}
    for d, g in df.groupby("d", sort=True):
        cut = (date.fromisoformat(d).replace(year=date.fromisoformat(d).year - 1)).isoformat()
        def jrate(j):
            v = [p_ for dd, p_ in jstat.get(j, []) if cut <= dd < d]
            return (sum(v) / len(v)) if len(v) >= 40 else None
        for r in g.itertuples():
            hid = r.HorseID
            past = [q for q in runs.get(hid, []) if q["d"] < d]
            today = next((q for q in runs.get(hid, []) if q["d"] == d), None)
            f = {}
            if past and today:
                last = past[-1]
                years = (date.fromisoformat(d) - date.fromisoformat(past[0]["d"])).days / 365.25
                old = years >= 4 or len(past) >= 35
                lp = F.pos(last.get("pos"))
                tr, lr = F.num(today.get("rating")), F.num(last.get("rating"))
                tc, lc = F.num(today.get("class")), F.num(last.get("class"))
                elite = (tr is not None and tr >= 95) or (tc is not None and tc <= 2)
                f["old"] = int(old)
                f["old_won_last"] = int(old and lp == 1)
                f["old_won_last_nonelite"] = int(old and lp == 1 and not elite)
                f["old_won_last_elite"] = int(old and lp == 1 and elite)
                f["old_placed_last_nonelite"] = int(old and lp in (2, 3) and not elite)
                f["young_won_last"] = int((not old) and lp == 1)
                # 降班＋換騎拆解
                drop = bool(tc and lc and tc > lc)
                jch = bool(today.get("jockey") and last.get("jockey") and today["jockey"] != last["jockey"])
                jt, jl = jrate(today.get("jockey")), jrate(last.get("jockey"))
                jup = jch and jt is not None and jl is not None and jt >= jl + 0.05
                jdown = jch and jt is not None and jl is not None and jt <= jl - 0.05
                f["classdrop_only"] = int(drop and not jch)
                f["jchange_only"] = int(jch and not drop)
                f["classdrop_jchange"] = int(drop and jch)
                f["classdrop_jup"] = int(drop and jup)
                f["jup_nodrop"] = int(jup and not drop)
                f["jdown"] = int(jdown)
                # 評分（三至五班）
                low_cls = tc is not None and tc >= 3
                wins = [F.num(q.get("rating")) for q in past if F.pos(q.get("pos")) == 1 and F.num(q.get("rating")) is not None]
                yr = [F.num(q.get("rating")) for q in past if q["d"] >= (date.fromisoformat(d).replace(year=date.fromisoformat(d).year - 1)).isoformat() and F.num(q.get("rating")) is not None]
                if low_cls and tr is not None:
                    if wins:
                        f["back_on_win_mark"] = int(tr <= wins[-1])
                        f["below_win_mark5"] = int(tr <= wins[-1] - 5)
                    if yr:
                        f["drop_from_1y_high10"] = int(max(yr) - tr >= 10)
                    if tc in BAND_HIGH:
                        f["top_of_band"] = int(tr >= BAND_HIGH[int(tc)] - 5)
                        f["bottom_of_band"] = int(tr <= BAND_LOW[int(tc)] + 5)
                    f["rating_drop_last"] = int(lr is not None and tr <= lr - 2)
                    f["classdrop_rating_back"] = int(bool(drop and wins and tr <= wins[-1]))
            out.setdefault((d, int(r.RaceNo), int(r.Rank)), []).append(f)
        for r in g.itertuples():
            jstat[r.Jockey].append((d, float(r.Rank <= 3)))
    return out
