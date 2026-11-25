"""Dashboard 機率（shadow · 未入分）：每匹馬「入頭三／獨贏」機會（Kelvin 2026-11-26「做 1-3」第 2 項）。

一樣嘢只准一個標準：機率**只**由 `shared_racing/scripts/model_probability.py` 計（同 AU log-loss 判決尺同一條公式；
參數 `<資料根>/AU_Prob_Calibration.json` 每晚 walk-forward 重 fit）。呢度唔重寫公式，只係調用 `top3_probs`／`win_probs`。
舊 Monte Carlo（`mc_simulator.py`）2026-05 之後已冇輸出，dashboard 只喺舊場次標「舊版模擬」顯示。

顯示條件（任何一個唔符合 = 唔顯示，唔扮有）：
  * 參數 `status == "ok"`（現行模型夠 20 個賽日先 fit）；
  * 參數 `model_id` == 而家嘅 `model_probability.model_id(platform)`（模型改咗而參數未重 fit = 唔顯示）；
  * 嗰場 `Race_N_Auto_Scoring.csv` 讀到每匹馬嘅 `ability_score`（N = 發佈時評分嘅馬數）。
HKJC：參數 `insufficient`（現行 contract 未夠 20 個賽日），而且 raw 係 Logic 嘅 `ability_score_raw`，未接。

純顯示：唔改任何分數、排名、grade。
"""
from __future__ import annotations

import csv
import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[3]
SHARED = REPO / ".agents" / "skills" / "shared_racing" / "scripts"


def _mp():
    if str(SHARED) not in sys.path:
        sys.path.insert(0, str(SHARED))
    import model_probability as M  # noqa: E402
    return M


@lru_cache(maxsize=4)
def load_params(platform: str, data_root: Optional[str] = None) -> Optional[dict]:
    """→ 可以用嘅參數，或者 None（附原因喺 `last_reason`）。"""
    try:
        M = _mp()
        root = Path(data_root) if data_root else M.default_root(platform)
        params = json.loads((root / M.OUTPUT_NAMES[platform]).read_text(encoding="utf-8"))
        if params.get("status") != "ok" or params.get("model_id") != M.model_id(platform):
            return None
        if any(params.get(k) is None for k in ("a", "alpha", "gamma", "beta_win")):
            return None
        return params
    except Exception:  # noqa: BLE001 — 顯示層：讀唔到就唔顯示，唔可以令 deploy 死
        return None


def _abilities(csv_path: Path) -> dict[int, float]:
    out: dict[int, float] = {}
    with csv_path.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                out[int(float(row.get("horse_number") or 0))] = float(row["ability_score"])
            except (TypeError, ValueError, KeyError):
                continue
    return out


def race_probabilities(csv_path: Path, platform: str = "au", data_root: Optional[str] = None) -> dict[int, dict]:
    """→ {馬號: {top3, win, fit_until, n_days, model_id}}；唔符合條件 = {}。"""
    params = load_params(platform, data_root)
    if not params or not Path(csv_path).exists():
        return {}
    ab = _abilities(Path(csv_path))
    if len(ab) < 2:
        return {}
    M = _mp()
    nums = sorted(ab)
    raws = [ab[n] for n in nums]
    top3 = M.top3_probs(raws, params, platform)
    win = M.win_probs(raws, params["beta_win"])
    meta = {"fit_until": params.get("fit_until"), "n_days": params.get("n_days"), "n_races": params.get("n_races"),
            "model_id": params.get("model_id"), "field_n": len(nums), "experiment": "EXP-20261125-07"}
    return {n: {"top3": round(float(t), 4), "win": round(float(w), 4), **meta} for n, t, w in zip(nums, top3, win)}


def attach(horses, csv_path: Path, platform: str = "au", data_root: Optional[str] = None) -> int:
    """將機率掛落 `horse.model_probability`（純顯示）。→ 掛咗幾多匹。"""
    probs = race_probabilities(csv_path, platform, data_root)
    count = 0
    for h in horses:
        p = probs.get(int(h.horse_number)) if probs else None
        if p:
            h.model_probability = p
            count += 1
    return count
