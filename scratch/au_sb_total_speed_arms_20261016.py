#!/usr/bin/env python3
"""EXP-20261016-02 G3：由 production dump 砌 S1／S2 候選 dump（只改登記咗嘅欄位）。

S1 疊加項：場內冇外部官方全程 A（full_time 全部 0）→ full_time = 1.5 × z × 可靠度（A_sb）；
          有外部 A 嘅場次原封不動。
S2 入 pace_perf：pace_figure_score = 0.5 × PF + 0.5 × (60 + 10 × z(A_sb))，冇 A_sb = 60。
兩個都用 production 算術重算 `ability`（refit 工具 verify 用）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SCRIPTS))

from au_racing_engine.scoring import MATRIX_WEIGHTS  # noqa: E402
from au_walkforward_refit import exact_score  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--asb", required=True)
    ap.add_argument("--arm", choices=("S1", "S2"), required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    dump = json.loads(Path(args.dump).read_text(encoding="utf-8"))
    asb = json.loads(Path(args.asb).read_text(encoding="utf-8"))["asb"]
    changed = kept_external = 0
    for race in dump["races"]:
        details = [asb.get(f"{race['date']}|{race['meeting']}|{race['race']}|{r['n']}") for r in race["rows"]]
        if not any(details):
            continue
        external = any(abs(float(r.get("full_time") or 0)) > 0 for r in race["rows"])
        for row, d in zip(race["rows"], details):
            if args.arm == "S1":
                if external:
                    kept_external += 1
                    continue
                # 4dp: refit numpy accelerator rounds halves differently at 8dp (≤5e-5 per runner)
                row["full_time"] = round(d["s1"], 4) if d else 0.0
            else:
                z = d["z"] if d and d["raw"] is not None else 0.0
                pf = row["features"]["pace_figure_score"]
                row["features"]["pace_figure_score"] = round(0.5 * pf + 0.5 * (60 + 10 * z), 6)
            row["ability"] = exact_score(row, MATRIX_WEIGHTS)
            changed += 1
    Path(args.out).write_text(json.dumps(dump), encoding="utf-8")
    print(f"{args.arm}: rows changed {changed}, external rows kept {kept_external} → {args.out}")


if __name__ == "__main__":
    main()
