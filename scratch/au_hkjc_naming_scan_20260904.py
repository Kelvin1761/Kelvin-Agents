#!/usr/bin/env python3
"""Where do AU and HKJC name the same artifact differently?

Five defects in one day shared a shape: the two platforms write the same
concept under different names or formats, and code that knows only one of them
fails silently. This enumerates what is actually on disk for each platform and
pairs the concepts up, so the mismatches are a list rather than a discovery.
Read-only.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from wongchoi_paths import AU_RACING, HK_RACING  # noqa: E402

# Meeting folders only; the roots also hold databases, CSVs and archives.
AU_MEETING = re.compile(r"^\d{4}-\d{2}-\d{2}\s+\S")
HKJC_MEETING = re.compile(r"^\d{4}-\d{2}-\d{2}_\w+")

DATE_TOKEN = re.compile(r"\d{4}-\d{2}-\d{2}|\d{2}-\d{2}")


def shape(name: str) -> str:
    """Collapse a filename to its naming shape so copies collapse together."""
    out = re.sub(r"\d{4}-\d{2}-\d{2}", "<YYYY-MM-DD>", name)
    out = re.sub(r"(?<![\d-])\d{2}-\d{2}(?![\d-])", "<MM-DD>", out)
    out = re.sub(r"\d+", "<N>", out)
    return out


def collect(root: Path, pattern: re.Pattern, limit: int = 12):
    meetings = [p for p in sorted(root.iterdir()) if p.is_dir() and pattern.match(p.name)]
    files: Counter = Counter()
    dirs: Counter = Counter()
    for meeting in meetings[-limit:]:
        for child in meeting.iterdir():
            (dirs if child.is_dir() else files)[shape(child.name)] += 1
    siblings = sorted(p.name for p in root.iterdir()
                      if not pattern.match(p.name) and not p.name.startswith("."))
    return {"meetings_sampled": len(meetings[-limit:]), "total_meetings": len(meetings),
            "files": files, "dirs": dirs, "root_siblings": siblings}


def main() -> int:
    au = collect(AU_RACING, AU_MEETING)
    # AU archives most meetings; sample there too or the picture is one week wide.
    archive = AU_RACING / "Archive"
    if archive.is_dir():
        extra = collect(archive, AU_MEETING)
        au["files"].update(extra["files"])
        au["dirs"].update(extra["dirs"])
        au["meetings_sampled"] += extra["meetings_sampled"]
    hk = collect(HK_RACING, HKJC_MEETING)

    print("=" * 74)
    print(f"AU  meeting folders sampled {au['meetings_sampled']} / {au['total_meetings']}")
    print(f"HK  meeting folders sampled {hk['meetings_sampled']} / {hk['total_meetings']}")
    print("=" * 74)

    print("\n--- 場次夾入面嘅子目錄 ---")
    print(f"{'AU':44}{'HKJC'}")
    for a, h in zip(sorted(au['dirs']) + [""] * 9, sorted(hk['dirs']) + [""] * 9):
        if not a and not h:
            break
        print(f"  {a:42}{h}")

    print("\n--- 檔名形狀（各自最常見） ---")
    print(f"{'AU':44}{'HKJC'}")
    a_shapes = [s for s, _ in au["files"].most_common(14)]
    h_shapes = [s for s, _ in hk["files"].most_common(14)]
    for a, h in zip(a_shapes + [""] * 14, h_shapes + [""] * 14):
        if not a and not h:
            break
        print(f"  {a:42}{h}")

    print("\n--- 兩個根目錄嘅非場次項 ---")
    print("AU  :", ", ".join(au["root_siblings"])[:300])
    print("HKJC:", ", ".join(hk["root_siblings"])[:300])

    print("\n--- 日期前綴用法 ---")
    for label, data in (("AU", au), ("HKJC", hk)):
        full = sum(n for s, n in data["files"].items() if "<YYYY-MM-DD>" in s)
        short = sum(n for s, n in data["files"].items() if "<MM-DD>" in s)
        none = sum(n for s, n in data["files"].items()
                   if "<YYYY-MM-DD>" not in s and "<MM-DD>" not in s)
        print(f"  {label:5} 全日期 {full:5}   短日期 {short:5}   冇日期 {none:5}"
              f"   {'⚠️ 兩種格式並存' if full and short else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
