"""EXP-20261115-22 跟進：解析補抓嘅 2019-09 至 2023-10 賽果頁事件報告（敘述格式，馬名喺「」入面，冇烙號）。

做法：每段（<br/>）再按「。」切句；每句歸屬**第一個出現**嘅馬名（句子主語，例如「X」出閘笨拙／獸醫報告「X」……）；
馬名 → 烙號用賽果索引同場馬名對照。輸出 {"日期|場次": {烙號: 句子串}}。
用法：python3 parse_old.py <out.json>
"""
import gzip
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
RAW = Path("/Volumes/Kelvin Hardisk 1/WongChoi-Archive/hkjc-history/raw/results")


def main():
    import hkjc_history_replay_build as b
    idx = b.load_index()
    out, stats = {}, dict(pages=0, no_report=0, sent=0, attributed=0)
    for f in sorted(RAW.glob("*.html.gz")):
        d, n = f.name[:10], int(f.name[11:].split(".")[0])
        race = idx["results"].get((d, n))
        if not race:
            continue
        stats["pages"] += 1
        h = gzip.open(f, "rt", encoding="utf-8").read()
        m = re.search(r'race_incident_report.*?<p class="info_p[^"]*">(.*?)</p>', h, re.S)
        if not m:
            stats["no_report"] += 1
            continue
        names = {}
        for row in race.get("results", []):
            mm = re.match(r"(.+?)\(([A-Z]\d{3})\)", str(row.get("horse_name") or ""))
            if mm:
                names[mm.group(1).strip()] = mm.group(2)
        per = {}
        for para in re.split(r"<br\s*/?>", m.group(1)):
            para = html.unescape(re.sub(r"<[^>]+>", "", para)).strip()
            for s in [x for x in re.split(r"(?<=。)", para) if x.strip()]:
                stats["sent"] += 1
                first = re.search(r"「([^」]+)」", s)
                if first and first.group(1) in names:
                    stats["attributed"] += 1
                    per.setdefault(names[first.group(1)], []).append(s.strip())
        out[f"{d}|{n}"] = {c: " ".join(v) for c, v in per.items()}
    json.dump(out, open(sys.argv[1], "w"), ensure_ascii=False)
    print(stats, len(out))


if __name__ == "__main__":
    main()
