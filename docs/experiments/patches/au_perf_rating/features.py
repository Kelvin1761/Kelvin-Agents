#!/usr/bin/env python3
"""EXP-20261122-05 特徵：每匹馬嘅 PR1／PR2／PR3 + 覆蓋。 features.py BASE.json OUT.json"""
import glob, json, math, re, sys
from pathlib import Path
ROOT = "/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/AU_Racing"
HEAD = re.compile(r"^\[(\d+)\]\s+(.+?) \((\d+)\)\s*$", re.M)
RUN = re.compile(r"^(?P<venue>.+?) R\d+ (?P<date>\d{4}-\d{2}-\d{2}) (?P<dist>\d+)m cond:\S* \$(?P<prize>\d+) .*? (?P<wt>\d+(?:\.\d+)?)kg .*?margin:(?P<m>[\d.]+)L starters:(?P<s>\d+) finish:(?P<f>\d+)/\d+", re.M)
SECOND = re.compile(r"2-[^,]*?\([\d.]+kg\)\s*([\d.]+)L")
W = (1.0, 0.8, 0.6, 0.4, 0.3, 0.2)


def runs_of(section, before):
    lines = section.splitlines(); out = []
    for i, ln in enumerate(lines):
        if "(TRIAL)" in ln:
            continue
        m = RUN.match(ln.strip())
        if not m or m.group("date") >= before:
            continue
        prize = int(m.group("prize"))
        if prize <= 0:
            continue
        d = int(m.group("dist")); wt = float(m.group("wt")); mg = float(m.group("m")); f = int(m.group("f"))
        if f == 1:
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            s2 = SECOND.search(nxt); mg = -float(s2.group(1)) if s2 else 0.0
        mg = max(-5.0, min(15.0, mg))
        lpl = 3.0 * (1000.0 / d) ** 0.75
        P = -lpl * mg + 2.2 * (wt - 57.0)
        out.append({"date": m.group("date"), "P": P, "R": P + 22.0 * math.log10(prize)})
    out.sort(key=lambda r: r["date"], reverse=True)
    return out[:6]


def main(base_path, out_path):
    data = json.loads(Path(base_path).read_text())["races"]
    dirs = {Path(d).name: d for d in glob.glob(ROOT + "/2026-*") + glob.glob(ROOT + "/Archive/**/2026-*", recursive=True)}
    cache = {}; out = {}; tot = cov = 0
    for r in data:
        if r["date"] < "2026-08-05":
            continue
        d = dirs.get(r["meeting"])
        key = (r["meeting"], r["race"])
        if key not in cache:
            fs = glob.glob(f"{d}/* Race {r['race']} Formguide.md") if d else []
            secs = {}
            if fs:
                t = open(fs[0], encoding="utf-8", errors="replace").read(); hs = list(HEAD.finditer(t))
                for i, h in enumerate(hs):
                    secs[int(h.group(1))] = t[h.start(): hs[i + 1].start() if i + 1 < len(hs) else len(t)]
            cache[key] = secs
        for x in r["rows"]:
            tot += 1
            rs = runs_of(cache[key].get(x["n"], ""), r["date"])
            if not rs:
                continue
            cov += 1
            w = W[:len(rs)]
            pr1 = sum(a["P"] * b for a, b in zip(rs, w)) / sum(w)
            pr2 = sum(a["R"] * b for a, b in zip(rs, w)) / sum(w)
            best = sorted((a["R"] for a in rs[:4]), reverse=True)[:2]
            out[f"{r['meeting']}|{r['race']}|{x['n']}"] = {"PR1": pr1, "PR2": pr2, "PR3": sum(best) / len(best), "runs": len(rs)}
        cache.pop(key, None) if len(cache) > 2000 else None
    Path(out_path).write_text(json.dumps(out))
    print("runners", tot, "with runs", cov, round(cov / tot, 3))


if __name__ == "__main__":
    main(*sys.argv[1:3])
