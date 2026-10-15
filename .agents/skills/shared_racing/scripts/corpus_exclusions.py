#!/usr/bin/env python3
"""Explicit, reviewable exclusions from the AU evaluation corpus.

WHY THIS EXISTS
---------------
EXP-20261015-04 found 7 AU meetings whose stored Formguide/Logic were extracted
on race day **after** the races.  The form-run *rows* were already gated
(`run_date >= D` is dropped), but the Sportsbet page's cumulative stats —
Career / Track / Distance / Good / 1st Up / 12 Month / J/H ... — were copied
verbatim and already include the result being predicted.  Every backtest that
read those meetings was scoring with the answer partly in the input.

Kelvin decided (2026-10-15) to exclude them rather than move data files.
Moving a meeting into `Archive/` is NOT an exclusion — `Archive/` is part of the
corpus (see corpus_paths), and "move it somewhere" silently removed 33 meetings
from every backtest once before.  So the exclusion lives in one JSON file in the
repo, with a reason and the experiment that found it, and `corpus_paths` applies
it for every harness.

DETECTION RULE (same as EXP-20261015-04)
----------------------------------------
`claw_sportsbet_form.write_meeting` writes `Meeting_Summary.md` with

    Form runs kept: K; dropped as on/after YYYY-MM-DD: N

A pre-race page has no row dated on/after race day, so N == 0.  N > 0 means the
page was fetched after (some of) the races had run — the page's cumulative
stats leak.  If the extractor reports it recomputed page stats from as-of rows
for every race (`Point-in-time mode: ... : P` with P >= races), the stats no
longer leak and the meeting is reported as `post_race_pit_recomputed`.
Meetings without that line (pre-Sportsbet extractors, Racenet era) are
`unknown` — the rule cannot judge them, and they are not claimed clean.

Usage:
    python3 corpus_exclusions.py --platform au          # scan whole corpus
    python3 corpus_exclusions.py --platform au --check  # exit 1 on a NEW leak
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

RESOURCES = Path(__file__).resolve().parents[1] / "resources"
EXCLUSIONS_PATH = {"au": RESOURCES / "au_corpus_exclusions.json"}

REASON_POST_RACE = "post_race_extraction"

_DROPPED = re.compile(r"dropped as on/after (\d{4}-\d{2}-\d{2}):\s*(\d+)")
_RACES = re.compile(r"(\d+) races extracted")
_PIT = re.compile(r"Point-in-time mode:\s*(\w+);.*?:\s*(\d+)")

STATUS_CLEAN = "clean"
STATUS_POST_RACE = "post_race"
STATUS_PIT_FIXED = "post_race_pit_recomputed"
STATUS_UNKNOWN = "unknown"


def load_exclusions(domain: str = "au", path: Path | str | None = None) -> dict[str, dict]:
    """Meeting folder name -> exclusion entry.  Missing file = no exclusions."""
    source = Path(path) if path else EXCLUSIONS_PATH.get(domain)
    if source is None or not source.exists():
        return {}
    data = json.loads(source.read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for entry in data.get("meetings") or []:
        name = entry.get("meeting")
        if not name or not entry.get("reason") or not entry.get("detected_by"):
            raise ValueError(f"{source}: 每個排除項都要有 meeting / reason / detected_by：{entry}")
        if name in out:
            raise ValueError(f"{source}: 重複排除 {name}")
        out[name] = entry
    return out


def detect_post_race_extraction(meeting_dir: Path | str) -> dict:
    """Classify one meeting folder by its extractor summary (see module doc)."""
    summary = Path(meeting_dir) / "Meeting_Summary.md"
    result = {"meeting": Path(meeting_dir).name, "status": STATUS_UNKNOWN,
              "dropped": None, "races": None, "pit_races": None}
    try:
        text = summary.read_text(encoding="utf-8")
    except OSError:
        return result
    match = _DROPPED.search(text)
    if not match:
        return result
    dropped = int(match.group(2))
    races = _RACES.search(text)
    pit = _PIT.search(text)
    result["dropped"] = dropped
    result["races"] = int(races.group(1)) if races else None
    result["pit_races"] = int(pit.group(2)) if pit else None
    if dropped == 0:
        result["status"] = STATUS_CLEAN
    elif (pit and result["races"] is not None
          and result["pit_races"] >= result["races"]):
        result["status"] = STATUS_PIT_FIXED
    else:
        result["status"] = STATUS_POST_RACE
    return result


def scan(meeting_dirs, exclusions: dict[str, dict]) -> dict:
    """Run the detector over meeting folders and compare with the exclusion list."""
    rows = [detect_post_race_extraction(m) for m in meeting_dirs]
    names = {r["meeting"] for r in rows}
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    leaks = [r for r in rows if r["status"] == STATUS_POST_RACE]
    return {
        "meetings": len(rows),
        "counts": counts,
        "post_race": leaks,
        # Detected but not listed: the case this whole module exists to catch.
        "unlisted": [r for r in leaks if r["meeting"] not in exclusions],
        # Listed but no longer present in the corpus (renamed / deleted).
        "listed_missing": sorted(n for n in exclusions if n not in names),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--platform", default="au", choices=sorted(EXCLUSIONS_PATH))
    parser.add_argument("--check", action="store_true",
                        help="exit 1 if a post-race-extracted meeting is not in the exclusion list")
    args = parser.parse_args(argv)

    repo = Path(__file__).resolve().parents[4]
    sys.path.insert(0, str(repo))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import wongchoi_paths
    from corpus_paths import meeting_dirs

    root = wongchoi_paths.AU_RACING
    exclusions = load_exclusions(args.platform)
    report = scan(meeting_dirs(root, include_excluded=True), exclusions)
    counts = report["counts"]
    print(f"AU 語料 {report['meetings']} 個場次："
          + "、".join(f"{k} {v}" for k, v in sorted(counts.items())))
    print(f"排除名單 {len(exclusions)} 個；偵測到賽後抽 {len(report['post_race'])} 個")
    for r in report["post_race"]:
        tag = "已排除" if r["meeting"] in exclusions else "❌ 未排除"
        print(f"  {tag}  {r['meeting']}（丟棄 {r['dropped']} 行）")
    for name in report["listed_missing"]:
        print(f"  ⚠️  排除名單有 {name}，但語料搵唔到")
    if report["unlisted"]:
        print("新出現賽後抽場次：頁面累積統計已計埋賽果。重抽（PIT 模式）或加入 "
              f"{EXCLUSIONS_PATH[args.platform].name}")
        return 1 if args.check else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
