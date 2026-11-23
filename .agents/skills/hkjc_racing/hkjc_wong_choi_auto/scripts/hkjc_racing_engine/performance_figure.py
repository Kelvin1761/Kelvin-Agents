"""表現數字取代段速維度（EXP-20261123-10 SW；Kelvin 2026-11-23「寫 live 版，上咗線先」）。

表現數字 = 每仗完成時間（秒／公里）扣走嗰場賽事本身快慢（賽事效應），再按今仗負磅換算，近 6 仗 1/k 加權：
  賽事效應：今仗日期之前嘅全部香港賽果，(時間/km − β·負磅) ~ 馬匹×馬季 ＋ 賽事，交替估 15 次（只用輸頭馬 ≤3 秒嘅仗）
  每仗 fig = −(封頂時間/km − 賽事效應)（輸頭馬 >3 秒封頂喺 3 秒），全部之前嘅仗置中
  figW = 近 6 仗 Σ (fig − β·(今仗負磅 − 嗰仗負磅)·km) / k ÷ Σ 1/k（至少 2 仗有數；k = 1 最近）
  β = 0.0094095 秒／公里／磅（只用 2019/20 估，EXP-20261112-11，凍結）
入分（取代段速，唔係疊加）：
  raw' = raw − 0.1285·(段速維度分 − 場均) ＋ 4.99·(figW − 場均) − 0.95·(冇表現數字 − 場均)；冇表現數字 = 用場均
  4.99／−0.95 = 2026/27 walk-forward 值（fit 2019/20–2025/26，base = live；
  docs/experiments/patches/hkjc_distance/build_figure_replay.py SW）。
回放尺 v5.2：dev Δlog-loss −0.00117 [−0.00171,−0.00057]、頭二入頭三 +19；holdout −0.00151 [−0.00215,−0.00086]、Gold +0.76、
頭二 +3（holdout 唔完全獨立，披露）。理由：加咗表現數字之後段速分係數 0.04（dev／holdout），即係表現數字包晒段速分。
算法同 `docs/experiments/patches/hkjc_figure_concept_walkforward.py` build() 一模一樣（嗰度係研究版；呢度係唯一 live 定義）。
次序：最後一個後置組件（薄證據收窄之後）、grade／排名之前 —— 同回放 base（base_live_20261122 已含所有後置組件）一致。
`ENABLED = False` = 退回（forward 退回 arm 用）。
"""
from __future__ import annotations

import glob
import json
import re
from pathlib import Path

ENABLED = True
BETA_LB = 0.009409486782794192
SECTIONAL_WEIGHT = 0.1285
BETA_FIG = 4.99
BETA_MISS = -0.95
BUCKETS = ((1000, 54, 60), (1200, 66.5, 73.5), (1400, 79, 87), (1600, 91, 98.2), (1650, 98.2, 104.5),
           (1800, 104.5, 113), (2000, 118, 127), (2200, 131, 141), (2400, 144, 156))
_ROWS = None
_CACHE: dict = {}
_SEG_CACHE: dict = {}


def _secs(t):
    m = re.fullmatch(r"(?:(\d+):)?(\d+(?:\.\d+)?)", str(t or "").strip())
    return (int(m.group(1) or 0) * 60 + float(m.group(2))) if m else None


def _root() -> Path:
    import wongchoi_paths
    return Path(wongchoi_paths.HK_RACING)


def load_results(root: Path | None = None):
    """全部香港賽果（同研究版 load() 一樣嘅去重同過濾）。返回 pandas DataFrame。"""
    global _ROWS
    if _ROWS is not None and root is None:
        return _ROWS
    import pandas as pd
    root = root or _root()
    rows, seen = [], set()
    files = sorted(glob.glob(str(root / "_research_old_season_results/*.json"))) + \
        sorted(glob.glob(str(root / "HKJC_Race_Results_Database/hkjc results */*/*.json")))
    for f in files:
        try:
            payload = json.loads(Path(f).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for key, race in payload.items():
            if not isinstance(race, dict) or not race.get("results"):
                continue
            venue = "HV" if str(race.get("venue")) in ("跑馬地", "HappyValley") else "ST"
            rid = (str(race.get("racedate")), venue, str(race.get("race_no") or key))
            if rid in seen:
                continue
            seen.add(rid)
            for r in race["results"]:
                t, w = _secs(r.get("finish_time")), r.get("actual_wt")
                code = re.search(r"\((\w+)\)", str(r.get("horse_name")))
                if t is None or not str(w).isdigit() or not str(r.get("pos")).strip().isdigit() or not code:
                    continue
                rows.append({"race": "|".join(rid), "date": rid[0], "code": code.group(1), "w": int(w), "time": t,
                             "pos": int(r["pos"]), "surface": "泥地" if "全天候" in str(race.get("course") or "") else ("谷草" if venue == "HV" else "田草")})
    R = pd.DataFrame(rows)
    if R.empty:
        _ROWS = R
        return R
    R["season"] = R.date.map(lambda d: int(d[:4]) - (int(d[5:7]) < 8))
    R["t_win"] = R.groupby("race").time.transform("min")
    R["beaten"] = R.time - R.t_win
    R["dist"] = R.t_win.map(lambda t: next((d for d, lo, hi in BUCKETS if lo <= t < hi), float("nan")))
    R = R[R.groupby("race").dist.transform(lambda s: s.notna().all())].copy()
    R["km"] = R.dist / 1000.0
    R["straight"] = (R.surface == "田草") & (R.dist == 1000)
    R["tkm"] = R.time / R.km
    R["tkm_cap"] = (R.t_win + R.beaten.clip(upper=3.0)) / R.km
    R["hs"] = R.code + "|" + R.season.astype(str)
    R = R.sort_values(["date", "race", "code"]).reset_index(drop=True)
    _ROWS = R
    return R


def figures_as_of(race_date: str, R=None):
    """日期嚴格早過 race_date 嘅每仗表現數字：{馬匹編號: [(fig, 負磅, km), …]}（最近先，最多 6 仗）。"""
    import numpy as np
    import pandas as pd
    if race_date in _CACHE:
        return _CACHE[race_date]
    R = load_results() if R is None else R
    out: dict = {}
    if R is None or R.empty:
        _CACHE[race_date] = out
        return out
    P = R[R.date < race_date]
    if P.empty:
        _CACHE[race_date] = out
        return out
    m = (P.beaten <= 3).values
    adj = (P.tkm - BETA_LB * P.w).values[m]
    hs, rc = P.hs.values[m], P.race.values[m]
    rfe = np.zeros(len(adj))
    for _ in range(15):
        hfe = pd.Series(adj - rfe).groupby(hs).transform("mean").values
        rfe = pd.Series(adj - hfe).groupby(rc).transform("mean").values
    rmap = pd.Series(rfe, index=rc).groupby(level=0).first()
    f = -(P.tkm_cap.values - P.race.map(rmap).values)
    f = f - np.nanmean(f)
    P = P.assign(fig=f)
    seg = {"awt": {}, "straight": {}}
    for code, g in P.groupby("code", sort=False):
        tail = g.tail(6).iloc[::-1]
        out[code] = list(zip(tail.fig.tolist(), tail.w.tolist(), tail.km.tolist(), tail.date.tolist(), tail.surface.tolist(), tail.straight.tolist()))
        for name, mask in (("awt", g.surface == "泥地"), ("straight", g.straight)):
            st = g[mask].tail(6).iloc[::-1]
            if len(st):
                seg[name][code] = list(zip(st.fig.tolist(), st.w.tolist(), st.km.tolist(), st.date.tolist(),
                                           st.surface.tolist(), st.straight.tolist()))
    _CACHE[race_date] = out
    _SEG_CACHE[race_date] = seg
    return out


def segment_figures(race_date: str) -> dict:
    """{"awt"|"straight": {馬匹編號: 最近 6 仗該分段嘅仗（最近先，同 figures_as_of 一樣嘅 tuple）}}，日期嚴格早過 race_date。"""
    if race_date not in _SEG_CACHE:
        figures_as_of(race_date)
    return _SEG_CACHE.get(race_date, {"awt": {}, "straight": {}})


def _wavg(runs, today_weight, need):
    import math
    if not runs or today_weight is None:
        return None
    num = den = 0.0
    ok = 0
    for k, (fv, w, km, *_rest) in enumerate(runs, 1):
        if fv is None or (isinstance(fv, float) and math.isnan(fv)):
            continue
        ok += 1
        num += (fv - BETA_LB * (today_weight - w) * km) / k
        den += 1.0 / k
    return num / den if ok >= need else None


def figure_w(runs, today_weight):
    """figW（換算到今仗負磅）；少過 2 仗有數 = None。runs = figures_as_of()[code]。"""
    return _wavg(runs, today_weight, 2)


def segment_gap(runs, seg_runs, today_weight) -> dict | None:
    """分段表現數字 − 整體（EXP-20261123-18 定義，唯一一份）：整體 = 最近 6 仗（≥2 仗），分段 = 最近 6 仗該分段（≥1 仗），
    都換算今仗負磅、1/k 加權。標籤同直路入分（straight_figure.py）都用呢個。"""
    overall = figure_w((runs or [])[:6], today_weight)
    part = _wavg((seg_runs or [])[:6], today_weight, 1)
    if overall is None or part is None:
        return None
    return {"gap": part - overall, "n": len(seg_runs or [])}


def _weight(h):
    for key in ("weight",):
        try:
            return float(str(h.get(key)).strip())
        except (TypeError, ValueError):
            continue
    data = h.get("_data") if isinstance(h.get("_data"), dict) else {}
    try:
        return float(data.get("formguide_today_weight"))
    except (TypeError, ValueError):
        return None


def adjustments(horses: dict, race_date: str, table=None) -> dict:
    """{馬號: (delta, info)}；delta = 取代段速嘅原始分加減（全場置中）。"""
    if not horses or not race_date:
        return {}
    from .market_history import horse_code
    table = figures_as_of(race_date) if table is None else table
    keys = list(horses)
    figs, secs = [], []
    for k in keys:
        h = horses[k]
        figs.append(figure_w(table.get(horse_code(h) or ""), _weight(h)))
        secs.append(float((h["python_auto"].get("matrix_scores") or {}).get("sectional", 60.0)))
    have = [v for v in figs if v is not None]
    mu = sum(have) / len(have) if have else 0.0
    filled = [v if v is not None else mu for v in figs]
    miss = [0.0 if v is not None else 1.0 for v in figs]
    n = len(keys)
    mf, mm, ms = sum(filled) / n, sum(miss) / n, sum(secs) / n
    out = {}
    for k, fv, fl, ms_, sc in zip(keys, figs, filled, miss, secs):
        sec_part = -SECTIONAL_WEIGHT * (sc - ms)
        fig_part = BETA_FIG * (fl - mf) + BETA_MISS * (ms_ - mm)
        out[k] = (sec_part + fig_part, {"figure": None if fv is None else round(fv, 3),
                                        "field_mean": round(mu, 3) if have else None,
                                        "sectional_removed": round(sec_part, 4), "figure_added": round(fig_part, 4)})
    return out


def apply(horses: dict, race_context: dict | None = None) -> int:
    """加落 ability_score_raw（最後一個後置組件、grade／排名之前）。返回郁咗幾多匹。"""
    if not ENABLED:
        return 0
    from .scoring import compute_grade, to_display_scale
    rc = race_context or {}
    race_date = str(rc.get("race_date") or "")[:10]
    scored = {k: h for k, h in horses.items() if isinstance(h, dict) and isinstance(h.get("python_auto"), dict)
              and h["python_auto"].get("ability_score_raw") is not None}
    if not scored or not race_date:
        return 0
    try:
        adj = adjustments(scored, race_date)
    except Exception as exc:  # 冇賽果庫／pandas → 唔郁（同其他組件冇表一樣），但要講出嚟
        print(f"⚠️ 表現數字組件跳過：{exc}")
        return 0
    n = 0
    for k, (add, info) in adj.items():
        auto = scored[k]["python_auto"]
        add = round(add, 4)
        auto["performance_figure"] = info
        raw = round(float(auto["ability_score_raw"]) + add, 4)
        auto["ability_score_raw"] = raw
        auto["ability_score"] = round(to_display_scale(raw), 2)
        auto["grade"] = compute_grade(auto["ability_score"])
        auto["performance_figure_delta"] = add
        for shadow in (auto.get("shadow_profiles") or {}).values():
            try:
                s_raw = round(float(shadow.get("ability_score_raw")) + add, 4)
            except (TypeError, ValueError):
                continue
            s_score = round(to_display_scale(s_raw), 2)
            shadow["ability_score_raw"] = s_raw
            shadow["ability_score"] = s_score
            shadow["grade"] = compute_grade(s_score)
            shadow["ability_delta"] = round(s_score - auto["ability_score"], 2)
            shadow.setdefault("sip_flags", []).append({"reason": "performance_figure", "boost": add, "boost_scale": "raw"})
        n += abs(add) > 1e-9
    return n
