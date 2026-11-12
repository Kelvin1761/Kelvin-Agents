"""EXP-20261113-02：逐段段速對馬會標準 —— 每一段（唔止 L400）有冇模型之上嘅訊號。

Kelvin 2026-11-13：「we are just using L400? hkjc have all sections speed … adjust the number with the 場地標準時間」。
預先登記（跑之前寫死）：
  每匹馬近 6 仗（賽績檔自己嘅分段），每段減馬會標準分段（今仗班次；冇就嗰仗班次），負磅按段長換算到今仗
  （0.01123 秒／公里／磅），近 6 仗 1/k 加權，最少 2 仗。秒數越細越好。
  特徵：total（全程）、first（第一段）、early（L400 之前各段）、mid（倒數第二段）、l800（最後兩段）、l400（最後一段）、
        kick（l400 − early 每 400 米平均：後勁相對前段）、best（近 6 仗最好一仗全程）、figW（賽果庫表現數字，對照）
  判法：449 場引擎回放（labels_final）；每個特徵報覆蓋、場內 AUC（入頭三）、同現行 speed_score 嘅 Spearman、
        模型之上係數（入頭三 ~ 場內 z(raw) + 場內 z(特徵)，每 SD，場次 bootstrap 1000）；Holm 後 < 0.05 先設計 arm。
用法：PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/hkjc_section_screen.py <labels.jsonl> <figtable.json>
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hkjc_std_pace_table import parse_fg, REPO  # noqa: E402

sys.path.insert(0, str(REPO / ".agents/scripts"))
BETA = 0.01123
FEATS = ("total", "first", "early", "mid", "l800", "l400", "kick", "best", "figW")


def auc_within(rows, key):
    num = den = 0.0
    for race in rows:
        hs = [h for h in race if h.get(key) is not None]
        pos = [h[key] for h in hs if h["top3"]]
        neg = [h[key] for h in hs if not h["top3"]]
        for p in pos:
            for q in neg:
                num += (p > q) + 0.5 * (p == q)
                den += 1
    return num / den if den else float("nan")


def main():
    import wongchoi_paths
    from inject_hkjc_fact_anchors import get_reference_sections
    root = Path(wongchoi_paths.HK_RACING)
    fig = json.load(open(sys.argv[2]))["table"]
    races = []
    for line in open(sys.argv[1], encoding="utf-8"):
        x = json.loads(line)
        if "error" in x or not x.get("horses"):
            continue
        md = root / x["meeting"]
        logic = json.loads((md / f"Race_{x['race']}_Logic.json").read_text(encoding="utf-8"))
        today_cls = str((logic.get("race_analysis") or {}).get("race_class") or "")
        fg = parse_fg(md, int(x["race"]))
        ftab = fig.get(f"{x['meeting']}|{x['race']}") or {}
        race = []
        for h in x["horses"]:
            if h.get("pos") is None:
                continue
            rec = {"top3": h["pos"] <= 3, "raw": h["raw"], "speed": (h.get("f") or {}).get("speed_score")}
            fw = ftab.get(str(h["n"]))
            rec["figW"] = fw[1] if fw and fw[1] is not None else None
            e = fg.get(h["n"])
            use = []
            if e:
                tw, runs = e
                for r in sorted([r for r in runs if r["date"] < x["date"]], key=lambda r: r["date"], reverse=True)[:6]:
                    ref = (get_reference_sections(r["venue"], r["dist"], today_cls) or {}).get("sections") if today_cls else None
                    if not ref:
                        continue
                    std = [float(s) for s in ref]
                    if len(std) != len(r["secs"]) or len(std) < 3:
                        continue
                    first_len = r["dist"] - 400 * (len(std) - 1)
                    lens = [first_len] + [400] * (len(std) - 1)
                    d = [a - b + BETA * L / 1000.0 * (tw - r["w"]) for a, b, L in zip(r["secs"], std, lens)]
                    early = sum(d[:-1])
                    use.append({"total": sum(d), "first": d[0], "early": early, "mid": d[-2], "l800": d[-2] + d[-1],
                                "l400": d[-1], "kick": d[-1] - early / ((r["dist"] - 400) / 400.0)})
            if len(use) >= 2:
                w = 1.0 / np.arange(1, len(use) + 1)
                for k in ("total", "first", "early", "mid", "l800", "l400", "kick"):
                    rec[k] = -float(np.dot([u[k] for u in use], w) / w.sum())   # 負號：越大越好
                rec["best"] = -min(u["total"] for u in use)
            race.append(rec)
        if sum(h["top3"] for h in race) >= 3 and len(race) >= 5:
            races.append(race)
    print(f"{len(races)} 場、{sum(map(len, races))} 匹")
    print("特徵｜覆蓋｜場內 AUC｜同 speed_score ρ｜模型之上係數（每 SD）[95%]｜p")
    out = []
    rng = np.random.default_rng(0)
    for k in FEATS:
        cov = np.mean([h.get(k) is not None for r in races for h in r])
        auc = auc_within(races, k)
        sp = [(h[k], h["speed"]) for r in races for h in r if h.get(k) is not None and h["speed"] is not None]
        rho = spearmanr(*zip(*sp))[0]
        Z = []
        for i, r in enumerate(races):
            raw = np.array([h["raw"] for h in r]); zr = (raw - raw.mean()) / (raw.std() or 1)
            vals = np.array([h.get(k) if h.get(k) is not None else np.nan for h in r], float)
            m = np.nanmean(vals) if np.isfinite(vals).any() else 0.0
            vals = np.where(np.isfinite(vals), vals, m)
            zf = (vals - vals.mean()) / (vals.std() or 1)
            Z.append(np.c_[np.full(len(r), i), zr, zf, [h["top3"] for h in r]])
        Z = np.vstack(Z)
        fit = lambda A: LogisticRegression(C=1e6, max_iter=2000).fit(A[:, 1:3], A[:, 3]).coef_[0][1]
        idx = {i: np.where(Z[:, 0] == i)[0] for i in range(len(races))}
        bs = [fit(Z[np.concatenate([idx[i] for i in rng.integers(0, len(races), len(races))])]) for _ in range(1000)]
        c = fit(Z)
        p = max(2 * min(np.mean(np.array(bs) <= 0), np.mean(np.array(bs) >= 0)), 1 / 1000)
        out.append([k, cov, auc, rho, c, np.percentile(bs, 2.5), np.percentile(bs, 97.5), p])
    order = sorted(range(len(out)), key=lambda i: out[i][7])
    for rank, i in enumerate(order):
        out[i].append(min(1.0, out[i][7] * (len(out) - rank)))
    print(f"  speed_score（現行）｜100%｜{auc_within(races, 'speed'):.3f}")
    for k, cov, auc, rho, c, lo, hi, p, holm in out:
        print(f"  {k:<6}｜{cov*100:.0f}%｜{auc:.3f}｜{rho:+.2f}｜{c:+.3f} [{lo:+.3f},{hi:+.3f}]｜p {p:.3f}，Holm {holm:.3f}")


if __name__ == "__main__":
    main()
