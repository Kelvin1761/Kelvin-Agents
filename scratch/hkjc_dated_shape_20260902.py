#!/usr/bin/env python3
"""EXP-20260902-10: fixed Race Shape candidates; never alters the live engine."""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

import numpy as np

import hkjc_pit_shape_refit_20260902 as base
from pit_sources import horse_key, venue_key

sys.path.insert(0, str(base.ROOT / ".agents/skills/hkjc_racing/hkjc_wong_choi/scripts"))
from create_hkjc_logic_skeleton import extract_horse_block, parse_horse_header

RANKING = ("top3_capture_at5", "top3_mean_model_rank", "competitive_recall_at5", "ndcg_at5")
PRIMARY = ("gold", "good_positional")


def parse_date(value):
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            pass
    return None


def surface(value):
    if any(t in str(value) for t in ("AWT", "全天候", "泥地")):
        return "AWT"
    if any(t in str(value) for t in ("草地", "Turf")):
        return "Turf"
    return ""


def historical_rows(block, target_date):
    """Only named race-history tables; date identity dedup, not finish/XW dedup."""
    rows, counts, seen, columns = [], Counter(), {}, None
    target = parse_date(target_date)
    if target is None:
        raise ValueError("Missing/invalid target date")
    for line in block.splitlines():
        if not line.startswith("|"):
            columns = None
            continue
        cells = [s.strip() for s in line.strip().strip("|").split("|")]
        if "走位(XW)" in cells and "頭馬距離" in cells and "日期" in cells:
            columns = cells
            continue
        if columns is None or len(cells) != len(columns) or not cells[0].isdigit():
            continue
        row = dict(zip(columns, cells))
        day = parse_date(row["日期"])
        if day is None or day >= target:
            counts["invalid_or_nonpast_date"] += 1
            continue
        age = (target - day).days
        if age > 365:
            counts["older_than_365d"] += 1
            continue
        wides = [int(x) for x in re.findall(r"(\d+)W", row["走位(XW)"])]
        if not wides or not row["名次"].isdigit() or not row["距離"].isdigit():
            counts["missing_structured_value"] += 1
            continue
        finish = int(row["名次"])
        margin = 0.0 if finish == 1 else base.RacingEngine({}, {})._margin_to_float(row["頭馬距離"])
        if margin is None or finish <= 0:
            counts["invalid_finish_margin"] += 1
            continue
        item = dict(date=day.isoformat(), venue=venue_key(row["場地"]),
                    surface=surface(row["場地"]), distance=int(row["距離"]),
                    race_class=row.get("班次"), wide=float(np.mean(wides)),
                    margin=margin, finish=finish, weight=2**(-age/90))
        # A horse cannot run twice on one day; same-date contradictory rows fail.
        if item["date"] in seen:
            if seen[item["date"]] != item:
                raise ValueError(f"Conflicting historical date identity: {day}")
            counts["duplicate_identity"] += 1
            continue
        seen[item["date"]] = item
        rows.append(item)
    return sorted(rows, key=lambda r: r["date"], reverse=True), counts


def component_deltas(history, barrier):
    """Pure pre-registered equations, with no outcome access."""
    groups = [[r for r in history if (r["wide"] <= 2) == inner] for inner in (True, False)]
    sums = [sum(r["weight"] for r in group) for group in groups]
    fit_st = fit_hv = confidence = 0.0
    if all(sums) and barrier > 0:
        means = [sum(min(r["margin"], 10)*r["weight"] for r in group)/total
                 for group, total in zip(groups, sums)]
        diff = means[1] - means[0]
        confidence = min(sums)/(min(sums)+3)
        inner_pref, outer_pref = diff >= 1, diff <= -1
        if (inner_pref and barrier <= 4) or (outer_pref and barrier >= 9):
            fit_st, fit_hv = 12*confidence, 4*confidence
        elif inner_pref and barrier >= 9:
            fit_st, fit_hv = -14*confidence, -8*confidence
        elif inner_pref and 5 <= barrier <= 8:
            fit_st, fit_hv = -6*confidence, -3*confidence
    numer = denom = 0.0
    for r in history[:3]:
        wide = float(np.clip((r["wide"]-2)/2, 0, 1))
        close = float(np.clip((3-r["margin"])/3, 0, 1))
        easy = float(np.clip(2-r["wide"], 0, 1))
        weak = float(np.clip((r["margin"]-3)/6, 0, 1))
        numer += r["weight"]*(8*wide*close-6*easy*weak)
        denom += r["weight"]
    return dict(fit_st=fit_st, fit_hv=fit_hv, trip=numer/(denom+1),
                confidence=confidence, matched=len(history), inner_mass=sums[0], outer_mass=sums[1])


def baseline_terms(runner, context):
    data = dict(runner["shape_text"])
    # running_style can affect HV confidence. Fetch exact original rather than
    # silently dropping its contribution from the old dump's display subset.
    engine = base.RacingEngine({"_data": data}, context)
    old_fit_st = engine._draw_position_fit_score()[0]
    pi_only = base.RacingEngine({"_data": {"position_pi": data["position_pi"]}}, context)
    pi_st = pi_only._draw_position_fit_score()[0]
    _, terms = engine._race_shape_context_delta()
    return old_fit_st-pi_st, sum(x["delta"] for x in terms if x["factor"] == "走位匹配"), sum(
        x["delta"] for x in terms if x["factor"] == "近仗消耗")


def transformed(race, name):
    result = deepcopy(race)
    st = base.RacingEngine({}, {"venue": race["venue"]})._is_sha_tin_context()
    for h in result["runners"]:
        d = h["dated_shape"]
        if st:
            fit, trip = h["fit"], h["trip"]
            if name in ("A", "AB"):
                fit += d["fit_st"]-h["old_terms"][0]
            if name in ("B", "AB"):
                trip = 60+d["trip"]
            if name == "neutral":
                fit, trip = 60, 60
            h["matrix"]["race_shape"] = .55*h["draw"]+.25*fit+.20*trip
        else:
            # Reconstruct the full unclipped original delta, retaining confidence
            # and PI, then clip once. Subtracting terms from clipped totals is wrong.
            delta = h["old_hv_delta"]
            if name in ("A", "AB"):
                delta += d["fit_hv"]-h["old_terms"][1]
            if name in ("B", "AB"):
                delta += .1*d["trip"]-h["old_terms"][2]
            if name == "neutral":
                delta = 0
            h["matrix"]["race_shape"] = float(np.clip(h["draw"]+np.clip(delta, -10, 7), 0, 100))
        # Production matrix_mapper rounds dimensions before ability composition.
        h["matrix"]["race_shape"] = round(h["matrix"]["race_shape"], 2)
    return result


@lru_cache(maxsize=None)
def read_json(path):
    return json.loads(Path(path).read_text())


def attach(races, raw):
    source_manifest, counts, problems = {}, Counter(), []
    history_index = {(r["Date"], horse_key(r["Horse"])): r for r in raw.to_dict("records")}
    for race in races:
        logic = read_json(race["source"])
        context = logic["race_analysis"]
        rn = int(Path(race["source"]).stem.split("_")[1])
        facts = [p for p in Path(race["source"]).parent.glob("*Facts.md")
                 if re.search(rf"Race[ _]?{rn} Facts\.md$", p.name)]
        if len(facts) > 1:
            raise ValueError(f"Ambiguous Facts: {race['key']}")
        content = facts[0].read_text() if facts else ""
        if facts:
            source_manifest[str(facts[0])] = hashlib.sha256(facts[0].read_bytes()).hexdigest()
        current_distance = re.search(r"\d+", str(context.get("distance", "")))
        target_venue = venue_key(context.get("venue"))
        if target_venue not in ("沙田", "跑馬地"):
            target_venue = venue_key(Path(race["source"]).parent.name)
            counts["context_venue_missing"] += 1
        # Target surface uses the same grass-default contract as the live engine.
        target_surface = surface(context.get("venue")) or "Turf"
        for h in race["runners"]:
            horse = logic["horses"][str(h["hn"])]
            block = extract_horse_block(content, h["hn"]) or ""
            header = parse_horse_header(block)
            if block and horse_key(header.get("name")) != horse_key(horse.get("horse_name")):
                problems.append(dict(race=race["key"], hn=h["hn"], problem="Facts horse identity mismatch"))
                block = ""
            history, audit = historical_rows(block, race["date"])
            counts.update(audit)
            matched = []
            for row in history:
                previous = history_index.get((row["date"], horse_key(horse.get("horse_name"))))
                if previous:
                    prior_surface = surface(previous.get("Track"))
                    row["surface"] = row["surface"] or prior_surface
                if not row["surface"]:
                    counts["unknown_historical_surface"] += 1
                    continue
                if (row["venue"] != target_venue or row["surface"] != target_surface or
                        not current_distance or abs(row["distance"]/int(current_distance[0])-1) > .20):
                    counts["context_mismatch"] += 1
                    continue
                matched.append(row)
            h["history"] = matched
            h["dated_shape"] = component_deltas(matched, int(h["barrier"] or 0))
            h["old_terms"] = baseline_terms(h, context)
            old = base.RacingEngine(horse, context)
            _, parts = old._race_shape_context_delta()
            h["old_hv_delta"] = sum(x["delta"] for x in parts)
            counts["horses_with_matched_history"] += bool(matched)
            counts["horses_fit_supported"] += h["dated_shape"]["confidence"] > 0
    return dict(counts=counts, problems=problems, sources=source_manifest,
                leakage_status="FLAG: date/identity guarded; immutable archive capture not proven")


def measure(race):
    order = base.ordering(race)[0]
    m = base.metrics(race, order)
    placed = {int(k) for k, v in race["actual"].items() if int(v) <= 3}
    m["top2_hits"] = sum(h in placed for h in order[:2])
    return m


def summary(rows):
    return {k: float(np.mean([r[k] for r in rows])) for k in rows[0]}


def leaf_auc(races, name):
    wins = count = 0
    for r in races:
        hs = r["runners"]
        actual = {int(k): int(v) for k,v in r["actual"].items()}
        for i, h in enumerate(hs):
            for hh in hs[i+1:]:
                a, b = actual.get(h["hn"]), actual.get(hh["hn"])
                x = h["dated_shape"][name]
                y = hh["dated_shape"][name]
                if a is None or b is None or a == b or x == 0 or y == 0:
                    continue
                wins += .5 if x == y else float((x > y) == (a < b))
                count += 1
    return dict(auc=wins/count if count else None, pairs=count)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--reuse", action="store_true")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    code = {str(p.relative_to(base.ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for parent in ("hkjc_wong_choi_auto", "hkjc_reflector")
            for p in (base.ROOT/f".agents/skills/hkjc_racing/{parent}/scripts").rglob("*.py")}
    raw = base.pit.load_all_rows()
    dump = args.out/"baseline.json"
    if args.reuse:
        stored = json.loads(dump.read_text())
        if code != stored["source_code"]:
            raise ValueError("Engine/harness changed: baseline must be rebuilt")
        races, audit = stored["races"], stored["audit"]
        if audit["raw_content_sha"] != base.digest(raw.fillna("").astype(str).to_dict("records")):
            raise ValueError("PIT source changed: baseline must be rebuilt")
    else:
        races, audit = base.collect()
        dump.write_text(json.dumps(dict(races=races, audit=audit, source_code=code), ensure_ascii=False))
    for r in races:
        _, scores = base.ordering(r)
        if any(scores[h["hn"]] != h["baseline_ability"] for h in r["runners"]):
            raise ValueError(f"Production replica mismatch: {r['key']}")
    provenance = attach(races, raw)
    for r in races:
        a, b = base.ordering(r), base.ordering(transformed(r, "baseline"))
        if a != b:
            raise ValueError(f"Component replica mismatch: {r['key']}")
    metrics = [measure(r) for r in races]
    # Neutral-component budget and bootstrap precede any candidate measurement.
    neutral = [measure(transformed(r, "neutral")) for r in races]
    power = base.compare(races, metrics, neutral)
    dev = [i for i, r in enumerate(races) if r["date"] < base.CUTOFF]
    term = [i for i, r in enumerate(races) if r["date"] >= base.CUTOFF]
    dev_summary = summary([metrics[i] for i in dev])
    dates = sorted({races[i]["date"] for i in dev})
    dev_races = [races[i] for i in dev]
    evidence = dict(baseline=dict(dev=dev_summary, terminal=summary([metrics[i] for i in term])),
        candidates={}, power=power, raw_source_audit=raw.attrs["source_audit"],
        signal_provenance=provenance, baseline_audit=audit, sample_hash=base.digest([
            (r["key"],r["source_sha"]) for r in races]),
        source_code=code, script_sha=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        commit=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        dev_leaf_auc={k:leaf_auc(dev_races,k) for k in ("fit_st","trip")})
    eligible = []
    for name in ("A", "B", "AB"):
        candidate = {i:measure(transformed(races[i], name)) for i in dev}
        avg = summary(list(candidate.values()))
        folds = []
        for block in np.array_split(dates, 6)[1:]:
            ix = [i for i in dev if races[i]["date"] in block]
            folds.append(dict(dates=list(block), n=len(ix), baseline=summary([metrics[i] for i in ix]),
                              candidate=summary([candidate[i] for i in ix])))
        regression = any(avg[k] < dev_summary[k]-1e-12 for k in PRIMARY)
        gain = any(avg[k] > dev_summary[k]+1e-12 for k in PRIMARY) or sum(
            (avg[k]-dev_summary[k])*(-1 if k in base.LOWER else 1) > 1e-12 for k in RANKING) >= 2
        fold_pass = sum(all(f["candidate"][k] >= f["baseline"][k]-1e-12 for k in PRIMARY) for f in folds)
        eligible_now = not regression and gain and fold_pass >= 3
        if eligible_now:
            eligible.append(name)
        weak = [i for i in dev if metrics[i]["zero_hit"] or metrics[i]["one_hit"]]
        evidence["candidates"][name] = dict(dev=avg, folds=folds, folds_primary_nonnegative=fold_pass,
            decision="DEV_SURVIVOR" if eligible_now else "REJECT_DEV", terminal="not evaluated",
            weak_baseline=summary([metrics[i] for i in weak]), weak_candidate=summary([candidate[i] for i in weak]))
        print(name, json.dumps(evidence["candidates"][name], ensure_ascii=False), flush=True)
    if eligible:
        selected = eligible[0]
        cand = [measure(transformed(r, selected)) for r in races]
        evidence["selected"] = selected
        evidence["confirmation"] = base.compare(races, metrics, cand)
        evidence["confirmation"]["top2"] = {label:dict(
            baseline=sum(metrics[i]["top2_hits"] for i in ix),
            candidate=sum(cand[i]["top2_hits"] for i in ix)) for label,ix in (("dev",dev),("terminal",term))}
        evidence["decision"] = "RESEARCH_ONLY: provenance FLAG; inspect fixed terminal gate"
    else:
        evidence["decision"] = "REJECT_DEV: no candidate qualified; terminal not used to rescue candidates"
    (args.out/"evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2)+"\n")
    (args.out/"dated_signals.json").write_text(json.dumps(races, ensure_ascii=False)+"\n")
    print(evidence["decision"], flush=True)


if __name__ == "__main__":
    main()
