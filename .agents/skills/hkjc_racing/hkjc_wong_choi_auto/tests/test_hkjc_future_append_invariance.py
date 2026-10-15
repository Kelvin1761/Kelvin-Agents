"""「加未來唔可以改過去」—— HKJC 通用 point-in-time 不變性測試。

同 AU 嗰份（`au_wong_choi_auto/tests/test_au_future_append_invariance.py`）一樣嘅
問題，但係**獨立嘅 harness** —— 兩個引擎唔准合併（AGENTS.md 第 4 條）。

點解要有呢個（2026-10-14，借自 hkjc-edge-lab）：EXP-20260902-03 發現 HKJC
回放經騎練 master stats 洩漏，而嗰個來源冇人寫過 PIT 測試。逐個特徵寫 PIT
測試，每加一個來源就要有人記得 —— 呢個測試改為直接問結果：

    1. 用 repo 入面嘅真實 HKJC formguide（跑馬地 2026-03-04 第 3 場）行**成條
       生產流程**：inject_hkjc_fact_anchors → create_hkjc_logic_skeleton →
       HKJCAutoOrchestrator.score_race。
    2. 喺每一個流程會讀嘅數據源加一個**未來場次** F（同場地、同一班馬／騎練，
       賽果極端）。
    3. 重新計 D：每個 leaf、維度分、綜合分、名次都要逐位元一樣。

已知洩漏標 `expectedFailure` 並寫明來源同 leaf；修好會 XPASS，嗰陣拆 decorator。
唔讀外置碟／Drive、唔出網：所有來源用 `mock.patch` 指去 tmp fixture。
"""
from __future__ import annotations

import contextlib
import csv
import io
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[5]
AUTO_SCRIPTS = ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_wong_choi_auto" / "scripts"
MAIN_SCRIPTS = ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_wong_choi" / "scripts"
SHARED_SCRIPTS = ROOT / ".agents" / "scripts"
for _p in (str(ROOT), str(SHARED_SCRIPTS), str(MAIN_SCRIPTS), str(AUTO_SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import create_hkjc_logic_skeleton as skeleton  # noqa: E402
import hkjc_auto_orchestrator as auto  # noqa: E402
import inject_hkjc_fact_anchors as inject  # noqa: E402
from hkjc_racing_engine import engine_core, live_priors, rail_draw_context  # noqa: E402
from hkjc_racing_engine.features import tier_loader  # noqa: E402

FORMGUIDE = ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_race_extractor" / "formguide_3.txt"
D_DATE = "2026-03-04"          # 跑馬地 第 3 場 2200m 第四班（真實 formguide）
F_DATE = "2026-03-18"          # 未來場次：同場地、同路程、同一班馬
F_DMY = "18/03/2026"
RACE_NO = 3
SEASON = "25_26"

SOURCES = (
    "formguide_runs", "standard_times", "reference_sectionals", "draw_stats",
    "master_stats", "general_priors", "recency_trainer", "rail_draw",
    "tier_table", "profile_history",
)


# ─────────────────────────────── fixture 來源 ───────────────────────────────

def _future_formguide(text: str) -> str:
    """每匹馬「往績紀錄:」之下插一條 F 往績（頭馬、能量 140、段速極快）。"""
    future = (
        f'  [1] {F_DMY} | 日數: 14 | 跑馬地 "C" 2200 好/快\n'
        "      檔位: 1 | 馬重: 1050 | 負磅: 113 | 騎師: 潘頓 | 名次: 1 / 12\n"
        "      能量: 140 | 分段時間: 13.00, 21.00, 22.00, 22.00, 21.00, 20.00\n"
        "      短評: 慢步速(-)(1W1W1W1W) 領放。大勝十二個馬位。\n"
    )
    out = text.replace("往績紀錄:\n", "往績紀錄:\n" + future)
    assert out.count(F_DMY) >= 10, "未來往績行冇插到 —— case 會假綠"
    return out


def _standard_times(future: bool) -> dict:
    """`hkjc_standard_times.json` 嘅 standard_times。future=True：F 之後 HKJC
    重新公佈（今場路程班次嘅標準時間大幅改）。"""
    real = json.loads((SHARED_SCRIPTS / "hkjc_standard_times.json").read_text(encoding="utf-8"))
    table = dict(real.get("standard_times") or {})
    if future:
        for key in list(table):
            if key.startswith("跑馬地_"):
                table[key] = round(table[key] - 3.0, 2)
    return table


def _reference_sectionals(future: bool) -> dict:
    real = json.loads((SHARED_SCRIPTS / "hkjc_reference_sectionals.json").read_text(encoding="utf-8"))
    if future:
        for dist in real["venues"]["happy_valley_turf"].values():
            for row in dist.values():
                row["sections"] = [round(s - 1.0, 2) for s in row.get("sections", [])]
                row["total"] = round(float(row.get("total") or 0) - 6.0, 2)
    return real


def _draw_stats(future: bool) -> dict:
    """`hkjc_draw_stats.json`：每個賽日前由 HKJC 檔位頁抓，只得一份全域檔。
    future=True = 下一個賽日（F）抓完覆蓋咗佢，同場地同路程同場次號。"""
    def draws(bias):
        rows = []
        for draw in range(1, 13):
            good = (draw <= 3) if bias == "inner" else (draw >= 10)
            rows.append({"draw": draw, "starts": 40, "wins": 8 if good else 2,
                         "seconds": 4, "thirds": 4, "fourths": 2,
                         "win_pct": 20.0 if good else 5.0,
                         "quinella_pct": 30.0 if good else 10.0,
                         "place_pct": 40.0 if good else 15.0, "top4_pct": 45.0,
                         "verdict": "✅有利" if good else "❌不利"})
        return rows
    meeting = f"跑馬地 {F_DMY}" if future else "跑馬地 04/03/2026"
    return {"meta": {"meeting": meeting, "scraped_at": "fixture"},
            "races": [{"race": RACE_NO, "distance": 2200, "surface": "草地", "course": "C",
                       "avg_place_pct": 25.0, "avg_win_pct": 8.3,
                       "draws": draws("outer" if future else "inner")}]}


def _people(logic: dict) -> tuple[list[str], list[str]]:
    horses = logic.get("horses") or {}
    jockeys = sorted({str(h.get("jockey") or "").strip() for h in horses.values()} - {""})
    trainers = sorted({str(h.get("trainer") or "").strip() for h in horses.values()} - {""})
    return jockeys, trainers


def _write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _write_people_sources(res: Path, logic: dict, future: frozenset) -> dict:
    """騎練 master stats／一般先驗／90 日練馬師近況 —— 全部係「本季累積到最近
    一個已完成賽日」嘅快照，冇逐行日期。F 之後重建 = 每人多 F 嗰場，全部贏。"""
    jockeys, trainers = _people(logic)
    bump = lambda key: 30 if key in future else 0  # noqa: E731
    paths = {}
    for group, names in (("jockey", jockeys), ("trainer", trainers)):
        col = "Jockey" if group == "jockey" else "Trainer"
        rows = [{col: n, "Wins": 10 + i + bump("master_stats"),
                 "Starts": 200 + 7 * i + bump("master_stats"),
                 "Places": 40 + 2 * i + bump("master_stats")}
                for i, n in enumerate(names)]
        paths[group] = res / SEASON / f"{group}_master_stats.csv"
        _write_csv(paths[group], [col, "Wins", "Starts", "Places"], rows)
    g = bump("general_priors")
    combo = [{"Jockey": j, "Trainer": t, "Wins": 2 + g, "Starts": 20 + g, "Places": 6 + g}
             for j in jockeys for t in trainers]
    paths["combo"] = res / SEASON / "general_pre_race_priors" / "jockey_trainer_combo_priors.csv"
    _write_csv(paths["combo"], ["Jockey", "Trainer", "Wins", "Starts", "Places"], combo)
    paths["jockey_distance"] = res / SEASON / "jockey_distance_stats.csv"
    _write_csv(paths["jockey_distance"], ["Jockey", "Distance", "Wins", "Starts", "Places"],
               [{"Jockey": j, "Distance": 2200, "Wins": 3 + g, "Starts": 30 + g, "Places": 9 + g}
                for j in jockeys])
    paths["trainer_distance"] = res / SEASON / "trainer_distance_stats.csv"
    _write_csv(paths["trainer_distance"], ["Trainer", "Distance", "Wins", "Starts", "Places"],
               [{"Trainer": t, "Distance": 2200, "Wins": 3 + g, "Starts": 30 + g, "Places": 9 + g}
                for t in trainers])
    paths["jockey_change"] = res / SEASON / "general_pre_race_priors" / "jockey_change_priors.csv"
    _write_csv(paths["jockey_change"], ["JockeyChanged", "Wins", "Starts", "Places"],
               [{"JockeyChanged": "True", "Wins": 50 + g, "Starts": 700 + g, "Places": 150 + g},
                {"JockeyChanged": "False", "Wins": 90, "Starts": 1000, "Places": 270}])
    paths["jockey_draw"] = res / SEASON / "jockey_draw_performance.csv"
    _write_csv(paths["jockey_draw"], ["Jockey", "Draw", "Wins", "Starts", "Places"],
               [{"Jockey": j, "Draw": 1, "Wins": 1 + g, "Starts": 10 + g, "Places": 3 + g}
                for j in jockeys])
    r = bump("recency_trainer")
    paths["recency"] = res / "experimental" / "trainer_recency_90d_stats.csv"
    _write_csv(paths["recency"], ["Trainer", "Wins", "Starts", "Places", "AsOfDate",
                                  "LatestResultDate", "HalfLifeDays"],
               [{"Trainer": t, "Wins": 5 + r, "Starts": 60 + r, "Places": 15 + r,
                 "AsOfDate": F_DATE if r else D_DATE,
                 "LatestResultDate": F_DATE if r else "2026-03-01", "HalfLifeDays": 30}
                for t in trainers])
    return paths


def _write_rail_draw(path: Path, future: bool) -> None:
    """`rail_draw_results.csv`：逐行有 Date。D 之前 34 日跑馬地 C／B 賽道 2200m；
    future=True 加 40 場 F 日期、外檔全部贏 —— 一定郁到 cell。"""
    rows = []
    days = [f"2025-{m:02d}-{d:02d}" for m in (9, 10, 11, 12) for d in (3, 10, 17, 24)]
    days += [f"2026-{m:02d}-{d:02d}" for m in (1, 2) for d in (3, 7, 14, 21, 25, 28)]
    for k, day in enumerate(days):
        for draw in range(1, 13):
            rows.append({"Date": day, "RaceNo": 3, "Venue": "跑馬地", "Track": "Turf",
                         "Distance": 2200, "Rail": "C", "FieldSize": 12, "Draw": draw,
                         "Place": 1 if (draw + k) % 4 == 0 else 0})
            # 另一條賽道（B）做 parent 對照，令 C 賽道 cell 有真超額。
            rows.append({"Date": day, "RaceNo": 4, "Venue": "跑馬地", "Track": "Turf",
                         "Distance": 2200, "Rail": "B", "FieldSize": 12, "Draw": draw,
                         "Place": 1 if (draw + k) % 5 == 0 else 0})
    if future:
        for race in range(1, 41):
            for draw in range(1, 13):
                rows.append({"Date": F_DATE, "RaceNo": race, "Venue": "跑馬地",
                             "Track": "Turf", "Distance": 2200, "Rail": "C",
                             "FieldSize": 12, "Draw": draw, "Place": 1 if draw >= 10 else 0})
    _write_csv(path, ["Date", "RaceNo", "Venue", "Track", "Distance", "Rail",
                      "FieldSize", "Draw", "Place"], rows)


def _tiers(logic: dict, future: bool) -> dict:
    """`05_jockey_trainer_tiers.json`：人手 tier 表，冇日期。future=True：F 之後
    重評，今場所有騎練升到頂級。"""
    real = json.loads((AUTO_SCRIPTS.parent / "resources" / "05_jockey_trainer_tiers.json")
                      .read_text(encoding="utf-8"))
    if not future:
        return real
    jockeys, trainers = _people(logic)
    out = dict(real)
    out["jockey"] = [{"names": jockeys, "score": 90.0, "reason": "fixture 重評"}]
    out["trainer"] = [{"names": trainers, "score": 90.0, "reason": "fixture 重評"}]
    return out


def _profile_entries(number: str, future: bool) -> list[dict]:
    """馬匹頁往績（`_enrich_profile_history`）。HKJC 馬匹頁係即時頁，賽後
    抓就會有 F。"""
    seed = int(number)
    entries = [{"date": "04/02/26", "rating": 50 + seed, "class_grade": "4",
                "placing": 1 + seed % 6, "jockey": "舊騎師", "running_positions": [3, 3, 3]},
               {"date": "11/01/26", "rating": 48 + seed, "class_grade": "4",
                "placing": 2 + seed % 5, "jockey": "舊騎師", "running_positions": [5, 4, 4]}]
    if future:
        entries.insert(0, {"date": "18/03/26", "rating": 99, "class_grade": "1",
                           "placing": 1, "jockey": "潘頓", "running_positions": [1, 1, 1]})
    return entries


# ─────────────────────────────── 生產流程 ───────────────────────────────

def _reset_caches():
    live_priors._JT_RATINGS = None
    live_priors._RECENCY_TRAINER_RATINGS = None
    engine_core._TRAINER_SIGNAL_PRIORS = None
    rail_draw_context._read_dataset.cache_clear()
    tier_loader.load_tiers.cache_clear()
    inject._DRAW_STATS = None
    inject._SCRAPED_STD_TIMES = None
    inject._REF_SECTIONALS = None


def score_meeting_d(work: Path, future: frozenset, *, dated_folder: bool = True) -> dict:
    """喺 `work` 由零行一次生產流程，回傳 D 每匹馬嘅指紋。

    `dated_folder=False`：賽日資料夾冇 `YYYY-MM-DD` 前綴，Logic 亦冇 race_date
    —— 即係 EXP-20260902-03 嗰批歸檔 Logic 嘅形狀（264 份零份有 race_date）。
    """
    unknown = set(future) - set(SOURCES)
    assert not unknown, unknown
    meeting = work / (f"{D_DATE}_HappyValley" if dated_folder else "HappyValley_archive")
    meeting.mkdir(parents=True, exist_ok=True)
    res = work / "stats"
    fg = meeting / f"03-04 Race {RACE_NO} Formguide.txt"
    text = FORMGUIDE.read_text(encoding="utf-8")
    fg.write_text(_future_formguide(text) if "formguide_runs" in future else text, encoding="utf-8")
    facts = meeting / f"03-04 Race {RACE_NO} Facts.md"
    draw_stats = _draw_stats("draw_stats" in future)

    _reset_caches()
    sink = io.StringIO()
    with contextlib.ExitStack() as stack:
        stack.enter_context(contextlib.redirect_stdout(sink))
        stack.enter_context(contextlib.redirect_stderr(sink))
        for patch in (
            mock.patch.object(inject, "_SCRAPED_STD_TIMES", _standard_times("standard_times" in future)),
            mock.patch.object(inject, "_REF_SECTIONALS", _reference_sectionals("reference_sectionals" in future)),
            mock.patch.object(inject, "_DRAW_STATS", draw_stats),
            mock.patch.object(skeleton, "_load_draw_stats_json", lambda: draw_stats),
        ):
            stack.enter_context(patch)
        # 1. Facts（生產 CLI；賽日由 run_prerace_pipeline 以 --race-date 傳入）
        with mock.patch.object(sys, "argv", [
                "inject_hkjc_fact_anchors.py", str(fg), "--output", str(facts),
                "--race-date", D_DATE, "--race-num", str(RACE_NO)]):
            inject.main()
        # 2. Logic（生產 `--all-horses` 路徑）
        facts_text = facts.read_text(encoding="utf-8")
        numbers = [int(v) for v in re.findall(r"^### 馬號\s+(\d+)\s+—", facts_text, re.M)]
        logic, _ = skeleton.build_full_logic_from_facts(facts_text, str(facts), RACE_NO, numbers)
        for number, horse in logic["horses"].items():
            # trackwork 檔帶 horseid；冇佢 `_enrich_profile_history` 就唔行。
            tw = horse.get("trackwork") if isinstance(horse.get("trackwork"), dict) else {}
            horse["trackwork"] = {**tw, "horseid": f"HK_2025_F{int(number):03d}"}
        logic_path = meeting / f"Race_{RACE_NO}_Logic.json"
        logic_path.write_text(json.dumps(logic, ensure_ascii=False), encoding="utf-8")
        # 3. 評分來源
        paths = _write_people_sources(res, logic, future)
        rail_csv = res / "rail_draw_results.csv"
        _write_rail_draw(rail_csv, "rail_draw" in future)
        tiers = _tiers(logic, "tier_table" in future)
        profile_future = "profile_history" in future
        for patch in (
            mock.patch.object(live_priors, "MASTER_STATS_FILES", {
                "jockey": [(paths["jockey"], SEASON)], "trainer": [(paths["trainer"], SEASON)]}),
            mock.patch.object(live_priors, "GENERAL_PRIOR_FILES", {
                key: [paths[key]] for key in
                ("combo", "jockey_distance", "trainer_distance", "jockey_change", "jockey_draw")}),
            mock.patch.object(live_priors, "TRAINER_RECENCY_PATH", paths["recency"]),
            mock.patch.object(live_priors, "_current_season_tag", lambda: SEASON),
            mock.patch.object(rail_draw_context, "DATASET", rail_csv),
            mock.patch.object(tier_loader, "load_tiers", lambda: tiers),
            mock.patch.object(auto, "_get_profile_scraper", lambda: (
                lambda hid: {"entries": _profile_entries(hid[-3:], profile_future)})),
        ):
            stack.enter_context(patch)
        # 4. 評分（生產入口；會寫 md/csv 落 tmp，冇所謂）
        orchestrator = auto.HKJCAutoOrchestrator(logic_path)
        scored = orchestrator.score_race(logic_path)
    _reset_caches()
    assert scored, "score_race 失敗：\n" + sink.getvalue()[-3000:]
    return fingerprint(scored)


def _num(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return value
    return round(float(value), 10)


def fingerprint(scored: dict) -> dict:
    horses = {}
    for number, horse in sorted((scored.get("horses") or {}).items(), key=lambda kv: int(kv[0])):
        auto_out = horse.get("python_auto") or {}
        horses[number] = {
            group: {k: _num(v) for k, v in sorted((auto_out.get(group) or {}).items())
                    if not isinstance(v, (dict, list))}
            for group in ("feature_scores", "derived_feature_scores", "matrix_scores")
        }
        rail = ((auto_out.get("race_shape_detail") or {}).get("rail_draw_context") or {})
        horses[number].update({
            # 前瞻 shadow，唔入綜合分；照樣要 PIT，所以一齊比。
            "rail_draw_adjustment": _num(rail.get("adjustment")),
            "ability_score": _num(auto_out.get("ability_score")),
            "grade": auto_out.get("grade"),
            "rank": auto_out.get("rank"),
        })
    ranking = sorted(horses, key=lambda n: (horses[n]["rank"] or 999, int(n)))
    return {"horses": horses, "ranking": ranking}


def diff(a: dict, b: dict) -> list[str]:
    out = []
    if a["ranking"] != b["ranking"]:
        out.append(f"ranking {a['ranking']} -> {b['ranking']}")
    for number, ha in a["horses"].items():
        hb = b["horses"].get(number, {})
        for group in ("feature_scores", "derived_feature_scores", "matrix_scores"):
            for key in sorted(set(ha[group]) | set(hb.get(group, {}))):
                va, vb = ha[group].get(key), hb.get(group, {}).get(key)
                if va != vb:
                    out.append(f"#{number} {group}.{key}: {va} -> {vb}")
        for key in ("rail_draw_adjustment", "ability_score", "grade", "rank"):
            if ha[key] != hb.get(key):
                out.append(f"#{number} {key}: {ha[key]} -> {hb.get(key)}")
    return out


class FutureAppendInvarianceTests(unittest.TestCase):
    """每個 case：只喺**一個**來源加 F，D 嘅指紋一定要唔變。"""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name)
        cls.baseline = score_meeting_d(cls.root / "baseline", frozenset())

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _assert_invariant(self, *sources, dated_folder=True):
        baseline = self.baseline
        tag = "+".join(sources) + ("" if dated_folder else "-undated")
        if not dated_folder:
            baseline = score_meeting_d(self.root / f"base{tag}", frozenset(), dated_folder=False)
        candidate = score_meeting_d(self.root / tag, frozenset(sources), dated_folder=dated_folder)
        changes = diff(baseline, candidate)
        self.assertEqual(changes, [], f"加咗未來場次 {F_DATE} 入 {sources} 之後，"
                         f"{D_DATE} 嘅評分變咗：\n  " + "\n  ".join(changes[:40]))

    # ── 健全性 ──
    def test_baseline_is_not_degenerate(self):
        self.assertGreaterEqual(len(self.baseline["horses"]), 10)
        abilities = {h["ability_score"] for h in self.baseline["horses"].values()}
        self.assertGreater(len(abilities), 5)
        leaves = self.baseline["horses"]["1"]["feature_scores"]
        self.assertGreater(len(leaves), 8)

    def test_rerun_is_deterministic(self):
        self.assertEqual(diff(self.baseline, score_meeting_d(self.root / "rerun", frozenset())), [])

    def test_detector_catches_a_real_change(self):
        """反證：D 之前嘅往績本身改咗，指紋一定要郁 —— 否則所有綠燈都冇意義。"""
        original = FORMGUIDE.read_text(encoding="utf-8")
        worse = re.sub(r"名次: \d+ / (\d+)", r"名次: \1 / \1", original)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "formguide_3.txt"
            path.write_text(worse, encoding="utf-8")
            with mock.patch(f"{__name__}.FORMGUIDE", path):
                changed = score_meeting_d(self.root / "detector", frozenset())
        self.assertNotEqual(diff(self.baseline, changed), [])

    # ── 每個來源一個 case ──
    # 量度（2026-10-14，呢個 fixture）寫喺每個 expectedFailure 嘅 docstring。

    @unittest.expectedFailure
    def test_formguide_future_runs(self):
        """LEAK（2026-10-14 呢個測試發現）：HKJC Formguide 往績行冇 as-of 閘。

        `inject_hkjc_fact_anchors` 嘅 `--race-date` 只用嚟剔馬匹頁 profile
        （`filter_profile_as_of`）同做錨點；`parse_hkjc_formguide` 讀到嘅往績行
        **一條都唔剔**。抽取層（`extract_formguide*.py`）亦冇日期閘。即係賽後
        重抽／頁面已含後續賽事，F 會直接入 Facts → Logic → 評分。
        AU 有兩道閘（`write_meeting` + `parse_formguide_for_horse(as_of)`），HKJC 零道。
        fixture 量度：speed_score／sectional 最多 +27.99、distance_score ±10、
        consistency ±7.62，12 匹綜合分全部郁（最多 8.44），**排名第 2–10 位重排**。
        """
        self._assert_invariant("formguide_runs")

    def test_standard_times(self):
        """⚠️ 覆蓋未證實：`get_standard_time` 只喺有馬匹頁 profile（`finish_time_raw`）
        先用，而生產 `run_prerace_pipeline` 唔傳 `--horse-ids` —— 呢個 fixture 嘅
        Facts 根本冇變。留住做絆線：將來接通咗而冇 as-of，呢度會紅。"""
        self._assert_invariant("standard_times")

    def test_reference_sectionals(self):
        """⚠️ 覆蓋未證實：同上，`get_reference_sections` 要逐仗班次，speedpro
        formguide 冇 —— Facts 冇變。絆線。"""
        self._assert_invariant("reference_sectionals")

    def test_draw_stats_from_a_later_meeting(self):
        """全域 `hkjc_draw_stats.json` 被下一個賽日（F）覆蓋。Logic 層
        `create_hkjc_logic_skeleton._resolve_draw_stats_race` 對賽日、拒絕 F 嘅
        統計；leaf 唔郁。

        ⚠️ 已知旁漏（唔入分）：`inject_hkjc_fact_anchors.get_draw_summary_block`
        **唔對賽日**，Facts 頂嘅「🎯 檔位優劣判讀」會印 F 嘅統計；而 pipeline 傳
        嘅 `--draw-stats <meeting>/Draw_Stats.json` main() 根本冇 parse。"""
        self._assert_invariant("draw_stats")

    def test_jockey_trainer_master_stats(self):
        """歷史日期 → `temporal_source_is_safe` 擋住 latest-season 快照
        （EXP-20260902-03 修正）。非空洞：見 undated case，同一份檔一冇日期就入分。"""
        self._assert_invariant("master_stats")

    def test_general_pre_race_priors(self):
        """combo / 騎練路程 / 換騎 / 騎師檔位先驗：同一個 temporal guard。"""
        self._assert_invariant("general_priors")

    def test_trainer_recency_shadow(self):
        """90 日練馬師近況（shadow）：同一個 temporal guard。"""
        self._assert_invariant("recency_trainer")

    def test_rail_draw_dataset(self):
        """`rail_draw_results.csv` 逐行有 Date，`history[Date < cutoff]`。
        非空洞：baseline 調整 +2.11，同一份 F 數據冇 cutoff 會變 −1.69。"""
        self._assert_invariant("rail_draw")

    def test_profile_history(self):
        """`_enrich_profile_history(as_of_date=D)` 剔走當日及之後嘅馬匹頁往績
        （display-only 欄位，leaf 唔讀）。"""
        self._assert_invariant("profile_history")

    @unittest.expectedFailure
    def test_tier_table(self):
        """LEAK：temporal guard 把 master stats 換成中性之後，`JockeyScorer` 跌落
        `05_jockey_trainer_tiers.json` —— 一個**冇日期、冇版本**嘅人手表。
        即係歷史回放實際上係用「今日嘅 tier 表」評舊場次；D 之後任何重評都會改 D。
        fixture 量度：jockey_score 最多 +30、trainer_signal 最多 +16.5、綜合分
        最多 +8.88，排名大幅重排（#1 由第 6 升第 3）。
        """
        self._assert_invariant("tier_table")

    @unittest.expectedFailure
    def test_master_stats_when_logic_has_no_meeting_date(self):
        """LEAK（EXP-20260902-03 嘅形狀仍然存在）：temporal guard **fail-open**。

        `temporal_source_is_safe` 收到 `race_date=None` 回 True；而 race_date 只由
        Logic 欄位或者資料夾名 `YYYY-MM-DD` 推出（`_meeting_date_for_logic`）。
        歸檔 Logic 冇 race_date（repo memory：264 份零份有）＋資料夾冇日期前綴
        → latest-season master stats（含 F）直接入分。
        fixture 量度：jockey_score 12 匹全郁（最多 0.95）、trainer_signal 0.52、
        綜合分 0.28（F 只加 30 場對 200+ 場基數，故幅度細；方向係結構性）。
        另：同一場、同一份檔，有冇日期前綴本身已經令排名唔同。
        """
        self._assert_invariant("master_stats", dated_folder=False)


if __name__ == "__main__":
    unittest.main()
