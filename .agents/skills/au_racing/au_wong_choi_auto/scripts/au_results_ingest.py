#!/usr/bin/env python3
"""Fold per-meeting `Race_Results_Reflector.md` files into the canonical results CSV.

WHY THIS EXISTS
---------------
`AU_Historical_Raw_Race_Results.csv` is the corpus every backtest, calibration and
matrix re-fit joins against. It was fed by a **Racenet** results driver. Racenet was
removed (see the `au_racenet_fully_removed` note), and `sb_results.py` replaced it —
but `sb_results.py` only writes the per-meeting `Race_Results_Reflector.md`. Nobody
wrote the step that folds those back into the canonical CSV.

Result: the CSV silently stopped at **2026-07-08** while meetings kept being scored and
reflected. Nothing errored; every harness just quietly evaluated an older, smaller
corpus. Checked 2026-08-16, that was five weeks and ~1,000 races — and exactly the
window in which formguide in-running coverage went from ~0% to ~94%.

`au_statistics_aggregator.py` cannot do this job: it only accepts filenames containing
"Flemington" or "Randwick" (`else: continue`), and parses the old rich
`Race_Results_<Track>_<date>.md` table, not the reflector's `1st: #5 Name SP$1.80`.

KNOWN LIMITATION — read before trusting field-size metrics
----------------------------------------------------------
Reflector files are usually truncated: measured over 1,136 races, only 3.0% list the
whole field (630 races stop at 6th, 330 at 4th). So a race ingested from a reflector
contributes only its recorded finishers. Top-3 / winner metrics are unaffected — they
only need the placed horses' identities — but anything deriving FIELD SIZE by counting
result rows will understate it. Races with fewer than `--min-finishers` recorded are
skipped rather than written half-blind; `load_historical_results` would reject them
downstream anyway (it needs >=4 rows, a winner, and >=3 in the top three).

Merging is idempotent and additive: existing rows are never modified or dropped, and a
timestamped backup is taken before the file is touched.

    python3 au_results_ingest.py --dry-run          # report only, writes nothing
    python3 au_results_ingest.py --apply
"""
from __future__ import annotations

import argparse
import csv
import re
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR))

from au_archive_calibrator import ARCHIVE_ROOT, HISTORICAL_RESULTS_CSV  # noqa: E402
from au_racing_engine.source_alignment import normalize_horse_name  # noqa: E402

FIELDNAMES = ["Date", "Track", "Race", "Distance", "Condition", "Pos", "Horse",
              "Barrier", "Weight", "Jockey", "Trainer", "Margin", "SP", "Time"]

MEETING_DIR_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}) (.+?)(?: Race \d+-\d+)?$")
TITLE_RE = re.compile(r"^#\s*(.+?)\s+Race Results\s*—\s*(\d{4}-\d{2}-\d{2})", re.M)
RACE_HDR_RE = re.compile(r"^##\s*Race\s*(\d+)", re.M)
PLACE_RE = re.compile(
    r"^(\d+)(?:st|nd|rd|th):\s*#(\S+)\s+(.+?)"
    r"(?:\s*\(([-\d.]+)L\))?"
    r"(?:\s*SP\$([\d.]+))?\s*$", re.M)
# "RACE 3 — 1200m | Class 2 | $50,000" and "Track: Good 4 | Weather: ..."
FG_DIST_RE = re.compile(r"^RACE\s+(\d+)\s*—\s*(\d+)m", re.M | re.I)
FG_COND_RE = re.compile(r"^Track:\s*([^|\n]+)", re.M)


def parse_reflector(path: Path) -> tuple[str, str, dict]:
    """-> (venue, date, {race_no: [ {pos, num, horse, margin, sp}, ... ]})"""
    text = path.read_text(encoding="utf-8")
    title = TITLE_RE.search(text)
    venue = title.group(1).strip() if title else ""
    date = title.group(2) if title else ""
    races, heads = {}, list(RACE_HDR_RE.finditer(text))
    for index, head in enumerate(heads):
        end = heads[index + 1].start() if index + 1 < len(heads) else len(text)
        rows = []
        for m in PLACE_RE.finditer(text[head.end():end]):
            rows.append({"pos": int(m.group(1)), "num": m.group(2),
                         "horse": m.group(3).strip(),
                         "margin": m.group(4) or "", "sp": m.group(5) or ""})
        if rows:
            races[str(int(head.group(1)))] = rows
    return venue, date, races


def race_context(meeting: Path) -> dict:
    """{race_no: (distance, condition)} from the per-race Formguide headers."""
    out = {}
    for fg in meeting.glob("*Formguide.md"):
        rn = re.search(r"Race\s+(\d+)\s+Formguide", fg.name)
        if not rn:
            continue
        try:
            text = fg.read_text(encoding="utf-8")
        except OSError:
            continue
        dm = FG_DIST_RE.search(text)
        cm = FG_COND_RE.search(text)
        out[str(int(rn.group(1)))] = (
            dm.group(2) if dm else "",
            cm.group(1).strip() if cm else "",
        )
    return out


def runner_details(meeting: Path) -> dict:
    """{(race_no, horse_slug): {Jockey, Trainer}} from the engine's own scoring CSV."""
    path = meeting / "Meeting_Auto_Scoring.csv"
    out = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            key = (str(row.get("race_number")), normalize_horse_name(row.get("horse_name")))
            out[key] = {"Jockey": (row.get("jockey") or "").strip(),
                        "Trainer": (row.get("trainer") or "").strip()}
    return out


def load_sb_csv(path: Path, stats: dict) -> list[dict]:
    """Rows from a `sb_results_csv.py` dump, normalised onto the canonical schema.

    That script reads the Sportsbet cache and takes each runner's own
    `Finished 3/11 0.42L` form line, so it carries the WHOLE field — the reflector
    is usually cut off at 4th or 6th. Prefer it wherever the cache reaches; it
    stops at whatever meetings are in the id map (2026-08-10 as of 2026-08-16),
    which is why the reflector path still has to exist.
    """
    out = []
    if not path.exists():
        stats["sb_csv_missing"] += 1
        return out
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if not str(row.get("Pos") or "").strip().isdigit():
                continue
            margin = str(row.get("Margin") or "").strip()
            sp = str(row.get("SP") or "").strip()
            record = {key: str(row.get(key) or "").strip() for key in FIELDNAMES}
            record["Pos"] = int(row["Pos"])
            # normalise onto the legacy conventions (see collect())
            if margin and not margin.endswith("L") and margin != "—":
                margin = f"{margin}L"
            record["Margin"] = margin or "—"
            record["SP"] = sp if (not sp or sp.startswith("$")) else f"${sp}"
            out.append(record)
    stats["sb_csv_rows"] += len(out)
    return out


def existing_keys(path: Path) -> tuple[set, int]:
    keys, count = set(), 0
    if not path.exists():
        return keys, count
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            count += 1
            keys.add((str(row.get("Date") or "").strip(),
                      str(row.get("Race") or "").strip(),
                      normalize_horse_name(row.get("Horse") or "")))
    return keys, count


def collect(archive_root: Path, min_finishers: int) -> tuple[list[dict], dict]:
    rows, stats = [], defaultdict(int)
    bases = [archive_root, archive_root / "Archive"]
    for base in bases:
        if not base.exists():
            continue
        for meeting in sorted(base.iterdir()):
            if not meeting.is_dir() or not MEETING_DIR_RE.match(meeting.name):
                continue
            reflector = meeting / "Race_Results_Reflector.md"
            if not reflector.exists():
                stats["meetings_without_reflector"] += 1
                continue
            stats["meetings_seen"] += 1
            venue, date, races = parse_reflector(reflector)
            if not (venue and date and races):
                stats["meetings_unparseable"] += 1
                continue
            context = race_context(meeting)
            details = runner_details(meeting)
            for race_no, finishers in races.items():
                positions = [f["pos"] for f in finishers]
                if len(finishers) < min_finishers or 1 not in positions:
                    stats["races_too_thin"] += 1
                    continue
                stats["races_ingested"] += 1
                distance, condition = context.get(race_no, ("", ""))
                for f in finishers:
                    extra = details.get((race_no, normalize_horse_name(f["horse"])), {})
                    rows.append({
                        "Date": date, "Track": venue, "Race": race_no,
                        "Distance": distance, "Condition": condition,
                        "Pos": f["pos"], "Horse": f["horse"],
                        "Barrier": "", "Weight": "",
                        "Jockey": extra.get("Jockey", ""), "Trainer": extra.get("Trainer", ""),
                        # Match the existing rows' conventions exactly ("1.25L",
                        # "$3.50", em dash for the winner). A second convention in
                        # the same column silently breaks whichever consumer parses
                        # the string rather than the number.
                        "Margin": f"{f['margin']}L" if f["margin"] else "—",
                        "SP": f"${f['sp']}" if f["sp"] else "",
                        # ⚠️ 2026-08-26：呢個硬寫嘅空字串殺死咗成條 `Time` 欄。
                        # 舊行（2025-08 → 2026-06）由 `au_statistics_aggregator`
                        # 寫入，係**逐匹馬個別時間**，覆蓋 99–100%。當呢個 ingest
                        # 變成主路徑（約 2026-07），覆蓋跌到 2026-07 29%、
                        # 2026-08 **0%**。
                        #
                        # 點解未修：呢度個來源係 reflector markdown，而
                        # `parse_reflector` 只攞到 pos/num/horse/margin/sp ——
                        # 賽果 markdown 本身冇時間。要真正補返就要由 Sportsbet
                        # 賽果頁抽（`claw_sportsbet_form.parse_race` 個 run dict
                        # 有 `winning_time`），再確認嗰個係頭馬時間定個別時間，
                        # 然後經 `--sb-csv` 路徑帶入嚟。
                        #
                        # 影響：任何「絕對時間 / 速度評分」研究都冇咗 2026-07 之後
                        # 嘅數據（見 EXP-20260826-05）。合併唔會蓋走舊行，所以
                        # 歷史時間仲喺度。
                        "Time": "",
                    })
    return rows, stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--archive-root", type=Path, default=ARCHIVE_ROOT)
    ap.add_argument("--results-csv", type=Path, default=HISTORICAL_RESULTS_CSV)
    ap.add_argument("--min-finishers", type=int, default=4,
                    help="skip races with fewer recorded finishers (default 4, the "
                         "minimum load_historical_results accepts)")
    ap.add_argument("--sb-csv", type=Path,
                    help="output of sb_results_csv.py. Preferred source: it reads the "
                         "Sportsbet cache and carries FULL fields (~9.9 runners/race) "
                         "where the reflector is truncated to ~6. Merged first; "
                         "reflectors then fill only what it does not cover.")
    ap.add_argument("--apply", action="store_true", help="write; otherwise dry-run")
    ap.add_argument("--dry-run", action="store_true", help="explicit no-op (the default)")
    args = ap.parse_args()

    rows, stats = [], defaultdict(int)
    if args.sb_csv:
        rows.extend(load_sb_csv(args.sb_csv, stats))
    reflector_rows, reflector_stats = collect(args.archive_root, args.min_finishers)
    for key, value in reflector_stats.items():
        stats[key] += value
    rows.extend(reflector_rows)
    known, existing_count = existing_keys(args.results_csv)
    fresh = [r for r in rows
             if (r["Date"], str(r["Race"]), normalize_horse_name(r["Horse"])) not in known]

    seen = set()
    deduped = []
    for r in fresh:
        key = (r["Date"], str(r["Race"]), normalize_horse_name(r["Horse"]))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)

    dates = sorted({r["Date"] for r in deduped})
    print(f"meetings with a reflector : {stats['meetings_seen']}")
    print(f"meetings without one      : {stats['meetings_without_reflector']}")
    print(f"races ingested            : {stats['races_ingested']}")
    print(f"races skipped (too thin)  : {stats['races_too_thin']}")
    print(f"existing CSV rows         : {existing_count}")
    print(f"new rows to add           : {len(deduped)}")
    if dates:
        print(f"new date range            : {dates[0]} .. {dates[-1]} ({len(dates)} race days)")

    if not args.apply:
        print("\ndry run — nothing written. re-run with --apply")
        return 0
    if not deduped:
        print("\nnothing to add.")
        return 0

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = args.results_csv.with_suffix(f".csv.bak_{stamp}")
    if args.results_csv.exists():
        shutil.copy2(args.results_csv, backup)
        print(f"\nbackup: {backup.name}")

    existing_rows = []
    if args.results_csv.exists():
        with args.results_csv.open(encoding="utf-8-sig", newline="") as handle:
            existing_rows = list(csv.DictReader(handle))

    tmp = args.results_csv.with_suffix(".csv.tmp")
    with tmp.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in existing_rows:
            writer.writerow({k: row.get(k, "") for k in FIELDNAMES})
        for row in deduped:
            writer.writerow(row)
    tmp.replace(args.results_csv)
    print(f"wrote {len(existing_rows) + len(deduped)} rows to {args.results_csv.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
