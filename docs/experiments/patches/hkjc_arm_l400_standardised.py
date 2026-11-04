"""EXP-20261105-03 arm B1：上仗 L400 按（場地／跑道, 路程）標準化，再套現行門檻。

raw_l400' = raw_l400 − cell平均 + 全體平均。cell = 上仗（Venue, Track, Distance），上仗由
`recent_6_detail` 第 1 仗日期 join 賽果庫攞。平均只用**目標賽日之前**嘅賽日 Logic 入面嘅
`raw_l400`（每匹馬每仗去重；唔讀同日或者之後嘅檔），cell 要 ≥30 個觀測；唔夠或者搵唔到 cell
→ 唔郁。SpeedScorer 門檻同權重完全唔變。接線同 `hkjc_arm_best_l400.py` 一樣（覆寫 summaries）。
"""
import bisect
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ARM_NAME = "l400_standardised"
MIN_CELL = 30
_LAST = re.compile(r"第1仗\((\d{2})/(\d{2})/(\d{4})")
_STATE = {}


def _clean(name):
    return re.sub(r"\([A-Z]\d+\)$", "", str(name or "")).strip()


def _last_run_date(data):
    m = _LAST.search(str((data or {}).get("recent_6_detail") or ""))
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


def _float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _build():
    if _STATE:
        return _STATE
    repo = Path(__file__).resolve().parents[3]
    for p in (repo / ".agents/skills/hkjc_racing/hkjc_reflector/scripts", repo / ".agents/skills/shared_racing/scripts", repo):
        sys.path.insert(0, str(p))
    import pit_backtest
    import wongchoi_paths
    from corpus_paths import logic_files

    rows = pit_backtest.load_all_rows()
    cell_of = {}
    for r in rows.itertuples():
        try:
            cell_of[(_clean(r.Horse), str(r.Date)[:10])] = (str(r.Venue), str(r.Track), int(float(r.Distance)))
        except (TypeError, ValueError):
            continue
    obs = {}  # (horse, run_date) -> (meeting_date, cell, l400); keep earliest meeting that reported it
    for lf in logic_files(wongchoi_paths.HK_RACING):
        lf = Path(lf)
        m = re.match(r"(\d{4}-\d{2}-\d{2})", lf.parent.name)
        if not m:
            continue
        meeting = m.group(1)
        try:
            logic = json.load(open(lf, encoding="utf-8"))
        except Exception:
            continue
        for h in (logic.get("horses") or {}).values():
            if not isinstance(h, dict):
                continue
            data = h.get("_data") or {}
            l4, run = _float(data.get("raw_l400")), _last_run_date(data)
            name = _clean(h.get("horse_name"))
            cell = cell_of.get((name, run)) if run else None
            if l4 is None or cell is None or not (run < meeting):
                continue
            key = (name, run)
            if key not in obs or meeting < obs[key][0]:
                obs[key] = (meeting, cell, l4)
    by_cell = defaultdict(list)
    allv = []
    for meeting, cell, l4 in obs.values():
        by_cell[cell].append((meeting, l4))
        allv.append((meeting, l4))
    def prefix(items):
        items.sort()
        dates, sums, acc = [], [], 0.0
        for d, v in items:
            acc += v; dates.append(d); sums.append(acc)
        return dates, sums
    _STATE.update(cell_of=cell_of, cells={c: prefix(v) for c, v in by_cell.items()}, total=prefix(allv))
    print(f"[{ARM_NAME}] {len(obs)} L400 observations, {len(by_cell)} cells", file=sys.stderr)
    return _STATE


def _mean_before(prefixed, date):
    dates, sums = prefixed
    n = bisect.bisect_left(dates, date)   # meetings strictly before the target date
    return (sums[n - 1] / n, n) if n else (None, 0)


def standardised(name, data, race_date):
    state = _build()
    l4, run = _float((data or {}).get("raw_l400")), _last_run_date(data)
    cell = state["cell_of"].get((_clean(name), run)) if run else None
    if l4 is None or cell is None or cell not in state["cells"]:
        return None
    cell_mean, n = _mean_before(state["cells"][cell], race_date)
    total_mean, _ = _mean_before(state["total"], race_date)
    if n < MIN_CELL or total_mean is None:
        return None
    return round(l4 - cell_mean + total_mean, 4)


def apply():
    import hkjc_auto_orchestrator as orch

    load = orch._load_formline_opponent_summaries

    def wrapped(race_file, race_context, horses):
        summaries = load(race_file, race_context, horses)
        m = re.match(r"(\d{4}-\d{2}-\d{2})", Path(race_file).parent.name)
        race_date = str(race_context.get("race_date") or (m.group(1) if m else ""))[:10]
        if not race_date:
            return summaries
        summaries = dict(summaries)
        for num, horse in horses.items():
            if not isinstance(horse, dict):
                continue
            value = standardised(horse.get("horse_name"), horse.get("_data") or {}, race_date)
            if value is not None:
                key = str(num)
                summaries[key] = {**summaries.get(key, {}), "raw_l400": value}
        return summaries

    orch._load_formline_opponent_summaries = wrapped
