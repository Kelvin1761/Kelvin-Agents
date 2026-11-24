#!/usr/bin/env python3
"""EXP-20261124-22：R2（EXP-20261122-04）同練馬師剩餘表現（EXP-20261122-02）喺真 live dump 重判（log-loss 尺 v2）。
  rollback.py DIR OUT.json   —— DIR 有 BASE.json（live）、NO_R2.json、NO_TRES.json（同一 code，各關一個開關）"""
import json, sys
from pathlib import Path
SC = Path(__file__).resolve().parents[4] / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SC)); sys.path.insert(0, str(SC.parents[2] / "shared_racing"))
import au_logloss_ruler as L  # noqa: E402
D = Path(sys.argv[1]); load = lambda n: L.eligible(json.loads((D / f"{n}.json").read_text())["races"])
live = load("BASE"); out = {}
for arm, off in (("R2", "NO_R2"), ("TRES", "NO_TRES")):
    base = load(off)
    moved = sum(1 for a, b in zip(base, live) for x, y in zip(a["rows"], b["rows"]) if abs(x["ability"] - y["ability"]) >= 0.005)
    v = L.evaluate(base, live, nnull=200)   # baseline = 冇呢個改動，candidate = live
    v["horses_moved"] = moved; out[arm] = v
    print(arm, "moved", moved, v["verdict"], v["reason"], [round(t, 6) for t in v["dlogloss"]], "AUC", v.get("auc"),
          "G", [round(t, 2) for t in v["gold_pp"]], "Gd", [round(t, 2) for t in v["good_pp"]],
          "top2any", round(v["top2_any_hit_pp"], 2), flush=True)
Path(sys.argv[2]).write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float))
