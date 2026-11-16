"""上仗競賽事件報告組件（EXP-20261116-06；Kelvin 2026-11-16 揀 B：「全語料測試過閘就直接入分」）。

**methodology**：只用之前賽事（日期嚴格早過今仗）嘅 HKJC 競賽事件報告（賽後公開）；睇匹馬**最近一仗**：
  走外疊冇遮擋  = 句子有「沒有遮擋／走外疊／三疊／四疊」→ 往績名次差但唔代表能力差（藉口）
  醫療事故      = 「喘鳴／流鼻血／鼻孔流血／心律／跛／呼吸／肺部有血／不良於行」
  raw' = raw + β_wide·(走外疊 − 場均) + β_med·(醫療 − 場均)
β 係逐季 walk-forward 嘅 2026/27 季值（fit 2019/20–2025/26 全部回放季；docs/experiments/patches/hkjc_incidents/build_cand.py I1）。
回放 6,047 場（舊格式 2019-09 至 2023-10 由賽果頁補抓）：dev Δlog-loss −0.00028 [−0.00050,−0.00006]、
holdout −0.00041 [−0.00067,−0.00012]（Holm 2 PASS）、holdout AUC +0.0017、Good +0.64。
表（`incident_history.json`，由 `hkjc_pit_sections_build.py` 每個賽日後重建，放本機資料根）：
  {"version": 1, "last_date": ..., "horses": {馬號(L245): [[日期, 旗]], ...舊到新}}，旗 = "W"／"M"／"R" 嘅組合或 ""；
  null = 嗰場冇事件報告（當冇旗）。外隊馬（tags.is_foreign）中性。冇表 = 不套用。`ENABLED = False` = 退回。
"R"（騎法被查詢／有策騎指示交代／騎師被告誡或未有力策）**只做顯示標籤，唔入分**：殘差 dev +3.4pp、holdout +3.0pp
兩段都正，但入分候選 R1 dev Δlog-loss −0.00010 [−0.00024,+0.00005] REJECT（EXP-20261116-11）。
"""
from __future__ import annotations

import json
import re
from bisect import bisect_left
from pathlib import Path

ENABLED = True
BETA_WIDE = 1.218867269611233
BETA_MEDICAL = -1.9362938666252367
WIDE_RE = r"沒有遮擋|走外疊|三疊|四疊"
MEDICAL_RE = r"喘鳴|流鼻血|鼻孔流血|心律|跛|呼吸|肺部有血|不良於行"
# 只顯示（EXP-20261116-11）：同 docs/experiments/patches/hkjc_incidents/diag_round3.py 嘅 INSTR｜RIDE_Q｜RIDE_WARN 一樣。
RIDE_RE = (r"獲指示|策騎指示|(查詢|研訊).{0,30}(騎法|策騎)|(騎法|策騎).{0,12}(展開研訊|查詢)"
           r"|告誡.{0,40}(策騎|騎法)|(策騎|騎法).{0,30}(引起小組關注|未能令小組滿意)|100\(2\)|未有力策|未有盡力")
# 只用嚟 forward shadow（EXP-20261117-05 joint_signals_shadow）＋日後研究；唔入 adjustments。
# 同 docs/experiments/patches/hkjc_incidents/diag.py 嘅 CATS 一樣。
BLOCKED_RE = r"未能望空|未能找到空位|找不到空位|受阻|勒避|被困|未能.{0,4}走位|須收慢"
SLOW_RE = r"出閘笨拙|出閘緩慢|起步緩慢|失地"
_TABLE: dict | None = None


def flags(sentence: str | None) -> str | None:
    """事件報告句子 → 旗（None = 冇報告）。"""
    if sentence is None:
        return None
    s = str(sentence)
    return (("W" if re.search(WIDE_RE, s) else "") + ("M" if re.search(MEDICAL_RE, s) else "")
            + ("R" if re.search(RIDE_RE, s) else "") + ("B" if re.search(BLOCKED_RE, s) else "")
            + ("S" if re.search(SLOW_RE, s) else ""))


# 用字漂移監察（Kelvin 2026-11-16「每次用字唔同，捉唔捉得齊？」）：HKJC 改寫法 → 命中率靜靜跌到 0 都唔會報錯。
# 歷史命中率（有報告嘅馬次）：W 7–9%、M 2–3%、R 2–5%；地板定喺約一半。
WORDING_FLOORS = {"W": 0.035, "M": 0.008, "R": 0.008}
WORDING_WINDOW_DAYS = 120
WORDING_MIN_RUNS = 300


def wording_check(table: dict) -> list[str]:
    """最近 WORDING_WINDOW_DAYS 日有報告嘅馬次，逐旗命中率；低過地板 → 警告句子。樣本唔夠 → 唔判。"""
    from datetime import date, timedelta
    last = (table or {}).get("last_date")
    if not last:
        return []
    since = (date.fromisoformat(str(last)[:10]) - timedelta(days=WORDING_WINDOW_DAYS)).isoformat()
    flags_ = [f for runs in (table.get("horses") or {}).values() for d, f in runs if d >= since and f is not None]
    if len(flags_) < WORDING_MIN_RUNS:
        return []
    out = []
    for k, floor in WORDING_FLOORS.items():
        rate = sum(k in f for f in flags_) / len(flags_)
        if rate < floor:
            out.append(f"事件報告旗 {k} 近 {WORDING_WINDOW_DAYS} 日命中率 {rate:.1%}（{len(flags_)} 馬次）低過地板 {floor:.1%}"
                       " —— HKJC 可能改咗寫法，incident_history 嘅 regex 要覆核")
    return out


def load_table(path: str | Path | None = None) -> dict | None:
    global _TABLE
    if path is None and _TABLE is not None:
        return _TABLE
    if path is None:
        import wongchoi_paths
        path = Path(wongchoi_paths.HK_RACING) / "HKJC_Sections" / "incident_history.json"
    p = Path(path)
    if not p.exists():
        return None
    _TABLE = json.loads(p.read_text(encoding="utf-8"))
    return _TABLE


def prev_flags(code: str, race_date: str, table: dict) -> str:
    runs = (table.get("horses") or {}).get(code) or []
    i = bisect_left([r[0] for r in runs], race_date)      # 嚴格早過今仗
    if i == 0:
        return ""
    return runs[i - 1][1] or ""


def prev_wide_two_back(code: str, race_date: str, table: dict) -> bool:
    """只顯示（EXP-20261116-18）：上上仗（上仗之前最近一場有報告嘅賽事）走外疊冇遮擋，而上仗冇。
    上仗要有報告（同 diag_twoback.py 一樣）；上仗走外疊已由 W 入分處理。"""
    runs = (table.get("horses") or {}).get(code) or []
    i = bisect_left([r[0] for r in runs], race_date)
    if i == 0 or runs[i - 1][1] is None or "W" in runs[i - 1][1]:
        return False
    for _d, fl in reversed(runs[:i - 1]):
        if fl is not None:
            return "W" in fl
    return False


def prev_two(code: str, race_date: str, table: dict) -> tuple[str | None, str | None]:
    """(上仗旗, 上上仗旗)：上仗 = 日期嚴格早過今仗嘅最近一仗（冇報告 = None）；上上仗 = 再之前最近一場有報告嘅。"""
    runs = (table.get("horses") or {}).get(code) or []
    i = bisect_left([r[0] for r in runs], race_date)
    if i == 0:
        return None, None
    last = runs[i - 1][1]
    two = next((fl for _d, fl in reversed(runs[:i - 1]) if fl is not None), None)
    return last, two


def horse_flags(horses: dict, race_date: str, table: dict) -> dict:
    """{馬號: 上仗旗}；外隊馬當冇旗（中性）。"""
    from .market_history import horse_code
    from .tags import is_foreign
    return {k: ("" if is_foreign(h) else prev_flags(horse_code(h), race_date, table)) for k, h in horses.items()}


def adjustments(horses: dict, race_date: str, table: dict) -> dict:
    """horses：{馬號: horse dict} → {馬號: raw 加減}（場內置中）。"""
    if not horses:
        return {}
    fl = horse_flags(horses, race_date, table)
    raw = {k: BETA_WIDE * ("W" in f) + BETA_MEDICAL * ("M" in f) for k, f in fl.items()}
    mean = sum(raw.values()) / len(raw)
    return {k: v - mean for k, v in raw.items()}


def apply(horses: dict, race_date: str | None, table: dict | None = None) -> int:
    """加落 ability_score_raw（上仗賠率之後、grade／排名之前）。返回郁咗幾多匹；冇表／冇日期 → 唔郁。"""
    if not ENABLED or not race_date:
        return 0
    table = table if table is not None else load_table()
    if not table:
        return 0
    from .market_history import horse_code
    from .scoring import compute_grade, to_display_scale
    from .tags import is_foreign
    scored = {k: h for k, h in horses.items() if isinstance(h, dict) and isinstance(h.get("python_auto"), dict)
              and h["python_auto"].get("ability_score_raw") is not None}
    n = 0
    fl = horse_flags(scored, str(race_date)[:10], table)
    for k, add in adjustments(scored, str(race_date)[:10], table).items():
        auto = scored[k]["python_auto"]
        auto["incident_history_flags"] = fl.get(k, "")
        auto["incident_wide_two_back"] = (False if is_foreign(scored[k])
                                          else prev_wide_two_back(horse_code(scored[k]), str(race_date)[:10], table))
        raw = round(float(auto["ability_score_raw"]) + add, 4)
        auto["ability_score_raw"] = raw
        auto["ability_score"] = round(to_display_scale(raw), 2)
        auto["grade"] = compute_grade(auto["ability_score"])
        auto["incident_history_delta"] = round(add, 4)
        # shadow 反事實要同主線一樣加（同 market_history；否則 SHADOW-024／027 驗證唔過）
        for shadow in (auto.get("shadow_profiles") or {}).values():
            try:
                s_raw = round(float(shadow.get("ability_score_raw")) + add, 4)
            except (TypeError, ValueError):
                continue
            s_score = round(to_display_scale(s_raw), 2)
            shadow["ability_score_raw"] = s_raw
            shadow["ability_score"] = s_score
            shadow["grade"] = compute_grade(s_score)
            shadow["ability_delta"] = round(s_score - auto["ability_score"], 2)
            shadow.setdefault("sip_flags", []).append({"reason": "incident_history", "boost": round(add, 4), "boost_scale": "raw"})
        n += abs(add) > 1e-9
    return n
