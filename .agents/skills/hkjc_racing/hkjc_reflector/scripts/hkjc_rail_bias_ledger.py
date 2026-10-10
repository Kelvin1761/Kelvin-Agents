#!/usr/bin/env python3
"""HKJC 賽道偏差 ledger：每場記低賽道配置、場地狀況同賽後實際偏差（EXP-20261010-14）。

點解要有：模型向內檔傾（方向啱，但押咗約三倍），好日子同壞日子嘅分別係當日偏差
（EXP-20261010-13）。今日偏內定偏外，同上一個賽日完全冇關（ρ ≈ 0），所以唯一可能
賽前預測到偏差嘅係**賽道配置（A／B／C／C+3…）同場地狀況**。賽果庫一直冇記呢兩樣，
歷史上量唔到 —— 呢個 ledger 由而家開始逐日記，夠樣本先測。

每場一行：
  rail          賽前排位表／Logic 嘅賽道（A、C+3、全天候…）—— 賽前已知
  going         賽果頁「場地狀況」—— 正式場地狀況賽前公佈，賽中可能改；只用嚟研究，唔入分
  inside_bias   頭三名平均檔位百分位 − 全場平均（負數 = 偏內）
  front_bias    頭三名平均第一個沿途位百分位 − 全場平均（負數 = 偏前置）

用法：
  python3 hkjc_rail_bias_ledger.py record <meeting_dir>     # 覆盤自動做
  python3 hkjc_rail_bias_ledger.py backfill                 # 掃晒 HK_Racing 已有嘅賽日
  python3 hkjc_rail_bias_ledger.py report                   # 賽道配置 → 偏差（夠樣本先判）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean

PROJECT_ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(PROJECT_ROOT))

LEDGER_NAME = "HKJC_Rail_Bias_Ledger.jsonl"
READY_MEETINGS = 60          # 每個場地夠呢個數先做配置比較（預先登記）
MIN_PER_RAIL = 5


def _hk_root() -> Path:
    from wongchoi_paths import HK_RACING

    return Path(HK_RACING)


def _rail_from_racecards(meeting_dir: Path) -> dict[int, str]:
    out = {}
    for card in meeting_dir.glob("*排位表.md"):
        text = card.read_text(encoding="utf-8")[:1500]
        race = re.search(r"場次[:：]\s*第(\d+)場", text)
        rail = re.search(r"賽道[:：]\s*(\S+)", text)
        surface = re.search(r"場地[:：]\s*(\S+)", text)
        if race and rail:
            label = rail.group(1).replace("賽道", "")
            if surface and "全天候" in surface.group(1):
                label = "全天候"
            out[int(race.group(1))] = label
    return out


def _results_file(meeting_dir: Path) -> Path | None:
    files = sorted(meeting_dir.glob("*全日賽果.json"))
    return files[0] if files else None


def _pct_rank(values: list[int]) -> dict[int, float]:
    order = sorted(values)
    n = len(order)
    return {v: order.index(v) / (n - 1) for v in values} if n > 1 else {}


def race_rows(meeting_dir: Path) -> list[dict]:
    results = _results_file(meeting_dir)
    if results is None:
        return []
    data = json.loads(results.read_text(encoding="utf-8"))
    rails = _rail_from_racecards(meeting_dir)
    rows = []
    for key, race in sorted(data.items(), key=lambda kv: int(kv[0]) if str(kv[0]).isdigit() else 0):
        runners = [r for r in race.get("results") or []
                   if str(r.get("draw", "")).isdigit() and str(r.get("pos", "")).isdigit()]
        if len(runners) < 6:
            continue
        draw_pct = _pct_rank([int(r["draw"]) for r in runners])
        calls = {}
        for r in runners:
            first = str(r.get("running_positions") or "").split()
            if first and first[0].isdigit():
                calls[r["horse_no"]] = (int(first[0]) - 1) / (len(runners) - 1)
        top = [r for r in runners if int(r["pos"]) <= 3]
        inside = mean(draw_pct[int(r["draw"])] for r in top) - mean(draw_pct[int(r["draw"])] for r in runners)
        front = None
        if calls and all(r["horse_no"] in calls for r in top):
            front = mean(calls[r["horse_no"]] for r in top) - mean(calls.values())
        race_no = int(race.get("race_no") or key)
        rows.append({"meeting": meeting_dir.name, "date": meeting_dir.name[:10], "race": race_no,
                     "venue": "跑馬地" if "HappyValley" in meeting_dir.name else "沙田",
                     "rail": rails.get(race_no), "going": race.get("going"), "course_text": race.get("course"),
                     "field": len(runners), "inside_bias": round(inside, 4),
                     "front_bias": None if front is None else round(front, 4)})
    return rows


def write(ledger: Path, meeting: str, rows: list[dict]) -> None:
    kept = []
    if ledger.exists():
        kept = [line for line in ledger.read_text(encoding="utf-8").splitlines()
                if line.strip() and json.loads(line).get("meeting") != meeting]
    kept.extend(json.dumps(r, ensure_ascii=False) for r in rows)
    ledger.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")


def record(meeting_dir: Path, ledger: Path | None = None) -> int:
    rows = race_rows(meeting_dir)
    if rows:
        write(ledger or meeting_dir.parent / LEDGER_NAME, meeting_dir.name, rows)
    return len(rows)


def meeting_summary(ledger: Path) -> list[dict]:
    """→ one row per (meeting, rail): mean inside/front bias over its races."""
    groups = defaultdict(list)
    for line in ledger.read_text(encoding="utf-8").splitlines() if ledger.exists() else []:
        if line.strip():
            r = json.loads(line)
            if r.get("rail"):
                groups[(r["meeting"], r["venue"], r["rail"])].append(r)
    out = []
    for (meeting, venue, rail), rs in sorted(groups.items()):
        fronts = [r["front_bias"] for r in rs if r.get("front_bias") is not None]
        out.append({"meeting": meeting, "venue": venue, "rail": rail, "races": len(rs),
                    "inside_bias": mean(r["inside_bias"] for r in rs),
                    "front_bias": mean(fronts) if fronts else None})
    return out


def report(ledger: Path) -> str:
    summary = meeting_summary(ledger)
    lines = ["# HKJC 賽道配置 → 當日偏差", "",
             f"預先登記：每個場地 ≥ {READY_MEETINGS} 個賽日、每個配置 ≥ {MIN_PER_RAIL} 個先做比較（Kruskal–Wallis）。", ""]
    by_venue = defaultdict(lambda: defaultdict(list))
    for s in summary:
        by_venue[s["venue"]][s["rail"]].append(s["inside_bias"])
    for venue, rails in sorted(by_venue.items()):
        meetings = len({s["meeting"] for s in summary if s["venue"] == venue})
        lines.append(f"## {venue}（{meetings} 個賽日）")
        lines.append("| 賽道 | 賽日 | 平均內檔偏差 |")
        lines.append("|---|---:|---:|")
        for rail, values in sorted(rails.items()):
            lines.append(f"| {rail} | {len(values)} | {mean(values):+.3f} |")
        groups = [v for v in rails.values() if len(v) >= MIN_PER_RAIL]
        if meetings >= READY_MEETINGS and len(groups) >= 2:
            from scipy.stats import kruskal

            lines.append(f"\n配置之間差異 Kruskal–Wallis p = {kruskal(*groups).pvalue:.3f}")
        else:
            lines.append(f"\n樣本未夠（要 {READY_MEETINGS} 個賽日、≥ 2 個配置各 {MIN_PER_RAIL} 日），未判。")
        lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record")
    r.add_argument("meeting_dir")
    sub.add_parser("backfill")
    sub.add_parser("report")
    args = ap.parse_args(argv)
    root = _hk_root()
    ledger = root / LEDGER_NAME
    if args.cmd == "record":
        print(record(Path(args.meeting_dir), ledger), "races recorded")
    elif args.cmd == "backfill":
        total = 0
        for meeting in sorted(root.glob("20[0-9][0-9]-[0-9][0-9]-[0-9][0-9]_*")):
            if meeting.is_dir() and "(" not in meeting.name:
                total += record(meeting, ledger)
        print(total, "races recorded")
    else:
        print(report(ledger))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
