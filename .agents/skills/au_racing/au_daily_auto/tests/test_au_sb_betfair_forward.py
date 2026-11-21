"""EXP-20261121-31：Sportsbet 對 Betfair 頭兩選紙上 forward。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import au_sb_betfair_forward as F  # noqa: E402

RANK = """全場綜合戰力排名
| 排名 | 馬號 | 馬名 |
|---|---|---|
| 1 | 8 | Graffiti Tycoon |
| 2 | 3 | Iron Rebel |
| 3 | 5 | Nobody |
"""


def _meeting(tmp_path, sb, bf):
    folder = tmp_path / "2026-11-21 Kembla Grange Race 1-10"
    folder.mkdir()
    (folder / "Race_5_Auto_Analysis.md").write_text(RANK)
    (folder / "odds_history.json").write_text(json.dumps({"5": sb}))
    (folder / "betfair_odds_history.json").write_text(json.dumps(bf))
    return folder


def test_freezes_first_morning_price_and_pairs_nearest_betfair(tmp_path):
    folder = _meeting(tmp_path, {
        "2026-11-20T22:00:00|analysis": {"8": ["2", "1.2"], "3": ["5", "2"]},
        "2026-11-21T10:17:00|morning-refresh": {"8": ["1.6", "1.06"], "3": ["6", "2.4"]},
        "2026-11-21T13:05:00|morning-refresh": {"8": ["1.5", "1.04"], "3": ["9", "3"]},
    }, {
        "2026-11-21T09:30:00|morning-refresh": {"graffititycoon": [1.7, 1.1]},
        "2026-11-21T10:22:00|morning-refresh": {"graffititycoon": [1.8, 1.15], "ironrebel": [6.4, 2.1]},
    })
    rows = {r["num"]: r for r in F.picks_for_meeting(folder, "2026-11-21")}
    assert set(rows) == {8, 3}                      # 只有頭兩選
    assert rows[8]["sb_key"].startswith("2026-11-21T10:17")   # 第一個早更，唔係最新
    assert rows[8]["bf_key"].startswith("2026-11-21T10:22")   # 最近嗰個 Betfair
    assert (rows[3]["sb_place"], rows[3]["bf_place"]) == (2.4, 2.1)


def test_betfair_place_above_win_is_bad_data(tmp_path):
    folder = _meeting(tmp_path, {"2026-11-21T10:00:00|morning-refresh": {"8": ["1.6", "1.06"], "3": ["6", "2"]}},
                      {"2026-11-21T10:05:00|morning-refresh": {"graffititycoon": [1.12, 2.34]}})
    row = next(r for r in F.picks_for_meeting(folder, "2026-11-21") if r["num"] == 8)
    assert row["bf_bad"] and row["bf_place"] is None


def test_no_pair_outside_window(tmp_path):
    folder = _meeting(tmp_path, {"2026-11-21T10:00:00|morning-refresh": {"8": ["1.6", "1.06"], "3": ["6", "2"]}},
                      {"2026-11-21T11:00:00|morning-refresh": {"graffititycoon": [1.8, 1.15]}})
    assert all(r["bf_key"] is None for r in F.picks_for_meeting(folder, "2026-11-21"))


def _settled(day, overlay, placed, price=2.0):
    return {"day": day, "overlay": overlay, "placed": placed, "won": False,
            "sb_place": price, "bf_place": price / (1.2 if overlay else 1.0),
            "sb_win": None, "place_return": price if placed else 0.0, "win_return": 0.0}


def test_evaluate_pass_needs_both_overlay_profit_and_gap():
    rows = []
    for d in range(30):
        day = f"2026-12-{d + 1:02d}"
        rows += [_settled(day, True, True), _settled(day, True, True), _settled(day, True, False)]   # +33%
        rows += [_settled(day, False, True), _settled(day, False, False), _settled(day, False, False)]  # −33%
    ev = F.evaluate(rows)
    assert ev["verdict"] == "PASS" and ev["overlay"]["place_roi_ci"][0] > 0 and ev["diff_ci"][0] > 0
    flat = [dict(r, overlay=not r["overlay"]) for r in rows]
    assert F.evaluate(flat)["verdict"] == "REJECT"


def test_status_is_blind_until_target_then_frozen(tmp_path, monkeypatch):
    picks = tmp_path / "picks.jsonl"
    picks.write_text("")
    status_path = tmp_path / "status.json"
    rows = [_settled(f"2026-12-{d % 28 + 1:02d}", True, d % 2 == 0) for d in range(F.TARGET - 1)]
    monkeypatch.setattr(F, "settle", lambda _rows, _folders: rows)
    st = F.status(picks, status_path)
    assert "evaluation" not in st and "place_roi" not in json.dumps(st)   # 盲測：未夠數冇 ROI
    rows.append(_settled("2026-12-01", True, True))
    st = F.status(picks, status_path)
    first = st["evaluation"]
    rows.extend(_settled("2026-12-02", True, False) for _ in range(500))
    assert F.status(picks, status_path)["evaluation"] == first           # 判咗就凍結
