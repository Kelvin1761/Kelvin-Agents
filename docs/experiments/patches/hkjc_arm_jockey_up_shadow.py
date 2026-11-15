"""Kelvin 2026-11-15 —— forward shadow `jockey_up_shadow`（EXP-20261114-08）：「換上頂級騎師」做 forward 收集數據，唔入分。

jockey_up = 今仗騎師係頂級（賽日前 365 日入頭三率頭 5 名、≥ 50 騎，as-of）而上仗騎師唔係；非初出馬 raw + 1.0
（δ = EXP-20261114-08 全 dev walk-forward 揀出，固定）。喺 SIP-C 之後加，登記做 sip_flag（驗證一致）。
資料：pit_backtest.load_all_rows（賽果庫，as-of 用 Date < 賽日）。Δ = 候選 − live；Gold／Good／NDCG@5 全部 ≥ 0 → 建議入分（Kelvin 決定）。
"""
import datetime as dt
import json
import re
from collections import defaultdict

ARM_NAME = "jockey_up_shadow"
DELTA = 1.0
_STATE = {"date": None}
_ROWS = {}


def _clean(name):
    return re.sub(r"\s*\([A-Z]\d{3}\)", "", str(name or "")).strip()


def _prepare():
    if _ROWS:
        return
    import pit_backtest
    df = pit_backtest.load_all_rows()
    df = df[df["Rank"].notna()]
    _ROWS["by_date"] = defaultdict(list)
    _ROWS["horse_runs"] = defaultdict(list)
    for r in df.itertuples():
        d = str(r.Date)[:10]
        try:
            placed = float(r.Rank) <= 3
        except (TypeError, ValueError):
            continue
        _ROWS["by_date"][d].append((r.Jockey, placed))
        _ROWS["horse_runs"][_clean(r.Horse)].append((d, r.Jockey))
    for v in _ROWS["horse_runs"].values():
        v.sort()


def _top(date):
    cut = (dt.date.fromisoformat(date) - dt.timedelta(days=365)).isoformat()
    agg = defaultdict(lambda: [0, 0])
    for d, items in _ROWS["by_date"].items():
        if cut <= d < date:
            for j, p in items:
                agg[j][0] += p
                agg[j][1] += 1
    return {j for _, j in sorted(((a[0] / a[1], j) for j, a in agg.items() if a[1] >= 50), reverse=True)[:5]}


def apply():
    import hkjc_auto_orchestrator as orch
    from hkjc_racing_engine.scoring import compute_grade, to_display_scale
    _prepare()
    orig_score = orch.HKJCAutoOrchestrator.score_race

    def score_race(self, race_file, *a, **k):
        try:
            ra = json.load(open(race_file, encoding="utf-8")).get("race_analysis") or {}
            _STATE["date"] = str(ra.get("race_date") or "")[:10] or None
        except Exception:
            _STATE["date"] = None
        return orig_score(self, race_file, *a, **k)

    orig_sip = orch._apply_sip_enhancements

    def sip(horses):
        orig_sip(horses)
        d = _STATE["date"]
        if not d:
            return
        top = _top(d)
        for h in horses.values():
            auto = h.get("python_auto") or {}
            if not auto or h.get("is_debut") or h.get("debut_runner"):
                continue
            prev = [j for rd, j in _ROWS["horse_runs"].get(_clean(h.get("horse_name")), []) if rd < d]
            if not prev or str(h.get("jockey") or "").strip() not in top or prev[-1] in top:
                continue
            raw = round(float(auto.get("ability_score_raw")) + DELTA, 4)
            auto["ability_score_raw"] = raw
            auto["ability_score"] = round(to_display_scale(raw), 2)
            auto["grade"] = compute_grade(auto["ability_score"])
            auto.setdefault("sip_flags", []).append({"reason": "jockey_up_shadow", "boost": DELTA, "boost_scale": "raw"})

    orch.HKJCAutoOrchestrator.score_race = score_race
    orch._apply_sip_enhancements = sip
