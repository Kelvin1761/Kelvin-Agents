"""早更影賠率／市場移動：場次一定要由頁面讀，唔可以用 raceId 喺對應表嘅位置。

2026-11-21 Ascot／Cranbourne／Kembla Grange 嘅 raceId 清單亂序（Cranbourne 第一個 ID 係 Race 2），
`enumerate(meta["races"], 1)` 令 R1 攞咗 R2 嘅賠率，落注單印錯價、市場移動警號亂報。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

DAILY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DAILY))
sys.path.insert(0, str(DAILY.parent))
import au_daily_schedule as S  # noqa: E402
import claw_sportsbet_form as C  # noqa: E402


class _Log:
    def __init__(self):
        self.data, self.steps = {}, []

    def step(self, *a, **k):
        self.steps.append((a, k))

    def warn(self, *a, **k):
        pass


def _pages(tmp_path, monkeypatch, order):
    """建 cache：raceId r{n} 嘅頁係 Race n，賠率 = n（贏）／n/2（位）。對應表用 `order` 次序。"""
    cache = tmp_path / "cache"
    cache.mkdir()
    for n in order:
        page = cache / f"r{n}.html"
        page.write_text(f"<html><head><title>Cranbourne Race {n}</title></head><body></body></html>")
        page.with_suffix(".odds.json").write_text(json.dumps(
            {"odds": {"1": {"Sportsbet-FixedWin": float(n), "Sportsbet-FixedPlace": n / 2}}}))
    monkeypatch.setattr(C.SportsbetFormFetcher, "_cache_path",
                        lambda self, url: cache / f"{url.rstrip('/').split('/')[-1]}.html")
    monkeypatch.setattr(S, "load_mapping", lambda: {"K": {"meetingId": "1", "races": [f"r{n}" for n in order]}})


def test_page_race_number_reads_title():
    assert C.page_race_number("<title>Kembla Grange Race 10</title>") == 10
    assert C.page_race_number("<title>Flemington Race 7</title>") == 7
    assert C.page_race_number("<html>no title</html>") is None


def test_odds_snapshot_keyed_by_page_race_not_list_position(tmp_path, monkeypatch):
    _pages(tmp_path, monkeypatch, order=[2, 3, 1])          # 同 Cranbourne 一樣：第一個 ID 係 Race 2
    folder = tmp_path / "2026-11-21 Cranbourne Race 1-3"
    folder.mkdir()
    assert S.record_odds_from_cache(_Log(), folder, "K", "morning-refresh") == 3
    hist = json.loads((folder / S.ODDS_HISTORY).read_text())
    for race in ("1", "2", "3"):
        (prices,) = hist[race].values()
        assert prices["1"][0] == str(float(race)), (race, prices)   # Race N 嘅價係 N


def test_unreadable_race_number_is_skipped_not_guessed(tmp_path, monkeypatch):
    _pages(tmp_path, monkeypatch, order=[1, 2])
    (tmp_path / "cache" / "r2.html").write_text("<html>title missing</html>")
    folder = tmp_path / "m"
    folder.mkdir()
    assert S.record_odds_from_cache(_Log(), folder, "K", "morning-refresh") == 1
    assert set(json.loads((folder / S.ODDS_HISTORY).read_text())) == {"1"}


def test_market_drift_compares_the_same_race(tmp_path, monkeypatch):
    _pages(tmp_path, monkeypatch, order=[2, 1])
    folder = tmp_path / "m"
    folder.mkdir()
    monkeypatch.setattr(S, "top_picks_snapshot", lambda folder, depth=2: {1: [(1, 1, "A")], 2: [(1, 1, "B")]})
    # 分析時：Race 1 #1 = 1.0、Race 2 #1 = 2.0 —— 同頁面而家嘅價一樣，所以唔應該有警號
    monkeypatch.setattr(S, "market_odds_from_formguide", lambda folder, race: {1: float(race)})
    assert S.market_drift(_Log(), folder, "K") == []


# ---------------------------------------------------------------- 入錯場嘅快照（odds_quality 統一判斷）
import au_betting as B  # noqa: E402
import odds_quality as Q  # noqa: E402


def _card(folder, race, numbers):
    lines = "\n".join(f"{n}. Horse {n} ({n})" for n in numbers)
    (folder / f"11-21 Race {race} Racecard.md").write_text(f"# Race {race}\n{lines}\n")


def _p(**prices):
    return {k.lstrip("n"): [str(w), str(round(w / 3, 2))] for k, w in prices.items()}


def test_outside_field_is_hard_evidence_with_one_late_scratching_allowed():
    field = {1, 2, 3, 4, 5}
    assert Q.outside_field(_p(n1=2.0, n2=3.0, n6=9.0), field) is None            # 1 匹（可能遲退出）唔算
    assert "唔喺出賽名單" in Q.outside_field(_p(n1=2.0, n7=3.0, n8=9.0), field)
    assert Q.outside_field(_p(n1=2.0, n9=3.0, n8=9.0), None) is None              # 冇 Racecard 唔判


def test_price_match_to_other_race_is_only_soft_evidence():
    ref1 = _p(n1=2.0, n2=4.0, n3=6.0, n4=8.0, n5=10.0)
    ref2 = _p(n1=21.0, n2=61.0, n3=71.0, n4=9.0, n5=5.0)
    snap = _p(n1=21.0, n2=61.0, n3=71.0, n4=9.0, n5=5.0)      # 寫喺 R1，但其實係 R2 嘅價
    why = Q.snapshot_problem(snap, 1, field={1, 2, 3, 4, 5}, references={"1": ref1, "2": ref2})
    assert why and "似 R2" in why
    assert Q.outside_field(snap, {1, 2, 3, 4, 5}) is None       # 軟證據唔會令佢被自動跳過


def test_betting_skips_snapshot_with_runners_outside_the_field(tmp_path):
    _card(tmp_path, 1, [1, 2, 3, 4, 5])
    hist = {"1": {"2026-11-21T00:30:29|analysis": _p(n1=2.6, n2=2.25, n3=6.0),
                  "2026-11-21T11:40:29|morning-refresh": _p(n1=21.0, n2=61.0, n6=3.0, n7=4.0, n8=5.0),
                  "2026-11-21T10:14:04|morning-rebuild": _p(n1=2.5, n2=2.3, n3=6.0)}}
    (tmp_path / "odds_history.json").write_text(json.dumps(hist))
    when, prices = B.odds_at(tmp_path, 1, "last")
    assert when.endswith("morning-rebuild") and prices[1][0] == "2.5"


def test_refresh_does_not_write_a_snapshot_that_does_not_fit_the_field(tmp_path, monkeypatch):
    _pages(tmp_path, monkeypatch, order=[1])
    folder = tmp_path / "m"
    folder.mkdir()
    _card(folder, 1, [7, 8, 9, 10])                              # 頁面賠率 #1–#3 全部唔喺名單
    (tmp_path / "cache" / "r1.odds.json").write_text(json.dumps({"odds": {
        str(n): {"Sportsbet-FixedWin": 2.0 + n, "Sportsbet-FixedPlace": 1.5} for n in (1, 2, 3)}}))
    log = _Log()
    warned = []
    log.warn = lambda msg, *a, **k: warned.append(msg)
    assert S.record_odds_from_cache(log, folder, "K", "morning-refresh") == 0
    assert not (folder / S.ODDS_HISTORY).exists() and warned


def test_healthcheck_reports_misfiled_snapshot_for_today(tmp_path):
    import au_healthcheck as H
    folder = tmp_path / "2026-11-21 Cranbourne Race 1-1"
    folder.mkdir()
    _card(folder, 1, [1, 2, 3, 4, 5])
    (folder / "odds_history.json").write_text(json.dumps({"1": {
        "2026-11-20T22:00:00|analysis": _p(n1=2.6, n2=2.25, n3=6.0),
        "2026-11-21T11:40:29|morning-refresh": _p(n1=21.0, n6=3.0, n7=4.0, n8=5.0)}}))
    issues = H.local_quality_issues("2026-11-21", root=tmp_path, require_morning=False)
    assert any("疑似入錯場" in i for i in issues)
