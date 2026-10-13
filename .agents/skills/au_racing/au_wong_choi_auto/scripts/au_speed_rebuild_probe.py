"""EXP-20261013-10（REJECT）：由 Formguide 往績行砌 B1/B2 速度特徵，接 au_eval 判決。

用法：
  PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 au_speed_rebuild_probe.py build  LEAVES OUT_FEATS
  PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 au_speed_rebuild_probe.py diag   LEAVES OUT_FEATS
  PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 au_speed_rebuild_probe.py judge  LEAVES OUT_FEATS FEATURE
"""
import json
import math
import re
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
SCRIPTS = REPO / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
for p in (SCRIPTS, REPO, REPO / ".agents/skills/shared_racing/scripts", REPO / ".agents/skills/shared_racing",
          REPO / ".agents/skills/au_racing"):
    sys.path.insert(0, str(p))

STD_CUTOFF = "2026-06-01"
FEATS = ("early_pace_faced", "early_speed_own", "late_speed_pos")
LBL = 0.17          # 秒／馬位

RUN = re.compile(
    r"^(?P<venue>\S.+?)\s+R(?P<race>\d+)\s+(?P<date>\d{4}-\d{2}-\d{2})\s+(?P<dist>\d+)m\s+cond:(?P<cond>\S+)"
    r".*?$", re.M)
POS = lambda mk: re.compile(rf"(\d+)(?:st|nd|rd|th)@{mk}\b")  # noqa: E731
P800, P400 = POS("800m"), POS("400m")
MARGIN = re.compile(r"\bmargin:([\d.]+)L?")
STARTERS = re.compile(r"\bstarters:(\d+)")
FINISH = re.compile(r"\bfinish:(\d+)/(\d+)")
WT = re.compile(r"\bWinningTime:(?:(\d{1,2}):)?(\d{1,2}\.\d{2,3})")
L600D = re.compile(r"L600 Delta:\s*(-?[\d.]+)")
CLS = re.compile(r"RaceClass:\[([^\]]*)\]")
HORSE = re.compile(r"^\[(\d+)\]\s+(.+?)\s+\((\d+)\)\s*$", re.M)


def going_family(cond, venue):
    c = (cond or "").lower()
    if "synth" in c or "synthetic" in (venue or "").lower():
        return "synth"
    if c.startswith("heavy"):
        return "heavy"
    if c.startswith("soft"):
        return "soft"
    return "good"


def parse_runs(block):
    from au_racing_engine.engine_core import _lookup_standard_l600
    runs = []
    for m in RUN.finditer(block):
        line = m.group(0)
        cls = (CLS.search(line) or [None, ""])[1] if CLS.search(line) else ""
        if re.search(r"(?i)trial|jump ?out|\bBT\b", cls + " " + line[:120]):
            continue
        dist = int(m.group("dist"))
        wt = WT.search(line)
        wts = (int(wt.group(1) or 0) * 60 + float(wt.group(2))) if wt else None
        ld = L600D.search(line)
        std = _lookup_standard_l600(m.group("venue"), dist) if ld else None
        l600raw = (float(ld.group(1)) + std) if (ld and std) else None
        fin = FINISH.search(line)
        mg = MARGIN.search(line)
        p8, p4 = P800.search(line), P400.search(line)
        runs.append(dict(
            date=m.group("date"), venue=m.group("venue"), dist=dist,
            going=going_family(m.group("cond"), m.group("venue")),
            wt=wts, l600=l600raw, l600_std=std,
            finish=int(fin.group(1)) if fin else None,
            starters=int(fin.group(2)) if fin else (int(STARTERS.search(line).group(1)) if STARTERS.search(line) else None),
            margin=float(mg.group(1)) if mg else None,
            p800=int(p8.group(1)) if p8 else None, p400=int(p4.group(1)) if p4 else None))
    return runs


def meeting_index():
    import wongchoi_paths
    from corpus_paths import meeting_dirs
    return {d.name: d for d in meeting_dirs(wongchoi_paths.AU_RACING)}


def norm(s):
    from au_leaf_power import norm as n
    return n(s)


def build(leaves_path, out_path):
    races = json.load(open(leaves_path))["races"]
    mi = meeting_index()
    per_race = {}
    all_runs = []
    for race in races:
        md = mi.get(race["meeting"])
        if not md:
            continue
        fg = next(iter(md.glob(f"* Race {race['race']} Formguide.md")), None)
        if not fg:
            continue
        text = fg.read_text(encoding="utf-8", errors="replace")
        heads = list(HORSE.finditer(text))
        horses = {}
        for i, h in enumerate(heads):
            end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
            runs = [r for r in parse_runs(text[h.end():end]) if r["date"] < race["date"]]
            horses[norm(h.group(2))] = runs
            all_runs += runs
        per_race[(race["meeting"], race["race"])] = horses
    # G = 每名次負距（終點），語料中位
    gs = [r["margin"] / (r["finish"] - 1) for r in all_runs
          if r["finish"] and r["finish"] > 1 and r["margin"] is not None and r["margin"] > 0]
    G = statistics.median(gs)
    # 去重（同一仗會出現喺好多份 Formguide）再建標準格
    uniq = {}
    for r in all_runs:
        uniq[(r["date"], r["venue"], r["dist"], r["finish"], r["margin"], r["p800"])] = r

    def early_parts(r):
        if r["wt"] is None or r["l600"] is None or r["dist"] <= 800:
            return None
        t = r["wt"] - r["l600"]
        if t <= 0:
            return None
        sp = (r["dist"] - 600) / t
        if not 11 < sp < 19:
            return None
        behind = None
        if r["p800"] and r["p400"]:
            behind = ((r["p800"] + r["p400"]) / 2 - 1) * G
        own = (r["dist"] - 600) / (t + behind * LBL) if behind is not None else None
        return sp, own

    def late_delta(r):
        if r["l600"] is None or r["l600_std"] is None or r["margin"] is None or not (r["p800"] and r["p400"]):
            return None
        behind600 = ((r["p800"] + r["p400"]) / 2 - 1) * G
        own = r["l600"] + LBL * (r["margin"] - behind600)
        return own - r["l600_std"]

    cells = {"race_early": {}, "own_early": {}, "late": {}}
    for r in uniq.values():
        if r["date"] >= STD_CUTOFF:
            continue
        ep = early_parts(r)
        key = (r["dist"] // 100, r["going"])
        if ep:
            cells["race_early"].setdefault(key, []).append(ep[0])
            if ep[1]:
                cells["own_early"].setdefault(key, []).append(ep[1])
        ld = late_delta(r)
        if ld is not None:
            cells["late"].setdefault(r["going"], []).append(ld)
    stats = {k: {c: (statistics.median(v), statistics.pstdev(v)) for c, v in d.items() if len(v) >= 30}
             for k, d in cells.items()}

    def z(kind, key, val):
        s = stats[kind].get(key)
        if not s or s[1] <= 0:
            return None
        return max(-3, min(3, (val - s[0]) / s[1]))

    out = {}
    for (meeting, rno), horses in per_race.items():
        for name, runs in horses.items():
            vals = {f: [] for f in FEATS}
            for r in sorted(runs, key=lambda x: x["date"], reverse=True):
                key = (r["dist"] // 100, r["going"])
                ep = early_parts(r)
                if ep:
                    a = z("race_early", key, ep[0])
                    if a is not None and len(vals["early_pace_faced"]) < 4:
                        vals["early_pace_faced"].append(a)
                    if ep[1]:
                        b = z("own_early", key, ep[1])
                        if b is not None and len(vals["early_speed_own"]) < 4:
                            vals["early_speed_own"].append(b)
                ld = late_delta(r)
                if ld is not None:
                    c = z("late", r["going"], ld)
                    if c is not None and len(vals["late_speed_pos"]) < 4:
                        vals["late_speed_pos"].append(-c)
            out[f"{meeting}|{rno}|{name}"] = {f: statistics.mean(v) for f, v in vals.items() if v}
    json.dump({"G": G, "n_runs": len(uniq), "features": out}, open(out_path, "w"))
    print(f"G={G:.3f} 馬位/名次；去重往績 {len(uniq)}；標準格 " +
          ", ".join(f"{k}:{len(v)}" for k, v in stats.items()) + f"；馬 {len(out)}")


def attach(leaves_path, feats_path):
    from au_eval import load_races
    races = load_races(leaves_path)
    F = json.load(open(feats_path))["features"]
    for race in races:
        for row in race["rows"]:
            row["_sf"] = F.get(f"{race['meeting']}|{race['race']}|{norm(row['name'])}", {})
    return races


def _auc_place(vals_pos):
    pos = [v for v, p in vals_pos if p is not None and p <= 3]
    neg = [v for v, p in vals_pos if p is not None and p > 3]
    if not pos or not neg:
        return None
    w = sum((a > b) + 0.5 * (a == b) for a in pos for b in neg)
    return w, len(pos) * len(neg)


def _rank(v):
    o = sorted(range(len(v)), key=lambda i: v[i])
    r = [0] * len(v)
    for k, i in enumerate(o):
        r[i] = k
    return r


def _spearman(a, b):
    if len(a) < 3:
        return None
    ra, rb = _rank(a), _rank(b)
    ma, mb = statistics.mean(ra), statistics.mean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = math.sqrt(sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb))
    return num / den if den else None


def diag(leaves_path, feats_path):
    races = attach(leaves_path, feats_path)
    runners = sum(len(r["rows"]) for r in races)
    for f in FEATS:
        have = sum(1 for r in races for row in r["rows"] if f in row["_sf"])
        w = t = 0
        rhos = {k: [] for k in ("pace_figure_score", "form_score", "performance_quality_score", "ability")}
        for race in races:
            vp = [(row["_sf"][f], row["pos"]) for row in race["rows"] if f in row["_sf"]]
            if len(vp) >= 3:
                a = _auc_place(vp)
                if a:
                    w += a[0]
                    t += a[1]
                rows = [row for row in race["rows"] if f in row["_sf"]]
                for k in rhos:
                    other = [row["ability"] if k == "ability" else row["features"].get(k, 60) for row in rows]
                    s = _spearman([row["_sf"][f] for row in rows], other)
                    if s is not None:
                        rhos[k].append(s)
        print(f"{f:18} 覆蓋 {100 * have / runners:5.1f}%  場內上名 AUC {w / t if t else float('nan'):.4f}  ρ " +
              "  ".join(f"{k.replace('_score', '')} {statistics.mean(v):+.3f}" for k, v in rhos.items() if v))


def judge(leaves_path, feats_path, feature, ks=(0.5, 1, 1.5, 2, 3)):
    import au_eval
    races = attach(leaves_path, feats_path)
    feats = feature.split("+")
    for race in races:
        race_z = [0.0] * len(race["rows"])
        for f in feats:
            vals = [row["_sf"].get(f) for row in race["rows"]]
            have = [v for v in vals if v is not None]
            sd = statistics.pstdev(have) if len(have) >= 2 else 0
            mu = statistics.mean(have) if have else 0
            for i, v in enumerate(vals):
                race_z[i] += 0.0 if (v is None or sd <= 0) else (v - mu) / sd
        for row, zv in zip(race["rows"], race_z):
            row["_z"] = zv

    def cand(k):
        return lambda row: au_eval.default_scorer(row) + k * row["_z"]

    dev_idx, _ = au_eval.date_partitions(races, au_eval.HOLDOUT)
    dev = [races[i] for i in dev_idx]
    base_c = au_eval._counts(dev, au_eval.default_scorer)
    base_p = au_eval._pairs(dev, au_eval.default_scorer, True)
    ok = []
    print(f"dev {len(dev)} 場；k 只用 dev 揀")
    for k in ks:
        c = au_eval._counts(dev, cand(k))
        p = au_eval._pairs(dev, cand(k), True)
        dg = c["gold"] - base_c["gold"]
        dgood = c["good_positional"] - base_c["good_positional"]
        dauc = au_eval._auc(p) - au_eval._auc(base_p)
        flag = dg >= 0 and dgood >= 0 and dauc > 0
        print(f"  k={k:<4} dev gold {dg:+.2f}pp  good {dgood:+.2f}pp  top5AUC {dauc:+.4f}  {'✓' if flag else ''}")
        if flag:
            ok.append(k)
    if not ok:
        print("❌ 冇一個 k 喺 dev 過預先登記條件 —— 唔碰 terminal，REJECT。")
        return
    k = statistics.median(ok)
    print(f"揀 k = {k}（合格 k 嘅中位數 {ok}）→ 跑一次 Stage 4 v2：")
    v = au_eval.compare(races, au_eval.default_scorer, cand(k), label=f"{feature} k={k}",
                        leakage_audit_passed=True)
    print(v)
    print("  stage4:", v.stage4_verdict, "|", v.reason)
    print("  detail:", json.dumps(v.decision_detail, ensure_ascii=False, default=str)[:2500])


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "build":
        build(sys.argv[2], sys.argv[3])
    elif cmd == "diag":
        diag(sys.argv[2], sys.argv[3])
    elif cmd == "judge":
        judge(sys.argv[2], sys.argv[3], sys.argv[4])
