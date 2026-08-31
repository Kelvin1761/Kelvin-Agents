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
import json
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


def runner_draw(meeting: Path) -> dict:
    """{(race_no, horse_slug): {Barrier, Weight}} 由場次自己嘅 Logic.json 攞。

    2026-08-31：`Barrier` 同 `Weight` 本來喺下面 reflector 路徑硬寫空字串，
    同 2026-08-26 記錄嘅 `Time` 缺陷一模一樣，但當時冇一齊掃。實測後果：

        2025-08 → 2026-06  檔位覆蓋 99–100%（舊行由 aggregator 寫）
        2026-07            52.7%
        2026-08            **0.0%**（9,809 行零檔位）

    而 `au_draw_bias_calculator` 靠呢個 CSV 建逐場地／逐距離檔位偏差表，即係
    `pace_map_score` 唯一嘅經驗基礎。個表最後成功建於 2026-08-22；今日重建
    會塌到只剩 backfill CSV 嘅 703 行。

    同 `Time` 唔同，檔位係揾得返嘅 —— 場次資料夾自己嘅 Logic.json 就有。呢度帶
    出去嘅係**原始抽籤**；轉成實際出閘檔位喺 `_densify_by_race` 做（分母一定要用
    「實際有賽果嗰批」，唔係 Logic 名單）。
    """
    out = {}
    for path in sorted(meeting.glob("Race_*_Logic.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        horses = data.get("horses")
        if not isinstance(horses, dict):
            continue
        # ⚠️ **唔喺呢度**做密集排位。`normalise_field_barriers` 係喺 Logic 嘅出賽
        # 名單上面 densify，而 42.5% 場次嘅 Logic 名單仍然含已退出嘅幽靈馬 ——
        # 實測咁樣只對 75.1%（`max(名次) == max(檔位)` 75.9%，而 aggregator 寫嘅
        # 舊行係 97.8%）。真值要用「呢場實際有賽果嗰批」做分母，見
        # `_densify_by_race`。呢度只帶原始抽籤出去。
        race_analysis = data.get("race_analysis") or {}
        distance = re.sub(r"[^0-9]", "", str(race_analysis.get("distance") or "").split(".")[0])
        condition = str(race_analysis.get("going") or "").strip()
        race_no = str(race_analysis.get("race_number") or "").strip()
        if not race_no:
            match = re.search(r"Race_(\d+)_Logic", path.name)
            race_no = match.group(1) if match else ""
        for horse in horses.values():
            if not isinstance(horse, dict):
                continue
            key = (race_no, normalize_horse_name(horse.get("horse_name")))
            barrier, weight = horse.get("barrier"), horse.get("weight")
            out[key] = {
                "Barrier": "" if barrier in (None, "") else str(int(float(barrier))),
                "Weight": "" if weight in (None, "") else str(weight),
                # 距離用純數字 —— 同 `au_draw_bias_calculator.canonical_distance`
                # 同 `_pace_map_score` 嘅查表寫法一致。
                "Distance": distance,
                "Condition": condition,
            }
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
            draw = runner_draw(meeting)
            for race_no, finishers in races.items():
                positions = [f["pos"] for f in finishers]
                if len(finishers) < min_finishers or 1 not in positions:
                    stats["races_too_thin"] += 1
                    continue
                stats["races_ingested"] += 1
                distance, condition = context.get(race_no, ("", ""))
                for f in finishers:
                    slug = normalize_horse_name(f["horse"])
                    extra = details.get((race_no, slug), {})
                    drawn = draw.get((race_no, slug), {})
                    rows.append({
                        "Date": date, "Track": venue, "Race": race_no,
                        "Distance": distance, "Condition": condition,
                        "Pos": f["pos"], "Horse": f["horse"],
                        # 由 Logic.json 攞（見 `runner_draw`）。攞唔到就留空 ——
                        # 空白比一個假檔位好，因為偏差表會照食。
                        "Barrier": drawn.get("Barrier", ""),
                        "Weight": drawn.get("Weight", ""),
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


FILLABLE_COLUMNS = ("Barrier", "Weight", "Distance", "Condition")


def _meeting_date(meeting: Path) -> str:
    """場次資料夾前綴嘅日期。reflector 缺失時嘅 fallback。"""
    match = re.match(r"(\d{4}-\d{2}-\d{2})", meeting.name)
    return match.group(1) if match else ""


def build_fill_map(archive_root: Path) -> dict:
    """{(Date, Race, horse_slug): {Barrier, Weight}} 橫跨所有場次資料夾。"""
    out = {}
    for meeting in sorted(archive_root.rglob("*")):
        if not meeting.is_dir() or not any(meeting.glob("Race_*_Logic.json")):
            continue
        date = _meeting_date(meeting)
        if not date:
            continue
        for (race_no, slug), values in runner_draw(meeting).items():
            if race_no and slug:
                out.setdefault((date, str(race_no), slug), values)
    return out


def _densify_by_race(rows: list[dict]) -> tuple[int, int]:
    """把 `Barrier` 由原始抽籤改成**實際出閘檔位**，分母 = 呢場實際有賽果嘅馬。

    2026-09-01：第一版喺 `normalise_field_barriers`（Logic 名單）度 densify，
    實測 `max(名次) == max(檔位)` 只有 **75.9%**，而 aggregator 寫嘅舊行係
    **97.8%** —— 因為 42.5% 場次嘅 Logic 名單仍然含已退出嘅幽靈馬。

    CSV 一場嘅行**就係**出賽馬（佢哋有名次），所以呢度才係正確嘅分母。

    ⚠️ 只喺全場齊行嘅時候做（`行數 >= max(名次)`）。reflector 路徑會剪短賽果，
    喺一個被剪短嘅集合上 densify 會砌出一個**更錯**嘅檔位。
    """
    by_race: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        key = ((row.get("Date") or "").strip(), (row.get("Track") or "").strip(),
               str(row.get("Race") or "").strip())
        by_race[key].append(row)
    changed = skipped = 0
    for group in by_race.values():
        vals = []
        for row in group:
            text = str(row.get("Barrier") or "").strip()
            try:
                vals.append((row, int(float(text))))
            except ValueError:
                vals = []
                break
        if len(vals) != len(group) or len({v for _, v in vals}) != len(vals):
            skipped += len(group)
            continue
        positions = []
        for row in group:
            try:
                positions.append(int(float(str(row.get("Pos") or "").strip())))
            except ValueError:
                pass
        if positions and len(group) < max(positions):
            skipped += len(group)   # 賽果被剪短 —— 分母唔可信
            continue
        for rank, (row, _) in enumerate(sorted(vals, key=lambda t: t[1]), start=1):
            if str(row.get("Barrier") or "").strip() != str(rank):
                row["Barrier"] = str(rank)
                changed += 1
    return changed, skipped


def fill_missing(results_csv: Path, archive_root: Path, apply: bool) -> int:
    """填返現有行嘅空白 `Barrier` / `Weight`，**唔覆蓋**任何已有值。

    點解要一個獨立模式：上面個合併係 add-only（`fresh` 只收 key 未見過嘅行），
    所以已經寫入去嘅空白格永遠唔會自己好返。2026-08-31 實測缺口：

        2026-07 檔位覆蓋 52.7% ・ 2026-08 **0.0%**（9,809 行）

    只填空格係故意嘅 —— 舊行（2025-08 → 2026-06）由 `au_statistics_aggregator`
    寫入，覆蓋 99–100%，冇理由用 Logic.json 去覆蓋一個已經對嘅值。
    """
    if not results_csv.exists():
        print(f"❌ {results_csv} 唔存在")
        return 1
    with results_csv.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    fill = build_fill_map(archive_root)
    print(f"Logic.json 覆蓋      : {len(fill)} 個 (日期,場次,馬) 記錄")
    print(f"CSV 行               : {len(rows)}")
    filled = defaultdict(int)
    blank_no_source = defaultdict(int)
    renormalised = defaultdict(int)
    # 保值格式正規化。`Barrier` / `Distance` 現有值係浮點寫法（`"2.0"` / `"1200.0"`），
    # 新填嘅係純數字 —— 同一欄兩個慣例，正正係本檔上面警告過嘅嘢：
    # 「A second convention in the same column silently breaks whichever consumer
    # parses the string rather than the number.」`"2.0".isdigit()` 係 False 已經
    # 令檔位偏差表讀到 0 行，而 `"1200.0"` 令逐距離 cell 引擎永遠查唔到。
    # 呢一步唔改任何數值，只統一寫法。
    for row in rows:
        for column in ("Barrier", "Distance"):
            text = str(row.get(column) or "").strip()
            if not text:
                continue
            try:
                number = float(text)
            except ValueError:
                continue
            if number != int(number):
                continue
            canonical = str(int(number))
            if canonical != text:
                row[column] = canonical
                renormalised[column] += 1
    for row in rows:
        key = (
            (row.get("Date") or "").strip(),
            str(row.get("Race") or "").strip(),
            normalize_horse_name(row.get("Horse")),
        )
        source = fill.get(key)
        for column in FILLABLE_COLUMNS:
            if str(row.get(column) or "").strip():
                continue
            value = (source or {}).get(column, "")
            if value:
                row[column] = value
                filled[column] += 1
            else:
                blank_no_source[column] += 1
    dens_changed, dens_skipped = _densify_by_race(rows)
    for column in FILLABLE_COLUMNS:
        print(f"{column:<20} 填返 {filled[column]:>6}｜仍然空白 {blank_no_source[column]:>6}")
    print(f"{'Barrier':<20} 實際出閘檔位修正 {dens_changed:>6}｜跳過（剪短／缺值）{dens_skipped:>6}")
    for column, count in sorted(renormalised.items()):
        print(f"{column:<20} 格式統一 {count:>6}（浮點寫法 → 純數字，數值不變）")
    if not apply:
        print("\ndry run — nothing written. re-run with --apply")
        return 0
    if not sum(filled.values()) and not sum(renormalised.values()) and not dens_changed:
        print("\nnothing to fill.")
        return 0
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = results_csv.with_suffix(f".csv.bak_{stamp}")
    shutil.copy2(results_csv, backup)
    print(f"\nbackup: {backup.name}")
    with results_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in FIELDNAMES})
    print(f"✅ 寫入 {results_csv.name}")
    return 0


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
    ap.add_argument("--fill-missing", action="store_true",
                    help="填返現有行嘅空白 Barrier / Weight（由 Logic.json），"
                         "唔加新行、唔覆蓋任何已有值")
    args = ap.parse_args()

    if args.fill_missing:
        return fill_missing(args.results_csv, args.archive_root, args.apply)

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
