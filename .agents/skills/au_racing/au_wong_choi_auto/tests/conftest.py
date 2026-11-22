"""測試唔准讀真實資料根嘅練馬師剩餘表現表（每晚都變 → 測試會飄）。"""
import pytest


@pytest.fixture(autouse=True)
def _no_live_trainer_residual_table(tmp_path, monkeypatch):
    monkeypatch.setenv("WC_AU_TRAINER_RESIDUAL_TABLE", str(tmp_path / "no-trainer-residual.json"))
