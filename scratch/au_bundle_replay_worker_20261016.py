#!/usr/bin/env python3
"""EXP-20261016-74 重播 worker：用 `--repo` 嗰個 checkout 嘅引擎，評分 `--stage` 入面已驗證、已抄出嘅賽前快照。

每個 stage 子目錄 = 一個場次（目錄名 = 場次名，所以引擎攞到賽日同場地），入面係快照原檔。
`stage/manifest.json`：[{"dir": 場次名, "date": "YYYY-MM-DD", "created_at": ISO}]。
輸出每匹馬嘅 features／wet／proven_class／full_time／ability（唔對賽果；對賽果喺主工具做）。
A0（d51796e1）冇 `refresh_form_quality`，所以所有 enrichment 都係「有就叫」。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--stage", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    scripts = Path(args.repo) / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
    sys.path.insert(0, str(scripts))
    from au_archive_calibrator import get_true_horse_name
    from au_auto_orchestrator import _build_field_summary
    from au_racing_engine import engine_core as ec
    from au_racing_engine import full_time_speed
    from au_racing_engine.scoring import FEATURE_KEYS

    stage = Path(args.stage)
    manifest = json.loads((stage / "manifest.json").read_text(encoding="utf-8"))
    out = []
    for item in manifest:
        folder = stage / item["dir"]
        date = item["date"]
        prediction_at = datetime.fromisoformat(item["created_at"])
        logic_files = sorted(folder.glob("Race_*_Logic.json"), key=lambda p: int(p.stem.split("_")[1]))
        for path in logic_files:
            logic = json.loads(path.read_text(encoding="utf-8"))
            ra = logic.get("race_analysis", {})
            race_no = int(ra.get("race_number") or path.stem.split("_")[1])
            facts = folder / f"{date[5:]} Race {race_no} Facts.md"
            for name in ("refresh_pf_own_l600", "refresh_form_quality"):
                fn = getattr(ec, name, None)
                if fn is not None:
                    fn(logic, facts)
            ec.backfill_prize_column(logic, folder, race_no, date)
            full_time_speed.prepare_field(logic, facts, prediction_at=prediction_at)
            horses = logic.get("horses", {})
            ctx = dict(ra)
            ctx["field_summary"] = _build_field_summary(horses)
            ctx["field_horse_names"] = [h.get("horse_name") for h in horses.values()
                                        if isinstance(h, dict) and h.get("horse_name")]
            rows = []
            for number, horse in horses.items():
                if not isinstance(horse, dict):
                    continue
                hd = dict(horse)
                hd.setdefault("horse_number", number)
                res = ec.RacingEngine(hd, ctx, facts_section=(hd.get("_data") or {}).get("facts_section", ""),
                                      facts_path=str(folder / f"{date}_dummy.md")).analyze_horse()
                fs = res.get("feature_scores") or {}
                rows.append({
                    "n": int(number) if str(number).isdigit() else 999,
                    "name": get_true_horse_name(horse),
                    "features": {k: round(float(60 if fs.get(k) is None else fs[k]), 6) for k in FEATURE_KEYS},
                    "wet": float(res.get("wet_form_feature") or 0.0),
                    "proven_class": float(res.get("proven_class_feature") or 0.0),
                    "full_time": float(res.get("full_time_speed_feature") or 0.0),
                    "ability": float(res.get("ability_score") or 0.0),
                })
            out.append({"meeting": item["dir"], "date": date, "race": race_no, "rows": rows})
    Path(args.out).write_text(json.dumps({"races": out}), encoding="utf-8")
    print(f"scored {len(out)} races from {len(manifest)} meetings")


if __name__ == "__main__":
    main()
