#!/usr/bin/env python3
"""EXP-20261121-34：AU 新標籤（由 HKJC 搬）喺模型名次之上嘅剩餘上名率 —— 用嚟決定語氣（有利／不利／事實），唔入分。

    measure.py BASE.json OUT.json
每匹馬：同（模型名次，場大細組）平均入三甲率比；賽日 bootstrap 2,000。
"""
import collections, glob, json, random, re, sys
from pathlib import Path
W = Path(__file__).resolve().parents[4]
ROOT = open(W / ".wongchoi_au_data_root").read().strip()
HEAD = re.compile(r"^### 馬匹 #(\d+) .*?\| 練馬師: ([^|]+?) \| 負重: ([\d.]+)kg", re.M)
REC = re.compile(r"(\d+)\s*:\s*(\d+)-(\d+)-(\d+)")
RC_HEAD = re.compile(r"^(\d+)\. (.+?) \(\d+\)\s*$", re.M)


def rec(text):
    m = REC.search(text or "")
    if not m:
        return None
    s, w, a, b = map(int, m.groups())
    return {"starts": s, "wins": w, "places": w + a + b}


def facts(meeting_dir):
    out = {}
    for f in glob.glob(meeting_dir + "/* Race * Facts.md"):
        rn = int(re.search(r" Race (\d+) Facts\.md$", f).group(1))
        text = Path(f).read_text(encoding="utf-8", errors="replace")
        heads = list(HEAD.finditer(text))
        rc = (glob.glob(meeting_dir + f"/* Race {rn} Racecard.md") or [None])[0]
        rctext = Path(rc).read_text(encoding="utf-8", errors="replace") if rc else ""
        rcblocks = {}
        rh = list(RC_HEAD.finditer(rctext))
        for i, h in enumerate(rh):
            rcblocks[int(h.group(1))] = rctext[h.end(): rh[i + 1].start() if i + 1 < len(rh) else len(rctext)]
        handicap = bool(re.search(r"handicap|hcp|bm\s?\d+|benchmark", rctext.splitlines()[0] if rctext else "", re.I))
        for i, h in enumerate(heads):
            n = int(h.group(1))
            block = text[h.end(): heads[i + 1].start() if i + 1 < len(heads) else len(text)]
            stage = re.search(r"初出:\s*([^|\n]+)\|\s*二出:\s*([^\n]+)", block)
            stats = re.search(r"同場:\s*([^|\n]+)", block)
            career = re.search(r"生涯:\s*(\d+)", block)
            rb = rcblocks.get(n, "")
            age = re.search(r"Age:\s*(\d+)yo", rb)
            gear = re.search(r"Gear:\s*([^\n]+)", rb)
            out[(rn, n)] = {"trainer": h.group(2).strip(), "weight": float(h.group(3)), "handicap": handicap,
                            "first_up": rec(stage.group(1)) if stage else None,
                            "second_up": rec(stage.group(2)) if stage else None,
                            "venue": rec(stats.group(1)) if stats else None,
                            "career": int(career.group(1)) if career else None,
                            "age": int(age.group(1)) if age else None,
                            "gear": gear.group(1).strip() if gear else ""}
    return out


def labels(x, f, race_f):
    """→ 呢匹馬有邊啲候選標籤（同 tags.py 一樣嘅條件）。"""
    out = []
    stage = x.get("prep_stage")
    for key, st in (("first_up", "first_up"), ("second_up", "second_up")):
        r = f.get(key)
        if stage == st and r and r["starts"] >= 3:
            if r["places"] / r["starts"] >= 0.5:
                out.append(f"{key}_good")
            elif r["places"] == 0:
                out.append(f"{key}_nil")
    d = x.get("days_since_last")
    if isinstance(d, (int, float)) and 0 < d <= 7:
        out.append("quick_backup")
    if sum(1 for g in race_f.values() if g["trainer"] == f["trainer"]) >= 2:
        out.append("stable_multi")
    if f.get("age") and f["age"] >= 8:
        out.append("old_horse")
    g = f.get("gear", "").upper()
    if "FIRST TIME" in g and " OFF " not in f" {g} ":
        out.append("gear_first_on")
    if " OFF" in g:
        out.append("gear_off")
    if f["handicap"] and f["weight"] >= 60.0:          # 同引擎 risk flag `top_weight` 一樣
        out.append("top_weight")
    v = f.get("venue")
    if v and v["starts"] == 0 and (f.get("career") or 0) >= 3:
        out.append("first_at_venue")
    return out


def main(base, outp):
    races = [r for r in json.loads(Path(base).read_text())["races"] if r["date"] >= "2026-08-05"
             and sum(x["pos"] <= 3 for x in r["rows"]) >= 3 and any(x["pos"] == 1 for x in r["rows"])]
    dirs = {Path(d).name: d for d in glob.glob(ROOT + "/2026-*") + glob.glob(ROOT + "/Archive/**/2026-*", recursive=True)}
    cache, rows = {}, []
    for r in races:
        d = dirs.get(r["meeting"])
        if not d:
            continue
        if r["meeting"] not in cache:
            cache[r["meeting"]] = facts(d)
        F = cache[r["meeting"]]
        race_f = {n: v for (rn, n), v in F.items() if rn == r["race"]}
        order = sorted(range(len(r["rows"])), key=lambda i: -r["rows"][i]["ability"])
        rank = {i: k + 1 for k, i in enumerate(order)}
        fb = "s" if len(r["rows"]) <= 7 else "m" if len(r["rows"]) <= 11 else "l"
        for i, x in enumerate(r["rows"]):
            f = race_f.get(x["n"])
            if not f:
                continue
            rows.append({"day": r["date"], "cell": (min(rank[i], 8), fb), "rank": rank[i],
                         "y": 1 if x["pos"] <= 3 else 0, "labels": labels(x, f, race_f)})
    base_rate = collections.defaultdict(list)
    for z in rows:
        base_rate[z["cell"]].append(z["y"])
    base_rate = {k: sum(v) / len(v) for k, v in base_rate.items()}
    keys = sorted({l for z in rows for l in z["labels"]})
    res = {"runners": len(rows)}
    for k in keys:
        sel = [z for z in rows if k in z["labels"]]
        by = collections.defaultdict(list)
        for z in sel:
            by[z["day"]].append(z["y"] - base_rate[z["cell"]])
        days = list(by); rng = random.Random(7); bs = []
        for _ in range(2000):
            s = [e for d in (rng.choice(days) for _ in days) for e in by[d]]
            bs.append(sum(s) / len(s))
        bs.sort()
        ex = sum(e for v in by.values() for e in v) / len(sel)
        top2 = [z for z in sel if z["rank"] <= 2]
        res[k] = {"n": len(sel), "top2_n": len(top2), "excess_pp": round(100 * ex, 2),
                  "ci": [round(100 * bs[50], 2), round(100 * bs[1949], 2)]}
        print(k, res[k], flush=True)
    Path(outp).write_text(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:3])
