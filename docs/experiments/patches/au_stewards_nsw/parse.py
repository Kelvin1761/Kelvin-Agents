#!/usr/bin/env python3
"""EXP-20261122-01：NSW 競賽主任 PDF → 每場每駒段落 → WIDE／VET／TROUBLE。  parse.py PDF_DIR LASTSTART.json OUT.json"""
import json, re, subprocess, sys
from pathlib import Path
TOOL = str(Path(__file__).resolve().parents[1] / "pdftext")
WIDE = re.compile(r"wide without cover", re.I)
VET = re.compile(r"\bbled\b|\blame\b|cardiac|irregular heart|poor recovery|respiratory|tied up|heat stress", re.I)
VET_NEG = re.compile(r"did not reveal any abnormalit", re.I)
TROUBLE = re.compile(r"\bchecked\b|held up|crowded|steadied|slow to begin|began awkwardly|\bbumped\b|hampered", re.I)
RACE = re.compile(r"^RACE\s+(\d+)\s*[:\-–]", re.M)


def norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def sections(text):
    """→ {場號: 該場文字}"""
    hs = list(RACE.finditer(text)); out = {}
    for i, h in enumerate(hs):
        out[int(h.group(1))] = text[h.end(): hs[i + 1].start() if i + 1 < len(hs) else len(text)]
    return out


def horse_text(race_text, horse):
    """段落：由「馬名 -／–／:」開始，到下一個段落開頭（行首大寫名 + -／–／:）為止。"""
    lines = race_text.splitlines(); key = norm(horse); buf = []; on = False
    for ln in lines:
        m = re.match(r"^([A-Z][A-Za-z' .\-]{1,30}?)\s*[\-–:]\s", ln)
        if m:
            on = norm(m.group(1)) == key
        if on:
            buf.append(ln)
    return " ".join(buf)


def main(pdf_dir, last_path, out_path):
    last = json.loads(Path(last_path).read_text()); cache = {}; out = {}; found = 0
    for key, r in last.items():
        pdf = Path(pdf_dir) / f"{r['pdf']}.pdf"
        if not pdf.exists():
            continue
        if r["pdf"] not in cache:
            cache[r["pdf"]] = sections(subprocess.run([TOOL, str(pdf)], capture_output=True, text=True).stdout)
        t = horse_text(cache[r["pdf"]].get(r["race"], ""), r["horse"])
        vet = bool(VET.search(t)) and not (VET_NEG.search(t) and not re.search(r"bled|lame|cardiac", t, re.I))
        out[key] = {"has_report": True, "mentioned": bool(t), "WIDE": bool(WIDE.search(t)), "VET": vet,
                    "TROUBLE": bool(TROUBLE.search(t))}
        found += bool(t)
    Path(out_path).write_text(json.dumps(out))
    n = len(out)
    print("runners with report", n, "mentioned", found,
          {k: sum(v[k] for v in out.values()) for k in ("WIDE", "VET", "TROUBLE")})


if __name__ == "__main__":
    main(*sys.argv[1:4])
