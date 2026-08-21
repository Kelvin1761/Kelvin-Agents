#!/usr/bin/env python3
"""Field-level data contract for scored Wong Choi meetings.

WHY THIS EXISTS
---------------
Every expensive data bug this project has shipped had the same shape: a field
kept existing, the code kept running, no test failed — and the VALUES quietly
went empty, constant, or stale.  A unit test cannot see that.  It asserts on
inputs it supplies itself; it never looks at what the live scrapers produced.

    - Sportsbet form pages leaked the race being predicted (17.1% of runs)
    - Racenet generic slugs all silently returned race 1
    - Seven state calendars froze 11 days behind a permanent cache
    - `speedmaps=` was written to every call site with 0 rows of real data
    - AU results CSV ingestion stopped for a month with green tests

So this checks the OUTPUT of a real run against what the corpus historically
looked like:

    presence  - the field still exists                (catches renames/drops)
    neutral   - share of horses scored exactly 60.0   (catches "stopped filling")
    spread    - within-race standard deviation        (catches "went constant")
    range     - min/max stay plausible                (catches unit/parse flips)

`--calibrate` learns the baseline from the existing corpus, so the thresholds
are measured rather than guessed.  `--check` enforces it and exits non-zero.

Usage
-----
    python data_contract.py --platform au --calibrate          # refresh baseline
    python data_contract.py --platform au --meeting <dir>      # gate one meeting
    python data_contract.py --platform au --check              # gate recent corpus
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import re
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
BASELINE_DIR = Path(__file__).resolve().parent.parent / "resources"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from corpus_paths import logic_files as _corpus_logic_files  # noqa: E402

PLATFORMS = {
    "au": {
        "data_root_attr": "AU_RACING",
        "baseline": "au_data_contract.json",
        "engine": REPO_ROOT / ".agents/skills/au_racing/au_wong_choi_auto/scripts/au_racing_engine",
    },
    "hkjc": {
        "data_root_attr": "HK_RACING",
        "baseline": "hkjc_data_contract.json",
        "engine": REPO_ROOT / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts/hkjc_racing_engine",
    },
}

# Files whose contents decide what a feature score means.  A baseline learned
# under a different engine describes a model that no longer exists — the AU
# `weight_score` neutralisation (2026-07-24) alone moved that field from 0%
# neutral to 93% neutral, which reads exactly like a broken scraper if you
# compare across the change.  So the baseline carries the engine fingerprint and
# refuses to be trusted silently once the engine moves.
ENGINE_FILES = ("scoring.py", "matrix_mapper.py", "engine_core.py")


def engine_fingerprint(platform: str) -> str:
    digest = hashlib.sha256()
    engine_dir = PLATFORMS[platform]["engine"]
    for name in ENGINE_FILES:
        path = engine_dir / name
        if path.exists():
            digest.update(path.read_bytes())
    return digest.hexdigest()[:12]

# How far a live run may drift from the calibrated corpus before it is a defect.
# Deliberately loose: this gate exists to catch a field going DEAD, not to police
# normal meeting-to-meeting variation.  A tight gate that cries every Saturday
# gets switched off, and then it protects nothing.
NEUTRAL_SLACK = 0.25        # +25 percentage points of "no evidence" horses
SPREAD_FLOOR_RATIO = 0.40   # a field may lose 60% of its spread before we call it
RANGE_SLACK = 15.0          # points outside the historical min/max


@dataclass
class Violation:
    field_name: str
    check: str
    detail: str
    severity: str = "error"


@dataclass
class Observation:
    """What one field looked like across a set of scored races."""
    present_races: int = 0
    horses: int = 0
    neutral: int = 0
    spreads: list = field(default_factory=list)
    lo: float | None = None
    hi: float | None = None

    def summarise(self) -> dict:
        return {
            "horses": self.horses,
            "neutral_rate": round(self.neutral / self.horses, 4) if self.horses else None,
            "mean_within_race_spread": round(statistics.fmean(self.spreads), 4) if self.spreads else 0.0,
            "min": self.lo,
            "max": self.hi,
        }


def resolve_root(platform: str) -> Path | None:
    sys.path.insert(0, str(REPO_ROOT))
    try:
        import wongchoi_paths
    except Exception:
        return None
    return getattr(wongchoi_paths, PLATFORMS[platform]["data_root_attr"], None)


MEETING_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def logic_files(root: Path, limit: int | None = None, since: str | None = None) -> list[str]:
    # Must include `<root>/Archive/` — the daily schedule moves finished
    # meetings there, and 49.1% of scored races (including almost every clean
    # point-in-time one) live in it.  See corpus_paths for the measurement.
    paths = _corpus_logic_files(root)
    if since:
        kept = []
        for path in paths:
            match = MEETING_DATE.search(Path(path).parent.name)
            if match and match.group(1) >= since:
                kept.append(path)
        paths = kept
    return paths[:limit] if limit else paths


def observe(paths) -> tuple[dict, int, int, list]:
    """Collect per-field statistics from scored races."""
    fields: dict[str, Observation] = {}
    races = 0
    unreadable = []
    horses_total = 0

    for path in paths:
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception as exc:
            unreadable.append((path, f"{type(exc).__name__}: {exc}"))
            continue
        rows = [
            h.get("python_auto", {}).get("feature_scores") or {}
            for h in (data.get("horses") or {}).values()
        ]
        rows = [r for r in rows if r]
        if len(rows) < 3:
            continue
        races += 1
        horses_total += len(rows)
        keys = set().union(*(set(r) for r in rows))
        for key in keys:
            obs = fields.setdefault(key, Observation())
            obs.present_races += 1
            values = []
            for row in rows:
                try:
                    value = float(row[key])
                except (KeyError, TypeError, ValueError):
                    continue
                values.append(value)
                obs.horses += 1
                if abs(value - 60.0) < 1e-9:
                    obs.neutral += 1
            if len(values) > 1:
                obs.spreads.append(statistics.pstdev(values))
            if values:
                lo, hi = min(values), max(values)
                obs.lo = lo if obs.lo is None else min(obs.lo, lo)
                obs.hi = hi if obs.hi is None else max(obs.hi, hi)
    return fields, races, horses_total, unreadable


def calibrate(platform: str, paths, out_path: Path) -> dict:
    fields, races, horses, unreadable = observe(paths)
    meetings = sorted({Path(p).parent.name for p in paths})
    baseline = {
        "platform": platform,
        "engine_fingerprint": engine_fingerprint(platform),
        "calibrated_from": {
            "races": races,
            "horses": horses,
            "files": len(paths),
            "first_meeting": meetings[0] if meetings else None,
            "last_meeting": meetings[-1] if meetings else None,
        },
        "fields": {name: obs.summarise() for name, obs in sorted(fields.items())},
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(baseline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if unreadable:
        print(f"⚠️  {len(unreadable)} unreadable file(s); first: {unreadable[0][1]}", file=sys.stderr)
    return baseline


def check(baseline: dict, paths, platform: str) -> tuple[list, dict]:
    fields, races, horses, unreadable = observe(paths)
    violations: list[Violation] = []

    recorded = baseline.get("engine_fingerprint")
    current = engine_fingerprint(platform)
    if recorded and recorded != current:
        violations.append(Violation(
            "(baseline)", "stale-baseline",
            f"基準係喺引擎 {recorded} 之下建立，而家引擎係 {current} —— "
            "下面嘅比較唔可信，請重新 --calibrate",
            "warning",
        ))

    if not races:
        violations.append(Violation("(meeting)", "empty", "冇一場可以讀到嘅已評分賽事"))
        return violations, {"races": 0, "horses": 0}

    for path, err in unreadable:
        violations.append(Violation(Path(path).name, "unreadable", err))

    for name, expected in baseline.get("fields", {}).items():
        obs = fields.get(name)
        if obs is None or not obs.horses:
            violations.append(Violation(name, "presence", "欄位完全消失（改名？抽取失敗？）"))
            continue
        actual = obs.summarise()

        want_neutral = expected.get("neutral_rate")
        got_neutral = actual["neutral_rate"]
        if want_neutral is not None and got_neutral is not None:
            if got_neutral > want_neutral + NEUTRAL_SLACK:
                violations.append(Violation(
                    name, "neutral",
                    f"「冇證據」比例 {got_neutral:.1%}，基準 {want_neutral:.1%}"
                    f"（超出容忍 {NEUTRAL_SLACK:.0%}）",
                ))

        want_spread = expected.get("mean_within_race_spread") or 0.0
        got_spread = actual["mean_within_race_spread"]
        if want_spread > 1.0 and got_spread < want_spread * SPREAD_FLOOR_RATIO:
            violations.append(Violation(
                name, "spread",
                f"場內分數散開度 {got_spread:.2f}，基準 {want_spread:.2f} —— 個欄位變咗差唔多常數",
            ))

        for bound, actual_value, expected_value, comparator in (
            ("min", actual["min"], expected.get("min"), "below"),
            ("max", actual["max"], expected.get("max"), "above"),
        ):
            if actual_value is None or expected_value is None:
                continue
            if comparator == "below" and actual_value < expected_value - RANGE_SLACK:
                violations.append(Violation(
                    name, "range", f"最低 {actual_value:.1f} 遠低於歷史 {expected_value:.1f}", "warning"))
            if comparator == "above" and actual_value > expected_value + RANGE_SLACK:
                violations.append(Violation(
                    name, "range", f"最高 {actual_value:.1f} 遠高於歷史 {expected_value:.1f}", "warning"))

    new_fields = set(fields) - set(baseline.get("fields", {}))
    for name in sorted(new_fields):
        violations.append(Violation(name, "new-field", "新欄位，基準未涵蓋 —— 記得重新 --calibrate", "warning"))

    return violations, {"races": races, "horses": horses}


def report(violations, summary, label: str) -> int:
    errors = [v for v in violations if v.severity == "error"]
    warnings = [v for v in violations if v.severity == "warning"]
    print(f"\n數據合約檢查 — {label}")
    print(f"樣本：{summary['races']} 場 / {summary['horses']} 匹馬")
    if not violations:
        print("✅ 全部欄位符合基準\n")
        return 0
    for group, title in ((errors, "❌ 唔合格"), (warnings, "⚠️  留意")):
        if not group:
            continue
        print(f"\n{title}")
        for v in group:
            print(f"  [{v.check}] {v.field_name}: {v.detail}")
    print()
    return 1 if errors else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--platform", required=True, choices=sorted(PLATFORMS))
    parser.add_argument("--meeting", type=Path, help="Check one meeting folder.")
    parser.add_argument("--calibrate", action="store_true", help="Rewrite the baseline from the corpus.")
    parser.add_argument("--check", action="store_true", help="Check the most recent corpus races.")
    parser.add_argument("--limit", type=int, default=150, help="How many recent races to use.")
    parser.add_argument("--since", help="Only meetings on/after this date (YYYY-MM-DD).")
    args = parser.parse_args(argv)

    baseline_path = BASELINE_DIR / PLATFORMS[args.platform]["baseline"]

    # A check must compare against races the baseline actually describes.  The
    # corpus spans several model generations — mixing them in reads as a data
    # regression when the model simply changed (AU weight_score went from 0% to
    # 93% neutral by design on 2026-07-24).  So unless the caller says otherwise,
    # the check window starts where the calibration window started.
    since = args.since
    if since is None and not args.calibrate and baseline_path.exists():
        try:
            recorded = json.loads(baseline_path.read_text(encoding="utf-8"))
            first = (recorded.get("calibrated_from") or {}).get("first_meeting")
            match = MEETING_DATE.search(first or "")
            if match:
                since = match.group(1)
        except Exception:
            since = None

    if args.meeting:
        paths = sorted(glob.glob(str(args.meeting / "Race_*_Logic.json")))
        label = args.meeting.name
    else:
        root = resolve_root(args.platform)
        if root is None:
            print("搵唔到資料根目錄（wongchoi_paths）", file=sys.stderr)
            return 2
        paths = logic_files(root, args.limit, since)
        label = f"{args.platform.upper()} 最近 {len(paths)} 場"
        if since:
            label += f"（{since} 之後，同基準同一個窗口）"

    if not paths:
        print(f"冇搵到已評分賽事：{label}", file=sys.stderr)
        return 2

    if args.calibrate:
        baseline = calibrate(args.platform, paths, baseline_path)
        print(f"已由 {baseline['calibrated_from']['races']} 場 / "
              f"{baseline['calibrated_from']['horses']} 匹馬建立基準")
        print(f"引擎指紋 {baseline['engine_fingerprint']}　"
              f"場次 {baseline['calibrated_from']['first_meeting']} → "
              f"{baseline['calibrated_from']['last_meeting']}")
        print(f"寫入 {baseline_path}")
        return 0

    if not baseline_path.exists():
        print(f"未有基準檔：{baseline_path}\n先跑一次 --calibrate", file=sys.stderr)
        return 2
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    violations, summary = check(baseline, paths, args.platform)
    return report(violations, summary, label)


if __name__ == "__main__":
    raise SystemExit(main())
