#!/usr/bin/env python3
"""一次過抽 archive 需要嘅欄位落本地 cache，之後 leaf-level shadow sweep 唔再讀 Drive。

同時做 faithful-replay 保真度檢查：由持久化嘅 `feature_scores` 重算
`pure_7d_score`，同存檔值比對。對唔上嘅 race 要標出嚟，唔可以靜靜計入 A/B。

唯讀。輸出 scratch/au_leaf_cache.json。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR / "racing_engine"))

from au_archive_calibrator import (  # noqa: E402
    ARCHIVE_ROOT,
    HISTORICAL_RESULTS_CSV,
    iter_logic_rows,
    load_historical_results,
)
from matrix_mapper import map_features_to_matrix_scores  # noqa: E402
from scoring import FEATURE_KEYS, MATRIX_WEIGHTS, clip_score  # noqa: E402

PI_HEAD = re.compile(r"[+-]\d+")


def recompute_pure7d(features):
    matrix = map_features_to_matrix_scores(features)
    return 60.0 + sum((matrix[k] - 60.0) * w for k, w in MATRIX_WEIGHTS.items())


def pi_run_count(data):
    trend = str(data.get("sectional_trend_line") or "")
    return len(PI_HEAD.findall(trend.split("L400")[0]))


def main():
    results = load_historical_results(HISTORICAL_RESULTS_CSV)
    races = []
    drift = []
    for race_rows in iter_logic_rows(ARCHIVE_ROOT, results):
        out_rows = []
        for r in race_rows:
            pa = r["horse"].get("python_auto") or {}
            ppd = pa.get("pace_perf_detail") or {}
            sd = pa.get("stability_detail") or {}
            pace = ppd.get("pace") or {}
            sec = ppd.get("sectional") or {}
            form = sd.get("form") or {}
            cons = sd.get("consistency") or {}
            features = {k: clip_score(r["feature_scores"].get(k, 60)) for k in FEATURE_KEYS}
            stored = r["pure_7d_score"]
            replay = recompute_pure7d(features)
            out_rows.append({
                "n": r["horse_number"],
                "name": r["horse_name"],
                "pos": r["actual_pos"],
                "sp": r["sp"],
                "ability": r["model_score"],
                "pure7d_stored": stored,
                "pure7d_replay": round(replay, 4),
                "wet": r["wet_form_feature"],
                "features": {k: round(v, 4) for k, v in features.items()},
                "pace_z": pace.get("z"),
                "pace_runs": pace.get("runs"),
                "pace_state": pace.get("state"),
                "sec_base": sec.get("base"),
                "sec_score": sec.get("score"),
                "sec_items": [{"d": i.get("delta"), "f": i.get("factor")}
                              for i in (sec.get("items") or [])],
                "sec_has_pi": sec.get("has_pi"),
                "pi_runs": pi_run_count(r["data"]),
                "form_rows": len(form.get("rows") or []),
                # 逐場明細，令 form_score 可以忠實 replay（base/mult/decay/place）
                "form_rows_detail": [
                    {"place": r0.get("place"), "base": r0.get("base"),
                     "mult": r0.get("mult"), "decay": r0.get("decay"),
                     "cls": r0.get("cls")}
                    for r0 in (form.get("rows") or [])
                ],
                # 平均分之後嘅加成，但唔包「劣績中性回歸」（replay 會自己重算）
                "_extra_bonus": round(sum(
                    float(b.get("delta") or 0.0)
                    for b in (form.get("bonus") or [])
                    if str(b.get("factor")) != "劣績中性回歸"
                ), 4),
                "form_final": form.get("final"),
                "cons_base": cons.get("base"),
                "cons_adj": [{"d": a.get("delta"), "f": a.get("factor"),
                              "e": a.get("evidence")} for a in (cons.get("adjustments") or [])],
            })
            if stored is not None and abs(replay - stored) > 0.05:
                drift.append({"meeting": r["meeting"], "race": r["race"],
                              "horse": r["horse_name"],
                              "stored": stored, "replay": round(replay, 4)})
        races.append({
            "meeting": race_rows[0]["meeting"],
            "date": race_rows[0]["date"],
            "race": race_rows[0]["race"],
            "field": len(race_rows),
            "rows": out_rows,
        })

    races.sort(key=lambda r: (r["date"], r["meeting"], r["race"]))
    runners = sum(len(r["rows"]) for r in races)
    payload = {"races": races, "replay_drift": drift[:200],
               "replay_drift_count": len(drift), "runners": runners}
    dest = Path(__file__).resolve().parent / "au_leaf_cache.json"
    dest.write_text(json.dumps(payload), encoding="utf-8")

    print(f"races {len(races)}  runners {runners}")
    print(f"faithful-replay drift (|Δpure7d| > 0.05): {len(drift)} / {runners}"
          f" = {100 * len(drift) / max(1, runners):.2f}%")
    for d in drift[:10]:
        print(f"   {d['meeting'][:30]:30} R{d['race']:<2} {d['horse'][:18]:18}"
              f" stored {d['stored']} replay {d['replay']}")
    pf_ok = sum(1 for r in races for h in r["rows"] if h["pace_state"] == "ok")
    print(f"pace_figure state=ok: {pf_ok} / {runners} = {100 * pf_ok / max(1, runners):.1f}%")
    pi = {}
    for r in races:
        for h in r["rows"]:
            pi[h["pi_runs"]] = pi.get(h["pi_runs"], 0) + 1
    print("PI run counts:", dict(sorted(pi.items())))
    pr = {}
    for r in races:
        for h in r["rows"]:
            if h["pace_state"] == "ok":
                pr[h["pace_runs"]] = pr.get(h["pace_runs"], 0) + 1
    print("pace_figure runs (state=ok):", dict(sorted(pr.items())))
    print(f"cache → {dest}")


if __name__ == "__main__":
    main()
