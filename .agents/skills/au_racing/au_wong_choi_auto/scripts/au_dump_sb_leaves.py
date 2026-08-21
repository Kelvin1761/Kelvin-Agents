#!/usr/bin/env python3
"""由**Sportsbet 重抽語料**砌 refit 用嘅 leaves dataset。

點解唔用 `au_dump_engine_leaves.py`：嗰個由 `ARCHIVE_ROOT`（Google Drive 上
現有數據源）重跑引擎。Refit 要嘅係**新數據源嘅 leaf 分佈**，所以要由我哋
重抽 + 重新評分嗰批嚟。

點解唔使重跑引擎：`Meeting_Auto_Scoring.csv` **本身就係引擎輸出** —— 17 個
`FEATURE_KEYS` 加 `ability_score` 加 `wet_form_feature` 全部喺度。重跑一次
只會慢，唔會更準。

賽果由 cache 嘅賽事頁攞（同 `au_source_compare` 同一個做法）。

⚠️ 只出**往績深度 ≥ --min-depth** 嘅場次。舊場次每匹馬得一兩仗賽前往績，
   溝埋一齊 fit 等於 fit「數據可得性隨日期變化」。

輸出格式同 `au_dump_engine_leaves.py` 逐個 key 一樣，所以
`au_matrix_refit.py verify` 照跑得。

用法：
    python3 au_dump_sb_leaves.py --scored /tmp/sb_archive --out /tmp/sb_leaves.json
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
AU_RACING = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(AU_RACING))
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR))

from au_leaf_power import norm, results_for  # noqa: E402
from au_racing_engine.scoring import FEATURE_KEYS  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="Sportsbet 語料 → refit leaves")
    ap.add_argument("--scored", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--min-depth", type=float, default=4.0)
    args = ap.parse_args()

    from sb_backfill_archive import load_meeting_ids, scored_meeting_index

    cj = Path(args.scored).parent / "source_compare.json"
    depth = ({d["meeting"]: d.get("form_depth", 0)
              for d in json.loads(cj.read_text())} if cj.exists() else {})

    meeting_dirs = scored_meeting_index(args.scored)
    races_out, runners, pf_ok, skipped_thin = [], 0, 0, 0
    for name, meta in sorted(load_meeting_ids().items(), key=lambda kv: kv[1]["date"]):
        meeting_dir = meeting_dirs.get(name)
        if meeting_dir is None:
            continue
        p = meeting_dir / "Meeting_Auto_Scoring.csv"
        if args.min_depth and depth.get(name, 0) < args.min_depth:
            skipped_thin += 1
            continue
        res = results_for(meta)
        if not res:
            continue
        by_race = {}
        with open(p, encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                by_race.setdefault(int(row["race_number"]), []).append(row)
        for rno, rows in sorted(by_race.items()):
            actual = res.get(rno)
            if not actual:
                continue
            out_rows = []
            for r in rows:
                pos = actual.get(norm(r["horse_name"]))
                if pos is None:
                    continue
                # ⚠️ 唔可以寫 `float(v) or 60` —— 0.0 係合法分數（pace_figure
                # 撞地板），`or` 會靜靜當佢中性 60。同 au_dump_engine_leaves
                # 嗰個已知陷阱一樣。
                feats = {}
                for k in FEATURE_KEYS:
                    v = r.get(k)
                    feats[k] = round(float(v), 4) if v not in (None, "") else 60.0
                runners += 1
                if abs(feats.get("pace_figure_score", 60.0) - 60.0) > 1e-9:
                    pf_ok += 1
                out_rows.append({
                    "n": int(r["horse_number"]) if str(r.get("horse_number", "")
                                                       ).isdigit() else 999,
                    "name": r["horse_name"],
                    "pos": int(pos),
                    "sp": None,
                    "features": feats,
                    "wet": float(r.get("wet_form_feature") or 0.0),
                    "ability": float(r.get("ability_score") or 0.0),
                })
            if len(out_rows) >= 4:
                races_out.append({"meeting": name, "date": meta["date"],
                                  "race": rno, "field": len(out_rows),
                                  "rows": out_rows})

    races_out.sort(key=lambda r: (r["date"], r["meeting"], r["race"]))
    Path(args.out).write_text(json.dumps({"races": races_out}), encoding="utf-8")
    print(f"races {len(races_out)}  runners {runners}")
    print(f"pace_figure 有證據: {pf_ok}/{runners} = {100*pf_ok/max(1,runners):.1f}%")
    print(f"因為往績太薄而跳過嘅場次: {skipped_thin}")
    print(f"日期範圍: {races_out[0]['date']} → {races_out[-1]['date']}")
    print(f"→ {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
