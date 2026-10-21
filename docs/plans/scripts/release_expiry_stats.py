import json, glob, os, subprocess
from collections import defaultdict, Counter
from datetime import datetime, timezone, timedelta
C = "/Users/imac/WongChoiData/WongChoiControl"; REPO = "/Users/imac/Antigravity-repo"
since = datetime(2026, 10, 7, tzinfo=timezone.utc)
ts = lambda s: datetime.fromisoformat(s)
mans = []
for f in glob.glob(f"{C}/releases/*.json"):
    try: d = json.load(open(f))
    except Exception: continue
    if not d.get("created_at") or ts(d["created_at"]) < since: continue
    evs = []
    for e in glob.glob(f"{C}/release-events/{os.path.basename(f)[:-5]}/*.json"):
        try: evs.append(json.load(open(e)))
        except Exception: pass
    types = {e["event_type"]: e for e in evs}
    d["_events"] = types
    mans.append(d)
print("manifests since 10-07:", len(mans))
state = Counter()
for d in mans:
    t = d["_events"]
    s = "merged" if "merged" in t else "superseded" if "release_superseded" in t else "rejected" if "rejected" in t or "release_rejected" in t else d.get("status")
    d["_state"] = s; state[s] += 1
print("final state:", dict(state))
print("check policy:", Counter((d.get("policy") or {}).get("check") for d in mans))
by_msg = defaultdict(list)
for d in mans: by_msg[d.get("message")].append(d)
merged_msgs = [m for m, ds in by_msg.items() if any(x["_state"] == "merged" for x in ds)]
attempts = [len(by_msg[m]) for m in merged_msgs]
print(f"changes merged: {len(merged_msgs)}; manifests per merged change: mean {sum(attempts)/len(attempts):.2f}, >1 in {sum(a>1 for a in attempts)} ({sum(a>1 for a in attempts)/len(attempts):.0%}); max {max(attempts)}")
print("never-merged messages (pending/expired leftovers):", sum(1 for m, ds in by_msg.items() if m not in merged_msgs))
# approval-side duration: created_at -> merged event
dur = []
for d in mans:
    m = d["_events"].get("merged")
    if m: dur.append((ts(m["created_at"]) - ts(d["created_at"])).total_seconds() / 60)
dur.sort()
if dur: print(f"created→merged minutes: median {dur[len(dur)//2]:.0f}, p75 {dur[int(len(dur)*.75)]:.0f}, max {dur[-1]:.0f}  (n={len(dur)})")
# overlap: for each manifest that was NOT merged but whose message later merged, files that main changed between its rollback_target and the replacement's rollback_target
ov = Counter(); examples = []
for m in [x for x in merged_msgs if x]:
    ds = sorted(by_msg[m], key=lambda x: x["created_at"]); final = [x for x in ds if x["_state"] == "merged"][-1]
    for x in ds:
        if x is final or x["_state"] == "merged": continue
        a, b = x.get("rollback_target"), final.get("rollback_target")
        if not a or not b or a == b: continue
        r = subprocess.run(["git", "-C", REPO, "diff", "--name-only", a, b], capture_output=True, text=True)
        if r.returncode: ov["unknown"] += 1; continue
        moved = set(r.stdout.split()); scope = set(x.get("scope") or [])
        hit = scope & moved
        ov["overlap" if hit else "disjoint"] += 1
        if hit: examples.append((str(m)[:50], sorted(hit)[:3]))
print("expired attempts whose scope overlapped what main changed meanwhile:", dict(ov))
for e in examples[:6]: print("  overlap:", e)
