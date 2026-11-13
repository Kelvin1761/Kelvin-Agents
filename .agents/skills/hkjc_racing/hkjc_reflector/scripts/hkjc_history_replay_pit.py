"""歷史引擎回放：PIT 騎練評分擴展去 2019 起嘅舊季（docs/plans/2026-11-13-hkjc-historic-engine-replay.md 第 1 步）。

pit_backtest.load_all_rows 只讀 comprehensive_stats 嘅季（24_25 起），所以 2019–2024 回放時騎練評分全部中性。
呢度將 `_research_old_season_results/*.json`（同 full_day_results.json 同一格式）用同一個
build_comprehensive_stats.result_row 轉做同一 schema，接喺前面。只用喺 harness／回放，live 唔郁。
as-of 由 pit_backtest.inject_as_of 負責（只取賽日之前嘅行），所以多咗舊行唔會前視。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent))
import pit_backtest  # noqa: E402

bcs = pit_backtest.bcs
OLD_DIR = bcs.HK_RACING / "_research_old_season_results"


def old_season_rows(before: str) -> pd.DataFrame:
    """舊季賽果 → race_results schema；只取 `before` 之前嘅日子（避免同正式季重疊）。"""
    rows = []
    for fp in sorted(OLD_DIR.glob("*.json")):
        day = fp.stem
        if day >= before:
            continue
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for race_key, race in data.items():
            if not isinstance(race, dict):
                continue
            header = bcs.race_header(race)
            for row in race.get("results", []):
                rec = bcs.result_row(day, race_key, race, row, header)
                if rec is not None:
                    rows.append(rec)
    df = pd.DataFrame(rows)
    if not df.empty:
        df["Date"] = df["Date"].astype(str)
        df["SeasonTag"] = df["Date"].map(pit_backtest._season_tag)
    return df


def load_all_rows_extended() -> pd.DataFrame:
    cur = pit_backtest.load_all_rows()
    first = str(cur["Date"].min())
    old = old_season_rows(first)
    if old.empty:
        return cur
    return pd.concat([old, cur], ignore_index=True, sort=False)


if __name__ == "__main__":
    df = load_all_rows_extended()
    print(df.groupby("SeasonTag").agg(rows=("Date", "size"), days=("Date", "nunique"),
                                      first=("Date", "min"), last=("Date", "max")).to_string())
    print("欄位：", list(df.columns))
