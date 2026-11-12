"""EXP-20261112-04 量度：（一）負磅對 L400 嘅實際影響（同一匹馬唔同仗比較）；（二）按今仗負磅調整上仗 L400 有冇多啲預測力。

用法：
  PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/hkjc_l400_weight_screen.py <base.jsonl>
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from hkjc_weight_history_screen import HANDICAP, boot, formguide  # noqa: E402

RUN = re.compile(r"\[(\d+)\]\s+(\d{2}/\d{2}/\d{4})\s*\|[^|\n]*\|\s*(\S+)\s+\"([^\"]*)\"\s+(\d{3,4})\s+(\S+)\s*\n"
                 r"[^\n]*負磅:\s*(\d+)[^\n]*名次:\s*(\S+)\s*/\s*(\d+)\s*\n[^\n]*分段時間:\s*([\d\., ]+)")


def all_runs(root):
    rows = {}
    for md in sorted(p for p in root.iterdir() if re.match(r"\d{4}-\d{2}-\d{2}_", p.name)):
        for f in md.glob("*賽績.*"):
            if f.suffix not in (".md", ".txt"):
                continue
            for block in re.split(r"\n(?=馬號:\s*\d+)", f.read_text(encoding="utf-8")):
                nm = re.search(r"馬名:\s*(\S+)", block)
                if not nm:
                    continue
                for r in RUN.finditer(block):
                    secs = [float(x) for x in re.findall(r"\d+\.\d+", r.group(10))]
                    if len(secs) < 2 or not r.group(8).isdigit():
                        continue
                    surface = "AWT" if "AWT" in r.group(4).upper() else "T"
                    rows[(nm.group(1), r.group(2))] = {
                        "horse": nm.group(1), "date": datetime.strptime(r.group(2), "%d/%m/%Y"),
                        "cond": f"{r.group(3)}|{surface}|{r.group(5)}|{r.group(6)}", "dist": int(r.group(5)),
                        "w": int(r.group(7)), "pos": int(r.group(8)), "l400": secs[-1], "early": sum(secs[:-1])}
    return pd.DataFrame(rows.values())


def fe_slope(df, y, xs, groups=("horse", "cond"), iters=30):
    """兩組 fixed effect（交替去均值）之後 OLS；CI 用馬匹 cluster bootstrap。"""
    def demean(d):
        d = d[[y, *xs, *groups]].copy()
        for _ in range(iters):
            for g in groups:
                d[[y, *xs]] -= d.groupby(g)[[y, *xs]].transform("mean")
        return d

    def fit(d):
        X, Y = d[xs].values, d[y].values
        return np.linalg.lstsq(X, Y, rcond=None)[0][0]
    dm = demean(df)
    horses = df.horse.unique()
    idx = {h: np.where(df.horse.values == h)[0] for h in horses}
    rng = np.random.default_rng(0)
    bs = [fit(dm.iloc[np.concatenate([idx[h] for h in rng.choice(horses, len(horses))])]) for _ in range(500)]
    return fit(dm), np.percentile(bs, 2.5), np.percentile(bs, 97.5)


def l400_delta(v):
    return 8.0 if v <= 22.4 else 5.0 if v <= 23.0 else 2.0 if v <= 23.6 else -5.0 if v >= 24.6 else -2.0 if v >= 24.0 else 0.0


def main():
    import wongchoi_paths
    root = Path(wongchoi_paths.HK_RACING)
    runs = all_runs(root)
    runs = runs[(runs.l400.between(20, 28))]
    n = runs.groupby("horse").w.transform("count")
    sd = runs.groupby("horse").w.transform("std")
    r = runs[(n >= 3) & (sd > 0)].copy()
    r = r[r.groupby("cond").l400.transform("count") >= 20]
    r["early_z"] = (r.early - r.groupby("cond").early.transform("mean")) / r.groupby("cond").early.transform("std")
    r = r.dropna(subset=["early_z"])
    print(f"== 一、負磅對 L400（同馬唔同仗）== {len(r)} 仗 / {r.horse.nunique()} 匹；同馬負磅 SD 中位 {r.groupby('horse').w.std().median():.1f} 磅")
    for lab, xs in (("只控制馬匹＋場地路程場地狀況", ["w"]), ("再控制早段步速", ["w", "early_z"])):
        b, lo, hi = fe_slope(r, "l400", xs)
        print(f"  {lab}：每磅 {b:+.4f}s [{lo:+.4f},{hi:+.4f}]（10 磅 = {b*10:+.3f}s）")
    r["relpos"] = r.pos
    b, lo, hi = fe_slope(r, "relpos", ["w"])
    print(f"  對照（同一個設計）名次：每磅 {b:+.4f} 名 [{lo:+.4f},{hi:+.4f}]")
    for lab, s in (("≤1200m", r[r.dist <= 1200]), ("1400–1650m", r[r.dist.between(1400, 1650)]), ("≥1800m", r[r.dist >= 1800])):
        if s.horse.nunique() > 50:
            b, lo, hi = fe_slope(s, "l400", ["w", "early_z"])
            print(f"  {lab}（{len(s)} 仗）：每磅 {b:+.4f}s [{lo:+.4f},{hi:+.4f}]")
    print(f"  L400 同場地路程內 SD：{r.groupby('cond').l400.std().median():.2f}s；引擎門檻一格 0.6s")

    rows = []
    for line in open(sys.argv[1], encoding="utf-8"):
        x = json.loads(line)
        if "error" in x or not x.get("horses"):
            continue
        if set(x.get("meeting_dead_fields") or []) - {"track_going_score", "trackwork_trend_score"}:
            continue
        head, fg = formguide(root / x["meeting"], int(x["race"]))
        if not fg or not any(c in head for c in HANDICAP):
            continue
        day = datetime.strptime(x["date"], "%Y-%m-%d").date()
        for h in x["horses"]:
            e = fg.get(h["n"])
            if h["pos"] is None or not e:
                continue
            past = sorted([y for y in e["runs"] if y[0] < day], reverse=True)
            row = {"race": f"{x['meeting']}|{x['race']}", "place": float(h["pos"] <= 3), "raw": h["raw"]}
            if past and past[0][3]:
                row.update(l400=past[0][3], dw=e["today"] - past[0][1])
            rows.append(row)
    df = pd.DataFrame(rows)
    g = df.groupby("race")
    df["zraw"] = (df.raw - g.raw.transform("mean")) / g.raw.transform("std").replace(0, np.nan)
    d = df.dropna(subset=["zraw", "l400"]).reset_index(drop=True)
    print(f"\n== 二、預測力 == 讓磅賽 {d.race.nunique()} 場 / {len(d)} 匹有上仗 L400；|今仗−上仗| ≥5 磅 {(d.dw.abs() >= 5).mean()*100:.0f}%、≥10 磅 {(d.dw.abs() >= 10).mean()*100:.0f}%")

    def coef(cols, target, data=d):
        def fit(z):
            return LogisticRegression(max_iter=2000, C=1e6).fit(z[cols], z.place).coef_[0][cols.index(target)]
        return boot(data, fit, 600)

    d["l400_c"] = d.l400 - d.groupby("race").l400.transform("mean")
    p, lo, hi, pv = coef(["zraw", "l400_c"], "l400_c")
    print(f"  模型之上，上仗 L400（場內置中，每秒）：{p:+.3f} [{lo:+.3f},{hi:+.3f}] p={pv:.3f}")
    p, lo, hi, pv = coef(["zraw", "l400_c", "dw"], "dw")
    print(f"  再加今仗−上仗負磅（每磅）：{p:+.4f} [{lo:+.4f},{hi:+.4f}] p={pv:.3f}  ← 如果按磅數調整有用，呢個應該係負")
    p, lo, hi, pv = coef(["l400_c", "dw"], "dw")
    print(f"  唔計模型，只有 L400＋負磅差（每磅）：{p:+.4f} [{lo:+.4f},{hi:+.4f}] p={pv:.3f}")
    base = d.l400.map(l400_delta)
    print("  引擎門檻下，調整後 L400 加減分 − 原本（每 1 分嘅 log-odds，模型之上；正 = 調整方向啱）：")
    for c in (-0.04, 0.02, 0.04, 0.08):
        d["chg"] = (d.l400 + c * d.dw).map(l400_delta) - base
        moved = (d.chg != 0).mean() * 100
        p, lo, hi, pv = coef(["zraw", "chg"], "chg")
        tag = "（反方向對照）" if c < 0 else "（事後參考）" if c == 0.08 else ""
        print(f"    C={c:+.2f}s/磅：{moved:4.1f}% 匹換格，係數 {p:+.4f} [{lo:+.4f},{hi:+.4f}] p={pv:.3f} {tag}")
    fast = d[d.l400 <= 23.0]
    m = LogisticRegression(max_iter=2000, C=1e6).fit(d[["zraw"]], d.place)
    fast = fast.assign(exp=m.predict_proba(fast[["zraw"]])[:, 1])
    print("  上仗 L400 ≤23.0（攞緊 +5／+8 分）嘅馬，按今仗比上仗重幾多：")
    for lab, s in (("輕咗 ≥3", fast[fast.dw <= -3]), ("±2", fast[fast.dw.between(-2, 2)]), ("重 3–9", fast[fast.dw.between(3, 9)]), ("重 ≥10", fast[fast.dw >= 10])):
        print(f"    {lab:<7} n={len(s):>4} 上名 {s.place.mean()*100:5.1f}% 模型預期 {s.exp.mean()*100:5.1f}% 差 {(s.place - s.exp).mean()*100:+5.2f}pp")


if __name__ == "__main__":
    main()
