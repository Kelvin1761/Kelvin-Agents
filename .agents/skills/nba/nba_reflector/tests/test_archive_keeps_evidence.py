"""EXP-20261125-03：歸檔要留低 `_prediction_snapshots`（研究證據絕對路徑＋sha256），其他照搬；淨係證據嘅資料夾唔算 live。"""
import hashlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import nba_daily_review_archive as archive  # noqa: E402


def _sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_archive_copies_snapshots_and_moves_the_rest(tmp_path, monkeypatch):
    source = tmp_path / "2026-11-24 NBA Analysis"
    snap = source / "_prediction_snapshots" / "20261124-210000-1"
    snap.mkdir(parents=True)
    (snap / "manifest.json").write_text('{"a": 1}')
    (source / "Game_A_B_Full_Analysis.md").write_text("report")
    before = _sha(snap / "manifest.json")
    monkeypatch.setattr(archive, "NBA_ANALYSIS", tmp_path / "archive")
    monkeypatch.setattr(archive, "emit", lambda status, day, msg, **kw: 0)
    assert archive._archive(source, tmp_path / "archive" / source.name, "2026-11-24") == 0
    dest = tmp_path / "archive" / source.name
    assert (dest / "Game_A_B_Full_Analysis.md").read_text() == "report"
    assert _sha(dest / "_prediction_snapshots" / "20261124-210000-1" / "manifest.json") == before
    assert _sha(snap / "manifest.json") == before                 # 證據原位留低、bytes 一樣
    assert not (source / "Game_A_B_Full_Analysis.md").exists()
    assert not archive._is_live(source)                           # 剩證據 = 已歸檔


def test_evidence_only_folder_is_not_live(tmp_path, monkeypatch):
    monkeypatch.setattr(archive, "NBA_ANALYSIS", tmp_path / "archive")
    folder = tmp_path / "x"
    (folder / "_prediction_snapshots").mkdir(parents=True)
    (folder / ".DS_Store").write_text("")
    assert archive._is_live(folder)                               # 未歸檔：照舊 live
    (tmp_path / "archive" / "x").mkdir(parents=True)
    assert not archive._is_live(folder)
    (folder / "Game_X_Full_Analysis.md").write_text("r")
    assert archive._is_live(folder)
    assert not archive._is_live(tmp_path / "missing")
