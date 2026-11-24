#!/usr/bin/env python3
"""EXP-20261124-30 特徵（預先登記，見 PROTOCOL.md）。 features.py BASE.json OUT.json
每匹馬（meeting|race|n）由 Formguide 讀賽前往績（日期嚴格早過今仗、唔計試閘）：
  V2  今仗路程 ±50m 有上名（頭三），但所有呢啲上名都唔喺今仗場地
  T1  今仗係人造地，而之前冇跑過人造地（最少有 1 仗往績）
  T2  上仗場地方向（順／逆時針）同今仗唔同（兩邊方向都知先計）
"""
import glob, json, re, sys
from pathlib import Path
ROOT = "/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/AU_Racing"
REPO = Path(__file__).resolve().parents[4]
GEO = json.loads((REPO / ".agents/skills/au_racing/au_wong_choi_auto/resources/au_track_geometry.json").read_text())["venues"]
HEAD = re.compile(r"^\[(\d+)\]\s+(.+?) \((\d+)\)\s*$", re.M)
RUN = re.compile(r"^(?P<venue>.+?) R\d+ (?P<date>\d{4}-\d{2}-\d{2}) (?P<dist>\d+)m .*?finish:(?P<f>\d+)/(?P<s>\d+)", re.M)


def key(name):
    return re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-")


def synthetic(name):
    return "synthetic" in str(name).lower() or "poly" in str(name).lower()


def direction(name):
    k = key(name)
    for cand in (k, re.sub(r"-synthetic$|-poly.*$", "", k)):
        d = (GEO.get(cand) or {}).get("direction")
        if d:
            return d
    return None


def runs_of(section, before):
    out = []
    for ln in section.splitlines():
        if "(TRIAL)" in ln:
            continue
        m = RUN.match(ln.strip())
        if m and m.group("date") < before:
            out.append({"venue": m.group("venue").strip(), "date": m.group("date"), "dist": int(m.group("dist")),
                        "f": int(m.group("f"))})
    return sorted(out, key=lambda r: r["date"], reverse=True)


def venue_of(meeting):
    return re.sub(r"^\d{4}-\d{2}-\d{2}[ _]", "", meeting).split(" Race")[0].split("_Race")[0].strip()


def main(base_path, out_path):
    data = json.loads(Path(base_path).read_text())["races"]
    dirs = {Path(d).name: d for d in glob.glob(ROOT + "/2026-*") + glob.glob(ROOT + "/Archive/**/2026-*", recursive=True)}
    out, n, cnt = {}, 0, {"V2": 0, "T1": 0, "T2": 0, "runs": 0}
    for r in data:
        if r["date"] < "2026-08-05":
            continue
        d = dirs.get(r["meeting"])
        fs = glob.glob(f"{d}/* Race {r['race']} Formguide.md") if d else []
        secs = {}
        if fs:
            t = open(fs[0], encoding="utf-8", errors="replace").read(); hs = list(HEAD.finditer(t))
            for i, h in enumerate(hs):
                secs[int(h.group(1))] = t[h.start(): hs[i + 1].start() if i + 1 < len(hs) else len(t)]
        today_v = venue_of(r["meeting"]); today_k = key(today_v); today_d = direction(today_v)
        for x in r["rows"]:
            n += 1
            rs = runs_of(secs.get(x["n"], ""), r["date"])
            dist = x.get("distance")
            try:
                dist = int(float(str(dist).rstrip("m")))
            except (TypeError, ValueError):
                dist = None
            f = {"V2": 0, "T1": 0, "T2": 0, "runs": len(rs)}
            if rs:
                cnt["runs"] += 1
                if dist:
                    placed = [a for a in rs if abs(a["dist"] - dist) <= 50 and a["f"] <= 3]
                    if placed and not any(key(a["venue"]) == today_k for a in placed):
                        f["V2"] = 1
                if synthetic(today_v) and not any(synthetic(a["venue"]) for a in rs):
                    f["T1"] = 1
                last_d = direction(rs[0]["venue"])
                if today_d and last_d and last_d != today_d:
                    f["T2"] = 1
            for k2 in ("V2", "T1", "T2"):
                cnt[k2] += f[k2]
            out[f"{r['meeting']}|{r['race']}|{x['n']}"] = f
    Path(out_path).write_text(json.dumps(out))
    print("runners", n, {k: (v, round(v / max(n, 1), 3)) for k, v in cnt.items()})


if __name__ == "__main__":
    main(*sys.argv[1:3])
