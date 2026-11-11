"""EXP-20261111-14：負磅著數（評分應負 − 實際負磅，磅）screening，只量度。

用法：
  PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/hkjc_weight_advantage_screen.py <dump.jsonl>
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

REPO = Path(__file__).resolve().parents[3]
for p in (REPO / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts",
          REPO / ".agents/skills/hkjc_racing/hkjc_reflector/scripts", REPO):
    sys.path.insert(0, str(p))
HANDICAP = ("第一班", "第二班", "第三班", "第四班", "第五班")


def card(md, race_no):
    import hkjc_auto_orchestrator as orch
    path = orch._racecard_path_for_logic(md / f"Race_{race_no}_Logic.json", race_no)
    if not path or not Path(path).exists():
        return "", {}
    cls, info = orch._parse_racecard_meta(Path(path).read_text(encoding="utf-8"))
    out = {}
    for k, e in info.items():
        if str(k).isdigit() and e.get("weight") is not None and e.get("rating") is not None:
            claim = int(e.get("jockey_claim") or 0)
            out[int(k)] = {"declared": int(e["weight"]) + claim, "claim": claim, "rating": int(e["rating"])}
    return cls, out


def build(dump):
    import wongchoi_paths
    root = Path(wongchoi_paths.HK_RACING)
    rows = []
    for line in open(dump, encoding="utf-8"):
        r = json.loads(line)
        if "error" in r or not r.get("horses"):
            continue
        if set(r.get("meeting_dead_fields") or []) - {"track_going_score", "trackwork_trend_score"}:
            continue
        cls, c = card(root / r["meeting"], int(r["race"]))
        if not any(x in str(cls) for x in HANDICAP):
            continue
        hs = [h for h in r["horses"] if h["pos"] is not None and h["n"] in c and not h["debut"]]
        if len(hs) < 5:
            continue
        top_w = max(c[h["n"]]["declared"] for h in hs)
        top_r = max(c[h["n"]]["rating"] for h in hs)
        for h in hs:
            e = c[h["n"]]
            implied = top_w - (top_r - e["rating"])
            rows.append({"race": f"{r['meeting']}|{r['race']}", "date": r["date"],
                         "place": float(h["pos"] <= 3), "raw": h["raw"], "claim": e["claim"],
                         "layout": implied - e["declared"], "adv": implied - (e["declared"] - e["claim"])})
    df = pd.DataFrame(rows)
    g = df.groupby("race")
    df["zraw"] = (df.raw - g.raw.transform("mean")) / g.raw.transform("std").replace(0, np.nan)
    return df.dropna(subset=["zraw"]).reset_index(drop=True)


def coef(df, cols, target, n=1000):
    def fit(d):
        m = LogisticRegression(max_iter=2000, C=1e6).fit(d[cols], d.place)
        return m.coef_[0][cols.index(target)]
    races = df.race.unique()
    idx = {r: np.where(df.race.values == r)[0] for r in races}
    rng = np.random.default_rng(0)
    bs = [fit(df.iloc[np.concatenate([idx[r] for r in rng.choice(races, len(races))])]) for _ in range(n)]
    return fit(df), np.percentile(bs, 2.5), np.percentile(bs, 97.5)


def main():
    df = build(sys.argv[1])
    print(f"讓磅賽 {df.race.nunique()} 場 / {len(df)} 匹（{df.date.min()} → {df.date.max()}）")
    print(f"著數 ≠ 0：{(df.adv != 0).mean()*100:.1f}%；見習減磅 >0：{(df.claim > 0).mean()*100:.1f}%；編排差 ≠ 0：{(df.layout != 0).mean()*100:.1f}%")
    print("編排差分佈：", df.layout.value_counts().sort_index().to_dict())
    print("減磅分佈：", df.claim.value_counts().sort_index().to_dict())
    p, lo, hi = coef(df, ["zraw", "adv"], "adv")
    print(f"\n主測試 place ~ z(模型) + 著數(磅)：著數係數 {p:+.4f} [{lo:+.4f},{hi:+.4f}]（每磅 log-odds）")
    for c in ("claim", "layout"):
        p, lo, hi = coef(df, ["zraw", c], c)
        print(f"  拆開：{c:<7} {p:+.4f} [{lo:+.4f},{hi:+.4f}]")
    m = LogisticRegression(max_iter=2000, C=1e6).fit(df[["zraw"]], df.place)
    df["exp"] = m.predict_proba(df[["zraw"]])[:, 1]
    print("\n分層：上名率 vs 模型預期")
    for lab, sel in (("著數 ≤ −1（蝕）", df.adv <= -1), ("著數 0", df.adv == 0), ("著數 1–4", df.adv.between(1, 4)), ("著數 ≥5", df.adv >= 5)):
        s = df[sel]
        if len(s):
            print(f"  {lab:<12} n={len(s):>5}  上名 {s.place.mean()*100:5.1f}%  模型預期 {s.exp.mean()*100:5.1f}%  差 {(s.place-s.exp).mean()*100:+5.2f}pp")


if __name__ == "__main__":
    main()
