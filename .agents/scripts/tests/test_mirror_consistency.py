"""Drive 鏡像一致性檢查：分得清「啱啱寫完未輪到鏡像」同「鏡像根本冇返去攞」。

點解要有呢個檢查：`step_mirror_reports` 只鏡像「今次動過嘅場次」，所以一個
舊場次事後被重新評分就永遠唔會再推上 Drive。而原本個健康檢查只問「上次
mirror run 有冇 failed」—— 永遠答「冇」，因為每次 run 都成功鏡像咗佢自己嗰批。

2026-09-05 實測：AU 16,202 個有對應正本嘅鏡像檔，**2,299 個（14.2%）落後**，
中位數 0.5 日、最耐 **98 日**，而當時所有警報都係綠嘅。
（已補齊：AU 2,299 + HKJC 96，兩邊 100.0%。）

把尺嘅關鍵係 `STALE_DAYS`：HKJC 當時有 96 個落後但全部喺 2 日內 —— 嗰個係
排程一日跑兩次之間嘅正常漂移，唔應該嗌。AU 有 888 個超過 2 日 —— 嗰個先係
「冇返去攞」。一個連正常漂移都嗌嘅閘，遲早會俾人熄咗。
"""
from __future__ import annotations

import importlib.util
import os
import sys
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "mirror_consistency.py"
_SPEC = importlib.util.spec_from_file_location("mirror_consistency_test", SCRIPT)
mc = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mc)

DAY = 86400


def _write(path: Path, text: str, age_days: float = 0.0):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    when = time.time() - age_days * DAY
    os.utime(path, (when, when))
    return path


@pytest.fixture
def tree(tmp_path):
    mirror = tmp_path / "mirror"
    primary = tmp_path / "primary"
    (mirror).mkdir()
    (primary).mkdir()
    return mirror, primary


def test_identical_sizes_count_as_matched(tree):
    mirror, primary = tree
    _write(mirror / "a.md", "same")
    _write(primary / "a.md", "same")
    r = mc.scan(mirror, primary)
    assert r["paired"] == 1 and r["matched"] == 1
    assert r["behind"] == 0 and r["stale"] == 0


def test_a_recent_difference_is_drift_not_stale(tree):
    """排程一日跑兩次，所以一日內嘅漂移係正常，唔應該嗌。"""
    mirror, primary = tree
    _write(mirror / "a.md", "old", age_days=0.5)
    _write(primary / "a.md", "much longer content", age_days=0.0)
    r = mc.scan(mirror, primary)
    assert r["behind"] == 1
    assert r["stale"] == 0, "喺 STALE_DAYS 之內唔算過期"


def test_an_old_difference_is_stale(tree):
    mirror, primary = tree
    _write(mirror / "a.md", "old", age_days=40)
    _write(primary / "a.md", "much longer content", age_days=0.0)
    r = mc.scan(mirror, primary)
    assert r["stale"] == 1
    assert r["worst_days"] > 30
    assert r["worst_path"] == "a.md"


def test_a_primary_inside_archive_is_found(tree):
    """完成嘅場次會搬入 `Archive/` —— 搵唔到就會誤報成「鏡像獨有」。"""
    mirror, primary = tree
    _write(mirror / "2026-08-30 Casterton" / "x.json", "old", age_days=40)
    _write(primary / "Archive" / "2026-08-30 Casterton" / "x.json",
           "new and longer", age_days=0)
    r = mc.scan(mirror, primary)
    assert r["paired"] == 1, "Archive/ 入面嘅正本要搵得返"
    assert r["stale"] == 1


def test_a_mirror_only_file_is_not_counted(tree):
    """鏡像獨有嘅舊檔唔係我哋要答嘅問題 —— 唔算落分母。"""
    mirror, primary = tree
    _write(mirror / "orphan.md", "x")
    r = mc.scan(mirror, primary)
    assert r["total"] == 1 and r["paired"] == 0


def test_dot_files_are_skipped(tree):
    """`.wongchoi-tmp-*` 係鏡像寫入途中嘅臨時檔，唔算。"""
    mirror, primary = tree
    _write(mirror / ".x.md.wongchoi-tmp-1", "x")
    r = mc.scan(mirror, primary)
    assert r["total"] == 0


def test_backfill_repairs_and_verifies(tree, monkeypatch):
    mirror, primary = tree
    _write(mirror / "a.md", "old", age_days=40)
    _write(primary / "a.md", "much longer content", age_days=0)
    r = mc.scan(mirror, primary)
    assert r["stale"] == 1

    import shutil

    class FakeSched:
        @staticmethod
        def atomic_copy2(src, dst):
            shutil.copy2(src, dst)
            return dst

    monkeypatch.setitem(sys.modules, "au_daily_schedule", FakeSched)
    out = mc.backfill(r["drift"], mirror)
    assert out == {"done": 1, "failed": 0, "verify_failed": 0, "problems": []}
    assert mc.scan(mirror, primary)["behind"] == 0


def test_backfill_reports_a_write_that_did_not_take(tree, monkeypatch):
    """`atomic_copy2` 回咗 ≠ 寫到 —— 一定要驗實物大細。"""
    mirror, primary = tree
    _write(mirror / "a.md", "old", age_days=40)
    _write(primary / "a.md", "much longer content", age_days=0)
    r = mc.scan(mirror, primary)

    class LyingSched:
        @staticmethod
        def atomic_copy2(src, dst):
            return dst          # 乜都唔做，扮成功

    monkeypatch.setitem(sys.modules, "au_daily_schedule", LyingSched)
    out = mc.backfill(r["drift"], mirror)
    assert out["done"] == 0
    assert out["verify_failed"] == 1


def test_the_stale_threshold_is_configurable_and_documented():
    assert mc.STALE_DAYS >= 1, "門檻細過一日會嗌正常漂移"
    assert "WC_MIRROR_STALE_DAYS" in SCRIPT.read_text(encoding="utf-8")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
