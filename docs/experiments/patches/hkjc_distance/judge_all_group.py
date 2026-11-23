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
grp = {k for k, r in hb.load_index()["results"].items()
       if str((r.get("_header") or {}).get("RaceClass") or "").startswith("Group")}
paths = []
for src in (base, cand):
    dst = out / ("grpall_" + Path(src).name)
    with open(dst, "w") as f:
        for line in open(src):
            x = json.loads(line)
            if "horses" in x and (x["date"], x["race"]) in grp:
                f.write(line)
    paths.append(str(dst))
C.WIN["dev"] = ("2020-09-01", "2099-12-31")
sys.argv = ["x", paths[0], paths[1], "--window", "dev", "--null", "200"]
C.main()
