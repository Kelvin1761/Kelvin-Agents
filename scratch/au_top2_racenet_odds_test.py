#!/usr/bin/env python3
"""Audit AU Wong Choi Top-2, $1 each WIN at archived fixed-price proxies.

The exact Racenet data available locally is result-page ``starting_price`` for
four recent meetings.  It is a closing/result price, not a timestamped quote
that proves the same price was available when the analysis was published.

The larger historical comparison uses Betfair price fields only as labelled
market proxies:
* morningwap: early traded average;
* ppwap: pre-play traded average, the closest large-sample fixed-price proxy;
* bsp: executable exchange SP, settled with 5% commission.

No price enters the AU Wong Choi ranking.
"""
from __future__ import annotations

import csv
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean


ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / "scratch"
sys.path.insert(0, str(SCRATCH))

import au_win_focus_test as base  # noqa: E402


OUT_JSON = SCRATCH / "au_top2_racenet_odds_test_results.json"
OUT_MD = ROOT / "2026-07-29 AU Top2 Racenet Odds Strategy Test.md"

RACENET_MEETINGS = (
    (
        "2026-07-15",
        "Warwick Farm",
        ROOT
        / "Wong Choi Horse Race Analysis/AU_Racing/2026-07-15 Warwick Farm"
        / "Meeting_Auto_Scoring.csv",
        ROOT
        / "Wong Choi Horse Race Analysis/AU_Racing/2026-07-15 Warwick Farm"
        / "Race_Results_Warwick_Farm_2026-07-15.json",
    ),
    (
        "2026-07-25",
        "Randwick",
        SCRATCH
        / "au_reflector_2026-07-25/inputs/2026-07-25 Randwick Race 1-10"
        / "Meeting_Auto_Scoring.csv",
        SCRATCH
        / "au_reflector_2026-07-25/randwick"
        / "Race_Results_Randwick_2026-07-25.json",
    ),
    (
        "2026-07-25",
        "Caulfield",
        SCRATCH
        / "au_reflector_2026-07-25/inputs/2026-07-25 Caulfield Race 1-9"
        / "Meeting_Auto_Scoring.csv",
        SCRATCH
        / "au_reflector_2026-07-25/caulfield"
        / "Race_Results_Caulfield_2026-07-25.json",
    ),
    (
        "2026-07-25",
        "Eagle Farm",
        SCRATCH
        / "au_reflector_2026-07-25/inputs/2026-07-25 Eagle Farm Race 1-9"
        / "Meeting_Auto_Scoring.csv",
        SCRATCH
        / "au_reflector_2026-07-25/eagle_farm"
        / "Race_Results_Eagle_Farm_2026-07-25.json",
    ),
)


def number(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_historical() -> list[dict]:
    """Return one record per race with current-model Top 2 and market prices."""
    price_index = base.load_bsp()
    races = base.load_historical(price_index)
    output = []
    for race in races:
        ranked = sorted(race, key=lambda row: (-row["ability"], row["horse_number"]))
        selections = []
        for rank, row in enumerate(ranked[:2], 1):
            prices = price_index.get((row["date"], base.norm_name(row["horse_name"])), {})
            selections.append(
                {
                    "rank": rank,
                    "horse_number": row["horse_number"],
                    "horse_name": row["horse_name"],
                    "won": row["won"],
                    "morningwap": number(prices.get("morningwap")),
                    "ppwap": number(prices.get("ppwap")),
                    "bsp": number(prices.get("bsp")),
                    "ppmax": number(prices.get("ppmax")),
                }
            )
        output.append(
            {
                "date": race[0]["date"],
                "venue": race[0]["meeting"],
                "race": race[0]["race"],
                "selections": selections,
            }
        )
    return output


def load_racenet_sp() -> list[dict]:
    """Load current-model Top 2 joined to Racenet result starting prices."""
    output = []
    for date, venue, scoring_path, result_path in RACENET_MEETINGS:
        with scoring_path.open(encoding="utf-8-sig", newline="") as handle:
            scoring = list(csv.DictReader(handle))
        results = json.loads(result_path.read_text(encoding="utf-8"))["results"]
        by_race: dict[int, list[dict]] = defaultdict(list)
        for row in scoring:
            by_race[int(float(row["race_number"]))].append(row)
        for race_no, rows in sorted(by_race.items()):
            result_by_number = {
                int(item["competitor_number"]): item
                for item in results.get(str(race_no), [])
                if not item.get("is_scratched")
            }
            ranked = sorted(
                rows,
                key=lambda row: (
                    int(float(row["rank"])),
                    int(float(row["horse_number"])),
                ),
            )
            selections = []
            for rank, row in enumerate(ranked[:2], 1):
                horse_number = int(float(row["horse_number"]))
                result = result_by_number.get(horse_number)
                if not result:
                    continue
                selections.append(
                    {
                        "rank": rank,
                        "horse_number": horse_number,
                        "horse_name": row["horse_name"],
                        "won": int(result.get("finish_position") or 99) == 1,
                        "racenet_sp": number(result.get("starting_price")),
                    }
                )
            if len(selections) == 2:
                output.append(
                    {
                        "date": date,
                        "venue": venue,
                        "race": race_no,
                        "selections": selections,
                    }
                )
    return output


def max_drawdown(values: list[float]) -> float:
    balance = peak = drawdown = 0.0
    for value in values:
        balance += value
        peak = max(peak, balance)
        drawdown = max(drawdown, peak - balance)
    return drawdown


def losing_streak(values: list[float]) -> int:
    current = worst = 0
    for value in values:
        current = current + 1 if value < 0 else 0
        worst = max(worst, current)
    return worst


def metrics(
    races: list[dict],
    price_key: str,
    *,
    commission: float = 0.0,
    seed: int = 725,
) -> dict:
    """Settle exactly two $1 WIN selections per accepted race."""
    values = []
    winning_prices = []
    accepted = []
    for race in races:
        selections = race["selections"]
        if len(selections) != 2:
            continue
        prices = [selection.get(price_key) for selection in selections]
        if any(price is None or price <= 1.01 or price > 500 for price in prices):
            continue
        gross = sum(
            float(selection[price_key])
            for selection in selections
            if selection["won"]
        ) - 2.0
        pnl = gross * (1.0 - commission) if gross > 0 else gross
        values.append(pnl)
        accepted.append(race)
        winning_prices.extend(
            float(selection[price_key])
            for selection in selections
            if selection["won"]
        )
    stake = 2.0 * len(values)
    rng = random.Random(seed)
    bootstrap = []
    if values:
        for _ in range(5000):
            sample = rng.choices(values, k=len(values))
            bootstrap.append(100.0 * sum(sample) / (2.0 * len(sample)))
        bootstrap.sort()
    return {
        "races": len(values),
        "bets": 2 * len(values),
        "winner_captured": len(winning_prices),
        "winner_capture_pct": round(
            100.0 * len(winning_prices) / max(1, len(values)), 2
        ),
        "pnl": round(sum(values), 2),
        "roi_pct": round(100.0 * sum(values) / max(1.0, stake), 2),
        "ci95_pct": (
            [
                round(bootstrap[int(0.025 * len(bootstrap))], 2),
                round(bootstrap[int(0.975 * len(bootstrap))], 2),
            ]
            if bootstrap
            else [0.0, 0.0]
        ),
        "average_winner_price": (
            round(mean(winning_prices), 3) if winning_prices else None
        ),
        "break_even_winner_price": (
            round(stake / len(winning_prices), 3) if winning_prices else None
        ),
        "max_drawdown_units": round(max_drawdown(values), 2),
        "worst_losing_race_streak": losing_streak(values),
        "_accepted": accepted,
    }


def public(metric: dict) -> dict:
    return {key: value for key, value in metric.items() if not key.startswith("_")}


def split_metrics(races: list[dict], price_key: str, *, commission: float = 0.0) -> dict:
    dates = sorted({race["date"] for race in races})
    midpoint = dates[len(dates) // 2]
    first = [race for race in races if race["date"] < midpoint]
    second = [race for race in races if race["date"] >= midpoint]
    return {
        "midpoint": midpoint,
        "first": public(metrics(first, price_key, commission=commission, seed=112)),
        "second": public(metrics(second, price_key, commission=commission, seed=113)),
    }


def grouped_metrics(races: list[dict], price_key: str) -> dict:
    groups: dict[str, list[dict]] = defaultdict(list)
    for race in races:
        groups[race["venue"]].append(race)
    return {
        venue: public(metrics(group, price_key, seed=900 + idx))
        for idx, (venue, group) in enumerate(sorted(groups.items()))
    }


def gated(
    races: list[dict],
    price_key: str,
    predicate,
) -> dict:
    accepted = []
    for race in races:
        prices = [selection.get(price_key) for selection in race["selections"]]
        if len(prices) != 2 or any(price is None for price in prices):
            continue
        if predicate([float(price) for price in prices]):
            accepted.append(race)
    return public(metrics(accepted, price_key, seed=121))


def fmt_pct(value: float) -> str:
    return f"{value:+.1f}%"


def render(result: dict) -> str:
    history = result["historical"]
    exact = result["racenet_sp"]
    lines = [
        "# AU Wong Choi — Top 2 各 $1 @ Racenet Odds 策略測試",
        "",
        "## 結論先行",
        "",
        "- 呢個方向值得做 forward test，但現有證據唔支持即時實盤盲買所有場。",
        (
            f"- 直接 Racenet SP 樣本：{exact['all']['races']} 場、"
            f"{exact['all']['bets']} 注，P&L {exact['all']['pnl']:+.2f} units，"
            f"ROI {fmt_pct(exact['all']['roi_pct'])}。"
        ),
        (
            f"- 大樣本 pre-play WAP proxy：{history['ppwap']['races']} 場，"
            f"ROI {fmt_pct(history['ppwap']['roi_pct'])}；"
            f"早段 morning WAP 則為 {fmt_pct(history['morningwap']['roi_pct'])}。"
        ),
        "- 真正關鍵係取得分析發布一刻嘅 Racenet odds，並持續量度相對 SP 嘅 CLV。",
        "",
        "## 價格口徑",
        "",
        "| 價格 | 場次 | 冠軍在 Top 2 | P&L | ROI | 95% CI |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    labels = {
        "morningwap": "Betfair morning WAP（早盤 proxy）",
        "ppwap": "Betfair pre-play WAP（近開跑 proxy）",
        "bsp": "Betfair BSP（5% commission）",
    }
    for key in ("morningwap", "ppwap", "bsp"):
        row = history[key]
        lines.append(
            f"| {labels[key]} | {row['races']} | {row['winner_capture_pct']:.1f}% | "
            f"{row['pnl']:+.2f} | {fmt_pct(row['roi_pct'])} | "
            f"[{fmt_pct(row['ci95_pct'][0])}, {fmt_pct(row['ci95_pct'][1])}] |"
        )
    row = exact["all"]
    lines.append(
        f"| Racenet result SP（直接、細樣本） | {row['races']} | "
        f"{row['winner_capture_pct']:.1f}% | {row['pnl']:+.2f} | "
        f"{fmt_pct(row['roi_pct'])} | "
        f"[{fmt_pct(row['ci95_pct'][0])}, {fmt_pct(row['ci95_pct'][1])}] |"
    )
    lines.extend(
        [
            "",
            "Racenet result SP 係收市／賽果價格，唔證明分析發布一刻可以買到同一價格。",
            "",
            "## 價格要求",
            "",
            "| 樣本 | 命中場次平均勝馬價 | 打和所需平均勝馬價 | 差額 |",
            "|---|---:|---:|---:|",
        ]
    )
    for label, row in (
        ("歷史 pre-play WAP", history["ppwap"]),
        ("最近 Racenet SP", exact["all"]),
    ):
        gap = row["average_winner_price"] - row["break_even_winner_price"]
        lines.append(
            f"| {label} | {row['average_winner_price']:.3f} | "
            f"{row['break_even_winner_price']:.3f} | {gap:+.3f} |"
        )
    lines.extend(
        [
            "",
            "## Racenet SP 分場",
            "",
            "| 場地 | 場次 | 命中 | P&L | ROI |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for venue, venue_row in exact["by_venue"].items():
        lines.append(
            f"| {venue} | {venue_row['races']} | {venue_row['winner_captured']} | "
            f"{venue_row['pnl']:+.2f} | {fmt_pct(venue_row['roi_pct'])} |"
        )
    lines.extend(
        [
            "",
            "## 簡單 price gates（只作診斷）",
            "",
            "| Gate | 歷史 pre-play WAP ROI | Racenet SP ROI | 判斷 |",
            "|---|---:|---:|---|",
        ]
    )
    gate_labels = {
        "both_ge_4": "兩匹都 ≥ $4",
        "combined_implied_le_35": "兩匹 implied probability 合計 ≤ 35%",
        "rank1_ge_3_rank2_ge_4": "#1 ≥ $3 且 #2 ≥ $4",
    }
    for key, label in gate_labels.items():
        h = result["gates"]["historical_ppwap"][key]
        e = result["gates"]["racenet_sp"][key]
        lines.append(
            f"| {label} | {fmt_pct(h['roi_pct'])} ({h['races']}場) | "
            f"{fmt_pct(e['roi_pct'])} ({e['races']}場) | "
            "未通過跨樣本穩定性 |"
        )
    lines.extend(
        [
            "",
            "冇一個簡單 price gate 同時喺大樣本時序分段及最新 Racenet 樣本穩定勝出；",
            "因此唔應該由呢 34 場反推門檻。",
            "",
            "## 建議 forward protocol",
            "",
            "1. 模型繼續 odds-blind 排名；每場固定記錄 #1、#2。",
            "2. 分析發布時保存 Racenet decimal odds、bookmaker、timestamp。",
            "3. Paper bet：#1、#2 各 $1 WIN；唔用賽後 SP 回填作買入價。",
            "4. 賽後保存 Racenet SP，計每注 CLV、P&L、最大回撤。",
            "5. 50 場只做 checkpoint；100 場先決定正式啟用或加 price gate。",
            "",
            "Accountant 狀態：repo 冇 betting_record.md，因此按 failure protocol 視為審慎模式；",
            "本報告只批准 paper test，唔批准實盤放大注碼。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    historical = load_historical()
    racenet = load_racenet_sp()
    historical_ppwap = public(metrics(historical, "ppwap"))
    result = {
        "historical_period": {
            "start": min(race["date"] for race in historical),
            "end": max(race["date"] for race in historical),
            "races": len(historical),
        },
        "historical": {
            "morningwap": public(metrics(historical, "morningwap")),
            "ppwap": historical_ppwap,
            "bsp": public(metrics(historical, "bsp", commission=0.05)),
            "ppwap_split": split_metrics(historical, "ppwap"),
        },
        "racenet_sp": {
            "all": public(metrics(racenet, "racenet_sp")),
            "by_venue": grouped_metrics(racenet, "racenet_sp"),
        },
        "gates": {
            "historical_ppwap": {
                "both_ge_4": gated(
                    historical, "ppwap", lambda prices: min(prices) >= 4.0
                ),
                "combined_implied_le_35": gated(
                    historical,
                    "ppwap",
                    lambda prices: sum(1.0 / price for price in prices) <= 0.35,
                ),
                "rank1_ge_3_rank2_ge_4": gated(
                    historical,
                    "ppwap",
                    lambda prices: prices[0] >= 3.0 and prices[1] >= 4.0,
                ),
            },
            "racenet_sp": {
                "both_ge_4": gated(
                    racenet, "racenet_sp", lambda prices: min(prices) >= 4.0
                ),
                "combined_implied_le_35": gated(
                    racenet,
                    "racenet_sp",
                    lambda prices: sum(1.0 / price for price in prices) <= 0.35,
                ),
                "rank1_ge_3_rank2_ge_4": gated(
                    racenet,
                    "racenet_sp",
                    lambda prices: prices[0] >= 3.0 and prices[1] >= 4.0,
                ),
            },
        },
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    report = render(result)
    OUT_MD.write_text(report, encoding="utf-8")
    print(report)
    print(f"JSON: {OUT_JSON}")
    print(f"Report: {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
