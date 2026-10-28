"""Replay A/B: score each 10-17..10-26 meeting's pre-race snapshot with old (6de9e625) and new (c60bcb38) engines."""
import os, re, shutil, subprocess, sys, json, glob
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

ROOT = Path("/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/AU_Racing/Archive")
S = Path("/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/claude-au-1016-replay-ab-20261027")
WT = {"old": "/Users/imac/Antigravity-worktrees/claude-replay-old-20261027",
      "new": "/Users/imac/Antigravity-worktrees/claude-replay-new-20261027"}
ORCH = ".agents/skills/au_racing/au_wong_choi_auto/scripts/au_auto_orchestrator.py"
sys.path.insert(0, WT["new"] + "/.agents/skills/shared_racing/race_reflector/scripts")
from unified_reflector_core import select_prerace_snapshot  # noqa: E402

KEEP = re.compile(r"(Racecard|Formguide|Facts|Formguide_Index)\.md$|^Race_\d+_Logic\.json$|^Odds\.json$|^odds_history\.json$")

meetings = sorted(d for d in ROOT.iterdir() if d.is_dir() and "2026-10-17" <= d.name[:10] <= "2026-10-26")
plan = []
for m in meetings:
    snap, created, _ = select_prerace_snapshot(m, platform="au")
    if snap is None:
        print("NO SNAPSHOT", m.name); continue
    plan.append((m, snap))
json.dump([(m.name, str(s)) for m, s in plan], open(S / "plan.json", "w"), ensure_ascii=False, indent=1)

env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", TMPDIR=str(S / "tmp"), WC_DISABLE_POST_SUCCESS_DEPLOY="1")

def run(arm, m, snap):
    dst = S / arm / m.name
    if (dst / "Meeting_Auto_Scoring.csv").exists() and (dst / ".done").exists():
        return arm, m.name, 0, "cached"
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    for f in snap.iterdir():
        if f.is_file() and KEEP.search(f.name):
            shutil.copy2(f, dst / f.name)
    p = subprocess.run([sys.executable, WT[arm] + "/" + ORCH, str(dst)], cwd=WT[arm], env=env,
                       capture_output=True, text=True, timeout=1800)
    (dst / "orchestrator.log").write_text(p.stdout[-20000:] + "\n--- stderr ---\n" + p.stderr[-20000:])
    if p.returncode == 0:
        (dst / ".done").write_text("ok")
    return arm, m.name, p.returncode, (p.stderr.strip().splitlines() or [""])[-1][:200]

jobs = [(arm, m, s) for m, s in plan for arm in ("old", "new")]
with ThreadPoolExecutor(max_workers=6) as ex:
    for arm, name, rc, msg in ex.map(lambda j: run(*j), jobs):
        print(f"{arm} {name}: rc={rc} {msg if rc else ''}", flush=True)
