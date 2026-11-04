"""EXP-20261105-04 arm A：前置習慣加減分（`WC_FRONT_K=2|4|6`）。

習慣 = 賽日之前最近 3 仗第一個沿途位嘅平均（賽果庫 RunningPos，最少 2 仗）。
相對今仗馬匹數：習慣 / 今仗出賽馬數 ≤ 0.25 → 前置 +K；> 0.60 → 後上 −K；其他、往績少過 2 仗、初出 → 0。
加落 `race_shape_context_score`（檔位與走位 leaf，clip 0–100），之後全場 race-shape 封頂照舊。

接線：包住 `_load_formline_opponent_summaries` 將習慣同今仗馬匹數寫入 `_data`，
再包住 `RacingEngine._race_shape_context_score` 加減。接線證明：races_with_ranking_change > 0。
"""
import os
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ARM_NAME = "front_habit"
FRONT_MAX, CLOSER_MIN = 0.25, 0.60
_STATE = {}


def _clean(name):
    return re.sub(r"\s*\(退出\)$", "", re.sub(r"\([A-Z]\d+\)$", "", str(name or ""))).strip()


def _history():
    if _STATE:
        return _STATE
    repo = Path(__file__).resolve().parents[3]
    for p in (repo / ".agents/skills/hkjc_racing/hkjc_reflector/scripts", repo / ".agents/skills/shared_racing/scripts", repo):
        sys.path.insert(0, str(p))
    import pit_backtest
    rows = pit_backtest.load_all_rows()
    runs = defaultdict(list)
    for r in rows.itertuples():
        m = re.match(r"^\s*(\d+)", str(r.RunningPos or ""))
        if m:
            runs[_clean(r.Horse)].append((str(r.Date)[:10], float(m.group(1))))
    for v in runs.values():
        v.sort()
    _STATE["runs"] = runs
    return _STATE


def habit(name, race_date):
    past = [fc for d, fc in _history()["runs"].get(_clean(name), []) if d < race_date][-3:]
    return statistics.mean(past) if len(past) >= 2 else None


def delta_for(h, field, k):
    if h is None or not field:
        return 0.0
    ratio = h / field
    return k if ratio <= FRONT_MAX else (-k if ratio > CLOSER_MIN else 0.0)


def apply():
    import hkjc_auto_orchestrator as orch
    from hkjc_racing_engine import engine_core
    from hkjc_racing_engine.scoring import clip_score

    k = float(os.environ.get("WC_FRONT_K", "4"))
    load = orch._load_formline_opponent_summaries

    def wrapped(race_file, race_context, horses):
        summaries = dict(load(race_file, race_context, horses))
        m = re.match(r"(\d{4}-\d{2}-\d{2})", Path(race_file).parent.name)
        race_date = str(race_context.get("race_date") or (m.group(1) if m else ""))[:10]
        live = {n: h for n, h in horses.items() if isinstance(h, dict) and "退出" not in str(h.get("horse_name") or "")}
        for num, horse in live.items():
            key = str(num)
            summaries[key] = {**summaries.get(key, {}), "exp04_front_habit": habit(horse.get("horse_name"), race_date),
                              "exp04_field": len(live)}
        return summaries

    orch._load_formline_opponent_summaries = wrapped
    original = engine_core.RacingEngine._race_shape_context_score

    def race_shape(self, features):
        score, note, source = original(self, features)
        if self._is_debut():
            return score, note, source
        d = delta_for(self.data.get("exp04_front_habit"), self.data.get("exp04_field"), k)
        if d:
            score = clip_score(score + d)
            note = f"{note}；EXP-04 前置習慣 {d:+.0f}"
        return score, note, source

    engine_core.RacingEngine._race_shape_context_score = race_shape
