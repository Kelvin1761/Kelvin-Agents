"""`_l600_delta` 一定要真係查得到 L600 標準表。

2026-08-22 事故：`claw_sportsbet_form._l600_delta` 內部條 `sys.path.insert`
指住 **package 目錄本身**（`.../scripts/au_racing_engine`）而唔係父目錄，於是
`from au_racing_engine.engine_core import _lookup_standard_l600` 拋
ModuleNotFoundError，被 `except Exception: return None` 靜靜吞咗。

後果：十個場次一個 `PF[Source: ... L600 Delta: N]` token 都冇寫入 Formguide，
於是 `pace_figure_score`（佔排名 **12.2%** 權重）全場中性 60、場內 SD 0.00。
抽取報「成功」、`WinningTime` 54 個齊全、日誌零錯 —— **完全靜**。

實測影響：拿三個有真 PF 嘅場次（24 場）強制 PF 中性，**71% 嘅場次 top-4 會唔同**。

呢個 test 唔 mock 任何嘢 —— 佢就係要行真嗰條 import 路徑。單元測試唔可能靠
「冇拋 exception」判斷，因為個 bug 本身就係一個被吞嘅 exception。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

AU_SKILL = Path(__file__).resolve().parents[2]
CLAW = AU_SKILL / "claw_sportsbet_form.py"


@pytest.fixture(scope="module")
def claw():
    sys.path.insert(0, str(AU_SKILL))
    spec = importlib.util.spec_from_file_location("claw_under_test", CLAW)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("track,distance", [
    ("Sale", 1400), ("Belmont", 1200), ("Newcastle", 1300), ("Doomben", 1615),
])
def test_l600_delta_resolves_a_real_benchmark(claw, track, distance):
    """A real number, not None. None here means the benchmark table is unreachable."""
    delta = claw._l600_delta(35.2, track, distance)
    assert delta is not None, (
        f"{track} {distance}m 查唔到 L600 標準 —— 十有八九係 `_l600_delta` 內部條 "
        "sys.path 又指錯咗 package 目錄本身。冇標準就冇 PF token，"
        "pace_figure_score 會全場中性而且完全冇聲。"
    )
    assert isinstance(delta, float)


def test_missing_inputs_still_return_none_quietly(claw):
    """查唔到基準（正常資料條件）同 import 爆（code bug）要分開 —— 前者照靜。"""
    assert claw._l600_delta(None, "Sale", 1400) is None
    assert claw._l600_delta(35.2, "", 1400) is None
    assert claw._l600_delta(35.2, "Sale", 0) is None


def test_import_failure_is_loud(claw, capsys, monkeypatch):
    """import 失敗要嘈到 stderr。靜靜 return None 就係 2026-08-22 嗰次事故。"""
    monkeypatch.setattr(claw, "_L600_IMPORT_WARNED", False)
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def boom(name, *args, **kwargs):
        if name.startswith("au_racing_engine"):
            raise ModuleNotFoundError("No module named 'au_racing_engine'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", boom)
    assert claw._l600_delta(35.2, "Sale", 1400) is None
    assert "PF token" in capsys.readouterr().err


def test_the_sys_path_insert_points_at_the_packages_parent():
    """靜態守衛：源碼層面唔准出現「插 package 目錄本身」。

    上面幾個 test 行真 import，但如果將來有人喺另一個 branch 改壞，
    呢個 assert 讀源碼，唔靠執行環境。
    """
    text = CLAW.read_text(encoding="utf-8")
    assert '"scripts" / "au_racing_engine"' not in text, (
        "sys.path 唔可以指住 au_racing_engine 本身，要指佢父目錄 `scripts`"
    )
