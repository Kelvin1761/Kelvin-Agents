"""EXP-20261112-16／-17／-18 訊號檢查：三個標籤（舊／新計法）有冇預測力，喺現行模型之上有冇剩餘訊號。

用法：PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/hkjc_label_signal_check.py <base.jsonl>
（base = hkjc_eval_harness run --dump-matrix，現行 main）
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
for p in (REPO, REPO / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts", Path(__file__).resolve().parent):
    sys.path.insert(0, str(p))
from hkjc_label_fix_common import engine_type_vs_standard, formline_counts_vs_original, run_classes_from_recent  # noqa: E402

ENGINE_PTS = {"漸進加速型": 3.03, "均速型": 1.5, "快開慢收型": -2.5, "混合型": 0.0}


def engine_kind(text):
    t = str(text or "")
    return next((k for k in ENGINE_PTS if k in t), "其他")


def boot_diff(df, a, b, n=2000):
    races = df.race.unique()
    idx = {r: np.where(df.race.values == r)[0] for r in races}
    rng = np.random.default_rng(0)

    def f(x):
        A, B = x[a(x)], x[b(x)]
        return ((A.place - A.exp).mean() - (B.place - B.exp).mean()) * 100 if len(A) and len(B) else np.nan
    bs = [f(df.iloc[np.concatenate([idx[r] for r in rng.choice(races, len(races))])]) for _ in range(n)]
    return f(df), np.nanpercentile(bs, 2.5), np.nanpercentile(bs, 97.5)


def coef(df, col, n=600):
    d = df.dropna(subset=[col])
    races = d.race.unique()
    idx = {r: np.where(d.race.values == r)[0] for r in races}
    rng = np.random.default_rng(0)
    fit = lambda x: LogisticRegression(max_iter=3000, C=1e6).fit(x[["zraw", col]], x.place).coef_[0][1]
    bs = [fit(d.iloc[np.concatenate([idx[r] for r in rng.choice(races, len(races))])]) for _ in range(n)]
    return fit(d), np.percentile(bs, 2.5), np.percentile(bs, 97.5)


def table(df, col, title):
    print(f"\n{title}")
    for k, s in df.groupby(col):
        print(f"  {str(k):<10} n={len(s):>5}  上名 {s.place.mean()*100:5.1f}%  模型預期 {s.exp.mean()*100:5.1f}%  差 {(s.place-s.exp).mean()*100:+6.2f}pp")


def main():
    import hkjc_auto_orchestrator as orch
    import wongchoi_paths
    from hkjc_racing_engine import past_runs
    root = Path(wongchoi_paths.HK_RACING)
    rows = []
    for line in open(sys.argv[1], encoding="utf-8"):
        r = json.loads(line)
        if "error" in r or not r.get("horses"):
            continue
        md = root / r["meeting"]
        lf = md / f"Race_{r['race']}_Logic.json"
        logic = json.loads(lf.read_text(encoding="utf-8"))
        rc = orch._racecard_path_for_logic(lf, r["race"])
        cls = orch._parse_racecard_meta(rc.read_text(encoding="utf-8"))[0] if rc else ""
        cls = cls or (logic.get("race_analysis") or {}).get("race_class")
        fgp = orch._formguide_path_for_logic(lf, r["race"])
        fg = past_runs.parse_formguide(fgp.read_text(encoding="utf-8")) if fgp else {}
        fp = orch._facts_path_for_logic(lf, r["race"])
        facts = fp.read_text(encoding="utf-8") if fp else ""
        day = datetime.strptime(r["date"], "%Y-%m-%d").date()
        dist = int(re.sub(r"\D", "", str((logic.get("race_analysis") or {}).get("distance") or "0")) or 0)
        cur_rank = orch._class_rank(cls)
        for h in r["horses"]:
            if h["pos"] is None:
                continue
            lg = (logic.get("horses") or {}).get(str(h["n"])) or {}
            d = lg.get("_data") or {}
            rec = {"race": f"{r['meeting']}|{r['race']}", "date": r["date"], "place": float(h["pos"] <= 3), "raw": h["raw"],
                   "dist": dist, "eng_old": engine_kind(d.get("engine_type") or lg.get("engine_type"))}
            e = fg.get(h["n"])
            if e:
                runs = sorted([x for x in e["runs"] if x["date"] < day], key=lambda x: x["date"], reverse=True)
                classes = {k: past_runs.class_code(v) for k, v in run_classes_from_recent(d.get("recent_6_detail")).items()}
                rec["eng_new"] = engine_kind(engine_type_vs_standard(runs, past_runs.class_code(cls), classes))
                rec["last_dist"] = runs[0]["distance"] if runs else None
            section = orch._section_for_horse(facts, h["n"]) if facts else ""
            if section:
                old = orch._build_formline_opponent_summary(orch._parse_formline_rows(section), cur_rank) or {}
                new = formline_counts_vs_original(section, d.get("recent_6_detail"), orch._class_rank, orch.CLASS_RANK_MAP)
                rec["fl_old_hi"] = old.get("formline_higher_win_count", 0)
                rec["fl_old_bonus"] = min(8, 3 * old.get("formline_higher_win_count", 0) + old.get("formline_same_win_count", 0)
                                          - old.get("formline_lower_win_count", 0))
                rec["fl_new_hi"] = new["higher"]
                rec["fl_new_bonus"] = min(8, 3 * new["higher"] + new["same"] - new["lower"])
            tail = str(d.get("weight_trend") or "")
            rec["wt"] = ("穩定" if "穩定" in tail else "微增減" if ("微增" in tail or "微減" in tail) else
                         "大變" if any(t in tail for t in ("急劇", "顯著")) else "持續" if "持續" in tail else "其他")
            rows.append(rec)
    df = pd.DataFrame(rows)
    g = df.groupby("race")
    df["zraw"] = (df.raw - g.raw.transform("mean")) / g.raw.transform("std").replace(0, np.nan)
    df = df.dropna(subset=["zraw"]).reset_index(drop=True)
    df["exp"] = LogisticRegression(max_iter=3000, C=1e6).fit(df[["zraw"]], df.place).predict_proba(df[["zraw"]])[:, 1]
    print(f"{df.race.nunique()} 場 / {len(df)} 匹")

    print("\n== 1. 引擎型態 ==")
    sub = df.dropna(subset=["last_dist"])
    print("舊標籤 × 上仗路程（行 %）：")
    print((pd.crosstab(sub.last_dist, sub.eng_old, normalize="index") * 100).round(0).to_string())
    print("新標籤 × 上仗路程（行 %）：")
    print((pd.crosstab(sub.last_dist, sub.eng_new, normalize="index") * 100).round(0).to_string())
    table(df, "eng_old", "舊標籤：上名 vs 模型預期")
    table(df.dropna(subset=["eng_new"]), "eng_new", "新標籤：上名 vs 模型預期")
    df["eng_old_pts"] = df.eng_old.map(ENGINE_PTS)
    df["eng_new_pts"] = df.eng_new.map(ENGINE_PTS)
    for c in ("eng_old_pts", "eng_new_pts"):
        p, lo, hi = coef(df, c)
        print(f"  模型之上 {c}（每 1 分 log-odds）：{p:+.4f} [{lo:+.4f},{hi:+.4f}]")
    for lab, col in (("舊", "eng_old"), ("新", "eng_new")):
        s = df.dropna(subset=[col])
        p, lo, hi = boot_diff(s, lambda x: x[col] == "漸進加速型", lambda x: x[col] == "快開慢收型")
        print(f"  {lab}：漸進加速 − 快開慢收（相對模型預期）{p:+.2f}pp [{lo:+.2f},{hi:+.2f}]")

    print("\n== 2. 對手後續更高班再贏 ==")
    s = df.dropna(subset=["fl_old_hi"])
    print(f"  有更高班計數：舊 {(s.fl_old_hi > 0).mean()*100:.1f}%  新 {(s.fl_new_hi > 0).mean()*100:.1f}%；兩者都有 {((s.fl_old_hi > 0) & (s.fl_new_hi > 0)).mean()*100:.1f}%")
    for lab, col in (("舊", "fl_old_hi"), ("新", "fl_new_hi")):
        p, lo, hi = boot_diff(s, lambda x: x[col] > 0, lambda x: x[col] == 0)
        print(f"  {lab}：有 − 冇（相對模型預期）{p:+.2f}pp [{lo:+.2f},{hi:+.2f}]")
    for c in ("fl_old_bonus", "fl_new_bonus"):
        p, lo, hi = coef(s, c)
        print(f"  模型之上 {c}（每 1 分）：{p:+.4f} [{lo:+.4f},{hi:+.4f}]")

    print("\n== 3. 體重趨勢 ==")
    table(df, "wt", "上名 vs 模型預期")
    p, lo, hi = boot_diff(df, lambda x: x.wt == "穩定", lambda x: x.wt == "微增減")
    print(f"  穩定 − 微增減 {p:+.2f}pp [{lo:+.2f},{hi:+.2f}]")


if __name__ == "__main__":
    main()
