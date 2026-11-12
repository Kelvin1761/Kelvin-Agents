"""EXP-20261112-08 準備：逐場逐匹嘅 PIT 表現數字（F 未換算／W 按今仗負磅換算）同四級門檻，寫成 JSON 畀 arm 讀。

門檻（跑之前寫死嘅做法，唔睇賽果）：只用 dev 半（< 2026-09-06）有現行「步速修正等級」又有表現數字嘅馬，
量現行四級各佔幾多，再喺 F 嘅分佈上取同樣比例嘅分位數。W 用同一組門檻（所以負磅換算會令馬匹過級）。

用法：PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/hkjc_fig_level_table.py <base.jsonl> <out.json>
"""
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from hkjc_weight_fig_pit import EVAL_START, SPLIT, figs_asof, prep  # noqa: E402
from hkjc_weight_effect_panel import ols_cluster, twoway  # noqa: E402
from hkjc_weight_history_screen import formguide  # noqa: E402

LEVELS = ("仍具競爭力", "接近平均", "仍偏慢", "明顯落後")


def main():
    sys.path.insert(0, str(REPO))
    import wongchoi_paths
    root = Path(wongchoi_paths.HK_RACING)
    R = prep(root)
    pre = R[R.date < EVAL_START]
    for _ in range(3):
        pre = pre[pre.groupby("hs").race.transform("count") >= 2]
        pre = pre[pre.groupby("race").hs.transform("count") >= 4]
    beta = float(ols_cluster(twoway(pre, "tkm", ["w"], "hs", "race"), "tkm", ["w"], pre.horse.values)[0][0])
    table, dev, cache = {}, [], {}
    for line in open(sys.argv[1], encoding="utf-8"):
        r = json.loads(line)
        if "error" in r or not r.get("horses"):
            continue
        md = root / r["meeting"]
        _head, fg = formguide(md, int(r["race"]))
        logic = json.loads((md / f"Race_{r['race']}_Logic.json").read_text(encoding="utf-8")).get("horses") or {}
        if r["date"] not in cache:
            cache.clear()
            cache[r["date"]] = figs_asof(R, r["date"], beta)
        hist = cache[r["date"]]
        row = {}
        for h in r["horses"]:
            lg = logic.get(str(h["n"])) or {}
            e = fg.get(h["n"]) if fg else None
            past = sorted(hist.get(lg.get("horse_name")) or [])[-6:]
            if not e or len(past) < 2:
                continue
            f = np.array([x[1] for x in past]); w = np.array([x[2] for x in past], float)
            wt = 1.0 / np.arange(len(past), 0, -1)
            F, Wp = float((f * wt).sum() / wt.sum()), float((w * wt).sum() / wt.sum())
            row[str(h["n"])] = [round(F, 5), round(F - beta * (e["today"] - Wp), 5)]
            lvl = str((lg.get("_data") or {}).get("finish_time_adj_level") or "")
            k = next((i for i, s in enumerate(LEVELS) if s in lvl), None)
            if k is not None and r["date"] < SPLIT:
                dev.append((F, k))
        table[f"{r['meeting']}|{r['race']}"] = row
    F = np.array([x[0] for x in dev]); K = np.array([x[1] for x in dev])
    shares = [float((K == i).mean()) for i in range(4)]
    cuts = [float(np.quantile(F, 1 - sum(shares[:i + 1]))) for i in range(3)]   # F 越大越好
    json.dump({"beta": beta, "shares": shares, "cuts": cuts, "table": table}, open(sys.argv[2], "w"))
    print(f"β {beta:+.5f}；dev {len(dev)} 匹；現行四級比例 {[round(s, 3) for s in shares]}；F 門檻（s/km）{[round(c, 4) for c in cuts]}；"
          f"{len(table)} 場 / {sum(len(v) for v in table.values())} 匹有表現數字")
    print("現行等級 vs 表現數字 Spearman：", round(float(np.corrcoef(np.argsort(np.argsort(F)), np.argsort(np.argsort(-K)))[0, 1]), 3))


if __name__ == "__main__":
    main()
