#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import glob
import json
import math
import os
import re
import shutil
import sqlite3
import subprocess
import sys

os.environ.setdefault("PYTHONUTF8", "1")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REFLECTOR_DIR = os.path.dirname(SCRIPT_DIR)
NBA_DIR = os.path.dirname(REFLECTOR_DIR)
AGENTS_DIR = os.path.dirname(os.path.dirname(NBA_DIR))
WORKSPACE_ROOT = os.path.dirname(AGENTS_DIR)

PYTHON = "python3" if shutil.which("python3") else "python"

FETCH_RESULTS = os.path.join(SCRIPT_DIR, "fetch_nba_results.py")
FETCH_PBP = os.path.join(SCRIPT_DIR, "fetch_nba_pbp.py")
VERIFY_PROPS = os.path.join(SCRIPT_DIR, "verify_props_hits.py")
DB_PATH = os.path.join(WORKSPACE_ROOT, "nba_reflector.db")

STAT_ALIASES = {
    "points": "pts",
    "pts": "pts",
    "rebounds": "reb",
    "reb": "reb",
    "rebs": "reb",
    "assists": "ast",
    "ast": "ast",
    "threes": "fg3m",
    "3pm": "fg3m",
    "fg3m": "fg3m",
    "threes made": "fg3m",
    "made threes": "fg3m",
    "steals": "stl",
    "stl": "stl",
    "blocks": "blk",
    "blk": "blk",
    "turnovers": "tov",
    "tov": "tov",
    "pts+reb+ast": "pra",
    "pra": "pra",
    "pts+reb": "pr",
    "pr": "pr",
    "pts+ast": "pa",
    "pa": "pa",
    "reb+ast": "ra",
    "ra": "ra",
    "stl+blk": "sb",
    "sb": "sb",
}

FEATURE_STAT_ORDER = ["pts", "reb", "ast", "fg3m", "pra", "pr", "pa", "ra", "sb", "stl", "blk", "tov"]


def _python_cmd(script_path: str, args: list[str]) -> list[str]:
    return [PYTHON, script_path] + args


def run_script(script_path: str, args: list[str], label: str) -> None:
    if not os.path.exists(script_path):
        raise FileNotFoundError(f"{label} script not found: {script_path}")
    cmd = _python_cmd(script_path, args)
    print(f"🔧 [{label}] {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout.strip())
    if result.returncode != 0:
        if result.stderr:
            print(result.stderr.strip())
        raise RuntimeError(f"{label} failed with exit code {result.returncode}")


def normalize_stat(value: str | None) -> str:
    if not value:
        return "unknown"
    key = value.lower().strip()
    return STAT_ALIASES.get(key, key)


def clamp_prob(prob: float | None) -> float:
    if prob is None:
        return 0.5
    return max(0.01, min(0.99, prob))


def parse_date(date_str: str) -> dt.date:
    return dt.datetime.strptime(date_str, "%Y-%m-%d").date()


def analysis_to_us_date(analysis_date: str) -> str:
    return (parse_date(analysis_date) - dt.timedelta(days=1)).strftime("%Y-%m-%d")


def resolve_target_dir(analysis_date: str, explicit_dir: str | None) -> str:
    if explicit_dir:
        return os.path.abspath(explicit_dir)
    return os.path.join(WORKSPACE_ROOT, f"{analysis_date} NBA Analysis")


def ensure_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reflector_legs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_date TEXT NOT NULL,
            us_game_date TEXT NOT NULL,
            game_tag TEXT NOT NULL,
            combo_id TEXT,
            report_file TEXT NOT NULL,
            player_name TEXT NOT NULL,
            team_abbr TEXT,
            prop_stat TEXT NOT NULL,
            line REAL NOT NULL,
            odds REAL,
            implied_prob REAL,
            predicted_prob REAL,
            edge_pct REAL,
            l10_hit_rate REAL,
            l10_hits INTEGER,
            l10_total INTEGER,
            l10_avg REAL,
            l10_med REAL,
            l10_sd REAL,
            cov_label TEXT,
            actual_value REAL,
            actual_minutes TEXT,
            margin REAL,
            cleared INTEGER,
            status TEXT,
            final_score TEXT,
            model_version TEXT,
            odds_source TEXT,
            raw_l10_json TEXT,
            source_run_key TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(source_run_key, game_tag, combo_id, player_name, prop_stat, line)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reflector_model_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_date TEXT NOT NULL,
            training_rows INTEGER NOT NULL,
            test_rows INTEGER NOT NULL,
            split_summary TEXT NOT NULL,
            baseline_brier REAL,
            ml_brier REAL,
            baseline_accuracy REAL,
            ml_accuracy REAL,
            summary_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()


def extract_game_tag_from_filename(path: str) -> str:
    base = os.path.basename(path)
    patterns = [
        r"Game_([A-Z]{2,4}_[A-Z]{2,4})_Full_Analysis\.(?:md|txt)$",
        r"_NBA_([A-Z]{2,4})_([A-Z]{2,4})_Analysis\.md$",
    ]
    for pattern in patterns:
        match = re.search(pattern, base)
        if not match:
            continue
        if len(match.groups()) == 1:
            return match.group(1)
        return f"{match.group(1)}_{match.group(2)}"
    return base


def parse_report_metadata(content: str) -> dict[str, str]:
    odds_source = ""
    model_version = ""
    for line in content.splitlines():
        if not odds_source:
            match = re.search(r"odds_source\**:\s*([A-Z_]+)", line)
            if match:
                odds_source = match.group(1)
        if not model_version and "引擎版本" in line:
            match = re.search(r"引擎版本\**:\s*(.+)", line)
            if match:
                model_version = match.group(1).strip()
        if odds_source and model_version:
            break
    return {
        "odds_source": odds_source or "UNKNOWN",
        "model_version": model_version or "UNKNOWN",
    }


def iter_leg_blocks(content: str):
    current_combo = "?"
    current_header = None
    current_lines: list[str] = []
    combo_re = re.compile(r"(?:###?\s*)?(?:🛡️|🔥|💎|💣)\s*(?:組合|Combo|SGM)\s*(\d+|X)", re.IGNORECASE)
    leg_re = re.compile(r"(?:####|###|\*\*)\s*.*Leg\s*\d+", re.IGNORECASE)

    def flush():
        nonlocal current_header, current_lines
        if current_header:
            yield current_combo, current_header, "\n".join(current_lines)
        current_header = None
        current_lines = []

    for line in content.splitlines():
        combo_match = combo_re.search(line)
        if combo_match:
            current_combo = combo_match.group(1)
        if leg_re.search(line):
            yield from flush()
            current_header = line.strip()
            current_lines = [line.strip()]
            continue
        if current_header:
            current_lines.append(line.rstrip())
    yield from flush()


def _extract_float(pattern: str, text: str) -> float | None:
    match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _extract_ints(pattern: str, text: str) -> tuple[int, int, float] | None:
    match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), float(match.group(3))


def _extract_l10_values(text: str) -> list[float]:
    match = re.search(r"L10(?:\s*逐場)?\**[:：]?\**\s*`?(\[[^\]]+\])`?", text, re.IGNORECASE | re.MULTILINE)
    if not match:
        return []
    raw = match.group(1)
    try:
        values = json.loads(raw)
        return [float(v) for v in values]
    except Exception:
        nums = re.findall(r"-?\d+(?:\.\d+)?", raw)
        return [float(v) for v in nums]


def _infer_stats_from_l10(values: list[float]) -> tuple[float | None, float | None, float | None]:
    if not values:
        return None, None, None
    avg = sum(values) / len(values)
    ordered = sorted(values)
    if len(ordered) % 2 == 0:
        med = (ordered[len(ordered) // 2 - 1] + ordered[len(ordered) // 2]) / 2
    else:
        med = ordered[len(ordered) // 2]
    variance = sum((v - avg) ** 2 for v in values) / len(values)
    return round(avg, 2), round(med, 2), round(math.sqrt(variance), 2)


def parse_leg_block(
    header: str,
    block_text: str,
    combo_id: str,
    analysis_date: str,
    us_game_date: str,
    game_tag: str,
    report_file: str,
    report_meta: dict[str, str],
) -> dict | None:
    header_patterns = [
        re.compile(
            r"Leg\s*(\d+)\s*[:：]\s*(.+?)\s*\(([A-Z]{2,4})\)\s*-\s*(\d+(?:\.\d+)?)\+\s*([A-Z0-9+]+)",
            re.IGNORECASE,
        ),
        re.compile(
            r"Leg\s*(\d+)\s*[:：]\s*(.+?)\s+(PTS|REB|AST|3PM|PRA|PR|PA|RA|SB|STL|BLK|TOV|Points|Rebounds|Assists|Threes Made?)\s*(?:Over\s*)?(\d+(?:\.\d+)?)",
            re.IGNORECASE,
        ),
    ]

    player_name = ""
    team_abbr = ""
    stat = ""
    line = None
    for pattern in header_patterns:
        match = pattern.search(header)
        if not match:
            continue
        if pattern is header_patterns[0]:
            _, player_name, team_abbr, line_str, stat = match.groups()
        else:
            _, player_name, stat, line_str = match.groups()
        player_name = player_name.replace("**", "").strip(" -")
        stat = normalize_stat(stat)
        line = float(line_str)
        break

    if not player_name or line is None or not stat:
        return None

    odds = _extract_float(r"賠率[^@\n]*@(\d+(?:\.\d+)?)", block_text)
    implied_prob = _extract_float(r"隱含(?:機率|勝率)\**[^0-9+\-]*(\d+(?:\.\d+)?)%", block_text)
    predicted_prob = _extract_float(r"預期勝率(?:\(Adj Prob\))?\**[^0-9+\-]*(\d+(?:\.\d+)?)%", block_text)
    edge_pct = _extract_float(r"Edge\**[:：]?\**\s*([+\-]?\d+(?:\.\d+)?)%", block_text)
    l10_hit = _extract_ints(r"L10 命中\**[:：]?\**\s*(?:⚠️\s*)?(\d+)\/(\d+)\s*\((\d+(?:\.\d+)?)%\)", block_text)
    l10_values = _extract_l10_values(block_text)
    avg = _extract_float(r"AVG\s+([+\-]?\d+(?:\.\d+)?)", block_text)
    med = _extract_float(r"MED\s+([+\-]?\d+(?:\.\d+)?)", block_text)
    sd = _extract_float(r"SD\s+([+\-]?\d+(?:\.\d+)?)", block_text)
    if avg is None or med is None or sd is None:
        inferred_avg, inferred_med, inferred_sd = _infer_stats_from_l10(l10_values)
        avg = avg if avg is not None else inferred_avg
        med = med if med is not None else inferred_med
        sd = sd if sd is not None else inferred_sd

    cov_match = re.search(r"CoV[:：]\s*(.+)", block_text)
    cov_label = cov_match.group(1).replace("*", "").strip() if cov_match else ""

    return {
        "analysis_date": analysis_date,
        "us_game_date": us_game_date,
        "game_tag": game_tag,
        "combo_id": combo_id,
        "report_file": report_file,
        "player_name": player_name,
        "team_abbr": team_abbr or game_tag.split("_")[0],
        "prop_stat": stat,
        "line": line,
        "odds": odds,
        "implied_prob": implied_prob,
        "predicted_prob": predicted_prob,
        "edge_pct": edge_pct,
        "l10_hit_rate": l10_hit[2] if l10_hit else None,
        "l10_hits": l10_hit[0] if l10_hit else None,
        "l10_total": l10_hit[1] if l10_hit else None,
        "l10_avg": avg,
        "l10_med": med,
        "l10_sd": sd,
        "cov_label": cov_label,
        "raw_l10_json": json.dumps(l10_values),
        "odds_source": report_meta["odds_source"],
        "model_version": report_meta["model_version"],
        "source_run_key": analysis_date,
    }


def load_prediction_rows(target_dir: str, analysis_date: str, us_game_date: str) -> list[dict]:
    reports = sorted(
        glob.glob(os.path.join(target_dir, "*_NBA_*_Analysis.md"))
        + glob.glob(os.path.join(target_dir, "Game_*_Full_Analysis.md"))
        + glob.glob(os.path.join(target_dir, "Game_*_Full_Analysis.txt"))
    )
    rows: list[dict] = []
    for report_path in reports:
        with open(report_path, "r", encoding="utf-8") as f:
            content = f.read()
        game_tag = extract_game_tag_from_filename(report_path)
        report_meta = parse_report_metadata(content)
        for combo_id, header, block_text in iter_leg_blocks(content):
            row = parse_leg_block(
                header,
                block_text,
                combo_id,
                analysis_date,
                us_game_date,
                game_tag,
                os.path.basename(report_path),
                report_meta,
            )
            if row:
                rows.append(row)
    return rows


def load_verification_index(verification_path: str) -> dict[tuple[str, str, float], dict]:
    with open(verification_path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    index: dict[tuple[str, str, float], dict] = {}
    for leg in payload.get("legs", []):
        player = leg.get("player", "").strip().lower()
        stat = normalize_stat(leg.get("stat_normalized") or leg.get("stat"))
        try:
            line = float(leg.get("line"))
        except (TypeError, ValueError):
            continue
        index[(player, stat, line)] = leg
    return index


def attach_verification(rows: list[dict], verification_index: dict[tuple[str, str, float], dict]) -> list[dict]:
    attached = []
    for row in rows:
        key = (row["player_name"].strip().lower(), row["prop_stat"], float(row["line"]))
        verified = verification_index.get(key, {})
        row = row | {
            "actual_value": verified.get("actual"),
            "actual_minutes": verified.get("minutes"),
            "margin": verified.get("margin"),
            "cleared": None if verified.get("cleared") is None else int(bool(verified.get("cleared"))),
            "status": verified.get("status"),
            "final_score": verified.get("game"),
        }
        attached.append(row)
    return attached


def write_training_snapshot(rows: list[dict], target_dir: str, analysis_date: str) -> str:
    out_path = os.path.join(target_dir, f"Reflector_Training_Snapshot_{analysis_date}.csv")
    fieldnames = [
        "analysis_date",
        "us_game_date",
        "game_tag",
        "combo_id",
        "report_file",
        "player_name",
        "team_abbr",
        "prop_stat",
        "line",
        "odds",
        "implied_prob",
        "predicted_prob",
        "edge_pct",
        "l10_hit_rate",
        "l10_hits",
        "l10_total",
        "l10_avg",
        "l10_med",
        "l10_sd",
        "cov_label",
        "actual_value",
        "actual_minutes",
        "margin",
        "cleared",
        "status",
        "final_score",
        "model_version",
        "odds_source",
    ]
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fieldnames})
    return out_path


def upsert_rows(conn: sqlite3.Connection, rows: list[dict]) -> int:
    now = dt.datetime.now().isoformat()
    count = 0
    for row in rows:
        conn.execute(
            """
            INSERT INTO reflector_legs (
                analysis_date, us_game_date, game_tag, combo_id, report_file, player_name, team_abbr,
                prop_stat, line, odds, implied_prob, predicted_prob, edge_pct, l10_hit_rate, l10_hits,
                l10_total, l10_avg, l10_med, l10_sd, cov_label, actual_value, actual_minutes, margin,
                cleared, status, final_score, model_version, odds_source, raw_l10_json, source_run_key,
                created_at, updated_at
            ) VALUES (
                :analysis_date, :us_game_date, :game_tag, :combo_id, :report_file, :player_name, :team_abbr,
                :prop_stat, :line, :odds, :implied_prob, :predicted_prob, :edge_pct, :l10_hit_rate, :l10_hits,
                :l10_total, :l10_avg, :l10_med, :l10_sd, :cov_label, :actual_value, :actual_minutes, :margin,
                :cleared, :status, :final_score, :model_version, :odds_source, :raw_l10_json, :source_run_key,
                :created_at, :updated_at
            )
            ON CONFLICT(source_run_key, game_tag, combo_id, player_name, prop_stat, line)
            DO UPDATE SET
                odds=excluded.odds,
                implied_prob=excluded.implied_prob,
                predicted_prob=excluded.predicted_prob,
                edge_pct=excluded.edge_pct,
                l10_hit_rate=excluded.l10_hit_rate,
                l10_hits=excluded.l10_hits,
                l10_total=excluded.l10_total,
                l10_avg=excluded.l10_avg,
                l10_med=excluded.l10_med,
                l10_sd=excluded.l10_sd,
                cov_label=excluded.cov_label,
                actual_value=excluded.actual_value,
                actual_minutes=excluded.actual_minutes,
                margin=excluded.margin,
                cleared=excluded.cleared,
                status=excluded.status,
                final_score=excluded.final_score,
                model_version=excluded.model_version,
                odds_source=excluded.odds_source,
                raw_l10_json=excluded.raw_l10_json,
                updated_at=excluded.updated_at
            """,
            row | {"created_at": now, "updated_at": now},
        )
        count += 1
    conn.commit()
    return count


def cov_bucket(label: str | None) -> float:
    text = (label or "").lower()
    if "極穩" in text:
        return 0.0
    if "穩定" in text:
        return 1.0
    if "中波" in text or "一般波動" in text:
        return 2.0
    if "神經刀" in text:
        return 3.0
    return 1.5


def build_feature_vector(row: sqlite3.Row | dict) -> list[float]:
    stat = normalize_stat(row["prop_stat"])
    vector = [
        float(row["line"] or 0.0),
        float(row["odds"] or 0.0),
        float(row["implied_prob"] or 0.0),
        float(row["predicted_prob"] or row["l10_hit_rate"] or 0.0),
        float(row["edge_pct"] or 0.0),
        float(row["l10_hit_rate"] or 0.0),
        float((row["l10_avg"] or 0.0) - (row["line"] or 0.0)),
        float((row["l10_med"] or 0.0) - (row["line"] or 0.0)),
        float(row["l10_sd"] or 0.0),
        cov_bucket(row.get("cov_label") if isinstance(row, dict) else row["cov_label"]),
    ]
    for feature_stat in FEATURE_STAT_ORDER:
        vector.append(1.0 if stat == feature_stat else 0.0)
    return vector


def standardize_features(vectors: list[list[float]]) -> tuple[list[list[float]], list[float], list[float]]:
    feature_count = len(vectors[0])
    means = []
    stds = []
    for idx in range(feature_count):
        values = [vec[idx] for vec in vectors]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        std = math.sqrt(variance) or 1.0
        means.append(mean)
        stds.append(std)

    normalized = []
    for vec in vectors:
        normalized.append([(value - means[idx]) / stds[idx] for idx, value in enumerate(vec)])
    return normalized, means, stds


def sigmoid(value: float) -> float:
    if value >= 0:
        exp_val = math.exp(-value)
        return 1.0 / (1.0 + exp_val)
    exp_val = math.exp(value)
    return exp_val / (1.0 + exp_val)


def fit_logistic_regression(rows: list[sqlite3.Row]) -> dict:
    vectors = [build_feature_vector(row) for row in rows]
    labels = [int(row["cleared"]) for row in rows]
    normalized, means, stds = standardize_features(vectors)
    weights = [0.0 for _ in range(len(normalized[0]))]
    bias = 0.0
    lr = 0.15
    l2 = 0.001

    for _ in range(900):
        grad_w = [0.0 for _ in weights]
        grad_b = 0.0
        for vec, label in zip(normalized, labels):
            score = bias + sum(weight * value for weight, value in zip(weights, vec))
            pred = sigmoid(score)
            diff = pred - label
            for idx, value in enumerate(vec):
                grad_w[idx] += diff * value
            grad_b += diff
        n = len(normalized)
        for idx in range(len(weights)):
            grad = (grad_w[idx] / n) + l2 * weights[idx]
            weights[idx] -= lr * grad
        bias -= lr * (grad_b / n)

    feature_names = [
        "line",
        "odds",
        "implied_prob",
        "predicted_prob",
        "edge_pct",
        "l10_hit_rate",
        "avg_minus_line",
        "med_minus_line",
        "l10_sd",
        "cov_bucket",
    ] + [f"stat_{stat}" for stat in FEATURE_STAT_ORDER]

    return {
        "weights": weights,
        "bias": bias,
        "means": means,
        "stds": stds,
        "feature_names": feature_names,
    }


def predict_probability(model: dict, row: sqlite3.Row) -> float:
    vector = build_feature_vector(row)
    normalized = [
        (value - model["means"][idx]) / model["stds"][idx]
        for idx, value in enumerate(vector)
    ]
    score = model["bias"] + sum(weight * value for weight, value in zip(model["weights"], normalized))
    return clamp_prob(sigmoid(score))


def brier_score(probs: list[float], labels: list[int]) -> float:
    return sum((prob - label) ** 2 for prob, label in zip(probs, labels)) / len(labels)


def accuracy(probs: list[float], labels: list[int], threshold: float = 0.5) -> float:
    hits = 0
    for prob, label in zip(probs, labels):
        pred = 1 if prob >= threshold else 0
        hits += int(pred == label)
    return hits / len(labels)


def bucket_summary(probs: list[float], labels: list[int]) -> list[dict]:
    buckets = [(0.0, 0.55), (0.55, 0.65), (0.65, 0.75), (0.75, 1.01)]
    summary = []
    for low, high in buckets:
        chosen = [(prob, label) for prob, label in zip(probs, labels) if low <= prob < high]
        if not chosen:
            continue
        hit_rate = sum(label for _, label in chosen) / len(chosen)
        summary.append(
            {
                "bucket": f"{int(low * 100)}-{int((high - 0.01) * 100)}%",
                "count": len(chosen),
                "avg_prob": round(sum(prob for prob, _ in chosen) / len(chosen), 3),
                "actual_hit_rate": round(hit_rate, 3),
            }
        )
    return summary


def top_feature_weights(model: dict, limit: int = 6) -> list[dict]:
    ranked = sorted(
        zip(model["feature_names"], model["weights"]),
        key=lambda item: abs(item[1]),
        reverse=True,
    )
    return [{"feature": name, "weight": round(weight, 4)} for name, weight in ranked[:limit]]


def evaluate_historical_model(conn: sqlite3.Connection, analysis_date: str, target_dir: str) -> dict:
    rows = conn.execute(
        """
        SELECT analysis_date, us_game_date, game_tag, combo_id, player_name, prop_stat, line, odds,
               implied_prob, predicted_prob, edge_pct, l10_hit_rate, l10_avg, l10_med, l10_sd,
               cov_label, cleared
        FROM reflector_legs
        WHERE cleared IN (0, 1) AND COALESCE(predicted_prob, l10_hit_rate) IS NOT NULL
        ORDER BY analysis_date, id
        """
    ).fetchall()

    if len(rows) < 25:
        return {
            "status": "insufficient_data",
            "message": f"Need at least 25 settled legs for ML evaluation, only have {len(rows)}.",
        }

    unique_dates = sorted({row["analysis_date"] for row in rows})
    if len(unique_dates) >= 4:
        split_index = max(2, int(len(unique_dates) * 0.7))
        split_index = min(split_index, len(unique_dates) - 1)
        train_dates = set(unique_dates[:split_index])
        test_dates = set(unique_dates[split_index:])
        train_rows = [row for row in rows if row["analysis_date"] in train_dates]
        test_rows = [row for row in rows if row["analysis_date"] in test_dates]
        split_summary = {
            "mode": "chronological_by_date",
            "train_dates": sorted(train_dates),
            "test_dates": sorted(test_dates),
        }
    else:
        split_at = max(18, int(len(rows) * 0.7))
        split_at = min(split_at, len(rows) - 5)
        train_rows = rows[:split_at]
        test_rows = rows[split_at:]
        split_summary = {
            "mode": "chronological_by_row",
            "train_rows": len(train_rows),
            "test_rows": len(test_rows),
        }

    if len(train_rows) < 18 or len(test_rows) < 5:
        return {
            "status": "insufficient_split",
            "message": "Not enough historical rows after chronological split.",
        }

    model = fit_logistic_regression(train_rows)
    labels = [int(row["cleared"]) for row in test_rows]
    baseline_probs = [
        clamp_prob((float(row["predicted_prob"] or row["l10_hit_rate"]) or 50.0) / 100.0)
        for row in test_rows
    ]
    ml_probs = [predict_probability(model, row) for row in test_rows]

    baseline_brier = round(brier_score(baseline_probs, labels), 4)
    ml_brier = round(brier_score(ml_probs, labels), 4)
    baseline_accuracy = round(accuracy(baseline_probs, labels), 4)
    ml_accuracy = round(accuracy(ml_probs, labels), 4)

    baseline_recommended = [
        label
        for prob, label in zip(baseline_probs, labels)
        if prob >= 0.70
    ]
    ml_recommended = [
        label
        for prob, label in zip(ml_probs, labels)
        if prob >= 0.70
    ]

    summary = {
        "status": "ok",
        "training_rows": len(train_rows),
        "test_rows": len(test_rows),
        "split_summary": split_summary,
        "baseline": {
            "brier": baseline_brier,
            "accuracy": baseline_accuracy,
            "recommended_count": len(baseline_recommended),
            "recommended_hit_rate": round(sum(baseline_recommended) / len(baseline_recommended), 4)
            if baseline_recommended else None,
            "calibration": bucket_summary(baseline_probs, labels),
        },
        "ml_model": {
            "brier": ml_brier,
            "accuracy": ml_accuracy,
            "recommended_count": len(ml_recommended),
            "recommended_hit_rate": round(sum(ml_recommended) / len(ml_recommended), 4)
            if ml_recommended else None,
            "calibration": bucket_summary(ml_probs, labels),
            "top_features": top_feature_weights(model),
        },
        "improvement": {
            "brier_delta": round(baseline_brier - ml_brier, 4),
            "accuracy_delta": round(ml_accuracy - baseline_accuracy, 4),
        },
    }

    timestamp = dt.datetime.now().isoformat()
    conn.execute(
        """
        INSERT INTO reflector_model_runs (
            analysis_date, training_rows, test_rows, split_summary,
            baseline_brier, ml_brier, baseline_accuracy, ml_accuracy,
            summary_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            analysis_date,
            len(train_rows),
            len(test_rows),
            json.dumps(split_summary, ensure_ascii=False, sort_keys=True),
            baseline_brier,
            ml_brier,
            baseline_accuracy,
            ml_accuracy,
            json.dumps(summary, ensure_ascii=False, sort_keys=True),
            timestamp,
        ),
    )
    conn.commit()

    json_path = os.path.join(target_dir, f"Reflector_ML_Evaluation_{analysis_date}.json")
    md_path = os.path.join(target_dir, f"Reflector_ML_Evaluation_{analysis_date}.md")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    md_lines = [
        f"# NBA Reflector ML Evaluation — {analysis_date}",
        "",
        f"- Training rows: {len(train_rows)}",
        f"- Test rows: {len(test_rows)}",
        f"- Split mode: {split_summary['mode']}",
        f"- Baseline Brier: {baseline_brier}",
        f"- ML Brier: {ml_brier}",
        f"- Baseline accuracy: {baseline_accuracy:.1%}",
        f"- ML accuracy: {ml_accuracy:.1%}",
        f"- Brier improvement: {summary['improvement']['brier_delta']:+.4f}",
        f"- Accuracy improvement: {summary['improvement']['accuracy_delta']:+.4f}",
        "",
        "## Top Features",
    ]
    for feature in summary["ml_model"]["top_features"]:
        md_lines.append(f"- {feature['feature']}: {feature['weight']:+.4f}")
    md_lines.append("")
    md_lines.append("## Calibration")
    md_lines.append("")
    md_lines.append("### Baseline")
    for bucket in summary["baseline"]["calibration"]:
        md_lines.append(
            f"- {bucket['bucket']}: n={bucket['count']} | avg_prob={bucket['avg_prob']} | actual_hit_rate={bucket['actual_hit_rate']}"
        )
    md_lines.append("")
    md_lines.append("### ML Model")
    for bucket in summary["ml_model"]["calibration"]:
        md_lines.append(
            f"- {bucket['bucket']}: n={bucket['count']} | avg_prob={bucket['avg_prob']} | actual_hit_rate={bucket['actual_hit_rate']}"
        )
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines) + "\n")

    summary["json_path"] = json_path
    summary["markdown_path"] = md_path
    return summary


def should_fetch_pbp(results_path: str, verification_path: str) -> bool:
    with open(results_path, "r", encoding="utf-8") as f:
        results = json.load(f)
    with open(verification_path, "r", encoding="utf-8") as f:
        verification = json.load(f)

    if any(game.get("blowout") for game in results.get("games", [])):
        return True
    if any(game.get("low_minutes_alert") for game in results.get("games", [])):
        return True
    for leg in verification.get("legs", []):
        margin = leg.get("margin")
        if margin is not None and margin <= -5:
            return True
    return False


def append_execution_log(target_dir: str, analysis_date: str, rows_recorded: int, ml_summary: dict | None) -> None:
    log_path = os.path.join(target_dir, "_execution_log.md")
    ml_status = ml_summary.get("status") if ml_summary else "skipped"
    line = (
        f"> 📝 LOG: Reflector Orchestrator | Date: {analysis_date} | "
        f"Rows: {rows_recorded} | ML: {ml_status} | Recorded At: {dt.datetime.now().isoformat()}\n"
    )
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line)


def main() -> None:
    parser = argparse.ArgumentParser(description="NBA Reflector Orchestrator")
    parser.add_argument("--date", required=True, help="Analysis date in Australia/Sydney (YYYY-MM-DD)")
    parser.add_argument("--dir", default=None, help="Override target analysis directory")
    parser.add_argument("--skip-fetch", action="store_true", help="Reuse existing Results/Verification files if present")
    parser.add_argument("--skip-pbp", action="store_true", help="Do not auto-fetch play-by-play")
    parser.add_argument("--skip-ml", action="store_true", help="Skip historical ML evaluation")
    args = parser.parse_args()

    analysis_date = args.date
    us_game_date = analysis_to_us_date(analysis_date)
    target_dir = resolve_target_dir(analysis_date, args.dir)
    os.makedirs(target_dir, exist_ok=True)

    results_path = os.path.join(target_dir, f"Results_Brief_{us_game_date}.json")
    verification_path = os.path.join(target_dir, f"Props_Verification_{us_game_date}.json")
    pbp_path = os.path.join(target_dir, f"PBP_Brief_{us_game_date}.json")

    print("=" * 60)
    print("🏀 NBA Reflector Orchestrator")
    print(f"📅 Analysis date (AU): {analysis_date}")
    print(f"🇺🇸 US game date: {us_game_date}")
    print(f"📁 Target dir: {target_dir}")
    print("=" * 60)

    if not args.skip_fetch or not os.path.exists(results_path):
        run_script(FETCH_RESULTS, ["--date", us_game_date, "--dir", target_dir], "Fetch Results")
    if not args.skip_fetch or not os.path.exists(verification_path):
        run_script(
            VERIFY_PROPS,
            ["--results", results_path, "--predictions", target_dir, "--output", verification_path],
            "Verify Props",
        )
    if not args.skip_pbp and (not os.path.exists(pbp_path) or not args.skip_fetch):
        if should_fetch_pbp(results_path, verification_path):
            run_script(FETCH_PBP, ["--date", us_game_date, "--dir", target_dir], "Fetch PBP")
        else:
            print("📉 PBP trigger not hit — skipping play-by-play fetch.")

    rows = load_prediction_rows(target_dir, analysis_date, us_game_date)
    if not rows:
        raise SystemExit("❌ No analysable NBA reports found in target directory.")
    verification_index = load_verification_index(verification_path)
    rows = attach_verification(rows, verification_index)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    ensure_db(conn)
    upserted = upsert_rows(conn, rows)
    snapshot_path = write_training_snapshot(rows, target_dir, analysis_date)
    ml_summary = None if args.skip_ml else evaluate_historical_model(conn, analysis_date, target_dir)
    conn.close()

    run_summary = {
        "analysis_date": analysis_date,
        "us_game_date": us_game_date,
        "target_dir": target_dir,
        "db_path": DB_PATH,
        "results_path": results_path,
        "verification_path": verification_path,
        "pbp_path": pbp_path if os.path.exists(pbp_path) else None,
        "rows_recorded": upserted,
        "training_snapshot": snapshot_path,
        "ml_summary": ml_summary,
    }
    summary_path = os.path.join(target_dir, f"Reflector_Run_Summary_{analysis_date}.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(run_summary, f, ensure_ascii=False, indent=2)
    append_execution_log(target_dir, analysis_date, upserted, ml_summary)

    print("\n📦 Reflector data recording complete")
    print(f"   Rows recorded: {upserted}")
    print(f"   SQLite DB: {DB_PATH}")
    print(f"   Training snapshot: {snapshot_path}")
    if ml_summary:
        if ml_summary.get("status") == "ok":
            print("🤖 Historical ML evaluation complete")
            print(f"   Baseline Brier: {ml_summary['baseline']['brier']}")
            print(f"   ML Brier: {ml_summary['ml_model']['brier']}")
            print(f"   Markdown report: {ml_summary['markdown_path']}")
        else:
            print(f"🤖 ML evaluation skipped: {ml_summary['message']}")
    print(f"🧾 Run summary: {summary_path}")


if __name__ == "__main__":
    main()
