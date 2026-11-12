"""EXP-20261113-04 arm：前段對馬會標準 —— 段速維度入面一個獨立組件（加喺 speed_score 上面，唔減現有段速）。

Kelvin 2026-11-13：「試前段對標準做獨立段速組件」。依據 EXP-20261113-02：L400 之前各段對標準同 speed_score ρ +0.01，
模型之上係數 +0.137（Holm 0.007）；L400／L800／後勁冇增量。
預先登記（跑之前寫死）：
  值      front_value：近 6 仗、L400 之前各段 − 馬會標準分段（今仗班次；冇就嗰仗班次），負磅按段長換算到今仗，
          ÷（路程 − 400）/ 400 = 每 400 米；1/k 加權，最少 2 仗；取負（越大越好）
  組件    front_pts = b × SD_speed × (front − mean) / SD，clip ±2.5 SD；speed' = clip(speed + front_pts)
          mean／SD 只用 dev 半（< 2026-09-06，prep 寫 WC_EXP_FRONT_STATS）；SD_speed 9.45（非中性 speed_score）
          冇值（< 2 仗有標準，或者 std_pace 冇值）唔郁
  b       {0.25, 0.5}（兩個 arm 全報）；MATRIX_WEIGHTS 唔郁 → 段速維度實際份量上升，冇任何維度被減
  判決    fixed_rule 389 場；Gold、Good 都唔可以負（Kelvin）；過咗都要 forward
"""
import json
import os

B = float(os.environ.get("WC_EXP_FRONT_B", "0.25"))
ARM_NAME = f"front_section_b{int(round(B * 100))}"
BETA = 0.01123


def front_value(items, today_weight):
    """items：[(路程, 分段list, 嗰仗負磅, 標準分段list 或 None)]，由新到舊，最多 6 仗。"""
    vals = []
    for dist, secs, w, std in items[:6]:
        if not std or len(std) != len(secs) or len(std) < 3 or w is None or today_weight is None or dist <= 400:
            continue
        lens = [dist - 400 * (len(std) - 1)] + [400] * (len(std) - 1)
        d = [a - b + BETA * L / 1000.0 * (today_weight - w) for a, b, L in zip(secs, std, lens)]
        vals.append(sum(d[:-1]) / ((dist - 400) / 400.0))
    if len(vals) < 2:
        return None
    wt = [1.0 / k for k in range(1, len(vals) + 1)]
    return -sum(v * x for v, x in zip(vals, wt)) / sum(wt)


def apply():
    from hkjc_racing_engine import past_runs
    from hkjc_racing_engine.features.speed import SpeedScorer
    from hkjc_racing_engine.scoring import clip_score

    st = json.load(open(os.environ["WC_EXP_FRONT_STATS"]))
    base_std_pace = past_runs.std_pace

    def std_pace(runs, today_weight, today_class, run_classes):
        pace = base_std_pace(runs, today_weight, today_class, run_classes)
        items = []
        for run in runs[:6]:
            std = past_runs.standard_sections(run["venue"], run["awt"], run["distance"], today_class) or \
                past_runs.standard_sections(run["venue"], run["awt"], run["distance"], run_classes.get(run["date"]))
            items.append((run["distance"], run["splits"], run["weight"], std))
        front = front_value(items, today_weight)
        if front is not None and pace:          # 只喺 std_pace 有值時加（避免殘缺 dict 影響顯示）
            pace["exp_front"] = front
        return pace

    past_runs.std_pace = std_pace
    base_compute = SpeedScorer.compute

    def compute(self):
        score, note = base_compute(self)
        front = (self._data().get("std_pace") or {}).get("exp_front")
        if front is None:
            return score, note
        z = max(-2.5, min(2.5, (front - st["mean"]) / st["sd"]))
        return clip_score(score + B * st["speed_sd"] * z), note

    SpeedScorer.compute = compute
