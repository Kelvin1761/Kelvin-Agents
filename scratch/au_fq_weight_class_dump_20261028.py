#!/usr/bin/env python3
"""研究用 dump（EXP-20261028-11／-12／-13），由 `au_dump_engine_leaves.py` 衍生。

評分路徑同 production 一模一樣，只係逐匹馬多記三欄畀離線 replica 用：
  fq   近績質素分逐仗輸入（form_quality_detail + 場內統計）
  cls  級數分／官方評分對位全部輸入，加負磅代理輸入、賽事名分類、年齡性別
唯讀，唔寫 Logic.json。
"""
from __future__ import annotations

import argparse
import re
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

# 賽事名分類（EXP-20261028-12 預先登記，量度前寫死）。只用賽前賽事名。
_HCP_RE = re.compile(r"\b(?:handicap|hcp|hcap|h'cap|benchmark|bm\s*\d+|rst\s*\d+)\b"
                     r"|\b(?:rating\s*)?\d{1,2}\s*-\s*\d{2,3}\b|\brating\s+\d", re.I)
_SW_RE = re.compile(r"\b(?:plate|quality|stakes|wfa|sw|set[ -]+weights?|weight[ -]+for[ -]+age|maiden|mdn|qtis)\b", re.I)


# 賽事名喺 ~45 字截斷：「MAIDEN HANDI」「CG&E MAIDEN HA」「BENCHMARK 65 Hand」。
# 量度前（睇 title 樣本、未睇賽果）發現，補：尾字係 "handicap" 嘅前綴（≥2 字）當讓磅。
_TRUNC_HCP_RE = re.compile(r"\bh(?:a(?:n(?:d(?:i(?:c(?:a(?:p)?)?)?)?)?)?)\s*$", re.I)


def classify_title(title):
    t = " ".join(str(title or "").replace("&amp;", "&").split())
    if _HCP_RE.search(t) or (len(t) >= 40 and _TRUNC_HCP_RE.search(t)):
        return "handicap"
    if _SW_RE.search(t):
        return "set_weight"
    return "unknown"


def _racecard_age_sex(meeting_dir, race_no):
    out = {}
    for p in sorted(meeting_dir.glob(f"*Race {race_no} Racecard.md"))[:1]:
        name = None
        for line in p.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^\d+\.\s+(.+?)\s+\(\d+\)\s*$", line)
            if m:
                name = m.group(1).strip()
                continue
            a = re.search(r"Age:\s*(\d+)yo([A-Za-z]+)", line)
            if a and name:
                out[name.lower()] = (int(a.group(1)), a.group(2).upper())
                name = None
    return out


def _extra(eng, res, ctx, hd, age_sex):
    fs = ctx.get("field_summary") or {}
    entries = eng._official_entries()
    latest = entries[0] if entries else {}
    fqd = dict(getattr(eng, "form_quality_detail", None) or {})
    fqd["runs"] = [{k: r.get(k) for k in ("date", "finish_pos", "starters", "prize", "distance", "value")}
                   for r in (fqd.get("runs") or [])]
    # 改動前 engine 有 `_is_wfa_or_sw_race`；改動後換成 `_is_handicap_race`（EXP-12）。
    wfa = eng._is_wfa_or_sw_race() if hasattr(eng, "_is_wfa_or_sw_race") else not eng._is_handicap_race()
    title = eng._race_class_text()
    age, sex = age_sex.get(str(hd.get("horse_name") or "").lower(), (None, None))
    return {
        "fq": {**fqd, "field_mean": fs.get("form_quality_field_mean"),
               "field_stdev": fs.get("form_quality_field_stdev"),
               "field_count": fs.get("form_quality_field_count"),
               "today_distance": eng._distance_m()},
        "cls": {
            "rating": eng._horse_rating(), "rated_count": fs.get("rated_count"),
            "avg_rating": fs.get("avg_rating"), "rating_stdev": fs.get("rating_stdev"),
            "rating_source": (getattr(eng, "rating_detail", None) or {}).get("source"),
            "weight": hd.get("weight"), "avg_weight": fs.get("avg_weight"),
            "weight_stdev": fs.get("weight_stdev"), "weighted_count": fs.get("weighted_count"),
            "engine_is_sw": wfa, "title": title, "title_class": classify_title(title),
            "age": age, "sex": sex,
            "career_starts": eng._career_starts(), "race_bucket": eng._race_class_bucket(),
            "latest_placing": latest.get("placing"), "latest_field_size": latest.get("field_size"),
            "today_tier": eng._venue_tier(eng._meeting_intelligence().get("venue") or eng._track_profile().get("venue") or ""),
            "latest_tier": eng._venue_tier(latest.get("venue") if entries else ""),
            "class_move": eng._class_move_today(), "latest_rt": eng._latest_l600_rt_metrics().get("rt"),
            "class_notes": (getattr(eng, "class_detail", None) or {}).get("notes", []),
        },
    }


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
    from au_racing_engine.engine_core import backfill_prize_column  # noqa: E402
    from au_racing_engine.scoring import FEATURE_KEYS  # noqa: E402

    from au_racing_engine.engine_core import backfill_pf_metrics
    from au_racing_engine.engine_core import refresh_pf_own_l600
    from au_racing_engine.engine_core import refresh_form_quality
    from au_racing_engine.engine_core import refresh_trial_runs

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
            refresh_form_quality(logic, facts_path)
            refresh_trial_runs(logic, facts_path)
            from au_racing_engine.full_time_speed import prepare_field
            prepare_field(logic, facts_path)
            ctx = dict(race_analysis)
            ctx["field_summary"] = _build_field_summary(horses)
            ctx["field_horse_names"] = [h.get("horse_name") for h in horses.values()
                                        if isinstance(h, dict) and h.get("horse_name")]

            age_sex = _racecard_age_sex(meeting_dir, race_no)
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
                    "style": (hd.get("_data") or {}).get("running_style_line"),  # walk-forward 研究欄（EXP-20261012-32）
                    **_extra(eng, res, ctx, hd, age_sex),
                })
            if len(out_rows) >= 4:
                # 場內統計用 Logic 全部馬（包括冇對到賽果嘅），候選要用同一個母體重算。
                fq_field = [((h.get("_data") or {}).get("form_quality_runs") or [])
                            for h in horses.values() if isinstance(h, dict)
                            and (h.get("_data") or {}).get("form_quality_raw") is not None]
                races_out.append({"meeting": meeting_dir.name, "date": date,
                                  "race": race_no, "field": len(out_rows),
                                  "fq_field": [[{k: r.get(k) for k in ("finish_pos", "starters", "prize", "value")}
                                                for r in runs] for runs in fq_field],
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
