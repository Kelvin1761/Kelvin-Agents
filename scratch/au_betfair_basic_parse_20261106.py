"""EXP-20261106-02：Betfair Basic stream → 每匹 AU 純種馬 WIN 跑手一行（T−60/−15/−5 LTP、BSP、結果）。
    python3 -I parse_basic.py EXTRACTED_DIR OUT.jsonl
LTP 只取 inPlay == false 期間、pt ≤ 時點嘅最後一次更新。"""
import bz2, glob, json, re, sys
from datetime import datetime
from multiprocessing import Pool

HARNESS = re.compile(r"\b(Pace|Trot|Pacers?|Trotters?)\b", re.I)
OFFSETS = (60, 15, 5)


def ms(iso):
    return int(datetime.strptime(iso.replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S.%f%z").timestamp() * 1000)


def parse(path):
    try:
        lines = bz2.open(path, "rt").read().splitlines()
    except (OSError, EOFError):
        return [{"error": path}]
    first_def = last_def = None
    inplay_pt = None
    ltps = {}  # sel -> [(pt, ltp)]
    for line in lines:
        try:
            d = json.loads(line)
        except ValueError:
            return [{"error": path}]   # 壞行 → 成個市場剔走，唔用一半
        pt = d.get("pt")
        for mc in d.get("mc", []):
            md = mc.get("marketDefinition")
            if md:
                if first_def is None:
                    first_def = md
                    if md.get("marketType") != "WIN" or md.get("countryCode") != "AU" or HARNESS.search(md.get("name", "")):
                        return []
                last_def = md
                if md.get("inPlay") and inplay_pt is None:
                    inplay_pt = pt
            for rc in mc.get("rc", []):
                if "ltp" in rc and (inplay_pt is None):
                    ltps.setdefault(rc["id"], []).append((pt, rc["ltp"]))
    if not last_def:
        return []
    t0 = ms(last_def["marketTime"])
    out = []
    for r in last_def.get("runners", []):
        if r.get("status") not in ("WINNER", "LOSER"):
            continue
        series = ltps.get(r["id"], [])
        row = {"market": path.rsplit("/", 1)[-1][:-4], "event": last_def.get("eventId"), "venue": last_def.get("venue"),
               "name": last_def.get("name"), "market_time": last_def["marketTime"], "t0": t0, "inplay_pt": inplay_pt,
               "sel": r["id"], "runner": r.get("name"), "win": int(r["status"] == "WINNER"), "bsp": r.get("bsp"),
               "n_active": last_def.get("numberOfActiveRunners"), "last_ltp_pt": series[-1][0] if series else None}
        for m in OFFSETS:
            cut = t0 - m * 60000
            prior = [(p, v) for p, v in series if p <= cut]
            row[f"ltp{m}"] = prior[-1][1] if prior else None
            row[f"age{m}_min"] = round((cut - prior[-1][0]) / 60000, 2) if prior else None
        out.append(row)
    return out


if __name__ == "__main__":
    files = sorted(glob.glob(f"{sys.argv[1]}/BASIC/**/*.bz2", recursive=True))
    n = err = 0
    with Pool(8) as pool, open(sys.argv[2], "w") as fh:
        for rows in pool.imap_unordered(parse, files, chunksize=200):
            for row in rows:
                if "error" in row:
                    err += 1
                    continue
                fh.write(json.dumps(row) + "\n"); n += 1
    print("files", len(files), "runner rows", n, "read errors", err)
