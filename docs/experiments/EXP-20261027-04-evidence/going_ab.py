"""Going A/B: rescore races whose scored going != official race-time rating, A = snapshot going, B = race-time going.

Same engine (detached worktree at origin/main), same snapshot inputs; only the going input differs.
"""
import csv, json, os, re, shutil, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

WT = "/Users/imac/Antigravity-worktrees/claude-going-ab-20261027"
ORCH = WT + "/.agents/skills/au_racing/au_wong_choi_auto/scripts/au_auto_orchestrator.py"
S = Path("/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/claude-au-going-ab-20261027")
AU = Path("/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/AU_Racing")
SCR = Path("/private/tmp/claude-501/-Users-imac-Antigravity-repo/8642939c-b0ef-4bdf-8853-73c9f334012f/scratchpad")
sys.path.insert(0, WT + "/.agents/skills/shared_racing/race_reflector/scripts")
from unified_reflector_core import select_prerace_snapshot  # noqa: E402

norm = lambda s: re.sub(r"[^a-z0-9]", "", (s or "").lower())  # noqa: E731
GOING = re.compile(r"(Firm|Good|Soft|Heavy)\s*(\d+)", re.I)
cond = {}
for x in csv.DictReader(open(AU / "AU_Historical_Raw_Race_Results.csv", encoding="utf-8-sig")):
    if x["Date"] >= "2026-08-05":
        cond[(x["Date"], norm(x["Track"]), x["Race"])] = x["Condition"]

rows = json.load(open(SCR / "tier_rows.json"))
jobs = []
for r in rows:
    actual = cond.get((r["date"], norm(r["track"]), str(r["race"])))
    a, b = GOING.search(r["going"] or ""), GOING.search(actual or "")
    if not a or not b:
        continue
    official = f"{b.group(1).title()} {b.group(2)}"
    if f"{a.group(1).title()} {a.group(2)}" == official:
        continue
    jobs.append((r["meeting"], r["race"], official))
print("mismatch races:", len(jobs), flush=True)

snaps = {}
for meeting in sorted({j[0] for j in jobs}):
    d = AU / "Archive" / meeting
    if not d.exists():
        d = AU / meeting
    snaps[meeting] = (d, select_prerace_snapshot(d, platform="au")[0])

KEEP = re.compile(r"(Racecard|Formguide|Facts|Formguide_Index)\.md$|^Race_\d+_Logic\.json$")
env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", TMPDIR=str(S / "tmp"), WC_DISABLE_POST_SUCCESS_DEPLOY="1")
(S / "tmp").mkdir(parents=True, exist_ok=True)


def prepare(arm, meeting):
    dst = S / arm / meeting
    if not (dst / ".ready").exists():
        if dst.exists():
            shutil.rmtree(dst)
        dst.mkdir(parents=True)
        mdir, snap = snaps[meeting]
        for f in snap.iterdir():
            if f.is_file() and KEEP.search(f.name):
                shutil.copy2(f, dst / f.name)
        for extra in ("odds_history.json",):
            if (mdir / extra).exists():
                shutil.copy2(mdir / extra, dst / extra)
        (dst / ".ready").write_text("ok")
    return dst


for meeting in snaps:
    for arm in ("A", "B"):
        prepare(arm, meeting)


def run(job):
    meeting, race, official = job
    out = []
    for arm in ("A", "B"):
        dst = S / arm / meeting
        done = dst / f".done_{race}"
        if done.exists():
            continue
        cmd = [sys.executable, ORCH, str(dst / f"Race_{race}_Logic.json")]
        if arm == "B":
            cmd += ["--going", official]
        p = subprocess.run(cmd, cwd=WT, env=env, capture_output=True, text=True, timeout=1800)
        if p.returncode == 0:
            done.write_text(official)
        else:
            out.append(f"{arm} {meeting} R{race}: rc={p.returncode} {p.stderr.strip()[-200:]}")
    return out


with ThreadPoolExecutor(max_workers=6) as ex:
    fails = [m for res in ex.map(run, jobs) for m in res]
print("failures:", len(fails))
for f in fails[:20]:
    print(f)
json.dump(jobs, open(S / "jobs.json", "w"))
