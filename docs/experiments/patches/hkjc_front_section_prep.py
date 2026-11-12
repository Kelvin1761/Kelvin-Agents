"""EXP-20261113-04 準備：前段對馬會標準（每 400 米）—— dev 半嘅 mean／SD（arm 用嚟標準化），同埋 449 場篩選複核。

前段值（每匹）：近 6 仗、每仗 L400 之前各段減馬會標準分段（今仗班次；冇就嗰仗班次），負磅按段長換算到今仗
（0.01123 秒／公里／磅），除以（路程 − 400）/ 400 → 每 400 米慢幾多秒；1/k 加權，最少 2 仗；取負（越大越好）。
同 `hkjc_arm_front_section.front_value` 用同一條式。
用法：PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/hkjc_front_section_prep.py <labels.jsonl> <out_stats.json>
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hkjc_std_pace_table import parse_fg, REPO  # noqa: E402
from hkjc_section_screen import auc_within  # noqa: E402
from hkjc_arm_front_section import front_value  # noqa: E402

sys.path.insert(0, str(REPO / ".agents/scripts"))
SPLIT = "2026-09-06"


def main():
    import wongchoi_paths
    from inject_hkjc_fact_anchors import get_reference_sections
    from sklearn.linear_model import LogisticRegression
    root = Path(wongchoi_paths.HK_RACING)
    races, dev_vals, sp = [], [], []
    for line in open(sys.argv[1], encoding="utf-8"):
        x = json.loads(line)
        if "error" in x or not x.get("horses"):
            continue
        md = root / x["meeting"]
        logic = json.loads((md / f"Race_{x['race']}_Logic.json").read_text(encoding="utf-8"))
        cls = str((logic.get("race_analysis") or {}).get("race_class") or "")
        fg = parse_fg(md, int(x["race"]))
        race = []
        for h in x["horses"]:
            if h.get("pos") is None:
                continue
            rec = {"top3": h["pos"] <= 3, "raw": h["raw"], "speed": (h.get("f") or {}).get("speed_score")}
            e = fg.get(h["n"])
            if e:
                tw, runs = e
                runs = sorted([r for r in runs if r["date"] < x["date"]], key=lambda r: r["date"], reverse=True)[:6]
                items = []
                for r in runs:
                    ref = (get_reference_sections(r["venue"], r["dist"], cls) or {}).get("sections") if cls else None
                    items.append((r["dist"], r["secs"], r["w"], [float(s) for s in ref] if ref else None))
                rec["front"] = front_value(items, tw)
                if rec["front"] is not None and x["date"] < SPLIT:
                    dev_vals.append(rec["front"])
            race.append(rec)
        if sum(h["top3"] for h in race) >= 3 and len(race) >= 5:
            races.append(race)
    st = {"mean": float(np.mean(dev_vals)), "sd": float(np.std(dev_vals)), "n_dev": len(dev_vals), "speed_sd": 9.448721755995477}
    json.dump(st, open(sys.argv[2], "w"))
    cov = np.mean([h.get("front") is not None for r in races for h in r])
    print(f"{len(races)} 場；覆蓋 {cov*100:.0f}%；dev 半 mean {st['mean']:+.3f} s/400m，SD {st['sd']:.3f}（n {st['n_dev']}）")
    print(f"場內 AUC 前段 {auc_within(races, 'front'):.3f}，speed_score {auc_within(races, 'speed'):.3f}")
    Z = []
    for i, r in enumerate(races):
        raw = np.array([h["raw"] for h in r]); zr = (raw - raw.mean()) / (raw.std() or 1)
        v = np.array([h.get("front") if h.get("front") is not None else np.nan for h in r], float)
        v = np.where(np.isfinite(v), v, np.nanmean(v) if np.isfinite(v).any() else 0.0)
        Z.append(np.c_[np.full(len(r), i), zr, (v - v.mean()) / (v.std() or 1), [h["top3"] for h in r]])
    Z = np.vstack(Z)
    fit = lambda A: LogisticRegression(C=1e6, max_iter=2000).fit(A[:, 1:3], A[:, 3]).coef_[0][1]
    idx = {i: np.where(Z[:, 0] == i)[0] for i in range(len(races))}
    rng = np.random.default_rng(0)
    bs = [fit(Z[np.concatenate([idx[i] for i in rng.integers(0, len(races), len(races))])]) for _ in range(1000)]
    print(f"模型之上係數 {fit(Z):+.3f} [{np.percentile(bs, 2.5):+.3f},{np.percentile(bs, 97.5):+.3f}]")


if __name__ == "__main__":
    main()
