"""Compact reproducible review of EXP-10; no new candidates or terminal peeking."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

import hkjc_dated_shape_20260902 as s


def review(directory):
    evidence = json.loads((directory/"evidence.json").read_text())
    races = json.loads((directory/"dated_signals.json").read_text())
    dev = [r for r in races if r["date"] < s.base.CUTOFF]
    result = {k:evidence[k] for k in ("baseline", "decision", "sample_hash", "commit",
                                     "dev_leaf_auc", "script_sha", "source_code")}
    result["collection_script_sha"] = hashlib.sha256(Path(s.base.__file__).read_bytes()).hexdigest()
    result["artifact_hashes"] = {p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in directory.glob("*.json")}
    result["raw_content_sha"] = evidence["baseline_audit"]["raw_content_sha"]
    result["cutoff"] = s.base.CUTOFF
    result["source_repair"] = {k:v for k,v in evidence["raw_source_audit"].items() if k != "sources"}
    result["signal_provenance"] = {k:v for k,v in evidence["signal_provenance"].items() if k != "sources"}
    result["counts"] = dict(races=len(races), runners=sum(len(r["runners"]) for r in races), dev=len(dev))
    result["power"] = {}
    for k in s.RANKING:
        e = evidence["power"]["evidence"][k]
        halfwidth = (e["terminal_ci_high"]-e["terminal_ci_low"])/2
        budget = abs(e["terminal_delta"])
        result["power"][k] = dict(component_budget=budget, ci_halfwidth=halfwidth,
                                  informative=budget >= halfwidth)
    result["candidates"] = {}
    for name, old in evidence["candidates"].items():
        stats = Counter()
        groups = defaultdict(lambda: ([], []))
        changed = []
        for race in dev:
            new = s.transformed(race, name)
            before, after = s.base.ordering(race)[0], s.base.ordering(new)[0]
            bm, cm = s.measure(race), s.measure(new)
            placed = {int(k) for k,v in race["actual"].items() if int(v) <= 3}
            gained = (set(after[:2])-set(before[:2])) & placed
            dropped = (set(before[:2])-set(after[:2])) & placed
            stats["top2_placed_gained"] += len(gained)
            stats["top2_placed_dropped"] += len(dropped)
            stats["rank3_placed_promoted"] += bool(before[2] in placed and before[2] in after[:2])
            stats["top2_placed_net"] += len(gained)-len(dropped)
            weak = bm["zero_hit"] or bm["one_hit"]
            stats["weak_to_pass"] += bool(weak and cm["pass"])
            stats["pass_to_weak"] += bool(bm["pass"] and not cm["pass"])
            stats["zero_rescued"] += bool(bm["zero_hit"] and not cm["zero_hit"])
            stats["new_zero"] += bool(not bm["zero_hit"] and cm["zero_hit"])
            size = len(race["runners"])
            bucket = "<=8" if size<=8 else "9-10" if size<=10 else "11-12" if size<=12 else "13+"
            for key in ("venue:"+race["venue"], "size:"+bucket, "sparse:"+str(race["sparse"])):
                groups[key][0].append(bm)
                groups[key][1].append(cm)
            if weak and before[:5] != after[:5]:
                changed.append(dict(key=race["key"], baseline_top5=before[:5], candidate_top5=after[:5],
                    actual_top3=sorted(placed), before_top2_hits=bm["top2_hits"], after_top2_hits=cm["top2_hits"],
                    affected=[dict(hn=h["hn"], evidence=h["dated_shape"], history=h["history"])
                              for h in race["runners"] if h["hn"] in set(before[:2]) ^ set(after[:2])]))
        result["candidates"][name] = dict(dev=old["dev"], decision=old["decision"],
            terminal=old["terminal"], folds=old["folds"], transitions=dict(stats),
            weak_baseline=old["weak_baseline"], weak_candidate=old["weak_candidate"],
            cohorts={k:dict(n=len(a), baseline=s.summary(a), candidate=s.summary(b)) for k,(a,b) in groups.items()},
            changed_weak_races=changed)
    if "confirmation" in evidence:
        result["confirmation"] = evidence["confirmation"]
        result["selected"] = evidence["selected"]
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("directory", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    result = review(args.directory)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
    print(result["decision"])
    for name, e in result["candidates"].items():
        print(name, json.dumps(dict(dev=e["dev"],transitions=e["transitions"]), ensure_ascii=False))
