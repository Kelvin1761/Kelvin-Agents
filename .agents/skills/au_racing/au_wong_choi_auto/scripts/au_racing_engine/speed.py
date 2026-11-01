"""AU 速度分（L600 環境分，維度 `pace_perf`）—— 唯一計算位置。

`engine_core._pf_aggregates`（每匹馬）同 `RacingEngine._pace_figure_score`（同場）都只係叫呢度。
計劃同已測過嘅改動：docs/plans/2026-11-01-au-speed-rebuild.md（EXP-20261101-30 至 42）。

點解係 L600 而唔係全程時間：全程速度單獨更準，但同狀態／穩定性／班次重疊，放入矩陣排名差咗
（EXP-41）；L600 帶住「嗰場跑得快定慢」呢份其他維度冇嘅資訊。逐駒末段估算越準越差（EXP-40／42）。

公式：

    每仗（只限正式賽）：
        race_i = l600_delta                       Sportsbet 賽事 L600 − 標準
        own_i  = round(race_i + margin × 0.17, 4) 只限 Sportsbet 來源而且有 margin
    每匹馬：近期加權平均，最近一仗權重 1，之後每仗 × 0.8（k 按日期由新到舊、計晒全部往績），捨入 3dp
    同場：own 有 ≥3 匹就用 own，否則用 race；z = (值 − 場均) / 場內 pstdev；分數 = clip(60 − 20z)
          冇值或者少過 3 匹 → 60（no_pf）；pstdev = 0 → 60（no_spread）
"""
from __future__ import annotations

from dataclasses import dataclass

SPORTSBET = "sportsbet_race_context"
SEC_PER_LENGTH = 0.17
RECENCY_DECAY = 0.8
NEUTRAL = 60.0
POINTS_PER_SD = 20.0
MIN_FIELD = 3


@dataclass(frozen=True)
class HorseSpeed:
    own: float | None      # 近期加權本駒 L600 差（秒，越細越快）
    race: float | None     # 近期加權賽事 L600 差
    runs: int


@dataclass(frozen=True)
class SpeedScore:
    score: float
    state: str             # ok／no_pf／no_spread
    basis: str             # own／race
    value: float | None
    mean: float | None
    stdev: float | None


def run_values(run: dict, horse_source: str) -> tuple[float | None, float | None]:
    """→ (own, race)。冇標 source 嘅往績跟馬匹整體 source。"""
    race = run.get("l600_delta")
    if race is None:
        return None, None
    race = float(race)
    margin = run.get("margin")
    source = run.get("source") or horse_source
    own = None
    if horse_source == SPORTSBET and source == SPORTSBET and margin is not None:
        own = round(race + float(margin) * SEC_PER_LENGTH, 4)
    return own, race


def weighted_mean(pairs: list[tuple[float, float]]) -> float | None:
    if not pairs:
        return None
    return round(sum(w * v for w, v in pairs) / sum(w for w, _ in pairs), 3)


def horse_speed(runs: list[dict], horse_source: str) -> HorseSpeed:
    ordered = sorted(runs, key=lambda run: str(run.get("run_date") or ""), reverse=True)
    own, race = [], []
    for k, run in enumerate(ordered):
        weight = RECENCY_DECAY ** k
        o, r = run_values(run, horse_source)
        if o is not None:
            own.append((weight, o))
        if r is not None:
            race.append((weight, r))
    return HorseSpeed(weighted_mean(own), weighted_mean(race), len(runs))


def evidence(runs: list[dict], horse_source: str, limit: int = 5) -> list[dict]:
    """逐仗證據（顯示用），次序同權重同 `horse_speed` 一樣：由新到舊，第 k 仗權重 0.8^k。"""
    ordered = sorted(runs, key=lambda run: str(run.get("run_date") or ""), reverse=True)
    out = []
    for k, run in enumerate(ordered[:limit]):
        own, race = run_values(run, horse_source)
        if race is None:
            continue
        out.append({"date": str(run.get("run_date") or ""), "venue": run.get("venue"),
                    "distance": run.get("distance"), "race": race, "margin": run.get("margin"),
                    "own": own, "weight": round(RECENCY_DECAY ** k, 2)})
    return out


def choose(own: float | None, own_count: int, race: float | None, race_count: int) -> tuple[str, float] | None:
    """own 有 ≥3 匹就用 own，否則 race；都唔夠 → None（中性）。"""
    if own is not None and own_count >= MIN_FIELD:
        return "own", own
    if race is not None and race_count >= MIN_FIELD:
        return "race", race
    return None


def score(value: float, mean: float, stdev: float) -> float:
    """越快（值越細）分越高；60 = 場均。"""
    z = (value - mean) / stdev
    return max(0.0, min(100.0, NEUTRAL - z * POINTS_PER_SD))


def _field_stats(values: list[float]) -> tuple[float, float]:
    mean = sum(values) / len(values) if values else 0.0
    stdev = (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5 if len(values) >= 2 else 0.0
    return mean, stdev


def field_scores(field: dict[str, HorseSpeed]) -> dict[str, SpeedScore]:
    """同場比較。`field` = 呢場 Logic 全部馬（包括冇賽果嘅），同引擎一樣嘅母體。"""
    own = [h.own for h in field.values() if h.own is not None]
    race = [h.race for h in field.values() if h.race is not None]
    own_mean, own_sd = _field_stats(own)
    race_mean, race_sd = _field_stats(race)
    out = {}
    for number, horse in field.items():
        picked = choose(horse.own, len(own), horse.race, len(race))
        if picked is None:
            out[number] = SpeedScore(NEUTRAL, "no_pf", "race", None, None, None)
            continue
        basis, value = picked
        mean, sd = (own_mean, own_sd) if basis == "own" else (race_mean, race_sd)
        if sd <= 0:
            out[number] = SpeedScore(NEUTRAL, "no_spread", basis, value, mean, sd)
            continue
        out[number] = SpeedScore(score(value, mean, sd), "ok", basis, value, mean, sd)
    return out
