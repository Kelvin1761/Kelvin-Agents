"""EXP-20261111-09：頂磅 dummy × 模型排名（重做 memory hkjc-top-weight-is-the-missing-signal，用負磅調轉後嘅引擎）。

用法：
  PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/hkjc_top_weight_dummy.py <dump.jsonl>
<dump.jsonl> = hkjc_eval_harness.py run --dump-matrix（baseline）。宣佈負磅、評分由排位表讀（賽前）。
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[3]
for p in (REPO / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts",
          REPO / ".agents/skills/hkjc_racing/hkjc_reflector/scripts", REPO):
    sys.path.insert(0, str(p))

HANDICAP = ("第一班", "第二班", "第三班", "第四班", "第五班")


def racecard(md, race_no):
    import hkjc_auto_orchestrator as orch
    path = orch._racecard_path_for_logic(md / f"Race_{race_no}_Logic.json", race_no)
    if not path or not Path(path).exists():
        return "", {}
    cls, info = orch._parse_racecard_meta(Path(path).read_text(encoding="utf-8"))
    out = {}
    for k, e in info.items():
        if str(k).isdigit() and e.get("weight") is not None:
            out[int(k)] = (int(e["weight"]) + int(e.get("jockey_claim") or 0), e.get("rating"))
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
        cls, card = racecard(root / r["meeting"], int(r["race"]))
        rank = {n: i + 1 for i, n in enumerate(r["picks"])}
        horses = [h for h in r["horses"] if h["pos"] is not None and h["n"] in card]
        if len(horses) < 5:
            continue
        top_w = max(card[h["n"]][0] for h in horses)
        ratings = [card[h["n"]][1] for h in horses if card[h["n"]][1] is not None]
        top_r = max(ratings) if ratings else None
        for h in horses:
            w, rt = card[h["n"]]
            rows.append({"race": f"{r['meeting']}|{r['race']}", "date": r["date"],
                         "handicap": any(c in str(cls) for c in HANDICAP),
                         "place": float(h["pos"] <= 3), "mrank": rank.get(h["n"], 99),
                         "top_w": w == top_w, "top_r": rt is not None and rt == top_r})
    return pd.DataFrame(rows)


def diff_ci(df, flag, n=2000):
    """頂組 − 其餘 上名率，按場次 bootstrap。"""
    races = df.race.unique()
    idx = {r: np.where(df.race.values == r)[0] for r in races}
    p, f = df.place.values, df[flag].values

    def d(sel):
        a, b = p[sel][f[sel]], p[sel][~f[sel]]
        return a.mean() - b.mean() if len(a) and len(b) else np.nan
    point = d(np.arange(len(df)))
    rng = np.random.default_rng(0)
    bs = [d(np.concatenate([idx[r] for r in rng.choice(races, len(races))])) for _ in range(n)]
    return point * 100, np.nanpercentile(bs, 2.5) * 100, np.nanpercentile(bs, 97.5) * 100, int(f.sum()), int((~f).sum())


def main():
    df = build(sys.argv[1])
    print(f"{df.race.nunique()} 場 / {len(df)} 匹（{df.date.min()} → {df.date.max()}）；讓磅賽 {df[df.handicap].race.nunique()} 場")
    for scope, sub in (("讓磅賽", df[df.handicap]), ("全部", df)):
        print(f"\n== {scope} ==")
        for flag, label in (("top_w", "頂磅（宣佈負磅最高）"), ("top_r", "全場最高評分")):
            for band, sel in (("模型排名 1", sub.mrank == 1), ("模型排名 2-3", sub.mrank.between(2, 3)),
                              ("模型排名 4-6", sub.mrank.between(4, 6)), ("模型排名 7+", sub.mrank >= 7),
                              ("模型排名 4+【判決】", sub.mrank >= 4), ("模型排名 1-3", sub.mrank <= 3)):
                s = sub[sel].reset_index(drop=True)
                d, lo, hi, na, nb = diff_ci(s, flag)
                print(f"  {label:<14} {band:<14} {d:+6.2f}pp [{lo:+.2f},{hi:+.2f}]  n={na} vs {nb}")


if __name__ == "__main__":
    main()
