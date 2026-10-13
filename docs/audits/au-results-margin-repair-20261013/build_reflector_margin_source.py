"""Dated post-race source rows from Race_Results_Reflector.md (margin label metadata only).

Each row is bound to the reflector file it came from (path + SHA256). Track comes
from the file's own header line, date from that header, race from the `## Race N`
section. Never a scoring input.
"""
import csv, hashlib, json, re, sys
from pathlib import Path
root = Path(sys.argv[1]); out = Path(sys.argv[2]); lo, hi = sys.argv[3], sys.argv[4]
HEAD = re.compile(r"^#\s+(.+?)\s+Race Results\s+[—-]\s+(\d{4}-\d{2}-\d{2})\s*$")
RACE = re.compile(r"^##\s*Race\s*(\d+)")
LINE = re.compile(r"^(\d+)(?:st|nd|rd|th):\s*#\d+\s+(.+?)(?:\s+\(([\d.]+)L\))?\s+SP\$")
rows, links, stats = [], [], {"files": 0, "rows": 0, "bad_header": 0}
for path in sorted(list(root.glob("*/Race_Results_Reflector.md")) + list((root / "Archive").glob("*/Race_Results_Reflector.md"))):
    date = path.parent.name[:10]
    if not (lo <= date <= hi):
        continue
    raw = path.read_bytes(); text = raw.decode("utf-8"); digest = hashlib.sha256(raw).hexdigest()
    lines = text.splitlines()
    head = HEAD.match(lines[0].strip()) if lines else None
    if not head or head.group(2) != date:
        stats["bad_header"] += 1; continue
    track = head.group(1).strip(); stats["files"] += 1; race = None
    for line in lines[1:]:
        m = RACE.match(line.strip())
        if m:
            race = m.group(1); continue
        m = LINE.match(line.strip())
        if not (m and race):
            continue
        pos, horse, margin = m.group(1), m.group(2).strip(), m.group(3)
        if pos != "1" and not margin:
            continue  # no margin printed: nothing to fill
        rows.append({"Date": date, "Track": track, "Race": race, "Horse": horse, "Pos": pos,
                     "Margin": "0" if pos == "1" else margin})
        links.append({"key": [date, track, race, horse], "source_path": str(path), "source_sha256": digest,
                      "dated_run_track": track, "dated_run_date": date, "dated_run_race": race,
                      "pit_status": "POST_RACE_LABEL_METADATA_ONLY",
                      "source_kind": "Race_Results_Reflector.md"})
stats["rows"] = len(rows)
fields = ["Date", "Track", "Race", "Horse", "Pos", "Barrier", "Weight", "Jockey", "Trainer", "Distance", "Condition", "Margin", "Time"]
with (out / "rows.csv").open("w", newline="", encoding="utf-8") as h:
    w = csv.DictWriter(h, fieldnames=fields, restval=""); w.writeheader(); w.writerows(rows)
(out / "lineage.json").write_text(json.dumps(links, indent=1), encoding="utf-8")
print(json.dumps(stats))
