"""自動覆盤（自學循環 L1）：核數、對市場、逐場表、跨日描述、輸出、排程接駁。"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve()
SCRIPTS = HERE.parents[1] / "scripts"
SKILLS = HERE.parents[2]
sys.path.insert(0, str(SCRIPTS))

import post_review as P  # noqa: E402


def _row(day, meeting, race, n, rank, pos, sp, p3=0.3, m3=0.3, cohorts=(), tags=()):
    return {"date": day, "meeting": meeting, "race": race, "n": n, "name": f"H{n}", "rank": rank, "pos": pos,
            "sp": sp, "p_top3": p3, "m_top3": m3, "p_win": 0.1, "m_win": 0.1, "hit3": int(pos <= 3),
            "cohorts": list(cohorts), "tags": list(tags)}


def test_generic_cohort_names_merge_variants():
    assert P._generic("久休 179 日復出") == P._generic("久休 200 日復出") == "久休 N 日復出"
    assert P._generic("騎練實績弱（Dan McGillivray）") == "騎練實績弱"
    assert P._cohort_key({"key": "dim:stability", "label": "近績質素高過同場（近3仗 5-9-8）"}) == "tag:近績質素高過同場"


def test_days_bins():
    assert P._days_bin(7) == "隔 ≤14 日" and P._days_bin(14) == "隔 ≤14 日"
    assert P._days_bin(90) == "休 ≥90 日" and P._days_bin(None) is None and P._days_bin("") is None
    assert P._days_bin(0) is None


def test_explain_uses_tag_impacts():
    x = {"tags": [{"label": "A", "impact": 3.0}, {"label": "B", "impact": -2.0}, {"label": "C", "impact": 1.0},
                  {"label": "D", "impact": -5.0}, {"label": "E", "impact": None}]}
    assert P._explain(x, True) == ["A（+3.0）", "C（+1.0）"]
    assert P._explain(x, False) == ["D（-5.0）", "B（-2.0）"]


def test_summary_counts_model_vs_market():
    day = "2026-12-01"
    rr = [_row(day, "m", 1, 1, 1, 1, 2.0), _row(day, "m", 1, 2, 2, 5, 3.0), _row(day, "m", 1, 3, 3, 2, 9.0),
          _row(day, "m", 1, 4, 4, 3, 4.0), _row(day, "m", 1, 5, 5, 4, 20.0)]
    for x, k in zip(rr, (1, 2, 4, 3, 5)):
        x["sp_rank"] = k
    s = P._summary(rr, {("m", 1): rr}, day)
    assert s["races"] == 1 and s["slots"] == 3
    assert s["model_top3_hits"] == 2          # 1、3 號
    assert s["market_top3_hits"] == 2         # SP 頭三 = 1、2、4 → 1、4 入
    assert s["model_top1_wins"] == 1 and s["fav_wins"] == 1 and s["winner_in_model_top5"] == 1


def test_reconcile_flags_missing_races():
    races = [{"meeting": "A", "date": "d"}] * 7 + [{"meeting": "B", "date": "d"}] * 8
    rc = P._reconcile([{"meeting": "A", "results_races": 8, "detail_races": 8, "reason": None},
                       {"meeting": "B", "results_races": 8, "detail_races": 8, "reason": None}], races, "d")
    assert not rc["ok"] and rc["missing_races"] == 1
    assert [m["missing"] for m in rc["meetings"]] == [1, 0]
    from collections import Counter
    full = [{"meeting": "A", "date": "d"}] * 8 + [{"meeting": "B", "date": "d"}] * 8
    rc = P._reconcile([{"meeting": "A", "results_races": 8, "detail_races": 8, "reason": None}], full, "d",
                      Counter({"A": 2}), Counter())
    assert not rc["ok"] and rc["unjoined_horses"] == 2 and rc["missing_races"] == 0   # 配唔到馬都唔准報 OK


def test_cohort_trail_excludes_today_and_reads_direction():
    rng = np.random.default_rng(0)
    rows = []
    for d in range(10):
        day = f"2026-11-{d + 10:02d}"
        for i in range(10):                     # 跨日：組別 X 實際入位率高過模型 0.3
            rows.append(_row(day, f"m{d}", 1, i, i + 1, 1 if i < 6 else 9, 5.0, p3=0.3, m3=0.6, cohorts=["tag:X"]))
    today = "2026-11-25"
    rows += [_row(today, "t", 1, i, i + 1, 1, 5.0, p3=0.3, m3=0.6, cohorts=["tag:X"]) for i in range(5)]
    out = P._cohorts(rows, today, [], rng)
    (c,) = out
    assert c["today_n"] == 5 and c["trail_n"] == 100          # 今日唔入跨日
    assert c["trail_model_resid_pp"] == 30.0 and c["trail_model_ci_pp"][0] > 0
    assert "跨日同方向" in c["reading"] and "市場冇顯著偏差" in c["reading"]


def test_small_cohorts_not_reported():
    today = "2026-11-25"
    rows = [_row(today, "t", 1, i, i + 1, 1, 5.0, cohorts=["tag:Y"]) for i in range(P.TODAY_MIN_N - 1)]
    assert P._cohorts(rows, today, [], np.random.default_rng(0)) == []


def test_render_and_telegram_text():
    rv = {"platform": "au", "date": "2026-12-01", "rules": "描述唔係判決",
          "reconciliation": {"ok": False, "missing_races": 1,
                             "meetings": [{"meeting": "A", "missing": 1, "reason": None}]},
          "summary": {"races": 1, "slots": 3, "model_top3_hits": 2, "market_top3_hits": 2, "model_top1_wins": 1,
                      "fav_wins": 1, "winner_in_model_top5": 1, "model_logloss_top3": 0.5, "market_logloss_top3": 0.48},
          "meetings": [{"meeting": "A", "labels": {"Good": 1}, "buckets": {}, "races": [
              {"race": 1, "label": "Good", "bucket": None,
               "under": [{"name": "U", "rank": 5, "pos": 2, "sp": 9.0, "why": ["X（-2.0）"]}], "over": []}]}],
          "cohorts": [], "window": {"n_days": 0}}
    md = P.render_md(rv)
    assert "核數" in md and "U（模型5→第2，$9.0）X（-2.0）" in md and "0.5000" in md
    tg = P.telegram_text(rv)
    assert "頭三入前三：模型 2/3・市場 2/3" in tg and "Good 1" in tg
    assert "error" not in tg.lower() and "失敗" not in tg        # 內容訊息唔夾錯誤句


def test_scheduler_wiring():
    au = (SKILLS / "au_racing" / "au_daily_auto" / "au_daily_schedule.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.parse(au).body if isinstance(n, ast.FunctionDef) and n.name == "step_post_review")
    assert not [c for c in ast.walk(fn) if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
                and c.func.attr == "warn"]
    assert "step_post_review(runlog, review_day)" in au
    hk = (SKILLS / "hkjc_racing" / "hkjc_daily_auto" / "hkjc_daily_schedule.py").read_text(encoding="utf-8")
    assert "update_post_review_async(completed)" in hk and 'POST_REVIEW = SHARED_SCRIPTS / "post_review.py"' in hk


def test_health_flags_missing_review(tmp_path, monkeypatch):
    import json as _json
    monkeypatch.setenv("WONGCHOI_CONTROL_STATE_ROOT", str(tmp_path))

    class Mt:
        def __init__(self, name):
            self.name = name
    monkeypatch.setattr(P.M, "default_root", lambda plat: tmp_path)
    monkeypatch.setattr(P.M, "meeting_list", lambda plat, root: [Mt("2026-11-24 X"), Mt("2026-11-25 Y")])
    sys.path.insert(0, str(SKILLS / "shared_wong_choi"))
    import post_review_sports as SP
    monkeypatch.setattr(SP, "latest_settled", lambda plat, cutoff: "2026-11-25")
    ok, lines = P.health("2026-11-26")
    assert ok and all("未有覆盤" in x for x in lines)          # 未開始 = 提示
    d = tmp_path / "reviews" / "au"
    d.mkdir(parents=True)
    (d / "2026-11-24.json").write_text(_json.dumps({"reconciliation": {"ok": True}}))
    ok, lines = P.health("2026-11-26")
    assert not ok and "2026-11-25 未有覆盤" in lines[0]
    (d / "2026-11-25.json").write_text(_json.dumps({"reconciliation": {"ok": False, "missing_races": 2}}))
    ok, lines = P.health("2026-11-26")
    assert not ok and "2 場用唔到" in lines[0]


def test_build_joins_and_window(monkeypatch, tmp_path):
    """build：只用有賽前快照嘅場；配唔到排名嘅馬唔入低估表、核數唔 OK；跨日唔包今日。"""
    from collections import Counter
    day = "2026-11-25"
    def race(d, m, rk_ok=True, snap=True):
        return {"date": d, "meeting": m, "race": 1, "published_at": "x" if snap else None,
                "rows": [{"n": i, "ability": 70 - i, "pos": i, "sp": 2.0 + i} for i in (1, 2, 3, 4, 5)]}
    races = [race("2026-11-24", "2026-11-24 Old"), race(day, "2026-11-25 Today"), race(day, "2026-11-25 Post", snap=False)]
    params = {"a": 0.0, "alpha": 0.08, "gamma": 1.1, "beta_win": 0.08}
    monkeypatch.setattr(P.M, "collect", lambda plat, root, until: (races, {}))
    monkeypatch.setattr(P.M, "walk_forward", lambda rs, plat: {"2026-11-24": params, day: params})

    class Mt:
        def __init__(self, name):
            self.name = name
    monkeypatch.setattr(P.M, "meeting_list", lambda plat, root: [Mt("2026-11-24 Old"), Mt("2026-11-25 Today")])
    monkeypatch.setattr(P, "_core", lambda: None)

    def detail(plat, m, core):
        ranks = {1: 4, 2: 1, 3: 2, 4: 3} if m.name == "2026-11-25 Today" else {i: i for i in (1, 2, 3, 4, 5)}  # 5 號冇排名
        return ({(1, n): {"name": f"H{n}", "rank": r, "tags": [], "cohorts": ["tag:X"]} for n, r in ranks.items()},
                {"meeting": m.name, "results_races": 1, "detail_races": 1, "reason": None})
    monkeypatch.setattr(P, "meeting_detail", detail)
    monkeypatch.setattr(P, "_meetings", lambda *a: [])
    rv = P.build("au", day, root=tmp_path, trail_days=5)
    rc = rv["reconciliation"]
    assert rc["unjoined_horses"] == 1 and not rc["ok"]            # today 5 號
    assert rv["summary"]["races"] == 1                           # post（冇快照）唔計
    assert rv["window"]["days"] == ["2026-11-24"]                # 跨日唔包今日


def test_hkjc_incidents_parse_and_flag(tmp_path):
    import json as _json
    raw = {"1": {"race_no": 1, "incident_report":
                 "1 4 頌星 (K343) 賽後須抽取樣本檢驗。 2 10 銳一 (J037) 接近千四米處時受阻，須收慢。 "
                 "3 5 獎星 (H087) 大部分途程在沒有遮擋下走外疊。 4 8 快樂老撾 (J115) 出閘緩慢。",
                 "results": [{"horse_no": "4", "horse_name": "頌星(K343)"}, {"horse_no": "10", "horse_name": "銳一(J037)"},
                             {"horse_no": "5", "horse_name": "獎星(H087)"}, {"horse_no": "8", "horse_name": "快樂老撾(J115)"},
                             {"horse_no": "2", "horse_name": "無報告(K001)"}]}}
    f = tmp_path / "2026-11-25_HappyValley_全日賽果.json"
    f.write_text(_json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    inc = P.hkjc_incidents(f)[1]
    assert inc[4]["labels"] == [] and "樣本" in inc[4]["text"]
    assert inc[10]["labels"] == ["受阻"] and inc[5]["labels"] == ["走外疊冇遮擋"] and inc[8]["labels"] == ["出閘慢"]
    assert 2 not in inc


def test_render_shows_incident_column():
    inc = {"labels": ["受阻"], "text": "接近千四米處時受阻。"}
    rv = {"platform": "hkjc", "date": "2026-11-25", "rules": "r",
          "reconciliation": {"ok": True, "missing_races": 0, "meetings": []},
          "summary": {"races": 1, "slots": 3, "model_top3_hits": 1, "market_top3_hits": 1, "model_top1_wins": 0,
                      "fav_wins": 0, "winner_in_model_top5": 1, "model_logloss_top3": None, "market_logloss_top3": None},
          "meetings": [{"meeting": "HV", "labels": {"Miss": 1}, "buckets": {}, "incident_reports": True,
                        "over_total": 1, "over_with_incident": 1, "races": [
                            {"race": 1, "label": "Miss", "bucket": None, "under": [],
                             "over": [{"name": "O", "rank": 1, "pos": 9, "sp": 3.0, "why": [], "incident": inc}],
                             "model_top3_report": [{"name": "O", "rank": 1, "pos": 9, "labels": ["受阻"], "text": inc["text"]}]}]}],
          "cohorts": [], "window": {"n_days": 0}}
    md = P.render_md(rv)
    assert "賽後報告（模型頭三）" in md and "〔受阻〕" in md and "1 匹有賽中事件" in md
    assert "賽後報告：被高估 1 匹入面 1 匹有賽中事件" in P.telegram_text(rv)
