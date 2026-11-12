#!/usr/bin/env python3
"""EXP-20261113-21：喺 BASE dump 離線砌 arm，再交 EXP-20261102-10 嘅 judge（v3 fixed_rule＋分層）。

    au_noise_judge_20261113.py BASE.json OUTDIR

先做 A/A：重算綜合分同 dump 嘅 ability 對唔對得上（最大差 < 1e-3），唔得就停。
"""
import copy
import json
import subprocess
import sys
from pathlib import Path

W = Path(__file__).resolve().parents[1]
SCRIPTS = W / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SCRIPTS))
from au_racing_engine.matrix_mapper import map_features_to_matrix_scores  # noqa: E402
from au_racing_engine.scoring import compose_matrix_score, clip_score  # noqa: E402


def ability(row, feats=None, wet=None):
    f = row["features"] if feats is None else feats
    w = row["wet"] if wet is None else wet
    return (compose_matrix_score(map_features_to_matrix_scores(f)) + w
            + row["proven_class"] + row["full_time"] + row["draw"])


def arm_rows(row, arm):
    f = dict(row["features"])
    wet = row["wet"]
    if arm == "AA":
        pass
    elif arm == "D1_GO":
        adj = row.get("track_going_adj") or 0.0
        f["track_score"] = clip_score(f["track_score"] - adj)
    elif arm == "D2_WO":
        wet = 0.0
    elif arm == "N1_trial_speed":
        f["trial_speed_score"] = 60.0
    elif arm == "N2_preparation":
        f["trial_speed_score"] = 60.0
        f["preparation_score"] = 60.0
    elif arm == "N3_class":
        f["class_score"] = 60.0
    elif arm == "N4_track":
        f["track_score"] = 60.0
    else:
        raise ValueError(arm)
    return ability(row, f, wet)


ARMS = ("AA", "D1_GO", "D2_WO", "N1_trial_speed", "N2_preparation", "N3_class", "N4_track")


def main():
    base_path, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    data = json.loads(base_path.read_text())
    worst = max(abs(ability(r) - r["ability"]) for race in data["races"] for r in race["rows"])
    print(f"A/A replica max |Δability| = {worst:.6f}")
    if worst > 1e-3:
        sys.exit("replica does not match the engine — stop")
    clipped = sum(1 for race in data["races"] for r in race["rows"]
                  if r.get("track_going_adj") and r["features"]["track_score"] in (0.0, 100.0))
    print(f"track_score clipped with going adj (D1 approx): {clipped}")
    for arm in ARMS:
        d = copy.deepcopy(data)
        for race in d["races"]:
            for r in race["rows"]:
                r["ability"] = arm_rows(r, arm)
        p = out / f"{arm}.json"
        p.write_text(json.dumps(d))
        subprocess.run([sys.executable, str(W / "scratch/au_track_rebuild_judge_20261102.py"),
                        str(base_path), str(p), str(out / f"{arm}.verdict.json")], check=True)
        p.unlink()


if __name__ == "__main__":
    main()
