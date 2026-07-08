from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[6]
import sys as _sys; _sys.path.insert(0, str(ROOT))
from wongchoi_paths import HK_RACING
STATS_ROOT = HK_RACING / "HKJC_Race_Results_Database" / "comprehensive_stats"

GENERAL_PRIOR_FILES = {
    "combo": [
        STATS_ROOT / "24_25" / "general_pre_race_priors" / "jockey_trainer_combo_priors.csv",
        STATS_ROOT / "25_26" / "general_pre_race_priors" / "jockey_trainer_combo_priors.csv",
    ],
    "jockey_distance": [
        STATS_ROOT / "24_25" / "jockey_distance_stats.csv",
        STATS_ROOT / "25_26" / "jockey_distance_stats.csv",
    ],
    "trainer_distance": [
        STATS_ROOT / "24_25" / "trainer_distance_stats.csv",
        STATS_ROOT / "25_26" / "trainer_distance_stats.csv",
    ],
    "jockey_change": [
        STATS_ROOT / "24_25" / "general_pre_race_priors" / "jockey_change_priors.csv",
        STATS_ROOT / "25_26" / "general_pre_race_priors" / "jockey_change_priors.csv",
    ],
    "jockey_draw": [
        STATS_ROOT / "24_25" / "jockey_draw_performance.csv",
        STATS_ROOT / "25_26" / "jockey_draw_performance.csv",
    ],
}


# 兩季 master stats → 逐個騎師/練馬師連續實績評分（取代舊人手層級表做主要來源）。
# ML 驗證（2026-07-08，15賽日/153場 10/5 train-test）：以下參數（A7 組合）
# FULL gold 3.9→6.5 / good 22.9→27.5 / champ 24.8→27.5 / t3c 54.2→55.6 / min 持平，
# 代價 single 87.6→84.3。負面縮放（騎師×0.5、練馬師×0.25＋floor 58）係保 single
# 嘅關鍵；再狠嘅版本 TEST 倒退。
JT_RATING_PARAMS = {
    "k": 100.0,            # EB shrink 樣本
    "a_place": 0.5,        # 上名率超額 → 分數
    "b_win": 0.6,          # 勝率超額 → 分數
    "jockey_neg_scale": 0.5,
    "trainer_neg_scale": 0.25,
    "trainer_floor": 58.0,
    # 練馬師舊季×0.3：馬房狀態季節性強（例：沈集成 24/25 勝率7.8% → 25/26 12.5%
    # 爭榜首），本季加權先反映到；backtest TEST 完全一致、TRAIN 只 1-2 場雜訊差。
    # 騎師唔衰減（測過 w24=.5 無得益）。
    "trainer_w24": 0.3,
    "jockey_w24": 1.0,
    # 細樣本×層級先驗 Bayesian blend：預設熄（blend_below=0）。
    # Backtest 證實開咗會蝕 TEST good −3.7pp（主要係布浩榮呢類「有tier但HK數據差」
    # 被拉高）。真正一次性客串本身無 master-stats row → 已自動 fallback 層級表/海外
    # G1 邏輯；有少量數據嘅新騎師交俾 EB shrink（自然貼近60中性）。
    "blend_below": 0.0,
    "blend_k": 100.0,
}

MASTER_STATS_FILES = {
    "jockey": [(STATS_ROOT / "24_25" / "jockey_master_stats.csv", "jockey_w24"),
               (STATS_ROOT / "25_26" / "jockey_master_stats.csv", None)],
    "trainer": [(STATS_ROOT / "24_25" / "trainer_master_stats.csv", "trainer_w24"),
                (STATS_ROOT / "25_26" / "trainer_master_stats.csv", None)],
}


class JockeyTrainerRatings:
    """{name: {score, starts, win_rate, place_rate}}，EB shrink 連續評分。"""

    def __init__(self) -> None:
        self.jockey = self._build("jockey")
        self.trainer = self._build("trainer")

    def _build(self, group: str) -> dict[str, dict]:
        p = JT_RATING_PARAMS
        col = "Jockey" if group == "jockey" else "Trainer"
        neg_scale = p["jockey_neg_scale"] if group == "jockey" else p["trainer_neg_scale"]
        floor = 0.0 if group == "jockey" else p["trainer_floor"]
        frames = []
        for path, weight_key in MASTER_STATS_FILES[group]:
            if not path.exists():
                continue
            df_season = pd.read_csv(path, encoding="utf-8-sig")
            season_w = float(p.get(weight_key, 1.0)) if weight_key else 1.0
            for c in ("Wins", "Starts", "Places"):
                df_season[c] = pd.to_numeric(df_season[c], errors="coerce").fillna(0.0) * season_w
            frames.append(df_season[[col, "Wins", "Starts", "Places"]])
        if not frames:
            return {}
        df = pd.concat(frames, ignore_index=True)
        df = df.groupby(col)[["Wins", "Starts", "Places"]].sum().reset_index()
        total_starts = float(df["Starts"].sum()) or 1.0
        g_win = float(df["Wins"].sum()) / total_starts
        g_place = float(df["Places"].sum()) / total_starts
        out: dict[str, dict] = {}
        for row in df.to_dict(orient="records"):
            starts = float(row["Starts"] or 0.0)
            if starts <= 0:
                continue
            win_sh = (float(row["Wins"]) + p["k"] * g_win) / (starts + p["k"])
            place_sh = (float(row["Places"]) + p["k"] * g_place) / (starts + p["k"])
            delta = p["b_win"] * (win_sh - g_win) * 100 + p["a_place"] * (place_sh - g_place) * 100
            if delta < 0:
                delta *= neg_scale
            score = 60.0 + delta
            if floor:
                score = max(score, floor)
            out[str(row[col]).strip()] = {
                "score": max(0.0, min(100.0, score)),
                "starts": starts,
                "win_rate": float(row["Wins"]) / starts * 100.0,
                "place_rate": float(row["Places"]) / starts * 100.0,
            }
        return out

    def lookup(self, group: str, raw_name: str) -> dict | None:
        table = self.jockey if group == "jockey" else self.trainer
        name = str(raw_name or "").strip()
        if not name:
            return None
        hit = table.get(name)
        if hit is not None:
            return hit
        for key, value in table.items():
            if key and (key in name or name in key):
                return value
        return None


_JT_RATINGS: JockeyTrainerRatings | None = None


def get_jt_ratings() -> JockeyTrainerRatings:
    global _JT_RATINGS
    if _JT_RATINGS is None:
        _JT_RATINGS = JockeyTrainerRatings()
    return _JT_RATINGS


class TrainerSignalPriors:
    def __init__(self) -> None:
        self.combo = self._load_grouped(GENERAL_PRIOR_FILES["combo"], ["Jockey", "Trainer"])
        self.jockey_distance = self._load_grouped(GENERAL_PRIOR_FILES["jockey_distance"], ["Jockey", "Distance"])
        self.trainer_distance = self._load_grouped(GENERAL_PRIOR_FILES["trainer_distance"], ["Trainer", "Distance"])
        self.jockey_change = self._load_jockey_change()

    def _load_grouped(self, paths: list[Path], keys: list[str]) -> dict[tuple[str, ...], dict]:
        frames = [pd.read_csv(path, encoding="utf-8-sig") for path in paths if path.exists()]
        if not frames:
            return {}
        df = pd.concat(frames, ignore_index=True)
        for column in ("Wins", "Starts", "Places"):
            df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0.0)
        grouped = df.groupby(keys, dropna=False)[["Wins", "Starts", "Places"]].sum().reset_index()
        records: dict[tuple[str, ...], dict] = {}
        for row in grouped.to_dict(orient="records"):
            starts = float(row.get("Starts", 0.0) or 0.0)
            wins = float(row.get("Wins", 0.0) or 0.0)
            places = float(row.get("Places", 0.0) or 0.0)
            key = tuple(str(row[item]).strip() for item in keys)
            records[key] = {
                "starts": starts,
                "wins": wins,
                "places": places,
                "win_rate": (wins / starts * 100.0) if starts else 0.0,
                "place_rate": (places / starts * 100.0) if starts else 0.0,
            }
        return records

    def _load_jockey_change(self) -> dict[bool, dict]:
        frames = [pd.read_csv(path, encoding="utf-8-sig") for path in GENERAL_PRIOR_FILES["jockey_change"] if path.exists()]
        if not frames:
            return {}
        df = pd.concat(frames, ignore_index=True)
        df["Wins"] = pd.to_numeric(df["Wins"], errors="coerce").fillna(0.0)
        df["Starts"] = pd.to_numeric(df["Starts"], errors="coerce").fillna(0.0)
        df["Places"] = pd.to_numeric(df["Places"], errors="coerce").fillna(0.0)
        grouped = df.groupby("JockeyChanged", dropna=False)[["Wins", "Starts", "Places"]].sum().reset_index()
        records: dict[bool, dict] = {}
        for row in grouped.to_dict(orient="records"):
            changed = str(row["JockeyChanged"]).strip().lower() == "true"
            starts = float(row["Starts"] or 0.0)
            wins = float(row["Wins"] or 0.0)
            places = float(row["Places"] or 0.0)
            records[changed] = {
                "starts": starts,
                "wins": wins,
                "places": places,
                "win_rate": (wins / starts * 100.0) if starts else 0.0,
                "place_rate": (places / starts * 100.0) if starts else 0.0,
            }
        return records
