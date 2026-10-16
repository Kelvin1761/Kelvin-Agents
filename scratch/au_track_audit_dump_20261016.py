#!/usr/bin/env python3
"""研究用 dump（EXP-20261016-70 場地審計：`trk` 欄記 track_score 輸入同 Formguide Synth 紀錄）。

上游：研究用 dump（EXP-20261016-18 官方評分對位審計，由 `au_jt_audit_dump_20261016.py` 衍生）。

只用 production 設定評一次，另記 rating_score／class_score 嘅全部輸入（`cls` 欄），畀離線 replica 重算。
以下係上游說明：
研究用 dump（EXP-20261016-12／-13，由 `au_stability_dump_20261016.py` 衍生）。

每匹馬評兩次：`FORM_ENTRY_CLASS_TIER=False`（baseline，即 main 5c41c8be 行為）同 True（K2）。
另記騎練訊號逐項加分（人馬配搭分 adjustments、現役騎師策騎次數、換騎訊號、騎練分來源）。

原說明（EXP-20261016-04，由 EXP-20261016-01 嘅 dump 衍生）：同 `au_dump_engine_leaves.py` 一模一樣嘅評分路徑，
另外逐匹馬輸出 `pf_run_list`（引擎實際食嘅 PF 往績，連位置／頭馬時間），
畀 pace_perf 診斷離線重算 L600 變體。唯讀，唔寫 Logic.json。

由 au_dump_engine_leaves.py 自動生成：喺 production dump 嘅 row 加一欄，其餘不變。
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR))


def _corpus_meeting_dirs(root):
    """Meeting folders under `root` AND under `root/Archive`."""
    import sys as _s
    from pathlib import Path as _P
    shared = SCRIPT_DIR.parents[2] / "shared_racing" / "scripts"
    if str(shared) not in _s.path:
        _s.path.insert(0, str(shared))
    from corpus_paths import meeting_dirs
    return sorted(meeting_dirs(root))

def _six_run_digests(meeting_dir, race_no, date):
    """Same parse + digest as production PQ, but up to 6 runs (research only).

    The recency tuple is swapped only for this call; production scoring above
    keeps its 4-run digest.
    """
    import re as _re
    from au_racing_engine import engine_core as _ec
    paths = sorted(meeting_dir.glob(f"*Race {race_no} Formguide.md"))
    if not paths:
        return {}
    text = paths[0].read_text(encoding="utf-8")
    heads = list(_re.finditer(r"^\[(\d+)\]\s+(.+?) \((\d+)\)\s*$", text, _re.M))
    saved = _ec._PERFORMANCE_QUALITY_RECENCY_WEIGHTS
    _ec._PERFORMANCE_QUALITY_RECENCY_WEIGHTS = (1.0, 0.8, 0.6, 0.4, 0.3, 0.2)
    out = {}
    try:
        for i, h in enumerate(heads):
            section = text[h.start(): heads[i + 1].start() if i + 1 < len(heads) else len(text)]
            entries = [e for e in _ec._parse_formguide_entries(section, h.group(2).strip())
                       if str(e.get("date") or "") < date and not e["is_trial"]]
            out[h.group(1)] = _ec._performance_quality_digest(entries, meeting_date=date).get("runs", [])
    finally:
        _ec._PERFORMANCE_QUALITY_RECENCY_WEIGHTS = saved
    return out


def _synth_records(meeting_dir, race_no):
    """{horse_number: (starts, wins, seconds, thirds)} from the Formguide `Synth:` cell."""
    import re as _re
    paths = sorted(meeting_dir.glob(f"*Race {race_no} Formguide.md"))
    if not paths:
        return {}
    text = paths[0].read_text(encoding="utf-8")
    heads = list(_re.finditer(r"^\[(\d+)\]\s+(.+?) \((\d+)\)\s*$", text, _re.M))
    out = {}
    for i, h in enumerate(heads):
        section = text[h.start(): heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        m = _re.search(r"Synth:\s*(\d+):\s*(\d+)-(\d+)-(\d+)", section)
        if m:
            out[h.group(1)] = [int(g) for g in m.groups()]
    return out


def _class_inputs(eng, ctx):
    entries = eng._official_entries()
    latest = entries[0] if entries else {}
    fs = ctx.get("field_summary") or {}
    wp = eng._handicap_weight_proxy()[0]
    return {
        "rating": eng._horse_rating(),
        "rated_count": fs.get("rated_count"), "avg_rating": fs.get("avg_rating"),
        "rating_stdev": fs.get("rating_stdev"), "top3_cutoff": fs.get("top3_rating_cutoff"),
        "race_bucket": eng._race_class_bucket(), "weight_proxy": wp,
        "rating_source": (getattr(eng, "rating_detail", None) or {}).get("source"),
        "career_starts": eng._career_starts(), "race_class": eng._race_class_text(),
        "latest_placing": latest.get("placing"), "latest_field_size": latest.get("field_size"),
        "latest_venue": latest.get("venue"), "latest_prize": latest.get("prize"),
        "today_venue": eng._meeting_intelligence().get("venue") or eng._track_profile().get("venue") or "",
        "today_prize": eng.race_context.get("prize"), "class_move": eng._class_move_today(),
        "latest_rt": eng._latest_l600_rt_metrics().get("rt"),
        "class_notes": (getattr(eng, "class_detail", None) or {}).get("notes", []),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--variant", required=True)
    args = ap.parse_args()

    # 一定要喺 import engine 之前設好，backfill 開關喺 module 層讀
    from au_archive_calibrator import (  # noqa: E402
        ARCHIVE_ROOT, HISTORICAL_RESULTS_CSV, choose_track_rows, detect_meeting_date,
        detect_meeting_track, get_true_horse_name, load_historical_results,
        normalize_horse_name, parse_int)
    from au_auto_orchestrator import _build_field_summary  # noqa: E402
    from au_racing_engine.engine_core import RacingEngine  # noqa: E402
    from au_racing_engine.engine_core import backfill_prize_column  # noqa: E402
    from au_racing_engine.scoring import FEATURE_KEYS  # noqa: E402

    from au_racing_engine.engine_core import backfill_pf_metrics
    from au_racing_engine.engine_core import refresh_pf_own_l600
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import au_paceperf_variants_20261016 as _variants
    _variants.apply(args.variant)
    from au_racing_engine import engine_core as _ec
    performance_pf_metrics = lambda h: _ec.performance_pf_metrics(h)  # noqa: E731  (patched per variant)

    results = load_historical_results(HISTORICAL_RESULTS_CSV)
    races_out = []
    pf_ok = runners = 0
    prize_filled = 0
    refreshed_own_l600 = 0

    # `ARCHIVE_ROOT.iterdir()` only saw the top level, so every meeting the daily
    # schedule had already filed into `<root>/Archive/` was invisible here —
    # measured 2026-08-21: 751 of 1,530 scored races (49.1%), and 16 of the 17
    # dates that are clean point-in-time. This dumper is the ONLY data source for
    # au_eval / au_feature_ab / au_matrix_refit, so the whole judging layer was
    # deciding on the older, post-race-rescored half of the corpus.
    for meeting_dir in _corpus_meeting_dirs(ARCHIVE_ROOT):
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
            # 舊 Logic 嘅 pf_metrics 只存咗 race-level `l600_delta`，冇 `margin`。
            # 唔喺呢度重新 parse，個體化 L600 就永遠接唔通，A/B 會同 baseline
            # 一模一樣 —— 而「一模一樣」係冇接通嘅徵狀。**一定要喺
            # `_build_field_summary` 之前跑**：個分係場內 z-score，分子同
            # 場均要嚟自同一個量。
            if refresh_pf_own_l600 is not None:
                try:
                    refreshed_own_l600 += refresh_pf_own_l600(logic, facts_path)
                except Exception as exc:  # noqa: BLE001
                    print(f"   own-L600 refresh 失敗 {meeting_dir.name} R{race_no}: {exc}")
            # 班次水平調整（`horse_prize_level`）讀 Facts 第 19 欄，而個欄 2026-07-31
            # 先開始寫。Live meeting 有（2026-09 實測 90-95%），但語料 14 個月入面
            # 有 12 個月冇 —— 即係話 dev 窗一直**冇施加**呢個調整，而 production 有。
            # 呢個唔係數據冇咗：Formguide 逐仗獎金 100% 仲喺度。
            # ⚠️ 一定要喺 `_build_field_summary` 之前 —— 個調整係「本駒水平 −
            # 場內中位」，兩邊要嚟自同一個量度，唔然就同 own-L600 一樣靜靜錯。
            prize_filled += backfill_prize_column(logic, meeting_dir, race_no, date)
            # 近績質素分（EXP-20261016-06）係場內相對，一定要喺 field summary 之前。
            from au_racing_engine.engine_core import refresh_form_quality
            refresh_form_quality(logic, facts_path)
            from au_racing_engine.full_time_speed import prepare_field
            prepare_field(logic, facts_path)
            ctx = dict(race_analysis)
            ctx["field_summary"] = _build_field_summary(horses)
            ctx["field_horse_names"] = [h.get("horse_name") for h in horses.values()
                                        if isinstance(h, dict) and h.get("horse_name")]

            out_rows = []
            runs6 = _six_run_digests(meeting_dir, race_no, date)
            synth = _synth_records(meeting_dir, race_no)
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
                    "features": {k: round(float(60 if fs.get(k) is None else fs[k]), 6)
                                 for k in FEATURE_KEYS},
                    "wet": float(res.get("wet_form_feature") or 0.0),
                    "proven_class": float(res.get("proven_class_feature") or 0.0),
                    "full_time": float(res.get("full_time_speed_feature") or 0.0),
                    "ability": float(res.get("ability_score") or 0.0),
                    # 分層用（唔入分）：初出／休後實驗要喺同一份 dump 切 cohort。
                    "career_starts": hd.get("career_race_starts"),
                    "prep_stage": (res.get("preparation_cycle") or {}).get("stage"),
                    "days_since_last": (res.get("preparation_cycle") or {}).get("days_since_last_run"),
                    "pf_runs": ((res.get("pace_perf_detail") or {}).get("pace") or {}).get("runs"),  # walk-forward 研究欄（EXP-20261012-32）
                    "barrier": hd.get("barrier"), "field_n": len(horses),  # walk-forward 研究欄（EXP-20261012-32）
                    "distance": race_analysis.get("distance"), "going": (res.get("race_context") or {}).get("going"),  # walk-forward 研究欄（EXP-20261012-32）
                    "style": (hd.get("_data") or {}).get("running_style_line"),
                    "pf_run_list": [
                        {k: run.get(k) for k in ("l600_delta", "margin", "run_date", "distance",
                                                 "run_kind", "source", "pos_800", "pos_400",
                                                 "pos_settled", "finish", "starters", "winning_time")}
                        for run in (performance_pf_metrics(hd).get("pf_runs") or [])],
                    "trial_score_raw": fs.get("trial_score"),
                    "form_entries": [{k: e.get(k) for k in ("placing", "field_size", "source_race_class",
                                                            "date", "venue", "prize", "kind")}
                                     for e in eng._official_entries()[:4]],
                    "today_class": ctx.get("race_class"),
                    "minus4": any(b.get("factor") == "[環境] 級數偏弱收回"
                                  for b in (getattr(eng, "form_detail", {}) or {}).get("bonus", [])),
                    "pq_runs": (eng.data.get("performance_quality_runs") or []),
                    "pq_source": eng.provenance.get("performance_quality_score"),
                    "pq_runs6": runs6.get(str(hnum), []),  # walk-forward 研究欄（EXP-20261012-32）
                    "trk": {"track_stats_line": eng.data.get("track_stats_line"),
                            "going_stats_line": eng.data.get("going_stats_line"),
                            "today_going": eng._today_going(), "wet_state": eng._wet_state(),
                            "going_bucket": eng._track_context().get("going_bucket", ""),
                            "today_venue": eng._meeting_intelligence().get("venue") or eng._track_profile().get("venue") or "",
                            "synth": synth.get(str(hnum))},
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
    print(f"own-L600 refreshed runners: {refreshed_own_l600}")
    print(f"prize column rows backfilled: {prize_filled}")
    print(f"WC_PF_BACKFILL={os.environ.get('WC_PF_BACKFILL', '(unset)')}")
    print(f"→ {dest}")


if __name__ == "__main__":
    main()
