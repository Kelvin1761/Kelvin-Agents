#!/usr/bin/env python3
"""用**現行引擎**重新評分全 archive，dump 逐匹馬嘅 leaf 分落本地 cache。

點解要重 dump：`au_leaf_cache.json` 係由 Logic.json 嘅**存檔**分數起，
即係原始引擎嘅輸出。之後兩條工作線都改咗嘢：

  另一邊 —— pace_map base 55.7→60（原本 60 係天花板）、sectional base 35.8→60
            （bonus ×0.753864）、weight_score 移出 matrix、`_handicap_weight_proxy`、
            **矩陣權重重新配過**（stability .299→.437、race_shape .149→.051…）
  呢邊   —— 馬群大細百分位 base、PI 競爭力封頂、L600 改用平均、獎金班次調整、
            統一上名率取代 jockey/trainer 分

所有舊 A/B 數字都係喺舊 leaf 標尺 + 舊權重下量嘅，已經唔作準。

`WC_PF_BACKFILL=1` 會開 PF backfill（覆蓋 32.8% → 94.3%）。兩邊都要 dump：
權重重新配權必須喺**全覆蓋**下做 —— 現行 0.18831 當初係喺呢個 leaf 對
三分二馬匹失明時 fit 出嚟。

唯讀（唔會寫任何 Logic.json）。輸出 scratch/au_live_leaves{,_pf}.json。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    # 一定要喺 import engine 之前設好，backfill 開關喺 module 層讀
    from au_archive_calibrator import (  # noqa: E402
        ARCHIVE_ROOT, HISTORICAL_RESULTS_CSV, choose_track_rows, detect_meeting_date,
        detect_meeting_track, get_true_horse_name, load_historical_results,
        normalize_horse_name, parse_int)
    from au_auto_orchestrator import _build_field_summary  # noqa: E402
    from au_racing_engine.engine_core import RacingEngine  # noqa: E402
    from au_racing_engine.scoring import FEATURE_KEYS  # noqa: E402

    try:
        from au_racing_engine.engine_core import backfill_pf_metrics
    except ImportError:
        backfill_pf_metrics = None

    results = load_historical_results(HISTORICAL_RESULTS_CSV)
    races_out = []
    pf_ok = runners = 0

    for meeting_dir in sorted(p for p in ARCHIVE_ROOT.iterdir() if p.is_dir()):
        logic_files = sorted(meeting_dir.glob("Race_*_Logic.json"),
                             key=lambda p: parse_int(p.stem.split("_")[1], 999))
        if not logic_files:
            continue
        sample = json.loads(logic_files[0].read_text(encoding="utf-8"))
        date = detect_meeting_date(meeting_dir)
        track = detect_meeting_track(meeting_dir, sample)
        if not date or not track:
            continue
        for logic_path in logic_files:
            logic = json.loads(logic_path.read_text(encoding="utf-8"))
            race_analysis = logic.get("race_analysis", {})
            race_no = (parse_int(race_analysis.get("race_number"))
                       or parse_int(logic_path.stem.split("_")[1]))
            rows = choose_track_rows(results.get((date, race_no), []), track)
            if not rows:
                continue
            lookup = {normalize_horse_name(r["horse_slug"]): r for r in rows}

            horses = logic.get("horses", {})
            # ⚠️ facts_path 唔可以係 None —— `backfill_pf_metrics` 第一句就係
            # `if not facts_path ... return 0`，傳 None 會靜靜咁完全唔生效
            # （我第一次就係咁，量到「全覆蓋」其實仍然係 33%）。
            # 佢用 path 嘅 parent 搵 meeting key、用檔名補 race number。
            facts_path = meeting_dir / f"{date[5:]} Race {race_no} Facts.md"
            if backfill_pf_metrics is not None:
                try:
                    backfill_pf_metrics(logic, facts_path)
                except Exception as exc:  # noqa: BLE001
                    print(f"   backfill 失敗 {meeting_dir.name} R{race_no}: {exc}")
            ctx = dict(race_analysis)
            ctx["field_summary"] = _build_field_summary(horses)
            ctx["field_horse_names"] = [h.get("horse_name") for h in horses.values()
                                        if isinstance(h, dict) and h.get("horse_name")]

            out_rows = []
            for hnum, horse in horses.items():
                row = lookup.get(normalize_horse_name(get_true_horse_name(horse)))
                if not row:
                    continue
                hd = dict(horse)
                hd.setdefault("horse_number", hnum)
                facts = (hd.get("_data") or {}).get("facts_section", "")
                eng = RacingEngine(hd, ctx, facts_section=facts,
                                   facts_path=str(meeting_dir / f"{date}_dummy.md"))
                res = eng.analyze_horse()
                fs = res.get("feature_scores") or {}
                runners += 1
                if (res.get("pace_perf_detail") or {}).get("pace", {}).get("state") == "ok":
                    pf_ok += 1
                out_rows.append({
                    "n": parse_int(hnum) or 999,
                    "name": get_true_horse_name(horse),
                    "pos": int(row["pos"]),
                    "sp": row.get("sp"),
                    # ⚠️ 唔可以寫 `fs.get(k, 60) or 60` —— 分數 **0.0** 係合法值
                    # （pace_figure 撞落地板），`or` 會靜靜雞當佢係中性 60。
                    # 實測 7,547 匹有 3 匹中招，replica 對唔到真引擎差 12.20 分。
                    "features": {k: round(float(60 if fs.get(k) is None else fs[k]), 4)
                                 for k in FEATURE_KEYS},
                    "wet": float(res.get("wet_form_feature") or 0.0),
                    "ability": float(res.get("ability_score") or 0.0),
                })
            if len(out_rows) >= 4:
                races_out.append({"meeting": meeting_dir.name, "date": date,
                                  "race": race_no, "field": len(out_rows),
                                  "rows": out_rows})

    races_out.sort(key=lambda r: (r["date"], r["meeting"], r["race"]))
    dest = Path(args.out)
    dest.write_text(json.dumps({"races": races_out}), encoding="utf-8")
    print(f"races {len(races_out)}  runners {runners}")
    print(f"pace_figure state=ok: {pf_ok}/{runners} = {100*pf_ok/max(1,runners):.1f}%")
    print(f"WC_PF_BACKFILL={os.environ.get('WC_PF_BACKFILL', '(unset)')}")
    print(f"→ {dest}")


if __name__ == "__main__":
    main()
