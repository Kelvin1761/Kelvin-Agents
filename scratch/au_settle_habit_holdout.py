#!/usr/bin/env python3
"""Honest-holdout tuning of a big-field settling-habit penalty.

Diagnosis being acted on: in metro 12+ fields the AU top pick fails to be
competitive 44.5% of the time, and 48.9% of those failures were behind the
half-field at BOTH the 800m and the 400m — never in the contest. Within the
model's own top 4 in big fields, horses that habitually settle back are "never
in it" 71.9% of the time (vs 22.5% for habitually-forward) and win 10.2% (vs
15.7%). A horse's settling percentile is a genuine trait: prior-run mean vs
this-run value correlates r=0.389.

Point-in-time safe: a horse's settling profile uses ONLY its runs on strictly
earlier dates. Weights are tuned on the earliest 60% of dates and scored once
on the unseen latest 40%.
"""
import json, re, statistics, sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/shared_racing")
from eval_metrics import race_metrics, summarize_races

SCRATCH = Path("/Users/imac/Antigravity-repo/scratch")


def nn(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def load():
    iso = json.loads((SCRATCH / "au_trainer_isolated.json").read_text())
    fin = json.loads((SCRATCH / "au_finishes_map.json").read_text())
    pos = json.loads((SCRATCH / "au_positions_map.json").read_text())

    hist = defaultdict(list)
    for meeting, mrows in iso.items():
        fm = fin.get(meeting) or {}
        pm = pos.get(meeting) or {}
        date = meeting[:10]
        for rno, hs in mrows.items():
            fr = fm.get(str(rno)) or {}
            pr = pm.get(str(rno)) or {}
            if not fr or not pr:
                continue
            n = len([1 for num in hs if fr.get(str(num))])
            if n < 5:
                continue
            for num, v in hs.items():
                f = fr.get(str(num))
                ip = pr.get(str(num))
                if not f or not ip or not ip.get("settled"):
                    continue
                name = nn(f.get("name") or v.get("name"))
                if name:
                    hist[name].append({"date": date, "settle": (ip["settled"] - 1) / (n - 1)})

    races = []
    for meeting, mrows in iso.items():
        fm = fin.get(meeting) or {}
        date = meeting[:10]
        for rno, hs in mrows.items():
            fr = fm.get(str(rno)) or {}
            if not fr:
                continue
            ent = []
            for num, v in hs.items():
                f = fr.get(str(num))
                if not f:
                    continue
                name = f.get("name") or v.get("name")
                if f.get("name") and v.get("name") and nn(f["name"]) != nn(v["name"]):
                    continue
                prior = [r["settle"] for r in hist.get(nn(name), []) if r["date"] < date]
                ent.append({"num": int(num), "ab": float(v["ab_on"]), "pos": int(f["pos"]),
                            "habit": statistics.mean(prior) if prior else None,
                            "n_prior": len(prior)})
            if len(ent) < 5 or sum(1 for e in ent if e["pos"] <= 3) < 3:
                continue
            if not any(e["pos"] == 1 for e in ent):
                continue
            races.append({"date": date, "field": len(ent), "ent": ent})
    races.sort(key=lambda r: r["date"])
    return races


def evaluate(races, penalty, threshold, min_field, min_prior=1):
    """Score races with the habit penalty applied; returns canonical summary."""
    rows = []
    for r in races:
        adjusted = []
        for e in r["ent"]:
            ab = e["ab"]
            if (r["field"] >= min_field and e["habit"] is not None
                    and e["n_prior"] >= min_prior and e["habit"] > threshold):
                ab -= penalty * (e["habit"] - threshold)
            adjusted.append((e["num"], ab, e["pos"]))
        adjusted.sort(key=lambda t: (-t[1], t[0]))
        order = [t[0] for t in adjusted]
        pb = {t[0]: t[2] for t in adjusted}
        top3 = [n for n, p in pb.items() if p <= 3]
        rows.append(race_metrics(order, top3, actual_pos=pb, field_size=r["field"]))
    s = summarize_races(rows)
    s["top4_all3"] = sum(
        1 for row in rows
        if len(row["picks"]) >= 4 and sum(
            1 for n in row["picks"][:4] if n in set(k for k, v in zip(row["picks"], row["pick_positions"]))
        ) >= 0)  # placeholder, recomputed below
    return s, rows


def top4_all3(races, penalty, threshold, min_field, min_prior=1):
    hit = 0
    for r in races:
        adjusted = []
        for e in r["ent"]:
            ab = e["ab"]
            if (r["field"] >= min_field and e["habit"] is not None
                    and e["n_prior"] >= min_prior and e["habit"] > threshold):
                ab -= penalty * (e["habit"] - threshold)
            adjusted.append((e["num"], ab, e["pos"]))
        adjusted.sort(key=lambda t: (-t[1], t[0]))
        top3 = {t[0] for t in adjusted if t[2] <= 3}
        if sum(1 for t in adjusted[:4] if t[0] in top3) >= 3:
            hit += 1
    return hit


def fmt(s, races, penalty, threshold, min_field):
    n = s["races"]
    c = s["counts"]
    comp = s["competitiveness"]
    t4 = top4_all3(races, penalty, threshold, min_field)
    return (f"頭兩揀 {c['good_positional']:>3}場({c['good_positional']/n*100:>4.1f}%) | "
            f"中2隻 {c['good_any2']:>3}場({c['good_any2']/n*100:>4.1f}%) | "
            f"捉冠軍 {c['winner_in_top3']/n*100:>4.1f}% | 頭揀贏 {c['champion']/n*100:>4.1f}% | "
            f"頭揀有競爭力 {comp['top_pick_competitive']['rate']*100:>4.1f}% | "
            f"頭揀慘敗 {comp['top_pick_blowout']['rate']*100:>4.1f}% | Top4包三甲 {t4/n*100:>4.1f}%")


def main():
    races = load()
    dates = sorted({r["date"] for r in races})
    split = dates[int(len(dates) * 0.6)]
    train = [r for r in races if r["date"] < split]
    holdout = [r for r in races if r["date"] >= split]
    print(f"全部 {len(races)} 場;調參期 {len(train)} 場(至 {split});"
          f"未見驗證期 {len(holdout)} 場\n")

    print("=== 調參期掃描(只在 12 匹以上場次施加)===")
    best = None
    for threshold in (0.4, 0.5, 0.6, 0.7):
        for penalty in (0, 1, 2, 4, 6, 9):
            s, _ = evaluate(train, penalty, threshold, 12)
            n = s["races"]
            c = s["counts"]
            comp = s["competitiveness"]
            # objective: the diagnosed problem — competitive top pick, fewer blowouts —
            # without giving up any-2, which is what the reports are read for.
            score = (comp["top_pick_competitive"]["rate"] * 2
                     - comp["top_pick_blowout"]["rate"] * 2
                     + c["good_any2"] / n
                     + c["champion"] / n)
            tag = ""
            if best is None or score > best[0]:
                best = (score, penalty, threshold)
                tag = " ←"
            if penalty in (0, 2, 4, 9):
                print(f"  門檻 {threshold} 罰分 {penalty:<2} | "
                      f"頭揀有競爭力 {comp['top_pick_competitive']['rate']*100:>5.1f}% | "
                      f"慘敗 {comp['top_pick_blowout']['rate']*100:>5.1f}% | "
                      f"中2隻 {c['good_any2']/n*100:>5.1f}% | 頭揀贏 {c['champion']/n*100:>5.1f}%{tag}")
    _, penalty, threshold = best
    print(f"\n調參期選出:門檻 {threshold}、罰分 {penalty}")

    print("\n=== 未見驗證期(從未參與調參)===")
    for lab, pen, thr in (("無罰分（現狀）", 0, threshold), (f"罰分 {penalty}", penalty, threshold)):
        s, _ = evaluate(holdout, pen, thr, 12)
        print(f"  {lab:<14} {fmt(s, holdout, pen, thr, 12)}")

    print("\n=== 只計 12 匹以上場次（直接目標）===")
    hb = [r for r in holdout if r["field"] >= 12]
    for lab, pen, thr in (("無罰分（現狀）", 0, threshold), (f"罰分 {penalty}", penalty, threshold)):
        s, _ = evaluate(hb, pen, thr, 12)
        print(f"  {lab:<14} ({len(hb)}場) {fmt(s, hb, pen, thr, 12)}")

    print("\n=== 全期(調參+驗證)參考 ===")
    for lab, pen, thr in (("無罰分（現狀）", 0, threshold), (f"罰分 {penalty}", penalty, threshold)):
        s, _ = evaluate(races, pen, thr, 12)
        print(f"  {lab:<14} {fmt(s, races, pen, thr, 12)}")
    ab = [r for r in races if r["field"] >= 12]
    for lab, pen, thr in (("無罰分（現狀）", 0, threshold), (f"罰分 {penalty}", penalty, threshold)):
        s, _ = evaluate(ab, pen, thr, 12)
        print(f"  12匹+ {lab:<10} ({len(ab)}場) {fmt(s, ab, pen, thr, 12)}")


if __name__ == "__main__":
    main()
