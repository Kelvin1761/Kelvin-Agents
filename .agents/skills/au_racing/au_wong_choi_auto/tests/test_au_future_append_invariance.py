"""「加未來唔可以改過去」—— AU 通用 point-in-time 不變性測試。

點解要有呢個（2026-10-14，借自 hkjc-edge-lab）：
repo 入面嘅 PIT 測試全部係**逐個特徵**寫（`test_sportsbet_point_in_time`、
`test_sb_horse_index`、`test_preparation_cycle` …）。每加一個新來源，就要有人
記得加一條新測試。EXP-20260902-03 證明咗呢個做法漏：HKJC 回放經 J/T 統計
洩漏，而嗰個來源冇人寫過 PIT 測試。repo memory 亦記住「派生嘅 as-of 表過到
日期過濾，但資訊集仍然大過賽前」呢個形狀。

呢個測試唔問「邊個欄位有日期過濾」，佢直接問結果：

    1. 由一個細 fixture 語料，行**成條生產流程**計場次 D 每匹馬嘅每個 leaf
       （write_meeting → inject_fact_anchors → build_au_logic → score_logic_data）。
    2. 喺每一個流程會讀嘅數據源，加一個**未來場次** F（日期 > D，同 D 共用
       馬、騎師、練馬師、馬場，賽果刻意極端）。
    3. 重新計 D。每個 leaf、每個維度分、綜合分同最終排名都要**逐位元一樣**。

每個來源一個 case，所以失敗嘅時候就知係邊個來源漏。

⚠️ 規則（AGENTS.md）：已知洩漏唔喺呢個測試修。佢哋標 `expectedFailure`，
寫明邊個來源、邊個 leaf、點解。修好之後 pytest 會報 XPASS —— 嗰陣拆走
decorator。一個永遠紅嘅 suite 會令人學識忽略佢。

唔讀外置碟、唔讀 Google Drive、唔出網：所有來源都係 tmp 入面嘅 fixture，
引擎模組嘅來源路徑用 `mock.patch` 指過去，cache 逐次清空。
"""
from __future__ import annotations

import contextlib
import copy
import csv
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts"
SHARED_SCRIPTS = ROOT / ".agents" / "scripts"
AU_SKILL = ROOT / ".agents" / "skills" / "au_racing"
for _p in (str(ROOT), str(SHARED_SCRIPTS), str(AU_SKILL), str(SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import au_auto_orchestrator  # noqa: E402
import build_au_logic  # noqa: E402
import claw_sportsbet_form  # noqa: E402
import inject_fact_anchors  # noqa: E402
import sb_horse_index  # noqa: E402
import sb_people_stats  # noqa: E402
from au_racing_engine import au_draw_bias_calculator, engine_core  # noqa: E402

D_DATE = "2026-08-01"
F_DATE = "2026-08-22"          # 未來場次：同馬場、同一班馬、同一班騎練
VENUE = "Flemington"
RACE_NO = 5
DISTANCE = 1410


# ─────────────────────────────── fixture 語料 ───────────────────────────────
# 四匹馬，每匹三條 D 之前嘅往績。名同騎練取自 scratch/sb_fieldtest 嘅真實
# Flemington 2026-08-01 R5，往績數字係細化過嘅 fixture（唔係真賽果）。

def _hdr(date, track, race, dist, going, cls="BM78"):
    y, m, d = date.split("-")
    return {"date": f"{d}/{m}/{y}", "track": track, "race": str(race),
            "dist": str(dist), "going": going, "cls": cls}


def _run(date, track, race, dist, going, *, pos, field, margin, jockey, barrier,
         weight, sp, settled, p800, p400, l600, prize, opponents, wt_time=None):
    return {"header": _hdr(date, track, race, dist, going), "pos": str(pos),
            "field": str(field), "margin": "0" if pos == 1 else margin,
            "jockey": jockey, "barrier": str(barrier), "weight": str(weight),
            "sp": sp, "is_trial": False, "prize": str(prize), "p1200": None,
            "p800": str(p800), "p400": str(p400), "settled": str(settled),
            "l600": l600, "winning_time": wt_time,
            "opponents": [{"ord": o, "name": n, "wt": w, "mgn": g}
                          for o, n, w, g in opponents]}


HORSES = [
    # num, name, barrier, trainer, jockey, trainer_id, jockey_id
    (1, "Silent Shares", 10, "Gavin Bedggood", "Emily Pozman", "t101", "j201"),
    (4, "Sixteen Reasons", 2, "John Salanitri", "Ryan Houston", "t102", "j202"),
    (7, "Cherish Me", 3, "Ciaron Maher", "Jabez Johnstone", "t103", "j203"),
    (8, "Stage 'n' Screen", 1, "Mark Walker", "Logan Bates", "t104", "j204"),
]


def _past_runs(name, jockey):
    """D 之前嘅三條往績（每匹馬唔同，令場內有排名）。"""
    seed = {"Silent Shares": 0, "Sixteen Reasons": 1, "Cherish Me": 2,
            "Stage 'n' Screen": 3}[name]
    rows = [
        ("2026-07-15", "Sandown Hillside", 3, 1400, "Heavy"),
        ("2026-07-04", "Flemington", 3, 1400, "Soft"),
        ("2026-06-20", "Flemington", 6, 1420, "Good"),
    ]
    out = []
    for i, (date, track, race, dist, going) in enumerate(rows):
        pos = 1 + (seed + i) % 5
        out.append(_run(
            date, track, race, dist, going, pos=pos, field=10,
            margin=f"{0.5 + seed + i:.2f}", jockey=jockey, barrier=2 + seed + i,
            weight="58.0", sp=f"{4.0 + seed * 2 + i:.2f}", settled=2 + seed,
            p800=2 + seed, p400=1 + seed + i % 2, l600=f"{34.2 + seed * 0.2 + i * 0.1:.2f}",
            prize=50000 + 25000 * (i % 2),
            opponents=[("1st", "Duchess Zou", "56.5", None),
                       ("2nd", "Stylish", "56.0", "1.75"),
                       ("3rd", "Miss Aria", "59.0", "2.00")]))
    return out


def _future_run(name, jockey, num):
    """未來場次 F：極端 —— 第一匹大勝 12L，其餘全部包尾。"""
    winner = num == HORSES[-1][0]
    return _run(F_DATE, VENUE, 3, 1400, "Good", pos=1 if winner else 10,
                field=10, margin="25.00", jockey=jockey, barrier=1,
                weight="54.0", sp="51.00" if winner else "1.50", settled=1,
                p800=1, p400=1, l600="32.10", prize=3_000_000,
                opponents=[("1st", HORSES[-1][1], "54.0", None),
                           ("2nd", "Duchess Zou", "56.5", "12.00"),
                           ("3rd", "Stylish", "56.0", "12.50")])


BASE_STATS = {
    "Career": "10: 2-2-2", "12 months": "6: 1-1-1", "Track": "3: 1-0-1",
    "Distance": "4: 1-1-0", "Trk/Dist": "2: 0-1-0", "Firm": "0: 0-0-0",
    "Good": "4: 1-1-1", "Soft": "5: 1-1-1", "Heavy": "1: 0-0-0",
    "Synthetic": "0: 0-0-0", "1st Up": "2: 0-1-0", "2nd Up": "2: 1-0-0",
    "3rd Up": "2: 0-0-1", "Jockey": "3: 1-0-1", "Prizemoney": "$150,000",
    "Turf": "10: 2-2-2", "Win Range": "1200m - 1600m", "Weight": "58.0kg",
}
# 一張「賽後喺 F 之後先抓」嘅頁面：每個累積統計都加埋 F。
FUTURE_STATS = {
    "Career": "11: 7-2-2", "12 months": "7: 6-1-1", "Track": "4: 4-0-1",
    "Distance": "5: 4-1-0", "Trk/Dist": "3: 3-1-0", "Firm": "0: 0-0-0",
    "Good": "5: 5-1-1", "Soft": "5: 1-1-1", "Heavy": "1: 0-0-0",
    "Synthetic": "0: 0-0-0", "1st Up": "2: 0-1-0", "2nd Up": "2: 1-0-0",
    "3rd Up": "3: 3-0-1", "Jockey": "4: 4-0-1", "Prizemoney": "$3,150,000",
    "Turf": "11: 7-2-2", "Win Range": "1000m - 1600m", "Weight": "58.0kg",
}


def build_races(*, future_runs=False, future_stats=False):
    """砌 `write_meeting` 吃嘅 `races`（同 `parse_race` 輸出同形）。

    future_runs  ：表格頁喺 F 之後先抓 → 每匹馬往績頂部多一行 F。
    future_stats ：表格頁嘅累積統計（Career / Track / 12 months / J/H …）
                   同總覽表欄位都已經計埋 F。
    """
    overview, blocks, people = {}, [], {}
    for num, name, barrier, trainer, jockey, tid, jid in HORSES:
        stats = dict(FUTURE_STATS if future_stats else BASE_STATS)
        overview[num] = {
            "name": name, "trainer": trainer, "jockey": jockey, "age_sex": "5yoM",
            "rating": "-", "career": stats["Career"].replace(": ", " : "),
            "win_pct": "64%" if future_stats else "20%",
            "place_pct": "100%" if future_stats else "60%",
            "last6": "1x2131" if future_stats else "x2131",
            "fixed_win": "4.50", "days": "10" if future_stats else "17",
            "ave_prize": "$286,000" if future_stats else "$15,000",
        }
        runs = _past_runs(name, jockey)
        if future_runs:
            runs = [_future_run(name, jockey, num)] + runs
        blocks.append({"name": name, "barrier": barrier, "stats": stats,
                       "profile": {"sire": "Snitzel", "dam": "Fixture Dam"},
                       "runs": runs, "jockey_allowance_kg": None})
        people[("Trainer", claw_sportsbet_form._people_key(trainer))] = tid
        people[("Jockey", claw_sportsbet_form._people_key(jockey))] = jid
    meta = {"distance": DISTANCE, "track_condition": "Good 4", "weather": "Fine",
            "rail": "True", "race_class": "BM78", "people_by_name": people,
            "odds": {}, "silks": {}, "gear_changes": {}}
    return [(RACE_NO, {"meta": meta, "overview": overview}, blocks)]


def people_cache(*, future=False):
    """`AU_Sportsbet_People_Cache.json`。future=True 係 F 之後先 refresh 嘅版本：
    12 個月往績已經計埋 F（騎師全部贏，練馬師多一場）。"""
    cache = {}
    for i, (_num, _name, _bar, trainer, jockey, tid, jid) in enumerate(HORSES):
        for kind, pid, pname, base in (("trainer", tid, trainer, 120 + 40 * i),
                                       ("jockey", jid, jockey, 300 + 50 * i)):
            starts = base + (1 if future else 0)
            wins = (base // 9) + (40 if future else 0)
            stats = {"12 Months": {"starts": starts, "1st": wins,
                                   "2nd": base // 10, "3rd": base // 11}}
            cache[f"{kind}|{pid}"] = {
                "name": pname, "id": pid, "kind": kind, "stats": stats,
                "contextual_stats": {}, "ly": sb_people_stats.ly_token(stats),
                "fetched_at": ("2026-08-23T00:00:00+00:00" if future
                               else "2026-07-31T00:00:00+00:00")}
    return cache


def horse_index(*, future=False):
    """`.sb_horse_index.json`。賽績線對手（Duchess Zou / Stylish / Miss Aria）
    喺 D 之前嘅記錄；future=True 再併入 F 嘅 runner block（佢哋喺 F 跑前列）。"""
    index = {}
    pre = [{"name": "Duchess Zou", "runs": [_run(
        "2026-07-25", "Caulfield", 4, 1400, "Good", pos=2, field=9, margin="0.5",
        jockey="X Rider", barrier=3, weight="57", sp="3.0", settled=2, p800=2, p400=2,
        l600="34.0", prize=100000,
        opponents=[("1st", "Stylish", "56", None), ("2nd", "Duchess Zou", "57", "0.5"),
                   ("3rd", "Miss Aria", "58", "1.0")])]}]
    sb_horse_index.update(pre, index=index, save_now=False)
    if future:
        blocks = [{"name": name, "runs": [_future_run(name, jockey, num)]}
                  for num, name, _b, _t, jockey, _ti, _ji in HORSES]
        sb_horse_index.update(blocks, index=index, save_now=False)
    return index


RESULT_FIELDS = ["Date", "Track", "Race", "Distance", "Horse", "Barrier", "Pos"]


def results_rows(*, future=False):
    """結果 CSV（檔位矩陣嘅輸入）。D 之前幾場 Flemington 1400m；future=True
    加 F：內檔全部贏 —— 一個極端到一定會郁 cell 嘅賽果。"""
    rows = []
    for k, date in enumerate(("2026-06-20", "2026-07-04", "2026-07-11", "2026-07-18")):
        for barrier in range(1, 11):
            pos = ((barrier + k * 3) % 10) + 1
            rows.append({"Date": date, "Track": VENUE, "Race": "3", "Distance": "1400",
                         "Horse": f"Old {k}-{barrier}", "Barrier": str(barrier),
                         "Pos": str(pos)})
    if future:
        for r in range(1, 9):
            for barrier in range(1, 11):
                rows.append({"Date": F_DATE, "Track": VENUE, "Race": str(r),
                             "Distance": str(DISTANCE), "Horse": f"Fut {r}-{barrier}",
                             "Barrier": str(barrier), "Pos": str(barrier)})
    return rows


COMBO_FIELDS = ["Track", "Jockey", "Trainer", "Total Runs", "Wins", "Win %",
                "Places (Top 3)", "Place %"]


def combo_rows(*, future=False):
    """`AU_Jockey_Trainer_Combo_Stats.csv`：冇日期欄，係全期累積。F 之後
    重建一次 = 每個 D 嘅騎練組合多一場、全部贏。"""
    rows = []
    for _n, _h, _b, trainer, jockey, _t, _j in HORSES:
        runs, wins, places = 12, 2, 5
        if future:
            runs, wins, places = runs + 6, wins + 6, places + 6
        rows.append({"Track": VENUE, "Jockey": jockey, "Trainer": trainer,
                     "Total Runs": runs, "Wins": wins,
                     "Win %": f"{wins / runs * 100:.1f}%", "Places (Top 3)": places,
                     "Place %": f"{places / runs * 100:.1f}%"})
    return rows


RATING_FIELDS = ["name", "canonical_name", "tier", "base_score", "confidence",
                 "source", "notes"]


def rating_rows(kind, *, future=False):
    """`AU_{Jockey,Trainer}_Ratings.csv`：tier 表，冇日期。F 之後重評 =
    D 嘅騎練全部升 T1。"""
    rows = []
    for _n, _h, _b, trainer, jockey, _t, _j in HORSES:
        name = jockey if kind == "jockey" else trainer
        tier, score = ("T1", 74) if future else ("T3", 60)
        rows.append({"name": name, "canonical_name": name, "tier": tier,
                     "base_score": score, "confidence": "fixture",
                     "source": "fixture", "notes": ""})
    return rows


def _write_csv(path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


# ─────────────────────────────── 生產流程 ───────────────────────────────

SOURCES = ("form_runs", "form_runs_raw", "form_stats", "people_cache", "horse_index",
           "draw_matrix", "jt_combo", "jt_ratings", "pf_backfill")


def _inject_raw_future_lines(formguide: Path) -> None:
    """繞過 `write_meeting` 個日期閘，直接將 F 嘅往績行插入 Formguide 每匹馬
    第一條往績之前 —— 即係 2026-08-01 之前、閘未存在時抽落嚟嘅舊檔個形狀。
    測嘅係**下游**（inject_fact_anchors / 引擎）自己有冇第二道 as-of 閘。"""
    import re
    text = formguide.read_text(encoding="utf-8")
    out = []
    for num, name, _b, _t, jockey, _ti, _ji in HORSES:
        head = re.search(rf"^\[{num}\] ", text, re.M)
        first = re.compile(r"^\S.+? R\d+ \d{4}-\d{2}-\d{2} ", re.M).search(text, head.end())
        a, b = claw_sportsbet_form.run_line(_future_run(name, jockey, num))
        block = f"{a}\n{b}\nVideo: \nNote: \nStewards: \n\n"
        out.append((first.start(), block))
    for pos, block in sorted(out, reverse=True):
        text = text[:pos] + block + text[pos:]
    assert text.count(F_DATE) >= len(HORSES), "未來往績行冇插到 —— case 會假綠"
    formguide.write_text(text, encoding="utf-8")


def _reset_engine_caches():
    engine_core.JOCKEY_TRAINER_COMBO_CACHE = None
    engine_core.TRAINER_TRACK_CACHE = None
    engine_core.JOCKEY_RATINGS_CACHE = None
    engine_core.TRAINER_RATINGS_CACHE = None
    engine_core.DRAW_BIAS_MATRIX_CACHE = None
    engine_core._PF_BACKFILL_CACHE = None
    inject_fact_anchors._SB_INDEX_CACHE.clear()


def score_meeting_d(work: Path, future: frozenset, *, people_empty: bool = False) -> dict:
    """喺 `work` 入面由零行一次生產流程，回傳 D 每匹馬嘅指紋。

    `future` 係「已經加咗 F 嘅來源」集合；其餘來源用 D 之前嘅版本。
    `people_empty`：騎練 cache 全空（`(LY: -)`），令引擎行 tier 表 fallback。
    """
    unknown = set(future) - set(SOURCES)
    assert not unknown, unknown
    work.mkdir(parents=True, exist_ok=True)
    res = work / "resources"
    res.mkdir(exist_ok=True)
    # 1. 引擎靜態表
    _write_csv(res / "combo.csv", COMBO_FIELDS, combo_rows(future="jt_combo" in future))
    _write_csv(res / "jockey.csv", RATING_FIELDS,
               rating_rows("jockey", future="jt_ratings" in future))
    _write_csv(res / "trainer.csv", RATING_FIELDS,
               rating_rows("trainer", future="jt_ratings" in future))
    results_csv = res / "results.csv"
    _write_csv(results_csv, RESULT_FIELDS, results_rows(future="draw_matrix" in future))
    matrix_path = res / "au_draw_bias_matrix.json"
    # 檔位矩陣用**生產**嘅 calculator 由結果 CSV 重建 —— 佢冇 as-of 參數。
    with mock.patch.object(au_draw_bias_calculator, "CSV_PATH", str(results_csv)), \
            mock.patch.object(au_draw_bias_calculator, "BACKFILL_CSV_PATH",
                              str(res / "no_backfill.csv")), \
            mock.patch.object(au_draw_bias_calculator, "OUTPUT_JSON", str(matrix_path)), \
            contextlib.redirect_stdout(io.StringIO()):
        assert au_draw_bias_calculator.main() == 0
    index_path = res / "sb_horse_index.json"
    sb_horse_index.save(horse_index(future="horse_index" in future), index_path)
    people = {} if people_empty else people_cache(future="people_cache" in future)
    # 騎練 point-in-time 快照（append-only）：D 之前一定有 07-31 嗰次；F 之後
    # refresh 會**追加**一條 08-23，而 cache 本身被覆蓋成 08-23 版本。
    snapshots = res / "people_snapshots.jsonl"
    with snapshots.open("w", encoding="utf-8") as handle:
        if not people_empty:
            versions = [people_cache(future=False)]
            if "people_cache" in future:
                versions.append(people)
            for version in versions:
                for key, entry in version.items():
                    handle.write(json.dumps({
                        "captured_at": entry["fetched_at"], "key": key, "name": entry["name"],
                        "kind": entry["kind"], "id": entry["id"], "stats": entry["stats"],
                        "contextual_stats": {}}) + "\n")

    archive = work / "archive"
    meeting = archive / f"{D_DATE} {VENUE} Race {RACE_NO}-{RACE_NO}"
    meeting.mkdir(parents=True, exist_ok=True)
    # PF 歷史 backfill cache 擺喺 archive root（引擎由 meeting_dir.parent 搵）。
    if "pf_backfill" in future:
        (archive / engine_core.PF_BACKFILL_FILENAMES[0]).write_text(json.dumps({
            "meetings": {meeting.name: {str(RACE_NO): {
                name: {"runs": [{"date": F_DATE, "l600_delta": -3.0}]}
                for _n, name, *_r in HORSES}}}}), encoding="utf-8")

    _reset_engine_caches()
    env = {k: v for k, v in os.environ.items() if not k.startswith("WC_")}
    patches = [
        mock.patch.dict(os.environ, env, clear=True),
        mock.patch.object(engine_core, "JOCKEY_TRAINER_COMBO_STATS_PATH", res / "combo.csv"),
        mock.patch.object(engine_core, "JOCKEY_RATINGS_PATH", res / "jockey.csv"),
        mock.patch.object(engine_core, "TRAINER_RATINGS_PATH", res / "trainer.csv"),
        mock.patch.object(engine_core, "DRAW_BIAS_MATRIX_PATH", matrix_path),
        mock.patch.object(sb_horse_index, "DEFAULT_INDEX", index_path),
        # `inject_fact_anchors.main()` 會 set 模組級 `_AS_OF`；唔還原會令同一個
        # pytest process 之後嘅測試靜靜帶住 D 做時點上限。
        mock.patch.object(inject_fact_anchors, "_AS_OF", inject_fact_anchors._AS_OF),
        mock.patch.object(sb_people_stats, "load_cache", lambda path=None: copy.deepcopy(people)),
        mock.patch.object(sb_people_stats, "snapshot_path", lambda path=None: snapshots),
    ]
    sink = io.StringIO()
    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        stack.enter_context(contextlib.redirect_stdout(sink))
        stack.enter_context(contextlib.redirect_stderr(sink))
        # 2. 抽取層：表格頁 → Racecard / Formguide（含 D 日期閘同 LY token）
        claw_sportsbet_form.write_meeting(
            build_races(future_runs="form_runs" in future,
                        future_stats="form_stats" in future),
            str(meeting), D_DATE, VENUE, verbose=False)
        racecard = meeting / f"08-01 Race {RACE_NO} Racecard.md"
        formguide = meeting / f"08-01 Race {RACE_NO} Formguide.md"
        if "form_runs_raw" in future:
            _inject_raw_future_lines(formguide)
        # 3. Facts 層（賽績線查對手索引，as-of 由資料夾日期抽）
        with mock.patch.object(sys, "argv", [
                "inject_fact_anchors.py", str(racecard), str(formguide),
                "--max-display", "5", "--venue", VENUE, "--distance", str(DISTANCE)]):
            inject_fact_anchors.main()
        facts = meeting / f"08-01 Race {RACE_NO} Facts.md"
        # 4. Logic 層 + 5. 評分（生產入口，唔寫輸出）
        logic_path = meeting / f"Race_{RACE_NO}_Logic.json"
        logic = build_au_logic.build_logic_from_facts(facts)
        logic_path.write_text(json.dumps(logic, ensure_ascii=False), encoding="utf-8")
        scored = au_auto_orchestrator.score_logic_data(logic_path)
    _reset_engine_caches()
    return fingerprint(scored)


def _num(value):
    return round(float(value), 10) if isinstance(value, (int, float)) and not isinstance(value, bool) else value


def fingerprint(scored: dict) -> dict:
    """每匹馬：全部 leaf、全部維度分、綜合分、評級；再加最終排名。"""
    horses = {}
    for num, horse in sorted((scored.get("horses") or {}).items()):
        auto = horse.get("python_auto") or {}
        horses[num] = {
            "feature_scores": {k: _num(v) for k, v in sorted((auto.get("feature_scores") or {}).items())},
            "matrix_scores": {k: _num(v) for k, v in sorted((auto.get("matrix_scores") or {}).items())},
            "ability_score": _num(auto.get("ability_score")),
            "grade": auto.get("final_grade") or auto.get("grade"),
        }
    ranking = sorted(horses, key=lambda n: (-(horses[n]["ability_score"] or 0), int(n)))
    return {"horses": horses, "ranking": ranking}


def diff(a: dict, b: dict) -> list[str]:
    out = []
    if a["ranking"] != b["ranking"]:
        out.append(f"ranking {a['ranking']} -> {b['ranking']}")
    for num in a["horses"]:
        ha, hb = a["horses"][num], b["horses"].get(num, {})
        for group in ("feature_scores", "matrix_scores"):
            for key in sorted(set(ha[group]) | set(hb.get(group, {}))):
                va, vb = ha[group].get(key), hb.get(group, {}).get(key)
                if va != vb:
                    out.append(f"#{num} {group}.{key}: {va} -> {vb}")
        for key in ("ability_score", "grade"):
            if ha[key] != hb.get(key):
                out.append(f"#{num} {key}: {ha[key]} -> {hb.get(key)}")
    return out


class FutureAppendInvarianceTests(unittest.TestCase):
    """每個 case：只喺**一個**來源加 F，D 嘅指紋一定要唔變。"""

    baseline: dict | None = None

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name)
        cls.baseline = score_meeting_d(cls.root / "baseline", frozenset())

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _assert_invariant(self, *sources, people_empty=False):
        baseline = self.baseline
        tag = "+".join(sources) + ("-noly" if people_empty else "")
        if people_empty:
            baseline = score_meeting_d(self.root / f"base{tag}", frozenset(), people_empty=True)
        candidate = score_meeting_d(self.root / tag, frozenset(sources), people_empty=people_empty)
        changes = diff(baseline, candidate)
        self.assertEqual(changes, [], f"加咗未來場次 {F_DATE} 入 {sources} 之後，"
                         f"{D_DATE} 嘅評分變咗：\n  " + "\n  ".join(changes))

    # ── 健全性：fixture 真係有料，唔係全中性（否則「冇變」係假綠）──
    def test_baseline_is_not_degenerate(self):
        self.assertEqual(len(self.baseline["horses"]), len(HORSES))
        abilities = {h["ability_score"] for h in self.baseline["horses"].values()}
        self.assertGreater(len(abilities), 1, "四匹馬綜合分一樣 —— fixture 冇區分度")
        leaves = self.baseline["horses"][str(HORSES[0][0])]["feature_scores"]
        self.assertGreater(len(leaves), 10)
        moved = [k for k, v in leaves.items() if isinstance(v, float) and v != 60.0]
        self.assertGreater(len(moved), 5, f"太多 leaf 坐中性 60：{leaves}")

    def test_rerun_is_deterministic(self):
        again = score_meeting_d(self.root / "rerun", frozenset())
        self.assertEqual(diff(self.baseline, again), [])

    def test_detector_catches_a_real_change(self):
        """反證：如果 harness 根本睇唔到變化，下面每個綠燈都冇意義。
        D 自己嘅往績改咗（唔係未來），指紋一定要郁。"""
        original = _past_runs

        def worse(name, jockey):
            runs = original(name, jockey)
            for r in runs:
                r["pos"], r["margin"] = "10", "20.00"
            return runs
        with mock.patch(f"{__name__}._past_runs", worse):
            changed = score_meeting_d(self.root / "detector", frozenset())
        self.assertNotEqual(diff(self.baseline, changed), [])

    # ── 每個來源一個 case ──
    # 量度（2026-10-14，呢個 fixture）寫喺每個 expectedFailure 嘅 docstring。
    # fixture 細，幅度只代表「會郁」同「郁邊個 leaf」，唔代表語料庫嘅平均影響。

    def test_form_page_runs(self):
        """表格頁往績行：`write_meeting` 有 `run_date >= D` 閘。"""
        self._assert_invariant("form_runs")

    def test_form_page_runs_downstream_gate(self):
        """第二道閘：F 往績行繞過抽取閘直接寫入 Formguide（2026-08-01 前抽嘅
        舊檔就係咁），`parse_formguide_for_horse(as_of)`、
        `_prize_map_from_formguide`、PF parser 仍然要剔走。"""
        self._assert_invariant("form_runs_raw")

    def test_form_page_cumulative_stats(self):
        """已修（EXP-20261015-04）。原本 LEAK（2026-10-14 呢個測試發現）：表格頁**累積統計**冇日期閘。

        `claw_sportsbet_form.write_meeting` 只濾往績**行**
        （`run_date(run) >= date_str`），但 `Career / Last 10 / Track / Distance /
        Good / 12 months / J/H / Prize / Win% / Place% / Days / Ave $` 係由同一張
        頁面原封抄入 Formguide／Racecard。賽後先抓嘅頁面（例如
        `sb_backfill_archive.py` 重抽舊場次）已經計埋當日同之後嘅賽果。
        賽前生產抽取冇事；回放／backfill 有事。
        fixture 量度：`consistency_score` 四匹馬 98.74 → 100.0（排名未變）。
        修法：歷史場次（D < 今日，或頁面已有 D 當日往績行）唔用頁面累積數，
        由已過日期閘嘅往績行重計（`pit_runner_stats`）；live 照用頁面數。
        """
        self._assert_invariant("form_stats")

    def test_people_stats_cache(self):
        """已修（EXP-20261015-04）。原本 LEAK（memory「騎練率有前視」）：`sb_people_stats` cache 冇 as-of。

        `write_meeting` 用 `entry["ly"]`（最近一次 refresh 嘅 12 個月往績）寫
        `(LY: …)`，唔理 `fetched_at` 係咪喺 D 之後；`jockey_score` /
        `trainer_score` 直接食呢個 token。`AU_Sportsbet_People_Snapshots.jsonl`
        已經有 point-in-time 快照，但冇 reader 用佢。
        fixture 量度：jockey_score +20.9~+30.7、trainer_score +21.3~+39.4、
        綜合分 +8.6~+14.2，**排名 #7/#8 對調**。
        修法：歷史場次用 `sb_people_stats.load_as_of(D)` —— 嚴格早過 D（悉尼
        00:00）最後一個快照；冇就 `-`（中性），唔准跌返 current cache。
        fixture 有寫快照檔，baseline 嘅 LY 係真值（唔係兩邊都中性嘅假綠）。
        """
        self._assert_invariant("people_cache")

    def test_opponent_horse_index(self):
        """賽績線對手索引：`sb_horse_index.lookup(as_of=D)` 剔走 D 當日及之後
        （baseline formline_score 唔係中性，即係呢條路真係有行）。"""
        formline = {h["feature_scores"]["formline_score"] for h in self.baseline["horses"].values()}
        self.assertNotEqual(formline, {60.0}, "賽績線全中性 —— 索引冇被查，case 會假綠")
        future = horse_index(future=True)
        self.assertTrue(any(r["date"] > D_DATE for r in future["duchess-zou"]["runs"]))
        self._assert_invariant("horse_index")

    def test_draw_bias_matrix(self):
        """已修（EXP-20261015-04）。原本 LEAK（memory「檔位矩陣洩漏入回測」）：

        `au_draw_bias_calculator.main()` 用**全份**結果 CSV（主 CSV + backfill）
        建矩陣，冇 as-of 參數；引擎讀單一靜態 `au_draw_bias_matrix.json`。
        fixture 量度：`pace_map_score` 60.0 → 64.05（四匹）。`race_shape` 已退役
        （權重 0），所以綜合分同排名今日唔郁 —— 但任何重新啟用 pace_map 嘅
        候選喺回放都會食到未來。
        修法：calculator 另寫逐場 sidecar `au_draw_bias_races.json`；歷史場次
        由 `Date < D` 嘅場次用同一個 `build_matrix()` 重砌。
        """
        self._assert_invariant("draw_matrix")

    def test_jockey_trainer_combo_stats(self):
        """`AU_Jockey_Trainer_Combo_Stats.csv` 全期累積、冇日期欄 —— 但今日只係
        display-only（`add(0.0, …)`），所以 leaf 唔郁。報告文字會郁。
        有 LY 同冇 LY 兩條路都要守住。"""
        self._assert_invariant("jt_combo")
        self._assert_invariant("jt_combo", people_empty=True)

    def test_jockey_trainer_ratings_with_ly(self):
        """有 `(LY:)` 嘅時候 tier 表唔入分（統一上名率優先）。"""
        self._assert_invariant("jt_ratings")

    def test_jockey_trainer_ratings_fallback(self):
        """已修（EXP-20261015-04）。原本 LEAK：`(LY: -)` 嘅馬跌落 `AU_{Jockey,Trainer}_Ratings.csv` tier 表，
        而個表冇日期／版本 —— D 之後任何重評都會改 D 嘅 leaf。
        fixture 量度：jockey_score / trainer_score 60 → 74、綜合分 +5.75（四匹）、
        評級升一級（排名未變，因為四匹同時升）。
        修法：tier 表加 `as_of` 欄；歷史場次只用 `as_of < D` 嘅行，冇日期 = 中性。
        """
        self._assert_invariant("jt_ratings", people_empty=True)

    def test_pf_backfill_cache_is_off_by_default(self):
        """PF 歷史 backfill 預設關（`WC_PF_BACKFILL` 未 set）。呢個 case 只證明
        生產預設唔讀佢；開咗之後嘅 as-of（`target_date`）**未有覆蓋**。"""
        self._assert_invariant("pf_backfill")


class PointInTimeModeTests(unittest.TestCase):
    """修法嘅另一面：live（D ≥ 今日）一定要同以前一模一樣。"""

    def _write(self, tmp, today, *, people=None, snapshots=()):
        snap = Path(tmp) / "snap.jsonl"
        snap.write_text("".join(json.dumps(r) + "\n" for r in snapshots), encoding="utf-8")
        out = Path(tmp) / today
        with mock.patch.dict(os.environ, {"WC_AU_PIT_TODAY": today}), \
                mock.patch.object(sb_people_stats, "load_cache",
                                  lambda path=None: copy.deepcopy(people or {})), \
                mock.patch.object(sb_people_stats, "snapshot_path", lambda path=None: snap), \
                contextlib.redirect_stdout(io.StringIO()):
            summary = claw_sportsbet_form.write_meeting(build_races(), str(out), D_DATE, VENUE,
                                                        verbose=False)
        return summary, (out / f"08-01 Race {RACE_NO} Formguide.md").read_text(encoding="utf-8")

    def test_live_keeps_page_stats_and_current_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary, text = self._write(tmp, D_DATE, people=people_cache(future=True))
        self.assertEqual(summary["pit_races"], 0)
        self.assertIn("Career:    10: 2-2-2", text)            # 頁面數，原封
        future_ly = people_cache(future=True)["jockey|j201"]["ly"]
        self.assertIn(f"(LY: {future_ly})", text)               # live 用 current cache

    def test_historical_recomputes_and_uses_pre_d_snapshot(self):
        base = people_cache(future=False)
        snaps = [{"captured_at": e["fetched_at"], "key": k, "stats": e["stats"]}
                 for k, e in base.items()]
        with tempfile.TemporaryDirectory() as tmp:
            summary, text = self._write(tmp, "2026-10-14", people=people_cache(future=True),
                                        snapshots=snaps)
        self.assertEqual(summary["pit_races"], 1)
        self.assertNotIn("10: 2-2-2", text)
        self.assertIn("Career:    3: ", text)                    # 三條 D 前往績
        self.assertIn(f"(LY: {base['jockey|j201']['ly']})", text)

    def test_historical_without_pre_d_snapshot_is_neutral(self):
        """冇 D 前快照 → `-`，唔准跌返 current cache。"""
        with tempfile.TemporaryDirectory() as tmp:
            _summary, text = self._write(tmp, "2026-10-14", people=people_cache(future=True))
        self.assertNotIn("(LY: 3", text)
        self.assertIn("(LY: -)", text)

    def test_dated_tier_rows_survive_historical_and_undated_do_not(self):
        engine = engine_core.RacingEngine.__new__(engine_core.RacingEngine)
        engine.race_context = {"meeting_intelligence": {"date": D_DATE}}
        engine.facts_path = None
        dated = {"tier": "T1", "as_of": "2026-05-16"}
        later = {"tier": "T1", "as_of": D_DATE}               # 同日先評 = 唔算賽前
        undated = {"tier": "T1", "as_of": ""}
        with mock.patch.dict(os.environ, {"WC_AU_PIT_TODAY": "2026-10-14"}):
            self.assertIs(engine._rating_known_at_race(dated), dated)
            self.assertIsNone(engine._rating_known_at_race(later))
            self.assertIsNone(engine._rating_known_at_race(undated))
        with mock.patch.dict(os.environ, {"WC_AU_PIT_TODAY": D_DATE}):   # live：照舊
            self.assertIs(engine._rating_known_at_race(undated), undated)

    def test_historical_draw_matrix_without_sidecar_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(engine_core, "DRAW_BIAS_MATRIX_PATH", Path(tmp) / "m.json"):
            self.assertEqual(engine_core._load_draw_bias_matrix_as_of(D_DATE), {})

    def test_post_race_page_is_historical_even_on_race_day(self):
        """同日賽後重跑：今日 = D，但頁面已經有 D 當日往績行 → 嗰場當歷史。"""
        races = build_races(future_runs=False)
        for blk in races[0][2]:
            blk["runs"] = [_run(D_DATE, VENUE, RACE_NO, DISTANCE, "Good", pos=1, field=10,
                                margin="0", jockey="X", barrier=1, weight="58", sp="2.0",
                                settled=1, p800=1, p400=1, l600="34.0", prize=100000,
                                opponents=[])] + blk["runs"]
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {"WC_AU_PIT_TODAY": D_DATE}), \
                mock.patch.object(sb_people_stats, "load_cache", lambda path=None: {}), \
                mock.patch.object(sb_people_stats, "snapshot_path",
                                  lambda path=None: Path(tmp) / "none.jsonl"), \
                contextlib.redirect_stdout(io.StringIO()):
            summary = claw_sportsbet_form.write_meeting(races, tmp, D_DATE, VENUE, verbose=False)
        self.assertEqual(summary["pit_mode"], "live")
        self.assertEqual(summary["pit_races"], 1)
        self.assertEqual(summary["dropped"], len(HORSES))


if __name__ == "__main__":
    unittest.main()
