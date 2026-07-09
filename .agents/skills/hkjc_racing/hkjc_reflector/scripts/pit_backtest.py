#!/usr/bin/env python3
"""pit_backtest.py — point-in-time HKJC Auto backtest（乾淨基準線）

問題：comprehensive_stats CSV 而家 static，一 `--write` 就會將 backtest set
自己嘅結果焗入 rating/先驗 → lookahead 污染，153 場數字唔再係 forward test。

呢個 harness score 每個賽日嗰陣，只用「嗰日之前」嘅結果重建騎師/練馬師連續
評分 + 騎練組合 / 同程 / 換騎先驗，逐個賽日 as-of 注入引擎再評分，攞返一條
可信嘅 forward 基準線。

原始 rows 由 build_comprehensive_stats 嘅 load_base_rows + append_new_meetings
攞（含 race_results 主表 + full_day_results.json 追加賽日，到 07-04）。
連續評分數學／參數由 live_priors.JT_RATING_PARAMS 引入，同 production 一致。

限制（已知、無 lookahead）：full_day_results.json 追加 rows 冇距離欄，所以
「同程先驗」對 05-09 之後嘅賽日凍結喺 05-09（只會缺近期資料，唔會有未來資料）。
master 評分 / 組合 / 換騎 先驗係完整 as-of 到賽日。

用法：
  python3 pit_backtest.py <meeting_dir> [<meeting_dir> ...] [--json]
"""
from __future__ import annotations
import argparse
import importlib.util
import os
import sys
from pathlib import Path

os.environ.setdefault("PYTHONUTF8", "1")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd

_HERE = Path(__file__).resolve()
# parents: 0=scripts 1=hkjc_reflector 2=hkjc_racing 3=skills 4=.agents 5=repo root
_ENGINE = _HERE.parents[2] / "hkjc_wong_choi_auto" / "scripts" / "racing_engine"
_SCRIPTS = _HERE.parents[4] / "scripts"   # .agents/scripts
_REPO = _HERE.parents[5]
sys.path.insert(0, str(_ENGINE))
sys.path.insert(0, str(_REPO))            # repo root (wongchoi_paths)

import rescore_backtest as bt  # noqa: E402 (sibling module)
import live_priors  # noqa: E402
import engine_core  # noqa: E402
from engine_core import RacingEngine  # noqa: E402
from live_priors import JT_RATING_PARAMS  # noqa: E402

# import build_comprehensive_stats by path
_spec = importlib.util.spec_from_file_location(
    "build_comprehensive_stats", _SCRIPTS / "build_comprehensive_stats.py"
)
bcs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bcs)


def load_all_rows() -> pd.DataFrame:
    """所有原始 rows（兩季 race_results + json 追加），帶 SeasonTag。"""
    frames = []
    for season in ("24_25", "25_26"):
        base = bcs.load_base_rows(season)
        base, _ = bcs.append_new_meetings(season, base)
        base = base.copy()
        base["SeasonTag"] = season
        frames.append(base)
    df = pd.concat(frames, ignore_index=True)
    df["Date"] = df["Date"].astype(str)
    return df


def _eb_score(wins, starts, places, g_win, g_place, neg_scale, floor):
    p = JT_RATING_PARAMS
    win_sh = (wins + p["k"] * g_win) / (starts + p["k"])
    place_sh = (places + p["k"] * g_place) / (starts + p["k"])
    delta = p["b_win"] * (win_sh - g_win) * 100 + p["a_place"] * (place_sh - g_place) * 100
    if delta < 0:
        delta *= neg_scale
    score = 60.0 + delta
    if floor:
        score = max(score, floor)
    return max(0.0, min(100.0, score))


def build_ratings(sub: pd.DataFrame, group: str) -> dict:
    p = JT_RATING_PARAMS
    col = "Jockey" if group == "jockey" else "Trainer"
    neg = p["jockey_neg_scale"] if group == "jockey" else p["trainer_neg_scale"]
    floor = 0.0 if group == "jockey" else p["trainer_floor"]
    w24 = p.get("jockey_w24", 1.0) if group == "jockey" else p.get("trainer_w24", 1.0)
    d = sub[[col, "SeasonTag", "Win", "Place"]].copy()
    d["w"] = d["SeasonTag"].map(lambda s: w24 if s == "24_25" else 1.0)
    d["Wins"] = d["Win"] * d["w"]
    d["Starts"] = d["w"]
    d["Places"] = d["Place"] * d["w"]
    g = d.groupby(col)[["Wins", "Starts", "Places"]].sum().reset_index()
    tot = g["Starts"].sum() or 1.0
    g_win, g_place = g["Wins"].sum() / tot, g["Places"].sum() / tot
    out = {}
    for r in g.to_dict("records"):
        s = r["Starts"]
        if s <= 0:
            continue
        out[str(r[col]).strip()] = {
            "score": _eb_score(r["Wins"], s, r["Places"], g_win, g_place, neg, floor),
            "starts": s,
            "win_rate": r["Wins"] / s * 100.0,
            "place_rate": r["Places"] / s * 100.0,
        }
    return out


def _grouped_priors(sub: pd.DataFrame, keys: list[str]) -> dict:
    d = sub.dropna(subset=keys)
    g = d.groupby(keys).agg(wins=("Win", "sum"), starts=("Win", "count"),
                            places=("Place", "sum")).reset_index()
    out = {}
    for r in g.to_dict("records"):
        s = float(r["starts"])
        if s <= 0:
            continue
        key = tuple(str(r[k]).strip() for k in keys)
        if len(key) == 2 and keys[1] == "Distance":
            # Distance 由 float 1650.0 → "1650"
            key = (key[0], str(int(float(r[keys[1]]))))
        out[key if len(key) > 1 else key[0]] = {
            "starts": s, "wins": float(r["wins"]), "places": float(r["places"]),
            "win_rate": r["wins"] / s * 100.0, "place_rate": r["places"] / s * 100.0,
        }
    return out


def build_change(sub: pd.DataFrame) -> dict:
    d = sub.sort_values("Date").copy()
    d["Prev"] = d.groupby("Horse")["Jockey"].shift(1)
    d = d[d["Prev"].notna()]
    d["Changed"] = d["Jockey"] != d["Prev"]
    g = d.groupby("Changed").agg(wins=("Win", "sum"), starts=("Win", "count"),
                                 places=("Place", "sum")).reset_index()
    out = {}
    for r in g.to_dict("records"):
        s = float(r["starts"]) or 1.0
        out[bool(r["Changed"])] = {
            "starts": s, "wins": float(r["wins"]), "places": float(r["places"]),
            "win_rate": r["wins"] / s * 100.0, "place_rate": r["places"] / s * 100.0,
        }
    return out


class _Ratings:
    def __init__(self, jockey, trainer):
        self.jockey, self.trainer = jockey, trainer

    def lookup(self, group, raw_name):
        table = self.jockey if group == "jockey" else self.trainer
        name = str(raw_name or "").strip()
        if not name:
            return None
        if name in table:
            return table[name]
        for k, v in table.items():
            if k and (k in name or name in k):
                return v
        return None


class _Priors:
    def __init__(self, combo, jd, td, change):
        self.combo, self.jockey_distance, self.trainer_distance, self.jockey_change = combo, jd, td, change


def inject_as_of(all_rows: pd.DataFrame, meeting_date: str):
    sub = all_rows[all_rows["Date"] < meeting_date]
    live_priors._JT_RATINGS = _Ratings(build_ratings(sub, "jockey"), build_ratings(sub, "trainer"))
    engine_core._TRAINER_SIGNAL_PRIORS = _Priors(
        _grouped_priors(sub, ["Jockey", "Trainer"]),
        _grouped_priors(sub, ["Jockey", "Distance"]),
        _grouped_priors(sub, ["Trainer", "Distance"]),
        build_change(sub),
    )
    return len(sub)


def meeting_date_from_dir(md: Path) -> str:
    import re
    m = re.match(r"(\d{4}-\d{2}-\d{2})", md.name)
    return m.group(1) if m else ""


def main() -> int:
    ap = argparse.ArgumentParser(description="point-in-time HKJC Auto backtest")
    ap.add_argument("meeting_dirs", nargs="+")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    # 強制 combo 行 as-of（archive 有注入 jockey_trainer_combo_prior，會蓋過 as-of）
    RacingEngine._jockey_trainer_prior = lambda self: None

    all_rows = load_all_rows()
    print(f"raw rows: {len(all_rows)}  date range {all_rows['Date'].min()}→{all_rows['Date'].max()}")

    all_races, errors, skipped = [], [], []
    for d in sorted(args.meeting_dirs):
        md = Path(d)
        mdate = meeting_date_from_dir(md)
        if not mdate:
            continue
        n_prior = inject_as_of(all_rows, mdate)
        races, errs = bt.rescore_meeting(md)
        all_races.extend(races)
        for e in errs:
            (skipped if e.startswith("SKIP ") else errors).append(e)
        print(f"  {md.name}: as-of<{mdate} 用 {n_prior} 行先驗，{len(races)} 場")

    agg = bt.evaluate(all_races)
    n = agg["races"] or 1
    line = " ".join(f"{m}={agg[m]}({100*agg[m]/n:.1f}%)" for m in bt.METRICS)
    print("\nPOINT-IN-TIME (no lookahead):")
    print(f"  races={agg['races']} {line}")
    if args.json:
        import json
        print(json.dumps({m: round(100*agg[m]/n, 1) for m in bt.METRICS} | {"races": agg["races"]},
                         ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
