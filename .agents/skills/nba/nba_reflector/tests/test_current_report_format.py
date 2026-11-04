"""Reflector rows come only from each report's hash-bound sidecar; the Markdown is never parsed.

Fixtures are trimmed real files from 2026-10-21 (BOS_DET / OKC_SAS / PHI_NYK): the
sidecar combos plus the legged players' leg entries, and the 36-leg
Props_Verification (20 HIT / 16 MISS).
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
    # The same numbers the report printed, now from the sidecar: implied = 100/odds, edge = p - implied.
    assert (row["line"], row["odds"], row["predicted_prob"], row["edge_pct"]) == (6.0, 1.52, 77.0, 11.21)
    assert (row["implied_prob"], row["l10_hit_rate"]) == (65.79, 80.0)
    assert row["team_abbr"] == "DET" and row["odds_source"] == "SPORTSBET_LIVE"
    assert row["model_version"] == "legacy:hybrid"
    # Only the Markdown ever carried these; they stay None rather than being guessed.
    assert all(row[f] is None for f in ("l10_hits", "l10_total", "l10_avg", "l10_med", "l10_sd",
                                        "cov_label", "raw_l10_json"))


def test_markdown_is_never_parsed(tmp_path):
    d = stage(tmp_path)
    for report in d.glob("Game_*_Full_Analysis.md"):
        sidecar = Path(f"{report}.market_legs.json")
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
        report.write_text("# rewritten for people\n", encoding="utf-8")   # no tables, no cards
        payload["report_sha256"] = hashlib.sha256(report.read_bytes()).hexdigest()
        sidecar.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    assert len(r.load_prediction_rows(str(d), "2026-10-21", "2026-10-20")) == 36


@pytest.mark.parametrize("kw", [{"with_sidecar": False}, {"corrupt_sidecar": True}])
def test_report_without_a_bound_sidecar_is_not_recorded(tmp_path, kw):
    assert rows_for(tmp_path, **kw) == []


def test_legacy_llm_era_report_is_not_recorded(tmp_path):
    (tmp_path / "Game_AAA_BBB_Full_Analysis.md").write_text(
        "### 🛡️ 組合 1: 穩膽\n#### Leg 1: LeBron James (PHI) - 25+ PTS\n- 賠率 @1.85\n", encoding="utf-8")
    assert r.load_prediction_rows(str(tmp_path), "2026-10-21", "2026-10-20") == []


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
