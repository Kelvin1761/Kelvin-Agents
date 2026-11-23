"""EXP-20261123-09 第三輪：六季級際賽判（v5.2 尺，dev 窗擴到 2020-09 → 全期；測試季 2021/22–2026/27 逐季 walk-forward 校準，2020/21 只做校準）。
用法：python3 judge_all_group.py <base.jsonl> <cand.jsonl> <out_dir>"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
import hkjc_history_replay_build as hb  # noqa: E402
import types  # noqa: E402
_src = open("/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_replay_compare_v5.py").read()
assert "for ts in (2021, 2022, 2023):" in _src
_src = _src.replace("for ts in (2021, 2022, 2023):", "for ts in (2021, 2022, 2023, 2024, 2025, 2026):")
_src = _src.replace('if __name__ == "__main__":', "if False:")
C = types.ModuleType("v5all"); C.__file__ = "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_replay_compare_v5.py"
exec(compile(_src, "v5all", "exec"), C.__dict__)

base, cand, out = sys.argv[1], sys.argv[2], Path(sys.argv[3])
SUBSET = sys.argv[4] if len(sys.argv) > 4 else "group"   # group｜d1000（EXP-20261123-11 第二輪：Kelvin「好似級際賽咁用六季全部 1000 米場次判」）
if SUBSET == "group":
    grp = {k for k, r in hb.load_index()["results"].items()
           if str((r.get("_header") or {}).get("RaceClass") or "").startswith("Group")}
elif SUBSET == "straight":   # 沙田草地 1000 米
    _idx = hb.load_index()["results"]
    grp = {(x["date"], x["race"]) for x in map(json.loads, open(base)) if "horses" in x and x["venue"] != "跑馬地"
           and x.get("distance") == 1000 and not (x.get("awt") or "全天候" in str((_idx.get((x["date"], x["race"])) or {}).get("course") or ""))}
elif SUBSET == "small":   # EXP-20261123-17：出賽 ≤ 9 匹
    grp = {(x["date"], x["race"]) for x in map(json.loads, open(base)) if "horses" in x
           and sum(1 for h in x["horses"] if h["pos"]) <= 9}
elif SUBSET == "awt":   # EXP-20261123-15：泥地
    _idx = hb.load_index()["results"]
    grp = {(x["date"], x["race"]) for x in map(json.loads, open(base)) if "horses" in x
           and (x.get("awt") or "全天候" in str((_idx.get((x["date"], x["race"])) or {}).get("course") or ""))}
elif SUBSET == "debut":   # EXP-20261123-13：有初出馬嘅場
    grp = {(x["date"], x["race"]) for x in map(json.loads, open(base)) if "horses" in x and any(h.get("debut") for h in x["horses"])}
else:
    grp = {(x["date"], x["race"]) for x in map(json.loads, open(base)) if "horses" in x and x.get("distance") == 1000}
paths = []
for src in (base, cand):
    dst = out / (f"{SUBSET}all_" + Path(src).name)
    with open(dst, "w") as f:
        for line in open(src):
            x = json.loads(line)
            if "horses" in x and (x["date"], x["race"]) in grp:
                f.write(line)
    paths.append(str(dst))
C.WIN["dev"] = ("2020-09-01", "2099-12-31")
sys.argv = ["x", paths[0], paths[1], "--window", "dev", "--null", "200"]
C.main()
