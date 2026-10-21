"""Reflector ingests the CURRENT (table + sidecar) report format; legacy still parses.

Fixtures are trimmed real files from 2026-10-21 (BOS_DET / OKC_SAS / PHI_NYK):
combo tables, the player cards of the legged players, the sidecar combos and the
36-leg Props_Verification (20 HIT / 16 MISS).
"""
from __future__ import annotations

import collections
import hashlib
import json
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import nba_reflector_orchestrator as r  # noqa: E402

FIX = HERE / "fixtures" / "postgame_20261021"
TAGS = ("BOS_DET", "OKC_SAS", "PHI_NYK")


def stage(tmp_path, with_sidecar=True, corrupt_sidecar=False):
    for name in FIX.iterdir():
        target = tmp_path / name.name
        if name.name.endswith(".market_legs.json"):
            if not with_sidecar:
                continue
            payload = json.loads(name.read_text(encoding="utf-8"))
            report = tmp_path / name.name[: -len(".market_legs.json")]
            payload["report_sha256"] = ("0" * 64) if corrupt_sidecar else hashlib.sha256(
                (FIX / report.name).read_bytes()).hexdigest()
            target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        else:
            shutil.copy(name, target)
    return tmp_path


def rows_for(tmp_path, **kw):
    d = stage(tmp_path, **kw)
    return r.load_prediction_rows(str(d), "2026-10-21", "2026-10-20")


def key(row):
    return (row["game_tag"], row["combo_id"], row["player_name"], row["prop_stat"], row["line"])


def test_36_legs_parse_from_sidecar_and_attach_verification(tmp_path):
    rows = rows_for(tmp_path)
    assert len(rows) == 36
    assert collections.Counter(x["game_tag"] for x in rows) == {"BOS_DET": 11, "OKC_SAS": 15, "PHI_NYK": 10}
    index = r.load_verification_index(str(tmp_path / "Props_Verification_2026-10-20.json"))
    attached = r.attach_verification(rows, index)
    assert all(x["status"] is not None for x in attached)
    assert collections.Counter(x["status"] for x in attached) == {"✅ HIT": 20, "❌ MISS": 16}


def test_known_leg_fields_and_provenance(tmp_path):
    row = next(x for x in rows_for(tmp_path) if x["player_name"] == "Ausar Thompson" and x["prop_stat"] == "reb")
    assert (row["line"], row["odds"], row["predicted_prob"], row["edge_pct"]) == (6.0, 1.52, 77.0, 11.21)
    assert (row["implied_prob"], row["l10_hit_rate"], row["l10_hits"], row["l10_total"]) == (65.79, 80.0, 8, 10)
    assert (row["l10_avg"], row["l10_med"], row["l10_sd"]) == (7.8, 7.0, 2.99)
    assert row["cov_label"].endswith("神經刀") and row["team_abbr"] == "DET"
    assert row["odds_source"] == "SPORTSBET_LIVE" and row["model_version"].startswith("Hybrid V1")
    assert row["raw_l10_json"] is None          # L10 values are not in the current report


def test_markdown_fallback_without_sidecar_matches_sidecar_path(tmp_path_factory):
    a = rows_for(tmp_path_factory.mktemp("a"))
    b = rows_for(tmp_path_factory.mktemp("b"), with_sidecar=False)
    assert len(b) == 36
    assert {key(x) for x in a} == {key(x) for x in b}
    by_a = {key(x): x for x in a}
    for row in b:
        for field in ("odds", "predicted_prob", "implied_prob", "edge_pct", "l10_hits", "l10_total", "l10_avg"):
            assert row[field] == by_a[key(row)][field], field


def test_stale_sidecar_is_ignored_not_trusted(tmp_path):
    rows = rows_for(tmp_path, corrupt_sidecar=True)
    assert len(rows) == 36                          # fell back to the markdown tables


def test_missing_facts_are_none_never_defaults(tmp_path):
    d = stage(tmp_path)
    report = d / "Game_PHI_NYK_Full_Analysis.md"
    text = report.read_text(encoding="utf-8")
    report.write_text(text.split("## 📊 球員盤口詳細分析")[0], encoding="utf-8")   # drop every card
    (d / "Game_PHI_NYK_Full_Analysis.md.market_legs.json").unlink()                  # sidecar sha no longer matches
    rows = [x for x in r.load_prediction_rows(str(d), "2026-10-21", "2026-10-20") if x["game_tag"] == "PHI_NYK"]
    assert len(rows) == 10
    assert all(x["implied_prob"] is None and x["l10_avg"] is None and x["l10_sd"] is None for x in rows)
    assert all(x["odds"] is not None and x["predicted_prob"] is not None for x in rows)   # combo-row facts remain


def test_legacy_block_format_still_parses(tmp_path):
    (tmp_path / "Game_AAA_BBB_Full_Analysis.md").write_text(
        "**odds_source**: SPORTSBET_LIVE | **引擎版本**: Legacy V8\n\n"
        "### 🛡️ 組合 1: 穩膽\n"
        "#### Leg 1: LeBron James (PHI) - 25+ PTS\n"
        "- 賠率 @1.85\n- 隱含勝率: 54.05%\n- 預期勝率: 62.0%\n- Edge: +7.95%\n"
        "- L10 命中: 7/10 (70.0%)\n- L10: [30, 22, 28, 26, 31, 20, 27, 29, 24, 33]\n- CoV: ✅穩定\n",
        encoding="utf-8")
    rows = r.load_prediction_rows(str(tmp_path), "2026-10-21", "2026-10-20")
    assert len(rows) == 1
    row = rows[0]
    assert (row["player_name"], row["prop_stat"], row["line"], row["odds"]) == ("LeBron James", "pts", 25.0, 1.85)
    assert row["predicted_prob"] == 62.0 and row["l10_hits"] == 7 and json.loads(row["raw_l10_json"])[0] == 30.0


def test_rows_persist_to_db_and_training_snapshot(tmp_path):
    rows = r.attach_verification(
        rows_for(tmp_path),
        r.load_verification_index(str(tmp_path / "Props_Verification_2026-10-20.json")))
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    r.ensure_db(conn)
    assert r.upsert_rows(conn, rows) == 36
    assert conn.execute("select count(*) from reflector_legs where cleared=1").fetchone()[0] >= 20
    assert conn.execute("select count(*) from reflector_legs where raw_l10_json is null").fetchone()[0] == 36
    snap = r.write_training_snapshot(rows, str(tmp_path), "2026-10-21")
    assert len(Path(snap).read_text(encoding="utf-8").splitlines()) == 37
