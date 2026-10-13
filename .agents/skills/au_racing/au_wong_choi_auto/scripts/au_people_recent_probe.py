#!/usr/bin/env python3
"""EXP-20261014-01：騎練近期狀態（已完結月份）＋見習減磅。研究工具，唔郁 engine。

    PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 au_people_recent_probe.py build LEAVES OUT
    PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 au_people_recent_probe.py diag  LEAVES OUT
    PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 au_people_recent_probe.py judge LEAVES OUT FEATURE
"""
import json
import re
import statistics
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
AU = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(AU))
import au_speed_rebuild_probe as base  # noqa: E402

MONTHS = {m: i for i, m in enumerate(
    ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1)}
ALPHA = 20.0
PEOPLE_LINE = re.compile(r"^T:\s*(?P<t>.+?)\s*\(LY:.*?\|\s*J:\s*(?P<j>.+?)\s*\(LY:", re.M)
CLAIM = re.compile(r"\(a-?(\d+(?:\.\d+)?)\)")


def pkey(name):
    import html
    s = html.unescape(name or "")
    s = re.sub(r"\s+A\d?(?:\.\d)?$", "", s.strip())     # 見習標記 A / A2
    return re.sub(r"[^a-z]", "", s.lower())


def people_months():
    """{(kind, name_key): {(y, m): (starts, places)}} —— 合併所有快照，同一月份取最新快照。"""
    import sb_people_stats as sps
    by_id, names = defaultdict(dict), {}
    for kid, entry in sps.load_cache().items():
        if isinstance(entry, dict) and str(entry.get("name") or "").strip():
            names[kid] = entry["name"]
    with open(sps.snapshot_path()) as fh:
        for line in fh:
            rec = json.loads(line)
            mb = ((rec.get("contextual_stats") or {}).get("Monthly Breakdown") or {}).get("Last 12 Months") or {}
            for label, s in mb.items():
                mon, _, yr = label.partition(" ")
                if mon[:3] in MONTHS and yr.isdigit() and s.get("starts") is not None:
                    by_id[rec["key"]][(int(yr), MONTHS[mon[:3]])] = (
                        int(s["starts"]), int(s.get("1st", 0)) + int(s.get("2nd", 0)) + int(s.get("3rd", 0)))
    out, clash = {}, set()
    for kid, months in by_id.items():
        if kid not in names:
            continue
        k = (kid.split("|")[0], pkey(names[kid]))
        if k in out:
            clash.add(k)
        out[k] = months
    for k in clash:
        out.pop(k, None)
    return out, len(clash)


def recent_delta(months, race_date):
    y, m = int(race_date[:4]), int(race_date[5:7])
    prior = []
    for back in range(1, 13):
        mm, yy = m - back, y
        while mm <= 0:
            mm += 12
            yy -= 1
        if (yy, mm) in months:
            prior.append((back, *months[(yy, mm)]))
    s12 = sum(s for _, s, _ in prior)
    p12 = sum(p for _, _, p in prior)
    if s12 < 20:
        return None
    base_rate = p12 / s12
    s3 = sum(s for b, s, _ in prior if b <= 3)
    p3 = sum(p for b, _, p in prior if b <= 3)
    if s3 == 0:
        return None
    return (p3 + ALPHA * base_rate) / (s3 + ALPHA) - base_rate


def claim_index():
    """{(venue_key, race_no, horse_norm): claim_kg} 由所有 cache 賽事頁抽。撞 key 而值唔同 = 棄。"""
    import claw_sportsbet_form as c
    idx, bad = {}, set()
    for f in Path(c.CACHE_DIR).glob("*.html"):
        h = f.read_text(errors="replace")
        if "Jump to top" not in h:
            continue
        try:
            meta = c.parse_race(h)["meta"]
        except Exception:  # noqa: BLE001
            continue
        venue, rno = meta.get("venue"), meta.get("race_number")
        if not venue or not rno:
            continue
        ne = [ln.strip() for ln in c.to_text(h).splitlines() if ln.strip()]
        for i, ln in enumerate(ne):
            if ln == "J" and i >= 4 and ne[i - 2] == "T" and re.fullmatch(r"\(\d+\)", ne[i - 3]) and i + 1 < len(ne):
                horse = base.norm(ne[i - 4])
                m = CLAIM.search(ne[i + 1])
                key = (re.sub(r"[^a-z]", "", venue.lower()), int(rno), horse)
                val = float(m.group(1)) if m else 0.0
                if key in idx and idx[key] != val:
                    bad.add(key)
                idx[key] = val
    for k in bad:
        idx.pop(k, None)
    return idx


def build(leaves_path, out_path):
    races = json.load(open(leaves_path))["races"]
    mi = base.meeting_index()
    pm, clashes = people_months()
    cl = claim_index()
    out = {}
    hit = defaultdict(int)
    for race in races:
        md = mi.get(race["meeting"])
        fg = next(iter(md.glob(f"* Race {race['race']} Formguide.md")), None) if md else None
        venue = re.sub(r"^\d{4}-\d{2}-\d{2}\s+", "", race["meeting"]).split(" Race ")[0]
        vkey = re.sub(r"[^a-z]", "", venue.lower())
        people = {}
        if fg:
            text = fg.read_text(encoding="utf-8", errors="replace")
            heads = list(base.HORSE.finditer(text))
            for i, h in enumerate(heads):
                end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
                m = PEOPLE_LINE.search(text[h.end():end])
                if m:
                    people[base.norm(h.group(2))] = (m.group("j"), m.group("t"))
        for row in race["rows"]:
            name = base.norm(row["name"])
            feats = {}
            j, t = people.get(name, (None, None))
            for kind, who, fname in (("jockey", j, "jockey_recent_delta"), ("trainer", t, "trainer_recent_delta")):
                months = pm.get((kind, pkey(who))) if who else None
                if months and (v := recent_delta(months, race["date"])) is not None:
                    feats[fname] = v
                    hit[fname] += 1
            ck = (vkey, int(race["race"]), name)
            if ck in cl:
                feats["claim_kg"] = cl[ck]
                hit["claim_kg"] += 1
            out[f"{race['meeting']}|{race['race']}|{name}"] = feats
    json.dump({"features": out}, open(out_path, "w"))
    n = sum(len(r["rows"]) for r in races)
    print(f"people 月表 {len(pm)} 人（同名撞 {clashes} 個剔走）；減磅 index {len(cl)} 匹次；runner {n}")
    print("覆蓋：" + "  ".join(f"{k} {100 * v / n:.1f}%" for k, v in hit.items()))
    print("見習比例（有頁面嘅）：", f"{100 * sum(1 for v in out.values() if v.get('claim_kg', 0) > 0) / max(1, hit['claim_kg']):.1f}%")


def diag(leaves_path, feats_path):
    races = base.attach(leaves_path, feats_path)
    for f, comp in (("jockey_recent_delta", "jockey_score"), ("trainer_recent_delta", "trainer_score"),
                    ("claim_kg", "jockey_score")):
        w = t = 0
        rhos = []
        for race in races:
            rows = [r for r in race["rows"] if f in r["_sf"]]
            vp = [(r["_sf"][f], r["pos"]) for r in rows]
            if len(vp) >= 3 and (a := base._auc_place(vp)):
                w += a[0]
                t += a[1]
            s = base._spearman([r["_sf"][f] for r in rows], [r["features"].get(comp, 60) for r in rows])
            if s is not None:
                rhos.append(s)
        print(f"{f:22} 場內上名 AUC {w / t if t else float('nan'):.4f}   ρ vs {comp} {statistics.mean(rhos) if rhos else float('nan'):+.3f}")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "build":
        build(sys.argv[2], sys.argv[3])
    elif cmd == "diag":
        diag(sys.argv[2], sys.argv[3])
    elif cmd == "judge":
        ks = (-3, -2, -1, -0.5, 0.5, 1, 2, 3) if sys.argv[4] == "claim_kg" else (0.5, 1, 1.5, 2, 3)
        base.judge(sys.argv[2], sys.argv[3], sys.argv[4], ks=ks)
