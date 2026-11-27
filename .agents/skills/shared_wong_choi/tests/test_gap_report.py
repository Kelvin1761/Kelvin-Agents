"""改善空間清單：欄缺口、已停用／一直空分開、舊 REJECT 去重、觀察中假設。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))

import gap_report as G  # noqa: E402


def _rows(field, fills, src="leaf", weak=None):
    return [{"week": f"2026-W{40 + i}", "source": src, "field": field, "fill_rate": f, "n": 100,
             **({"weak_rate": weak} if weak is not None else {})} for i, f in enumerate(fills)]


def test_field_gaps_classifies():
    rows = (_rows("ok", [1, 1, 1, 1, 1]) + _rows("low", [0.5] * 5) + _rows("dropped", [1, 1, 0.9, 0.7, 0.6])
            + _rows("retired", [1, 1, 0, 0, 0]) + _rows("never", [0] * 5) + _rows("weak", [1] * 5, src="evidence", weak=0.7))
    g = G.field_gaps(rows, [{"field": "retired", "reason": "r", "exp": "EXP-1"}])
    names = [x["field"] for x in g["gaps"]]
    assert set(names) == {"low", "dropped", "weak", "never"}                    # 一直空都係缺口
    assert g["known_retired_hidden"] == ["retired"]                              # 只有確認清單先隱藏
    g2 = G.field_gaps(rows)
    assert "retired" in [x["field"] for x in g2["gaps"]]                        # 冇登記 = 照報


def test_known_list_wildcard_and_file():
    assert G._is_known("season_rate_v2_prob_S", [{"field": "season_rate_*"}])
    assert not G._is_known("availability.espn_level", G.known_retired("nba"))
    assert G._is_known("availability.official_level", G.known_retired("nba"))   # EXP-20261127-02 量度後確認停用
    known = G.known_retired("nba")
    assert len(known) >= 5 and all(k.get("reason") and k.get("exp") for k in known)   # 讀唔到唔可以 all([]) 過關


def test_field_missing_in_latest_week_is_gap():
    rows = _rows("vanished", [1, 1, 1, 1]) + _rows("ok", [1, 1, 1, 1, 1])
    g = G.field_gaps(rows)
    assert [x["field"] for x in g["gaps"]] == ["vanished"] and "冇咗" in g["gaps"][0]["why"]


def test_old_rejects_dedupe_and_domain(tmp_path):
    idx = tmp_path / "INDEX.md"
    idx.write_text("\n".join([
        "- [EXP-20260801-01](x.md) — AU 某某（REJECT）",
        "| [EXP-20260801-01](x.md) | 2026-08-01 | AU | 某某 | **REJECT** |",
        "- [EXP-20260802-02](y.md) — Tennis 某某 REJECT",
        "- [EXP-20261120-03](z.md) — HKJC 太新 REJECT",
        "- [EXP-20260803-04](w.md) — AU KEEP 唔係 reject"]), encoding="utf-8")
    r = G.old_rejects("2026-11-26", idx)
    assert [x["id"] for x in r["au"]] == ["EXP-20260801-01"] and [x["id"] for x in r["tennis"]] == ["EXP-20260802-02"]
    assert "hkjc" not in r


def test_old_rejects_hides_recently_reevaluated(tmp_path):
    idx = tmp_path / "INDEX.md"
    idx.write_text("\n".join([
        "| [EXP-20261127-30](a.md) | 2026-11-27 | AU | 重評 EXP-20260801-01、EXP-20260801-02 | **REJECT 維持**：交 EXP-20260801-03 forward |",
        "| [EXP-20260801-01](x.md) | 2026-08-01 | AU | 甲 | **REJECT** |",
        "| [EXP-20260801-02](y.md) | 2026-08-01 | AU | 乙 | **REJECT** |",
        "| [EXP-20260801-03](z.md) | 2026-08-01 | AU | 丙 | **REJECT** |",
        "| [EXP-20260701-09](o.md) | 2026-07-01 | AU | 重評 EXP-20260601-05 | **REJECT** |",
        "| [EXP-20260601-05](p.md) | 2026-06-01 | AU | 丁 | **REJECT** |"]), encoding="utf-8")
    ids = [x["id"] for x in G.old_rejects("2026-11-27", idx)["au"]]
    assert "EXP-20260801-01" not in ids and "EXP-20260801-02" not in ids    # 60 日內重評過
    assert "EXP-20260801-03" in ids                                         # 只係判決欄提到，唔算重評
    assert "EXP-20260601-05" in ids and "EXP-20260701-09" in ids             # 重評本身都舊咗 = 照列


def test_build_handles_domain_errors(monkeypatch, tmp_path):
    monkeypatch.setenv("WONGCHOI_CONTROL_STATE_ROOT", str(tmp_path))
    monkeypatch.setattr(G, "_racing_rows", lambda p: (_ for _ in ()).throw(OSError("no disk")))
    monkeypatch.setattr(G, "_sports_rows", lambda d: _rows("x", [0.3] * 3))
    (tmp_path / "learning").mkdir()
    (tmp_path / "learning" / "hypotheses.jsonl").write_text(json.dumps({"id": "H1", "state": "watching", "domain": "au"}) + "\n"
                                                           + json.dumps({"id": "H2", "state": "covered"}) + "\n")
    r = G.build("2026-11-26")
    assert "error" in r["domains"]["au"] and r["domains"]["nba"]["gaps_total"] == 1
    assert [h["id"] for h in r["watching_hypotheses"]] == ["H1"]
    assert "唔准講" in r["rule"]


def test_source_lag_is_gap():
    rows = [{"week": "2026-W48", "source": "daily", "field": "source_lag.tml", "n": 1, "fill_rate": 1.0, "mean": 31.0},
            {"week": "2026-W48", "source": "daily", "field": "source_lag.te", "n": 1, "fill_rate": 1.0, "mean": 1.0}]
    g = G.field_gaps(rows)
    assert [x["field"] for x in g["gaps"]] == ["source_lag.tml"] and "31 日" in g["gaps"][0]["why"]
