#!/usr/bin/env python3
"""旺財統一 ROI 板 —— 所有旺財用同一個格式報 ROI。

點解要有：之前 AU、NBA、網球各自有一個 ROI 訊息，格式、單位、時間窗全部唔同
（網球一條訊息印紙上盤、近 14 日、實盤、8 個市場、Brier、策略閘），Kelvin 同
Heison 冇辦法一眼比較。Kelvin 2026-11-05 定咗標準：

  * 每個旺財只報四樣嘢：落咗幾多注、中幾多注、ROI（單位）、ROI%。
  * 兩個時間窗：最近一次結算嗰日 + 累計。
  * 任何一個旺財結算完，就發成塊板（標明邊個啱啱更新），其他旺財照列。
  * 每朝另外發一條總結（`--summary`，由 launchd 叫）。
  * HKJC 暫時唔計 —— 佢未有落注定義。

做法：每個旺財結算之後將自己嘅數字寫入一個共用 ledger
（`<WongChoiControl>/roi_board.json`），再由 `render()` 讀 ledger 出訊息。
各旺財用返自己一直用開嘅來源（AU `au_betting`、NBA dashboard tracking、
網球正式推薦紙上盤），所以呢度唔會計出一個同 dashboard 唔同嘅數。

⚠️ ROI 訊息係內容，發俾 Kelvin + Heison（`audience="content"`）。
⚠️ 寫 ledger／發訊息失敗都唔可以令結算失敗 —— 呼叫者要自己 try/except。
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

try:  # pragma: no cover - fcntl always exists on macOS/Linux
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

HERE = Path(__file__).resolve().parent

# 顯示次序 = 呢個 tuple 嘅次序。加新旺財只要加一行。
DOMAINS: tuple[tuple[str, str], ...] = (
    ("au", "🇦🇺 AU 賽馬"),
    ("nba", "🏀 NBA 大細盤精選（紙上盤）"),
    ("tennis", "🎾 網球"),
)
DOMAIN_LABELS = dict(DOMAINS)
LEDGER_NAME = "roi_board.json"


def ledger_path() -> Path:
    root = os.environ.get("WONGCHOI_CONTROL_STATE_ROOT") or (
        Path.home() / "WongChoiData" / "WongChoiControl")
    return Path(root) / LEDGER_NAME


# ── 數字 ────────────────────────────────────────────────────────────────

def make_row(bets: Any = 0, hits: Any = 0, stake: Any = None, pnl: Any = 0.0) -> dict:
    """一格數字。`stake` 冇俾就當平注（每注 1u）。"""
    bets = int(bets or 0)
    return {
        "bets": bets,
        "hits": int(hits or 0),
        "stake": round(float(bets if stake is None else stake or 0.0), 4),
        "pnl": round(float(pnl or 0.0), 4),
    }


def add_rows(rows: Iterable[Mapping[str, Any]]) -> dict:
    total = make_row()
    for row in rows:
        total["bets"] += int(row.get("bets") or 0)
        total["hits"] += int(row.get("hits") or 0)
        total["stake"] = round(total["stake"] + float(row.get("stake") or 0.0), 4)
        total["pnl"] = round(total["pnl"] + float(row.get("pnl") or 0.0), 4)
    return total


# ── ledger ──────────────────────────────────────────────────────────────

def load(path: Path | None = None) -> dict:
    path = Path(path or ledger_path())
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"domains": {}}
    if not isinstance(data, dict) or not isinstance(data.get("domains"), dict):
        return {"domains": {}}
    return data


@contextlib.contextmanager
def _locked(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_suffix(path.suffix + ".lock")
    with open(lock, "a+") as handle:
        if fcntl is not None:
            fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(handle, fcntl.LOCK_UN)


def _write(path: Path, data: dict) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".roi_board.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def record(domain: str, *, day: str, latest: Mapping[str, Any],
           cumulative: Mapping[str, Any], since: str | None = None,
           days: Mapping[str, Mapping[str, Any]] | None = None,
           path: Path | None = None) -> dict:
    """寫入一個旺財最新嘅結算日同累計。同一個旺財重寫 = 覆蓋（idempotent）。"""
    if domain not in DOMAIN_LABELS:
        raise ValueError(f"unknown ROI domain: {domain}")
    path = Path(path or ledger_path())
    entry = {
        "day": str(day),
        "latest": make_row(**{k: latest.get(k) for k in ("bets", "hits", "stake", "pnl")}),
        "cumulative": make_row(**{k: cumulative.get(k) for k in ("bets", "hits", "stake", "pnl")}),
        "since": since,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    with _locked(path):
        data = load(path)
        old = data["domains"].get(domain) or {}
        if days is not None:
            entry["days"] = {k: make_row(**{f: v.get(f) for f in ("bets", "hits", "stake", "pnl")})
                             for k, v in sorted(days.items())}
        elif "days" in old:
            entry["days"] = old["days"]
        data["domains"][domain] = entry
        _write(path, data)
    return entry


def record_days(domain: str, days: Mapping[str, Mapping[str, Any]], *, day: str,
                since: str | None = None, path: Path | None = None,
                merge: bool = False) -> dict:
    """由逐日數字寫入：最新 = `day` 嗰日，累計 = 全部日子加埋（只計到 `day`）。

    `merge=True` 會保留 ledger 入面已經有、今次冇俾嘅日子（AU 逐日補數用）。
    """
    path = Path(path or ledger_path())
    merged = dict(days)
    if merge:
        old = (load(path)["domains"].get(domain) or {}).get("days") or {}
        merged = {**old, **days}
    upto = {k: v for k, v in merged.items() if k <= day}
    if since:
        upto = {k: v for k, v in upto.items() if k >= since}
    return record(domain, day=day, latest=upto.get(day) or make_row(),
                  cumulative=add_rows(upto.values()), since=since or (min(upto) if upto else None),
                  days=merged, path=path)


def known_days(domain: str, path: Path | None = None) -> set[str]:
    return set(((load(path)["domains"].get(domain) or {}).get("days") or {}).keys())


# ── 出訊息 ──────────────────────────────────────────────────────────────

def _money(value: float) -> str:
    text = f"{abs(value):.2f}u"
    return ("+" if value >= 0 else "−") + text


def _pct(row: Mapping[str, Any]) -> str:
    stake = float(row.get("stake") or 0.0)
    if not stake:
        return "—"
    pct = 100.0 * float(row.get("pnl") or 0.0) / stake
    return ("+" if pct >= 0 else "−") + f"{abs(pct):.1f}%"


def format_row(label: str, row: Mapping[str, Any]) -> str:
    bets = int(row.get("bets") or 0)
    if not bets:
        return f"  {label}：冇注"
    return (f"  {label}：{bets} 注｜中 {int(row.get('hits') or 0)}｜"
            f"ROI {_money(float(row.get('pnl') or 0.0))}｜{_pct(row)}")


def _short(day: str) -> str:
    return day[5:] if len(day) == 10 else day


def _day_word(day: str, today: str) -> str:
    if day == today:
        return "今日"
    try:
        if day == (date.fromisoformat(today) - timedelta(days=1)).isoformat():
            return "昨日"
    except ValueError:
        pass
    return "最近"


def render(*, updated: str | None = None, today: str | None = None,
           path: Path | None = None, title: str = "📊 旺財 ROI") -> str:
    data = load(path)
    today = today or date.today().isoformat()
    lines = [f"{title}｜{today}"]
    if updated in DOMAIN_LABELS:
        lines.append(f"🆕 啱啱結算：{DOMAIN_LABELS[updated]}")
    totals = []
    for key, label in DOMAINS:
        entry = data["domains"].get(key)
        lines.append("")
        lines.append(label + (" 🆕" if key == updated else ""))
        if not entry:
            lines.append("  未有紀錄")
            continue
        day = str(entry.get("day") or "")
        lines.append(format_row(f"{_day_word(day, today)}（{_short(day)}）",
                                entry.get("latest") or {}))
        since = entry.get("since")
        lines.append(format_row(f"累計（{since} 起）" if since else "累計",
                                entry.get("cumulative") or {}))
        totals.append(entry.get("cumulative") or {})
    if len(totals) > 1:
        lines.append("")
        lines.append(format_row("合共累計", add_rows(totals)).strip())
    lines.append("")
    lines.append("每注 1u 平注；ROI 係歷史結果，唔保證之後為正。")
    return "\n".join(lines)


def publish(updated: str | None = None, *, today: str | None = None,
            path: Path | None = None, dry_run: bool = False,
            title: str = "📊 旺財 ROI") -> dict:
    """出板並發俾 Kelvin + Heison。回傳 racing_telegram 嘅結果 dict。"""
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    from racing_telegram import send_message  # noqa: PLC0415

    text = render(updated=updated, today=today, path=path, title=title)
    result = send_message(text, audience="content", dry_run=dry_run)
    result["text"] = text
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="旺財統一 ROI 板")
    parser.add_argument("--summary", action="store_true",
                        help="發每朝總結（Kelvin + Heison）")
    parser.add_argument("--date", help="訊息日期（預設今日）")
    parser.add_argument("--dry-run", action="store_true", help="只印，唔發")
    args = parser.parse_args(argv)
    if not args.summary:
        print(render(today=args.date))
        return 0
    result = publish(today=args.date, dry_run=args.dry_run, title="☀️ 旺財每日 ROI 總結")
    print(result.get("text", ""))
    print(f"Telegram: {result.get('status')}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
