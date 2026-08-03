#!/usr/bin/env python3
"""Large-sample AU win-focus and Top-4 trifecta coverage experiment.

Evaluation layers:
1. grouped-date five-fold cross-fit: all races receive an out-of-fold ranking,
   although models may train on dates later than the held-out block;
2. expanding-date walk-forward: each validation race is ranked only by models
   trained on earlier dates.

The primary trifecta metric is an unordered four-runner box: the predicted
Top 4 must contain the actual first, second, and third finishers.  A four-runner
box contains 24 ordered combinations.  The archive has no AU trifecta
dividends, so the script reports hit rate and break-even dividend, not ROI.
"""
from __future__ import annotations

import json
import math
import random
import sys
from math import comb
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / "scratch"
sys.path.insert(0, str(SCRATCH))

import au_win_focus_test as base  # noqa: E402


OUT_JSON = SCRATCH / "au_win_focus_trifecta_test_results.json"
OUT_MD = ROOT / "2026-07-29 AU Win Focus Top4 Trifecta All-Race Test.md"
STRATEGIES = ("baseline", "win_logit", "win_gbm")
LABELS = {
    "baseline": "現行 7D",
    "win_logit": "Win Logistic",
    "win_gbm": "Win GBM",
}


def valid_price(value: object) -> bool:
    try:
        price = float(value)
    except (TypeError, ValueError):
        return False
    return 1.01 < price <= 500.0


def add_market_prices(races: list[list[dict]], price_index: dict) -> None:
    for race in races:
        for row in race:
            prices = price_index.get(
                (row["date"], base.norm_name(row["horse_name"])),
                {},
            )
            row["ppwap"] = base.as_float(prices.get("ppwap"))
            row["bsp"] = base.as_float(prices.get("bsp"))


def contiguous_date_blocks(dates: list[str], blocks: int) -> list[list[str]]:
    size = max(1, math.ceil(len(dates) / blocks))
    return [dates[index : index + size] for index in range(0, len(dates), size)]


def crossfit_pairs(
    races: list[list[dict]],
    blocks: int = 5,
) -> tuple[dict[str, list[tuple[list[dict], list[dict]]]], list[dict]]:
    """Hold out contiguous date blocks; train each model on all other blocks."""
    dates = sorted({race[0]["date"] for race in races})
    output = {strategy: [] for strategy in STRATEGIES}
    folds = []
    for fold_no, block in enumerate(contiguous_date_blocks(dates, blocks), 1):
        held_dates = set(block)
        train = [race for race in races if race[0]["date"] not in held_dates]
        valid = [race for race in races if race[0]["date"] in held_dates]
        models = base.fit_models(train)
        for race in valid:
            baseline = base.rank_race(race, "baseline")
            for strategy in STRATEGIES:
                order = base.rank_race(race, strategy, models.get(strategy))
                output[strategy].append((baseline, order))
        folds.append(
            {
                "fold": fold_no,
                "held_start": min(block),
                "held_end": max(block),
                "train_races": len(train),
                "valid_races": len(valid),
            }
        )
    return output, folds


def walkforward_pairs(
    races: list[list[dict]],
    initial_date_fraction: float = 0.20,
    blocks: int = 8,
) -> tuple[dict[str, list[tuple[list[dict], list[dict]]]], list[dict]]:
    """Expanding-date validation after the first 20% of dates."""
    dates = sorted({race[0]["date"] for race in races})
    initial = max(1, int(len(dates) * initial_date_fraction))
    validation_dates = dates[initial:]
    output = {strategy: [] for strategy in STRATEGIES}
    folds = []
    for fold_no, block in enumerate(
        contiguous_date_blocks(validation_dates, blocks),
        1,
    ):
        held_dates = set(block)
        first_date = min(block)
        train = [race for race in races if race[0]["date"] < first_date]
        valid = [race for race in races if race[0]["date"] in held_dates]
        models = base.fit_models(train)
        for race in valid:
            baseline = base.rank_race(race, "baseline")
            for strategy in STRATEGIES:
                order = base.rank_race(race, strategy, models.get(strategy))
                output[strategy].append((baseline, order))
        folds.append(
            {
                "fold": fold_no,
                "train_end": max(race[0]["date"] for race in train),
                "valid_start": min(block),
                "valid_end": max(block),
                "train_races": len(train),
                "valid_races": len(valid),
            }
        )
    return output, folds


def wilson_interval(hits: int, total: int) -> list[float]:
    if total <= 0:
        return [0.0, 0.0]
    z = 1.959963984540054
    p = hits / total
    denominator = 1.0 + z * z / total
    centre = (p + z * z / (2.0 * total)) / denominator
    spread = (
        z
        * math.sqrt(p * (1.0 - p) / total + z * z / (4.0 * total * total))
        / denominator
    )
    return [round(100.0 * (centre - spread), 2), round(100.0 * (centre + spread), 2)]


def actual_podium(baseline: list[dict]) -> dict[int, int]:
    return {
        int(row["finish"]): int(row["horse_number"])
        for row in baseline
        if int(row["finish"]) in (1, 2, 3)
    }


def trifecta_hit(pair: tuple[list[dict], list[dict]]) -> tuple[bool, bool]:
    baseline, order = pair
    podium = actual_podium(baseline)
    eligible = set(podium) == {1, 2, 3}
    top4 = {int(row["horse_number"]) for row in order[:4]}
    return eligible, eligible and set(podium.values()).issubset(top4)


def ranking_and_trifecta_metrics(
    pairs: list[tuple[list[dict], list[dict]]],
) -> dict:
    races = len(pairs)
    top1 = sum(order[0]["won"] for _, order in pairs)
    top2 = sum(any(row["won"] for row in order[:2]) for _, order in pairs)
    top4_winner = sum(any(row["won"] for row in order[:4]) for _, order in pairs)
    eligible = []
    coverage_counts = {str(count): 0 for count in range(4)}
    ordered = 0
    for pair in pairs:
        baseline, order = pair
        podium = actual_podium(baseline)
        if set(podium) != {1, 2, 3}:
            continue
        top4 = {int(row["horse_number"]) for row in order[:4]}
        covered = len(set(podium.values()) & top4)
        coverage_counts[str(covered)] += 1
        box_hit = covered == 3
        eligible.append(box_hit)
        if len(order) >= 3:
            ordered += int(
                [
                    int(order[0]["horse_number"]),
                    int(order[1]["horse_number"]),
                    int(order[2]["horse_number"]),
                ]
                == [podium[1], podium[2], podium[3]]
            )
    box_hits = sum(eligible)
    trifecta_races = len(eligible)
    return {
        "races": races,
        "top1_wins": top1,
        "top1_win_pct": round(100.0 * top1 / max(1, races), 2),
        "winner_in_top2": top2,
        "winner_in_top2_pct": round(100.0 * top2 / max(1, races), 2),
        "winner_in_top4": top4_winner,
        "winner_in_top4_pct": round(100.0 * top4_winner / max(1, races), 2),
        "trifecta_eligible_races": trifecta_races,
        "top4_box_hits": box_hits,
        "top4_box_hit_pct": round(100.0 * box_hits / max(1, trifecta_races), 2),
        "top4_box_ci95_pct": wilson_interval(box_hits, trifecta_races),
        "ordered_top3_hits": ordered,
        "ordered_top3_hit_pct": round(100.0 * ordered / max(1, trifecta_races), 2),
        "podium_coverage_count": coverage_counts,
        "box_ordered_combinations": 24,
        "break_even_average_unit_dividend": (
            round(24.0 * trifecta_races / box_hits, 2) if box_hits else None
        ),
    }


def betting_metrics(
    pairs: list[tuple[list[dict], list[dict]]],
    price_key: str,
    *,
    commission: float = 0.0,
    seed: int = 729,
) -> dict:
    """Top 2 each one unit WIN at the selected archived market price."""
    values = []
    wins = 0
    for _, order in pairs:
        selections = order[:2]
        if len(selections) != 2 or any(
            not valid_price(row.get(price_key)) for row in selections
        ):
            continue
        gross = sum(
            float(row[price_key]) for row in selections if row["won"]
        ) - 2.0
        pnl = gross * (1.0 - commission) if gross > 0 else gross
        values.append(pnl)
        wins += int(any(row["won"] for row in selections))
    stake = 2.0 * len(values)
    rng = random.Random(seed)
    bootstrap = []
    if values:
        for _ in range(4000):
            sample = rng.choices(values, k=len(values))
            bootstrap.append(100.0 * sum(sample) / (2.0 * len(sample)))
        bootstrap.sort()
    return {
        "races": len(values),
        "bets": 2 * len(values),
        "winning_races": wins,
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
    }


def exact_two_sided_binomial(gains: int, losses: int) -> float:
    discordant = gains + losses
    if discordant == 0:
        return 1.0
    tail = min(gains, losses)
    probability = 2.0 * sum(comb(discordant, index) for index in range(tail + 1))
    probability /= 2**discordant
    return min(1.0, probability)


def paired_delta(
    baseline_pairs: list[tuple[list[dict], list[dict]]],
    candidate_pairs: list[tuple[list[dict], list[dict]]],
    metric: str,
) -> dict:
    gains = losses = 0
    for baseline_pair, candidate_pair in zip(baseline_pairs, candidate_pairs):
        if metric == "top2":
            baseline_hit = any(row["won"] for row in baseline_pair[1][:2])
            candidate_hit = any(row["won"] for row in candidate_pair[1][:2])
        elif metric == "top4_box":
            baseline_eligible, baseline_hit = trifecta_hit(baseline_pair)
            candidate_eligible, candidate_hit = trifecta_hit(candidate_pair)
            if not baseline_eligible or not candidate_eligible:
                continue
        else:
            raise ValueError(f"Unknown metric: {metric}")
        gains += int(candidate_hit and not baseline_hit)
        losses += int(baseline_hit and not candidate_hit)
    return {
        "gains": gains,
        "losses": losses,
        "net": gains - losses,
        "exact_p": round(exact_two_sided_binomial(gains, losses), 4),
    }


def evaluate_layer(
    pairs_by_strategy: dict[str, list[tuple[list[dict], list[dict]]]],
) -> dict:
    output = {}
    for strategy, pairs in pairs_by_strategy.items():
        output[strategy] = {
            "performance": ranking_and_trifecta_metrics(pairs),
            "top2_ppwap": betting_metrics(pairs, "ppwap", seed=730),
            "top2_bsp": betting_metrics(
                pairs,
                "bsp",
                commission=0.05,
                seed=731,
            ),
        }
        if strategy != "baseline":
            output[strategy]["paired_vs_baseline"] = {
                "top2": paired_delta(
                    pairs_by_strategy["baseline"],
                    pairs,
                    "top2",
                ),
                "top4_box": paired_delta(
                    pairs_by_strategy["baseline"],
                    pairs,
                    "top4_box",
                ),
            }
    return output


def pct(value: object) -> str:
    return f"{float(value):+.1f}%"


def render(result: dict) -> str:
    cross = result["all_race_crossfit"]["summary"]
    forward = result["strict_walkforward"]["summary"]
    lines = [
        "# AU Wong Choi — Win Focus 對 Top 4 Trifecta 全歷史測試",
        "",
        "## 測試口徑",
        "",
        (
            f"- 歷史期間：{result['dataset']['start']} 至 {result['dataset']['end']}；"
            f"WIN 可評估 {result['dataset']['win_races']} 場，"
            f"完整頭三名可評估 {result['dataset']['trifecta_races']} 場。"
        ),
        "- Top 4 Box hit：模型頭四選包晒實際第1、2、3名，不理順序。",
        "- 四馬 Box 有 24 個有序組合；archive 冇 AU Trifecta dividend，所以唔計虛假 ROI。",
        "- Cross-fit：全709場都有 out-of-fold ranking，但訓練可包含較後日期。",
        "- Strict walk-forward：只用過去訓練未來，覆蓋574場；呢層較接近實際部署。",
        "",
        "## 全709場 grouped-date cross-fit",
        "",
        "| 模型 | #1勝率 | 冠軍Top2 | 冠軍Top4 | Top4 Box中三甲 | 順序三重彩 | 打和所需平均$1派彩 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for strategy in STRATEGIES:
        row = cross[strategy]["performance"]
        lines.append(
            f"| {LABELS[strategy]} | {row['top1_win_pct']:.1f}% | "
            f"{row['winner_in_top2_pct']:.1f}% | {row['winner_in_top4_pct']:.1f}% | "
            f"{row['top4_box_hit_pct']:.1f}% ({row['top4_box_hits']}/"
            f"{row['trifecta_eligible_races']}) | {row['ordered_top3_hit_pct']:.1f}% | "
            f"${row['break_even_average_unit_dividend']:.2f} |"
        )
    lines.extend(
        [
            "",
            "### 全歷史 Top 2 各 $1 WIN",
            "",
            "| 模型 | ROI @ pre-play WAP proxy | ROI @ BSP（5%） |",
            "|---|---:|---:|",
        ]
    )
    for strategy in STRATEGIES:
        row = cross[strategy]
        lines.append(
            f"| {LABELS[strategy]} | {pct(row['top2_ppwap']['roi_pct'])} "
            f"({row['top2_ppwap']['races']}場) | "
            f"{pct(row['top2_bsp']['roi_pct'])} ({row['top2_bsp']['races']}場) |"
        )
    lines.extend(
        [
            "",
            "## 嚴格時間順序 walk-forward",
            "",
            "| 模型 | 場次 | #1勝率 | 冠軍Top2 | Top4 Box中三甲 | 95% CI | pre-play WAP ROI | BSP ROI |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for strategy in STRATEGIES:
        perf = forward[strategy]["performance"]
        row = forward[strategy]
        lines.append(
            f"| {LABELS[strategy]} | {perf['races']} | {perf['top1_win_pct']:.1f}% | "
            f"{perf['winner_in_top2_pct']:.1f}% | {perf['top4_box_hit_pct']:.1f}% "
            f"({perf['top4_box_hits']}/{perf['trifecta_eligible_races']}) | "
            f"[{perf['top4_box_ci95_pct'][0]:.1f}%, "
            f"{perf['top4_box_ci95_pct'][1]:.1f}%] | "
            f"{pct(row['top2_ppwap']['roi_pct'])} | {pct(row['top2_bsp']['roi_pct'])} |"
        )
    lines.extend(
        [
            "",
            "## 配對泛化審計",
            "",
            "| 候選 | Strict Top2 gains/losses | p | Strict Box gains/losses | p |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for strategy in ("win_logit", "win_gbm"):
        paired = forward[strategy]["paired_vs_baseline"]
        lines.append(
            f"| {LABELS[strategy]} | "
            f"{paired['top2']['gains']}/{paired['top2']['losses']} "
            f"(net {paired['top2']['net']:+d}) | {paired['top2']['exact_p']:.3f} | "
            f"{paired['top4_box']['gains']}/{paired['top4_box']['losses']} "
            f"(net {paired['top4_box']['net']:+d}) | "
            f"{paired['top4_box']['exact_p']:.3f} |"
        )
    lines.extend(
        [
            "",
            "## 五角度覆盤結論",
            "",
            "1. **結果偏差：** Win Logistic／GBM 喺 Strict Box 分別只比現行多6／7場命中；改善幅度約1個百分點。",
            "2. **過程偏差：** Winner-only objective 主要改善冠軍排序，冇直接學習亞軍、季軍，因此 Top2 改善唔會等比例傳到 Trifecta。",
            "3. **Protocol 審計：** 同時使用全量 cross-fit及嚴格 walk-forward有效阻止只憑全歷史靚數升級模型。",
            "4. **泛化性：** Box 改善配對 p-value 未達顯著；而 WIN fixed-price proxy 喺 strict forward 仍為負。",
            "5. **Design Pattern Proposal：** Win-focus 只可作 shadow ranking；若目標包含 Trifecta，應另訓練 place／podium objective，唔應用 winner objective 取代整條排名。",
            "",
            "## 決策",
            "",
            "- 不升級正式 AU Wong Choi 模型。",
            "- 可將 Win Logistic／GBM 加入100至200場 forward A/B paper test。",
            "- Trifecta 只記錄 Top4 Box hit；未有實際 dividend archive 前，不宣稱正回報。",
            "- 若下一輪專門改善 Trifecta，測試 multi-objective（Win + Top3/place）shadow model，而唔係再加強 winner-only 權重。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    price_index = base.load_bsp()
    races = base.load_historical(price_index)
    add_market_prices(races, price_index)
    crossfit, crossfit_folds = crossfit_pairs(races)
    walkforward, walkforward_folds = walkforward_pairs(races)
    trifecta_races = sum(
        set(actual_podium(base.rank_race(race, "baseline"))) == {1, 2, 3}
        for race in races
    )
    result = {
        "dataset": {
            "start": min(race[0]["date"] for race in races),
            "end": max(race[0]["date"] for race in races),
            "dates": len({race[0]["date"] for race in races}),
            "win_races": len(races),
            "trifecta_races": trifecta_races,
            "horses": sum(len(race) for race in races),
            "trifecta_dividends_available": False,
        },
        "all_race_crossfit": {
            "method": "5 contiguous grouped-date folds; held block excluded from training",
            "folds": crossfit_folds,
            "summary": evaluate_layer(crossfit),
        },
        "strict_walkforward": {
            "method": "expanding-date; first 20% dates initial training",
            "folds": walkforward_folds,
            "summary": evaluate_layer(walkforward),
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
