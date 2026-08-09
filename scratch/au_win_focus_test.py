#!/usr/bin/env python3
"""Leak-free AU win-focus and Top-2 WIN strategy experiment.

Inputs are existing local research assets:
- stored pre-race ability/trainer scores (trainer-fix comparison cache);
- Racenet finish maps;
- Betfair historical WIN BSP files;
- the 2026-07-25 three-meeting scoring/results holdout.

Odds are used only to settle betting returns.  Win-focused candidate rankings
use pre-race model-derived fields and never receive BSP/morning price inputs.
"""
from __future__ import annotations

import csv
import json
import math
import random
import re
from collections import defaultdict
from pathlib import Path
from statistics import mean

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / "scratch"
SCORES_JSON = SCRATCH / "au_trainer_fix_scores.json"
FINISHES_JSON = SCRATCH / "au_finishes_map.json"
BSP_DIR = SCRATCH / "betfair_bsp"
OUT_JSON = SCRATCH / "au_win_focus_test_results.json"
OUT_MD = ROOT / "2026-07-29 AU Win Focus and Top2 WIN Strategy Test.md"
COMMISSION = 0.05

HOLDOUTS = (
    (
        "Randwick",
        SCRATCH / "au_reflector_2026-07-25/inputs/2026-07-25 Randwick Race 1-10/Meeting_Auto_Scoring.csv",
        SCRATCH / "au_reflector_2026-07-25/randwick/Race_Results_Randwick_2026-07-25.json",
    ),
    (
        "Caulfield",
        SCRATCH / "au_reflector_2026-07-25/inputs/2026-07-25 Caulfield Race 1-9/Meeting_Auto_Scoring.csv",
        SCRATCH / "au_reflector_2026-07-25/caulfield/Race_Results_Caulfield_2026-07-25.json",
    ),
    (
        "Eagle Farm",
        SCRATCH / "au_reflector_2026-07-25/inputs/2026-07-25 Eagle Farm Race 1-9/Meeting_Auto_Scoring.csv",
        SCRATCH / "au_reflector_2026-07-25/eagle_farm/Race_Results_Eagle_Farm_2026-07-25.json",
    ),
)


def norm_name(value: object) -> str:
    text = re.sub(r"^\s*\d+\.?\s*", "", str(value or "").lower())
    return re.sub(r"[^a-z0-9]", "", text)


def as_float(value: object, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def load_bsp() -> dict[tuple[str, str], dict]:
    index: dict[tuple[str, str], dict] = {}
    for path in sorted(BSP_DIR.glob("dwbfpricesauswin*.csv")):
        with path.open(encoding="utf-8-sig", errors="replace", newline="") as handle:
            for row in csv.DictReader(handle):
                match = re.match(r"(\d{2})-(\d{2})-(\d{4})", str(row.get("event_dt") or ""))
                horse = norm_name(row.get("selection_name"))
                if not match or not horse:
                    continue
                date = f"{match.group(3)}-{match.group(2)}-{match.group(1)}"
                key = (date, horse)
                # Horse names are effectively date-unique in the joined archive.
                # Keep the higher traded-volume row if another racing code reuses
                # a name on the same day.
                prior = index.get(key)
                volume = as_float(row.get("pptradedvol"), 0.0) or 0.0
                prior_volume = as_float((prior or {}).get("pptradedvol"), 0.0) or 0.0
                if prior is None or volume > prior_volume:
                    index[key] = row
    return index


def race_features(rows: list[dict]) -> None:
    ordered = sorted(rows, key=lambda row: (-row["ability"], row["horse_number"]))
    scores = [row["ability"] for row in ordered]
    avg = mean(scores)
    sd = math.sqrt(mean((score - avg) ** 2 for score in scores)) or 1.0
    trainer_avg = mean(row["trainer"] for row in ordered)
    field = len(ordered)
    for idx, row in enumerate(ordered, 1):
        row["baseline_rank"] = idx
        row["field_size"] = field
        row["ability_z"] = (row["ability"] - avg) / sd
        row["gap_to_top"] = scores[0] - row["ability"]
        row["rank_pct"] = (idx - 1) / max(1, field - 1)
        row["trainer_delta"] = row["trainer"] - trainer_avg
        row["number_pct"] = row["horse_number"] / max(1, max(r["horse_number"] for r in ordered))


def load_historical(bsp: dict[tuple[str, str], dict]) -> list[list[dict]]:
    scores = json.loads(SCORES_JSON.read_text())
    finishes = json.loads(FINISHES_JSON.read_text())
    races: list[list[dict]] = []
    for meeting, meeting_rows in scores.items():
        date_match = re.match(r"(\d{4}-\d{2}-\d{2})", meeting)
        finish_meeting = finishes.get(meeting) or {}
        if not date_match or not finish_meeting:
            continue
        date = date_match.group(1)
        for race_no, horse_rows in meeting_rows.items():
            finish_race = finish_meeting.get(str(race_no)) or {}
            race: list[dict] = []
            for number, source in horse_rows.items():
                result = finish_race.get(str(number))
                if not result or norm_name(result.get("name")) != norm_name(source.get("name")):
                    continue
                ability = as_float(source.get("old_ability"))
                finish = int(as_float(result.get("pos"), 99) or 99)
                if ability is None or finish <= 0:
                    continue
                price_row = bsp.get((date, norm_name(source.get("name"))))
                race.append(
                    {
                        "date": date,
                        "meeting": meeting,
                        "race": int(race_no),
                        "horse_number": int(number),
                        "horse_name": source.get("name") or result.get("name") or "",
                        "ability": ability,
                        "trainer": as_float(source.get("old_trainer"), 60.0) or 60.0,
                        "trainer_fill_ability": as_float(source.get("new_ability"), ability) or ability,
                        "finish": finish,
                        "won": finish == 1,
                        "bsp": as_float((price_row or {}).get("bsp")),
                        "morning": as_float((price_row or {}).get("morningwap")),
                    }
                )
            if len(race) >= 5 and sum(row["won"] for row in race) == 1:
                race_features(race)
                races.append(race)
    return sorted(races, key=lambda race: (race[0]["date"], race[0]["meeting"], race[0]["race"]))


def load_holdout() -> list[list[dict]]:
    races: list[list[dict]] = []
    for venue, scoring_path, result_path in HOLDOUTS:
        with scoring_path.open(encoding="utf-8-sig", newline="") as handle:
            scoring = list(csv.DictReader(handle))
        result_data = json.loads(result_path.read_text())
        by_race: dict[int, list[dict]] = defaultdict(list)
        for row in scoring:
            by_race[int(row["race_number"])].append(row)
        for race_no, score_rows in sorted(by_race.items()):
            result_rows = result_data["results"].get(str(race_no)) or []
            by_number = {str(item.get("competitor_number")): item for item in result_rows}
            race: list[dict] = []
            for source in score_rows:
                number = str(int(float(source["horse_number"])))
                result = by_number.get(number)
                if not result or result.get("is_scratched"):
                    continue
                finish = int(as_float(result.get("finish_position"), 99) or 99)
                if finish <= 0:
                    continue
                race.append(
                    {
                        "date": "2026-07-25",
                        "meeting": f"2026-07-25 {venue}",
                        "race": race_no,
                        "horse_number": int(number),
                        "horse_name": source["horse_name"],
                        "ability": float(source["ability_score"]),
                        "trainer": float(source["trainer_score"]),
                        "trainer_fill_ability": float(source["ability_score"]),
                        "finish": finish,
                        "won": finish == 1,
                        "sp": as_float(result.get("starting_price")),
                    }
                )
            if len(race) >= 5 and sum(row["won"] for row in race) == 1:
                race_features(race)
                races.append(race)
    return races


FEATURES = (
    "ability",
    "ability_z",
    "gap_to_top",
    "rank_pct",
    "field_size",
    "trainer_delta",
    "number_pct",
)


def xy(races: list[list[dict]]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rows = [row for race in races for row in race]
    x = np.asarray([[float(row[key]) for key in FEATURES] for row in rows], dtype=float)
    y = np.asarray([int(row["won"]) for row in rows], dtype=int)
    weights = np.asarray([1.0 / row["field_size"] for row in rows], dtype=float)
    return x, y, weights


def fit_models(train: list[list[dict]]) -> dict[str, object]:
    x, y, weights = xy(train)
    logit = make_pipeline(
        StandardScaler(),
        LogisticRegression(C=0.1, max_iter=2000, solver="lbfgs"),
    )
    logit.fit(x, y, logisticregression__sample_weight=weights)
    gbm = HistGradientBoostingClassifier(
        learning_rate=0.04,
        max_iter=120,
        max_leaf_nodes=7,
        min_samples_leaf=35,
        l2_regularization=2.0,
        random_state=17,
    )
    gbm.fit(x, y, sample_weight=weights)
    return {"win_logit": logit, "win_gbm": gbm}


def rank_race(race: list[dict], strategy: str, model: object | None = None) -> list[dict]:
    if strategy == "baseline":
        return sorted(race, key=lambda row: (-row["ability"], row["horse_number"]))
    if strategy == "trainer_fill":
        return sorted(race, key=lambda row: (-row["trainer_fill_ability"], row["horse_number"]))
    x = np.asarray([[float(row[key]) for key in FEATURES] for row in race], dtype=float)
    probabilities = model.predict_proba(x)[:, 1]
    return [
        row
        for _, row in sorted(
            zip(probabilities, race),
            key=lambda item: (-float(item[0]), item[1]["horse_number"]),
        )
    ]


def ranking_metrics(races: list[tuple[list[dict], list[dict]]]) -> dict:
    n = len(races)
    return {
        "races": n,
        "top1_win": sum(order[0]["won"] for _, order in races),
        "top1_win_pct": round(100 * sum(order[0]["won"] for _, order in races) / max(1, n), 2),
        "winner_in_top2": sum(any(row["won"] for row in order[:2]) for _, order in races),
        "winner_in_top2_pct": round(
            100 * sum(any(row["won"] for row in order[:2]) for _, order in races) / max(1, n), 2
        ),
        "changed_top1": sum(order[0]["horse_number"] != base[0]["horse_number"] for base, order in races),
        "changed_top2_set": sum(
            {row["horse_number"] for row in order[:2]} != {row["horse_number"] for row in base[:2]}
            for base, order in races
        ),
    }


def price_pnl(order: list[dict], price_key: str, top_n: int = 2) -> tuple[float, float]:
    selections = [row for row in order[:top_n] if row.get(price_key)]
    stakes = float(len(selections))
    if not selections:
        return 0.0, 0.0
    gross = sum(float(row[price_key]) for row in selections if row["won"]) - stakes
    net = gross * (1.0 - COMMISSION) if gross > 0 and price_key == "bsp" else gross
    return net, stakes


def betting_metrics(
    races: list[tuple[list[dict], list[dict]]],
    price_key: str,
    top_n: int = 2,
    bootstrap_seed: int = 29,
) -> dict:
    values = [price_pnl(order, price_key, top_n) for _, order in races]
    values = [value for value in values if value[1] > 0]
    pnl = sum(value[0] for value in values)
    stake = sum(value[1] for value in values)
    wins = sum(any(row["won"] and row.get(price_key) for row in order[:top_n]) for _, order in races)
    rng = random.Random(bootstrap_seed)
    boot = []
    if values:
        for _ in range(4000):
            sample = rng.choices(values, k=len(values))
            sample_stake = sum(item[1] for item in sample)
            boot.append(sum(item[0] for item in sample) / sample_stake if sample_stake else 0.0)
        boot.sort()
    return {
        "races": len(values),
        "bets": int(stake),
        "winning_races": wins,
        "strike_race_pct": round(100 * wins / max(1, len(values)), 2),
        "pnl": round(pnl, 2),
        "roi_pct": round(100 * pnl / max(1.0, stake), 2),
        "ci95_pct": (
            [round(100 * boot[int(0.025 * len(boot))], 2), round(100 * boot[int(0.975 * len(boot))], 2)]
            if boot
            else [0.0, 0.0]
        ),
    }


def single_rank_betting_metrics(
    races: list[tuple[list[dict], list[dict]]],
    price_key: str,
    rank_index: int,
    bootstrap_seed: int = 41,
) -> dict:
    values = []
    wins = 0
    for _, order in races:
        if len(order) <= rank_index or not order[rank_index].get(price_key):
            continue
        row = order[rank_index]
        gross = (float(row[price_key]) - 1.0) if row["won"] else -1.0
        net = gross * (1.0 - COMMISSION) if gross > 0 and price_key == "bsp" else gross
        values.append(net)
        wins += int(row["won"])
    rng = random.Random(bootstrap_seed)
    boot = []
    if values:
        for _ in range(4000):
            boot.append(sum(rng.choices(values, k=len(values))) / len(values))
        boot.sort()
    return {
        "bets": len(values),
        "wins": wins,
        "strike_pct": round(100 * wins / max(1, len(values)), 2),
        "pnl": round(sum(values), 2),
        "roi_pct": round(100 * sum(values) / max(1, len(values)), 2),
        "ci95_pct": (
            [round(100 * boot[int(0.025 * len(boot))], 2), round(100 * boot[int(0.975 * len(boot))], 2)]
            if boot
            else [0.0, 0.0]
        ),
    }


def consensus_betting_metrics(
    races: list[list[dict]],
    market_key: str,
    settle_key: str,
    bootstrap_seed: int = 91,
) -> dict:
    """Bet model Top 2 only when the horse is also market Top 2."""
    values: list[tuple[float, float]] = []
    wins = bets = 0
    for race in races:
        model_top2 = rank_race(race, "baseline")[:2]
        priced = [row for row in race if row.get(market_key) and row.get(settle_key)]
        market_top2 = sorted(priced, key=lambda row: (row[market_key], row["horse_number"]))[:2]
        market_ids = {row["horse_number"] for row in market_top2}
        selections = [row for row in model_top2 if row["horse_number"] in market_ids and row.get(settle_key)]
        if not selections:
            continue
        stake = float(len(selections))
        gross = sum(float(row[settle_key]) for row in selections if row["won"]) - stake
        net = gross * (1.0 - COMMISSION) if gross > 0 and settle_key == "bsp" else gross
        values.append((net, stake))
        bets += len(selections)
        wins += sum(int(row["won"]) for row in selections)
    pnl = sum(item[0] for item in values)
    stake = sum(item[1] for item in values)
    rng = random.Random(bootstrap_seed)
    boot = []
    if values:
        for _ in range(4000):
            sample = rng.choices(values, k=len(values))
            boot.append(sum(item[0] for item in sample) / sum(item[1] for item in sample))
        boot.sort()
    return {
        "races": len(values),
        "bets": bets,
        "wins": wins,
        "strike_pct": round(100 * wins / max(1, bets), 2),
        "pnl": round(pnl, 2),
        "roi_pct": round(100 * pnl / max(1.0, stake), 2),
        "ci95_pct": (
            [round(100 * boot[int(0.025 * len(boot))], 2), round(100 * boot[int(0.975 * len(boot))], 2)]
            if boot
            else [0.0, 0.0]
        ),
    }


def date_folds(races: list[list[dict]], folds: int = 5) -> list[tuple[list[list[dict]], list[list[dict]]]]:
    dates = sorted({race[0]["date"] for race in races})
    start = max(1, int(len(dates) * 0.5))
    valid_dates = dates[start:]
    fold_size = max(1, math.ceil(len(valid_dates) / folds))
    output = []
    for idx in range(0, len(valid_dates), fold_size):
        fold_dates = set(valid_dates[idx : idx + fold_size])
        first_valid = min(fold_dates)
        train = [race for race in races if race[0]["date"] < first_valid]
        valid = [race for race in races if race[0]["date"] in fold_dates]
        if train and valid:
            output.append((train, valid))
    return output


def evaluate_walk_forward(races: list[list[dict]]) -> tuple[dict, dict[str, list[tuple[list[dict], list[dict]]]]]:
    accumulated: dict[str, list[tuple[list[dict], list[dict]]]] = defaultdict(list)
    fold_rows = []
    for fold_no, (train, valid) in enumerate(date_folds(races), 1):
        models = fit_models(train)
        fold_result = {"fold": fold_no, "train_races": len(train), "valid_races": len(valid)}
        for strategy in ("baseline", "trainer_fill", "win_logit", "win_gbm"):
            model = models.get(strategy)
            pairs = []
            for race in valid:
                base = rank_race(race, "baseline")
                order = rank_race(race, strategy, model)
                pairs.append((base, order))
            accumulated[strategy].extend(pairs)
            fold_result[strategy] = ranking_metrics(pairs)
        fold_rows.append(fold_result)
    summary = {}
    for strategy, pairs in accumulated.items():
        dates = [order[0]["date"] for _, order in pairs]
        midpoint = sorted(set(dates))[len(set(dates)) // 2] if dates else ""
        first = [pair for pair in pairs if pair[1][0]["date"] < midpoint]
        second = [pair for pair in pairs if pair[1][0]["date"] >= midpoint]
        summary[strategy] = {
            "ranking": ranking_metrics(pairs),
            "top2_bsp": betting_metrics(pairs, "bsp", top_n=2),
            "rank1_bsp": betting_metrics(pairs, "bsp", top_n=1),
            "top2_morning": betting_metrics(pairs, "morning", top_n=2),
            "split_half_top2_bsp": {
                "first": betting_metrics(first, "bsp", top_n=2),
                "second": betting_metrics(second, "bsp", top_n=2),
            },
        }
    return {"folds": fold_rows, "summary": summary}, accumulated


def evaluate_full_baseline(races: list[list[dict]]) -> dict:
    pairs = []
    for race in races:
        base = rank_race(race, "baseline")
        pairs.append((base, base))
    dates = sorted({race[0]["date"] for race in races})
    midpoint = dates[len(dates) // 2]
    first_races = [race for race in races if race[0]["date"] < midpoint]
    second_races = [race for race in races if race[0]["date"] >= midpoint]
    return {
        "ranking": ranking_metrics(pairs),
        "top2_bsp": betting_metrics(pairs, "bsp", top_n=2),
        "rank1_bsp": betting_metrics(pairs, "bsp", top_n=1),
        "rank2_bsp": single_rank_betting_metrics(pairs, "bsp", rank_index=1),
        "top2_morning": betting_metrics(pairs, "morning", top_n=2),
        "split_half_top2_bsp": {
            "first": betting_metrics(
                [(rank_race(race, "baseline"), rank_race(race, "baseline")) for race in first_races],
                "bsp",
                top_n=2,
            ),
            "second": betting_metrics(
                [(rank_race(race, "baseline"), rank_race(race, "baseline")) for race in second_races],
                "bsp",
                top_n=2,
            ),
        },
        "morning_consensus_bsp": consensus_betting_metrics(races, "morning", "bsp"),
        "split_half_morning_consensus_bsp": {
            "first": consensus_betting_metrics(first_races, "morning", "bsp"),
            "second": consensus_betting_metrics(second_races, "morning", "bsp"),
        },
    }


def evaluate_holdout(history: list[list[dict]], holdout: list[list[dict]]) -> dict:
    models = fit_models(history)
    output = {}
    for strategy in ("baseline", "trainer_fill", "win_logit", "win_gbm"):
        pairs = []
        for race in holdout:
            base = rank_race(race, "baseline")
            order = rank_race(race, strategy, models.get(strategy))
            pairs.append((base, order))
        output[strategy] = {
            "ranking": ranking_metrics(pairs),
            "top2_sp": betting_metrics(pairs, "sp", top_n=2),
            "rank1_sp": betting_metrics(pairs, "sp", top_n=1),
        }
    output["market_consensus"] = consensus_betting_metrics(holdout, "sp", "sp")
    return output


def pct(value: object) -> str:
    return f"{float(value):+.1f}%"


def render_report(result: dict) -> str:
    full = result["full_baseline"]
    wf = result["walk_forward"]["summary"]
    hold = result["holdout_2026_07_25"]
    lines = [
        "# AU Wong Choi — Win-focused 模型 + Top 2 WIN 投注測試",
        "",
        "## 測試口徑",
        "",
        f"- 歷史可比對：{result['history_races']} 場；Betfair WIN BSP files：{result['bsp_files']}。",
        "- 每場 Top 2 各 $1 WIN；Betfair 5% commission 按同一 market 淨盈利計。",
        "- Odds 只用作結算 ROI，冇輸入 win-focused 排名。",
        "- 模型候選用 expanding-date walk-forward；2026-07-25 三地為額外未見 holdout。",
        "",
        "## 現行 Top 2 全買 WIN — 全歷史點估",
        "",
        "| 策略 | 場次 | Bets | 捉到冠軍 | P&L | ROI @ BSP | 95% bootstrap CI | ROI @ morning |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
        (
            f"| 現行 #1+#2 各 $1 | {full['top2_bsp']['races']} | {full['top2_bsp']['bets']} | "
            f"{full['top2_bsp']['strike_race_pct']:.1f}% | {full['top2_bsp']['pnl']:+.2f} | "
            f"{pct(full['top2_bsp']['roi_pct'])} | "
            f"[{pct(full['top2_bsp']['ci95_pct'][0])}, {pct(full['top2_bsp']['ci95_pct'][1])}] | "
            f"{pct(full['top2_morning']['roi_pct'])} |"
        ),
        (
            f"| 現行 #1 單買 | {full['rank1_bsp']['races']} | {full['rank1_bsp']['bets']} | "
            f"{full['rank1_bsp']['strike_race_pct']:.1f}% | {full['rank1_bsp']['pnl']:+.2f} | "
            f"{pct(full['rank1_bsp']['roi_pct'])} | "
            f"[{pct(full['rank1_bsp']['ci95_pct'][0])}, {pct(full['rank1_bsp']['ci95_pct'][1])}] | — |"
        ),
        (
            f"| 現行 #2 單買 | — | {full['rank2_bsp']['bets']} | "
            f"{full['rank2_bsp']['strike_pct']:.1f}% | {full['rank2_bsp']['pnl']:+.2f} | "
            f"{pct(full['rank2_bsp']['roi_pct'])} | "
            f"[{pct(full['rank2_bsp']['ci95_pct'][0])}, {pct(full['rank2_bsp']['ci95_pct'][1])}] | — |"
        ),
        "",
        "### 穩定性與可執行 market gate",
        "",
        "| 策略 | 全期 ROI | 前半 ROI | 後半 ROI | 95% CI |",
        "|---|---:|---:|---:|---:|",
        (
            f"| Top2 全買 @ BSP | {pct(full['top2_bsp']['roi_pct'])} | "
            f"{pct(full['split_half_top2_bsp']['first']['roi_pct'])} | "
            f"{pct(full['split_half_top2_bsp']['second']['roi_pct'])} | "
            f"[{pct(full['top2_bsp']['ci95_pct'][0])}, {pct(full['top2_bsp']['ci95_pct'][1])}] |"
        ),
        (
            f"| Model Top2 ∩ morning-market Top2，再取 BSP | "
            f"{pct(full['morning_consensus_bsp']['roi_pct'])} | "
            f"{pct(full['split_half_morning_consensus_bsp']['first']['roi_pct'])} | "
            f"{pct(full['split_half_morning_consensus_bsp']['second']['roi_pct'])} | "
            f"[{pct(full['morning_consensus_bsp']['ci95_pct'][0])}, "
            f"{pct(full['morning_consensus_bsp']['ci95_pct'][1])}] |"
        ),
        "",
        "## Win-focused 候選 — Walk-forward OOS",
        "",
        "| 模型 | 場次 | #1 勝率 | 冠軍在 Top 2 | Top2改動 | ROI @ BSP | 前半 ROI | 後半 ROI |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    labels = {
        "baseline": "現行 7D",
        "trainer_fill": "Trainer-fill 重分",
        "win_logit": "Win logistic",
        "win_gbm": "Win GBM",
    }
    for key in ("baseline", "trainer_fill", "win_logit", "win_gbm"):
        row = wf[key]
        rank = row["ranking"]
        bet = row["top2_bsp"]
        halves = row["split_half_top2_bsp"]
        lines.append(
            f"| {labels[key]} | {rank['races']} | {rank['top1_win_pct']:.1f}% | "
            f"{rank['winner_in_top2_pct']:.1f}% | {rank['changed_top2_set']} | "
            f"{pct(bet['roi_pct'])} | {pct(halves['first']['roi_pct'])} | "
            f"{pct(halves['second']['roi_pct'])} |"
        )
    lines.extend(
        [
            "",
            "## 2026-07-25 Randwick／Caulfield／Eagle Farm Holdout",
            "",
            "| 模型 | #1 勝率 | 冠軍在 Top 2 | Top2改動 | Top2 ROI @ Racenet SP | #1 ROI @ SP |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for key in ("baseline", "trainer_fill", "win_logit", "win_gbm"):
        row = hold[key]
        lines.append(
            f"| {labels[key]} | {row['ranking']['top1_win_pct']:.1f}% | "
            f"{row['ranking']['winner_in_top2_pct']:.1f}% | {row['ranking']['changed_top2_set']} | "
            f"{pct(row['top2_sp']['roi_pct'])} | {pct(row['rank1_sp']['roi_pct'])} |"
        )
    consensus = hold["market_consensus"]
    lines.extend(
        [
            "",
            (
                f"- 三地 holdout：Model Top2 ∩ SP-market Top2 共 {consensus['bets']} 注，"
                f"中 {consensus['wins']} 注，ROI {pct(consensus['roi_pct'])}。"
            ),
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    bsp = load_bsp()
    history = load_historical(bsp)
    holdout = load_holdout()
    walk_forward, _ = evaluate_walk_forward(history)
    result = {
        "history_races": len(history),
        "history_horses": sum(len(race) for race in history),
        "bsp_files": len(list(BSP_DIR.glob("dwbfpricesauswin*.csv"))),
        "bsp_rows": len(bsp),
        "full_baseline": evaluate_full_baseline(history),
        "walk_forward": walk_forward,
        "holdout_races": len(holdout),
        "holdout_2026_07_25": evaluate_holdout(history, holdout),
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    report = render_report(result)
    OUT_MD.write_text(report, encoding="utf-8")
    print(report)
    print(f"JSON: {OUT_JSON}")
    print(f"Report: {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
