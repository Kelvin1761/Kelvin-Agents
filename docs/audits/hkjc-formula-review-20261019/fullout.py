"""Run the HKJC engine on every stored Logic runner and write the full analyze_horse() output (JSON lines)."""
import glob, json, sys, os
from pathlib import Path
repo = Path(sys.argv[1]); out = sys.argv[2]
sys.path.insert(0, str(repo / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts")); sys.path += [str(repo), str(repo / ".agents/skills/hkjc_racing/hkjc_reflector/scripts"), str(repo / ".agents/scripts")]
from hkjc_racing_engine.engine_core import RacingEngine
root = Path(open(repo / ".wongchoi_hk_data_root").read().strip())
files = sorted(glob.glob(str(root / "20*_*" / "Race_*_Logic.json")))
n = 0
with open(out, "w") as fh:
    for lf in files:
        try:
            logic = json.load(open(lf, encoding="utf-8"))
        except Exception:
            continue
        ctx = dict(logic.get("race_context") or {})
        ctx.setdefault("race_date", Path(lf).parent.name[:10])
        for num, h in sorted((logic.get("horses") or {}).items()):
            if not isinstance(h, dict):
                continue
            h = {k: v for k, v in h.items() if k != "python_auto"}
            r = RacingEngine(h, dict(ctx)).analyze_horse()
            fh.write(json.dumps({"file": lf[len(str(root)):], "h": num, "r": r}, ensure_ascii=False, sort_keys=True, default=str) + "\n")
            n += 1
print(f"files={len(files)} runners={n}")
