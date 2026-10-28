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

# 已知死咗、而且講得出點解嘅欄位。仍然照報，但狀態係 `known`、縮成一行，唔再
# 用 💀 —— 一個每週都嗌同一句嘅警報好快冇人睇，咁真嘅新問題就會被淹沒。
# 修好咗就要由呢度剷走，否則佢復活亦睇唔到。
ACKNOWLEDGED = {
    ("results_csv", "Time"): "冇逐駒時間來源：Sportsbet 頁面只有頭馬時間（WinningTime），"
                             "au_results_ingest 刻意寫空（EXP-20261012-01 限制）",
}

WEAK_STATES = frozenset({"fallback", "missing"})
EMPTY_CELLS = frozenset({"", "—", "-", "nan", "None"})

# AU 結果 CSV 嘅欄位（au_results_ingest.py COLUMNS）。Date／Track／Race 係 key，唔量。
RESULTS_COLUMNS = ("Distance", "Condition", "Pos", "Horse", "Barrier", "Weight",
                   "Jockey", "Trainer", "Margin", "SP", "Time")
LEDGER_NAMES = {"au": "AU_Field_Health.jsonl", "hkjc": "HKJC_Field_Health.jsonl"}

# 騎練訊號加減項（HKJC `python_auto.trainer_signal_detail.adjustments`）逐週出現率。
# 2026-10-07 → 10-18 騎師同程／練馬師同程每匹馬都消失（統計寫 `1200.0`、引擎查
# `1200`），leaf 分佈只係細幅移位，data_contract 同上面四個來源全部睇唔到
# （EXP-20261018-02/04）。只量平時出現率高嘅項；「除去配備」本身罕見，唔量。
ADJUSTMENT_FACTORS = {"hkjc": ("人馬歷史", "騎練組合", "騎師同程", "練馬師同程", "換騎")}
ADJUSTMENT_MIN_HORSES = 100       # 一個香港賽日 ~100–145 匹；單日週都要判到
ADJUSTMENT_HEALTHY_FLOOR = 0.30   # 曾經 ≥30% 匹馬有呢項先叫得「死」


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


def _adjustment_presence(paths, factors) -> tuple[Counter, int, int]:
    """每個加減項有幾多匹馬帶住（有記錄就算，±0 都計）。"""
    present: Counter = Counter()
    horses = races = 0
    for path in paths:
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception:
            continue
        autos = [h.get("python_auto") or {} for h in (data.get("horses") or {}).values() if isinstance(h, dict)]
        autos = [pa for pa in autos if pa.get("feature_scores")]
        if not autos:
            continue
        races += 1
        for pa in autos:
            horses += 1
            seen = {a.get("factor") for a in ((pa.get("trainer_signal_detail") or {}).get("adjustments") or [])
                    if isinstance(a, dict)}
            for factor in factors:
                if factor in seen:
                    present[factor] += 1
    return present, horses, races


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
    factors = ADJUSTMENT_FACTORS.get(platform, ())
    if factors:
        present, horses, adj_races = _adjustment_presence(paths, factors)
        for factor in factors:  # 0 次都要寫一行，唔係就變咗「消失」而唔係「死」
            rows.append({
                "week": week, "source": "adjustment", "field": factor,
                "n": horses, "races": adj_races,
                "fill_rate": round(present[factor] / horses, 4) if horses else None,
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
    if row.get("source") == "adjustment":
        return (row.get("n") or 0) >= ADJUSTMENT_MIN_HORSES
    minimum = MIN_ROWS if row.get("source") == "results_csv" else MIN_HORSES
    return (row.get("n") or 0) >= minimum


def _median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def _judge(source: str, current: dict, history: list[dict]) -> tuple[str, str] | None:
    """回傳 (status, detail) 或 None。history 由舊到新，已經過濾樣本量。"""
    baseline = history[-BASELINE_WEEKS:]
    if source in ("results_csv", "adjustment"):
        now = current.get("fill_rate")
        med = _median(r.get("fill_rate") for r in baseline)
        best = max((r.get("fill_rate") or 0.0) for r in history)
        floor = ADJUSTMENT_HEALTHY_FLOOR if source == "adjustment" else DEAD_HEALTHY_FLOOR
        if now is None:
            return None
        if now <= 0.01 and best >= floor:
            word = "出現率" if source == "adjustment" else "非空率"
            return "dead", f"{word} {now:.0%}，以前最高 {best:.0%}"
        if med is not None and med - now >= FILL_DROP:
            word = "出現率" if source == "adjustment" else "非空率"
            return "degrading", f"{word} {now:.0%}，前 {len(baseline)} 週中位數 {med:.0%}"
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
            provenance = next((r for r in series.get(("provenance", field), [])
                               if r["week"] == week), {})
            if source in {"leaf", "evidence"} and provenance.get("top_value") == "disabled_neutral":
                share = provenance.get("top_share")
                if share is not None:
                    detail += f"；其中 {share:.1%} 係引擎明確停用（disabled_neutral），唔等於抽取缺失"
            if source == "leaf":
                evidence = next((r for r in series.get(("evidence", field), [])
                                 if r["week"] == week), {})
                weak = evidence.get("weak_rate")
                if weak is not None:
                    detail += f"；同期證據 fallback／missing {weak:.1%}"
            finding = {"week": week, "source": source, "field": field,
                       "status": status, "detail": detail, "n": current.get("n")}
            if status == "dead":
                finding["since"] = _dead_since(source, items, week)
            reason = ACKNOWLEDGED.get((source, field))
            if reason and status == "dead":
                finding["status"] = "known"
                finding["detail"] = reason
            findings.append(finding)
    order = {"dead": 0, "missing": 1, "degrading": 2, "known": 3}
    findings.sort(key=lambda f: (order.get(f["status"], 9), f["source"], f["field"]))
    return week, findings


def _previous_week(week: str) -> str:
    start = dt.date.fromisoformat(week_start(week)) - dt.timedelta(days=7)
    year, num, _ = start.isocalendar()
    return f"{year}-W{num:02d}"


SOURCE_LABELS = {"leaf": "leaf 分數", "evidence": "證據狀態",
                 "provenance": "分數來源", "results_csv": "結果 CSV",
                 "adjustment": "騎練調整項"}
STATUS_ICONS = {"dead": "💀", "missing": "❓", "degrading": "📉", "known": "ℹ️"}


def known_line(known: list[dict]) -> str:
    """已知死欄縮成一行：「ℹ️ 已知死欄：結果 CSV Time（2026-W30 起）」。"""
    parts = [f"{SOURCE_LABELS.get(f['source'], f['source'])} {f['field']}"
             + (f"（{f['since']} 起）" if f.get("since") else "") for f in known]
    return f"{STATUS_ICONS['known']} 已知死欄：" + "、".join(parts)


def format_findings(platform: str, week: str | None, findings: list[dict], limit: int | None = None) -> str:
    title = f"欄位健康趨勢 — {platform.upper()} {week or '(冇數據)'}"
    if not week:
        return f"{title}\n未有足夠紀錄，先跑 --record"
    active = [f for f in findings if f["status"] != "known"]
    known = [f for f in findings if f["status"] == "known"]
    lines = [title]
    if not active:
        lines.append("✅ 冇欄位變差")
    shown = active[:limit] if limit else active
    for f in shown:
        since = f.get("since")
        tail = f"（{since} 起）" if since and since != f["week"] else ("（今週新出現）" if since else "")
        lines.append(f"{STATUS_ICONS.get(f['status'], '•')} [{SOURCE_LABELS.get(f['source'], f['source'])}] "
                     f"{f['field']}: {f['detail']}{tail}")
    if limit and len(active) > limit:
        lines.append(f"…另外 {len(active) - limit} 項（跑 field_health.py --trend 睇全部）")
    if known:
        lines.append(known_line(known))
    if active:
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
