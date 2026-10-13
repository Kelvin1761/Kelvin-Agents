#!/usr/bin/env python3
"""逐週欄位健康時間序列 —— 捉「慢慢死」嘅欄位。

點解要有呢個
------------
`data_contract.py` 係**發佈閘**：每個場次同一份 calibrate 好嘅基準比較，只攔死
欄位。佢捉唔到三類嘢：

1. **漸變**。佢唔留紀錄，所以「上個月 5% 冇證據、今個月 30%」睇唔到。
2. **evidence state**。engine 自己講明 exact 60 唔係可靠嘅完整性測試
   （`engine_core.py` `feature_evidence_state`）。一個 leaf 可以全部 fallback
   但分數唔係 60，`neutral_rate` 照樣靚。
3. **結果 CSV**。佢只讀 `Race_X_Logic.json`。`AU_Historical_Raw_Race_Results.csv`
   嘅 `Time` 由 99% 跌到 0%、之後 `Barrier`／`Weight` 又逐條死，全部係人手
   發現。2026-10-13 第一次跑呢個工具，即刻量到 live CSV 嘅 `Margin` 由
   2026-W35 起 0%（之前約 50%）。EXP-20261012-01 嘅修補工具只喺研究副本補過；
   `au_healthcheck.CORPUS_COLUMNS` 唔包 `Margin`／`Time`，所以一直冇警報。

所以呢度只做兩件事：

    --record   按 ISO 週將每個欄位嘅健康度寫入 <資料根>/<平台>_Field_Health.jsonl
               （同一個 (week, source, field) 重跑會覆蓋，唔會重複）
    --trend    將目標週同之前 4 週嘅中位數比較，出 degrading／dead／missing

**只出警告，永遠唔攔 deploy。** 攔 deploy 係 `data_contract --gate` 嘅工作。

Usage
-----
    python field_health.py --platform au --record                    # 重錄最近 8 週
    python field_health.py --platform au --record --since 2026-08-01 # backfill
    python field_health.py --platform au --trend
    python field_health.py --platform au --trend --week 2026-W35     # 回溯某一週
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import data_contract as dc  # noqa: E402

SOURCES = ("leaf", "evidence", "provenance", "results_csv")

# 每週最少樣本先判。一個 5 場鄉郊場次唔係一個星期。
MIN_HORSES = 200
MIN_ROWS = 200
BASELINE_WEEKS = 4
MIN_BASELINE_WEEKS = 2
DEFAULT_RECORD_WEEKS = 8

# 門檻沿用 data_contract 嘅尺度，唔另外發明。
NEUTRAL_RISE = dc.NEUTRAL_SLACK            # 「冇證據」比例升 25pp
SPREAD_FLOOR_RATIO = dc.SPREAD_FLOOR_RATIO  # 散開度跌剩 40%
WEAK_RISE = dc.NEUTRAL_SLACK               # fallback／missing 比例升 25pp
PROVENANCE_RISE = dc.NEUTRAL_SLACK         # 單一來源比例升 25pp
FILL_DROP = 0.20                           # 結果 CSV 非空率跌 20pp
DEAD_HEALTHY_FLOOR = 0.50                  # 曾經 ≥50% 有值先叫得「死」

WEAK_STATES = frozenset({"fallback", "missing"})
EMPTY_CELLS = frozenset({"", "—", "-", "nan", "None"})

# AU 結果 CSV 嘅欄位（au_results_ingest.py COLUMNS）。Date／Track／Race 係 key，唔量。
RESULTS_COLUMNS = ("Distance", "Condition", "Pos", "Horse", "Barrier", "Weight",
                   "Jockey", "Trainer", "Margin", "SP", "Time")
LEDGER_NAMES = {"au": "AU_Field_Health.jsonl", "hkjc": "HKJC_Field_Health.jsonl"}


def iso_week(date_text: str) -> str | None:
    try:
        year, week, _ = dt.date.fromisoformat(date_text[:10]).isocalendar()
    except (TypeError, ValueError):
        return None
    return f"{year}-W{week:02d}"


def week_start(week: str) -> str:
    year, num = week.split("-W")
    return dt.date.fromisocalendar(int(year), int(num), 1).isoformat()


def ledger_path(platform: str, root: Path) -> Path:
    return Path(root) / LEDGER_NAMES[platform]


# ── 量度 ──────────────────────────────────────────────────────────────────────

def _group_by_week(paths) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for path in paths:
        match = dc.MEETING_DATE.search(Path(path).parent.name)
        week = iso_week(match.group(1)) if match else None
        if week:
            groups[week].append(path)
    return groups


def _evidence_and_provenance(paths) -> tuple[dict, dict, int]:
    """逐 leaf 數 fallback／missing 同 score_provenance 分佈。"""
    weak: dict[str, Counter] = defaultdict(Counter)
    provenance: dict[str, Counter] = defaultdict(Counter)
    races = 0
    for path in paths:
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception:
            continue  # data_contract.observe 已經會報 unreadable
        horses = [h.get("python_auto") or {} for h in (data.get("horses") or {}).values()]
        horses = [pa for pa in horses if pa.get("feature_scores")]
        if len(horses) < 3:
            continue
        races += 1
        for pa in horses:
            for leaf, state in (pa.get("feature_evidence_state") or {}).items():
                weak[leaf]["n"] += 1
                if state in WEAK_STATES:
                    weak[leaf]["weak"] += 1
            for leaf, source in (pa.get("score_provenance") or {}).items():
                provenance[leaf][str(source)] += 1
    return weak, provenance, races


def measure_logic_week(week: str, paths, platform: str) -> list[dict]:
    rows = []
    fields, races, _horses, _unreadable = dc.observe(paths, platform)
    for name, obs in sorted(fields.items()):
        summary = obs.summarise()
        rows.append({
            "week": week, "source": "leaf", "field": name,
            "n": summary["horses"], "races": obs.present_races,
            "neutral_rate": summary["neutral_rate"],
            "spread": summary["mean_within_race_spread"],
            "min": summary["min"], "max": summary["max"],
        })
    weak, provenance, ev_races = _evidence_and_provenance(paths)
    for leaf, counts in sorted(weak.items()):
        rows.append({
            "week": week, "source": "evidence", "field": leaf,
            "n": counts["n"], "races": ev_races,
            "weak_rate": round(counts["weak"] / counts["n"], 4) if counts["n"] else None,
        })
    for leaf, counts in sorted(provenance.items()):
        total = sum(counts.values())
        top_value, top_count = counts.most_common(1)[0]
        rows.append({
            "week": week, "source": "provenance", "field": leaf,
            "n": total, "races": ev_races,
            "top_value": top_value,
            "top_share": round(top_count / total, 4),
            "distinct": len(counts),
        })
    return rows


def results_csv_path(platform: str, root: Path | None = None) -> Path | None:
    if platform != "au":
        return None
    sys.path.insert(0, str(dc.REPO_ROOT))
    try:
        import wongchoi_paths
        return Path(wongchoi_paths.au_historical_results_csv(root))
    except Exception:
        return None


def measure_results_csv(csv_path: Path, since: str | None = None) -> list[dict]:
    if not csv_path or not Path(csv_path).exists():
        return []
    counts: dict[str, Counter] = defaultdict(Counter)
    with open(csv_path, encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            date_text = (row.get("Date") or "").strip()
            if since and date_text < since:
                continue
            week = iso_week(date_text)
            if not week:
                continue
            counts[week]["_rows"] += 1
            for column in RESULTS_COLUMNS:
                if column in row and str(row.get(column) or "").strip() not in EMPTY_CELLS:
                    counts[week][column] += 1
    rows = []
    for week, counter in sorted(counts.items()):
        n = counter["_rows"]
        for column in RESULTS_COLUMNS:
            rows.append({
                "week": week, "source": "results_csv", "field": column,
                "n": n, "fill_rate": round(counter[column] / n, 4) if n else None,
            })
    return rows


def record(platform: str, root: Path, since: str | None, out: Path,
           csv_path: Path | None = None) -> list[dict]:
    """量度 `since` 之後每一週，覆蓋 ledger 入面同一個 key 嘅舊紀錄。"""
    paths = dc.logic_files(root, None, since)
    rows: list[dict] = []
    for week, week_paths in sorted(_group_by_week(paths).items()):
        rows.extend(measure_logic_week(week, week_paths, platform))
    if platform == "au":
        rows.extend(measure_results_csv(csv_path or results_csv_path(platform, root), since))
    stamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    for row in rows:
        row["recorded_at"] = stamp
    write_ledger(out, rows)
    return rows


# ── Ledger ────────────────────────────────────────────────────────────────────

def _key(row: dict) -> tuple:
    return (row.get("week"), row.get("source"), row.get("field"))


def read_ledger(path: Path) -> list[dict]:
    if not Path(path).exists():
        return []
    rows = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def write_ledger(path: Path, new_rows: list[dict]) -> None:
    """同一個 (week, source, field) 只留最新一行。原子寫入。"""
    merged = {_key(row): row for row in read_ledger(path)}
    for row in new_rows:
        merged[_key(row)] = row
    ordered = sorted(merged.values(), key=lambda r: (r["week"], r["source"], r["field"]))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        for row in ordered:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    os.replace(tmp, path)


# ── 趨勢判斷 ──────────────────────────────────────────────────────────────────

def _enough(row: dict) -> bool:
    minimum = MIN_ROWS if row.get("source") == "results_csv" else MIN_HORSES
    return (row.get("n") or 0) >= minimum


def _median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def _judge(source: str, current: dict, history: list[dict]) -> tuple[str, str] | None:
    """回傳 (status, detail) 或 None。history 由舊到新，已經過濾樣本量。"""
    baseline = history[-BASELINE_WEEKS:]
    if source == "results_csv":
        now = current.get("fill_rate")
        med = _median(r.get("fill_rate") for r in baseline)
        best = max((r.get("fill_rate") or 0.0) for r in history)
        if now is None:
            return None
        if now <= 0.01 and best >= DEAD_HEALTHY_FLOOR:
            return "dead", f"非空率 {now:.0%}，以前最高 {best:.0%}"
        if med is not None and med - now >= FILL_DROP:
            return "degrading", f"非空率 {now:.0%}，前 {len(baseline)} 週中位數 {med:.0%}"
        return None
    if source == "leaf":
        now = current.get("neutral_rate")
        med = _median(r.get("neutral_rate") for r in baseline)
        best = min((r.get("neutral_rate") if r.get("neutral_rate") is not None else 1.0) for r in history)
        spread = current.get("spread") or 0.0
        med_spread = _median(r.get("spread") for r in baseline) or 0.0
        if now is not None and now >= dc.DEAD_NEUTRAL_RATE and best <= dc.DEAD_BASELINE_MAX:
            return "dead", f"{now:.0%} 匹馬停喺中性點，以前最低 {best:.0%}"
        if med_spread > 1.0 and spread <= dc.DEAD_SPREAD:
            return "dead", f"場內散開度 {spread:.2f}（前 {len(baseline)} 週中位數 {med_spread:.2f}）—— 變咗常數"
        if now is not None and med is not None and now - med >= NEUTRAL_RISE:
            return "degrading", f"中性比例 {now:.0%}，前 {len(baseline)} 週中位數 {med:.0%}"
        if med_spread > 1.0 and spread < med_spread * SPREAD_FLOOR_RATIO:
            return "degrading", f"場內散開度 {spread:.2f}，前 {len(baseline)} 週中位數 {med_spread:.2f}"
        return None
    if source == "evidence":
        now = current.get("weak_rate")
        med = _median(r.get("weak_rate") for r in baseline)
        best = min((r.get("weak_rate") if r.get("weak_rate") is not None else 1.0) for r in history)
        if now is None:
            return None
        if now >= dc.DEAD_NEUTRAL_RATE and best <= dc.DEAD_BASELINE_MAX:
            return "dead", f"{now:.0%} 匹馬係 fallback／missing，以前最低 {best:.0%}"
        if med is not None and now - med >= WEAK_RISE:
            return "degrading", f"fallback／missing {now:.0%}，前 {len(baseline)} 週中位數 {med:.0%}"
        return None
    if source == "provenance":
        now = current.get("top_share")
        med = _median(r.get("top_share") for r in baseline)
        if now is not None and med is not None and now - med >= PROVENANCE_RISE:
            return "degrading", (f"「{current.get('top_value')}」佔 {now:.0%}，"
                                 f"前 {len(baseline)} 週中位數 {med:.0%} —— 來源收窄")
        return None
    return None


def latest_week(rows: list[dict], today: dt.date | None = None) -> str | None:
    """最近一個**完整**週。今個星期未完，CSV 樣本未夠，判咗只會漏報。"""
    current = iso_week((today or dt.date.today()).isoformat())
    weeks = sorted({r["week"] for r in rows if _enough(r) and r["week"] < current})
    return weeks[-1] if weeks else None


def _dead_since(source: str, items: list[dict], week: str) -> str:
    """同一個 dead 狀態由邊週開始連續至今。"""
    usable = [r for r in items if _enough(r) and r["week"] <= week]
    since = week
    for index in range(len(usable) - 1, -1, -1):
        history = usable[:index]
        if len(history) < MIN_BASELINE_WEEKS:
            break
        verdict = _judge(source, usable[index], history)
        if not verdict or verdict[0] != "dead":
            break
        since = usable[index]["week"]
    return since


def trend(rows: list[dict], week: str | None = None,
          today: dt.date | None = None) -> tuple[str | None, list[dict]]:
    """目標週每條 series 同之前幾週比較。回傳 (week, findings)。"""
    week = week or latest_week(rows, today)
    if not week:
        return None, []
    series: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        series[(row["source"], row["field"])].append(row)
    findings = []
    for (source, field), items in sorted(series.items()):
        items = sorted(items, key=lambda r: r["week"])
        history = [r for r in items if r["week"] < week and _enough(r)]
        if len(history) < MIN_BASELINE_WEEKS:
            continue
        current = next((r for r in items if r["week"] == week), None)
        if current is None:
            # 上一週仲有、今週冇 —— 欄位消失。只限 Logic 來源（CSV 欄位每週都會寫）。
            if source != "results_csv" and history[-1]["week"] == _previous_week(week):
                week_has_data = any(r["week"] == week and _enough(r) and r["source"] == source
                                    for r in rows)
                if week_has_data:
                    findings.append({"week": week, "source": source, "field": field,
                                     "status": "missing", "detail": "上週仲有，今週完全消失"})
            continue
        if not _enough(current):
            continue
        verdict = _judge(source, current, history)
        if verdict:
            status, detail = verdict
            finding = {"week": week, "source": source, "field": field,
                       "status": status, "detail": detail, "n": current.get("n")}
            if status == "dead":
                finding["since"] = _dead_since(source, items, week)
            findings.append(finding)
    order = {"dead": 0, "missing": 1, "degrading": 2}
    findings.sort(key=lambda f: (order.get(f["status"], 9), f["source"], f["field"]))
    return week, findings


def _previous_week(week: str) -> str:
    start = dt.date.fromisoformat(week_start(week)) - dt.timedelta(days=7)
    year, num, _ = start.isocalendar()
    return f"{year}-W{num:02d}"


SOURCE_LABELS = {"leaf": "leaf 分數", "evidence": "證據狀態",
                 "provenance": "分數來源", "results_csv": "結果 CSV"}
STATUS_ICONS = {"dead": "💀", "missing": "❓", "degrading": "📉"}


def format_findings(platform: str, week: str | None, findings: list[dict], limit: int | None = None) -> str:
    title = f"欄位健康趨勢 — {platform.upper()} {week or '(冇數據)'}"
    if not week:
        return f"{title}\n未有足夠紀錄，先跑 --record"
    if not findings:
        return f"{title}\n✅ 冇欄位變差"
    lines = [title]
    shown = findings[:limit] if limit else findings
    for f in shown:
        since = f.get("since")
        tail = f"（{since} 起）" if since and since != f["week"] else ("（今週新出現）" if since else "")
        lines.append(f"{STATUS_ICONS.get(f['status'], '•')} [{SOURCE_LABELS.get(f['source'], f['source'])}] "
                     f"{f['field']}: {f['detail']}{tail}")
    if limit and len(findings) > limit:
        lines.append(f"…另外 {len(findings) - limit} 項（跑 field_health.py --trend 睇全部）")
    lines.append("（只係警告。如果呢週改過引擎，leaf／來源變化可能係設計使然。）")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--platform", required=True, choices=sorted(dc.PLATFORMS))
    parser.add_argument("--record", action="store_true", help="量度並寫入 ledger")
    parser.add_argument("--trend", action="store_true", help="同之前幾週比較")
    parser.add_argument("--since", help="--record 由呢日開始（YYYY-MM-DD）；預設最近 8 週")
    parser.add_argument("--week", help="--trend 目標週，例如 2026-W35；預設最新一週")
    parser.add_argument("--ledger", type=Path, help="覆寫 ledger 路徑（測試用）")
    parser.add_argument("--json", action="store_true", help="--trend 輸出 JSON")
    args = parser.parse_args(argv)
    if not (args.record or args.trend):
        parser.error("要揀 --record 或者 --trend")

    root = dc.resolve_root(args.platform)
    if root is None and (args.record or not args.ledger):
        print("搵唔到資料根目錄（wongchoi_paths）", file=sys.stderr)
        return 2
    out = args.ledger or ledger_path(args.platform, root)

    if args.record:
        since = args.since or (dt.date.today() - dt.timedelta(weeks=DEFAULT_RECORD_WEEKS)).isoformat()
        rows = record(args.platform, root, since, out)
        weeks = sorted({r["week"] for r in rows})
        span = f"{weeks[0]} → {weeks[-1]}" if weeks else "冇"
        print(f"已記錄 {len(rows)} 行（{span}）→ {out}")

    if args.trend:
        week, findings = trend(read_ledger(out), args.week)
        if args.json:
            print(json.dumps({"week": week, "findings": findings}, ensure_ascii=False, indent=2))
        else:
            print(format_findings(args.platform, week, findings))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
