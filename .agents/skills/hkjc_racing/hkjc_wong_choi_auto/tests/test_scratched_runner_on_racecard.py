"""A runner scratched after the first build must not fail the race (2026-10-11 R4)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import hkjc_auto_orchestrator as orch  # noqa: E402


def test_withdrawn_names_are_recognised():
    for name in ("三軍勇將 (退出)", "三軍勇將（退出）", "MIGHTY COMMANDER (Scratched)", "某馬 退賽"):
        assert orch._is_withdrawn_runner({"horse_name": name})
    for name in ("三軍勇將", "退出馬王", ""):
        assert not orch._is_withdrawn_runner({"horse_name": name})


def test_racecard_runner_set_ignores_scratched_runner():
    card = """班次: 第四班

馬號: 1
馬名: 甲馬
評分: 60

馬號: 3
馬名: 三軍勇將 (退出)
評分: 55
"""
    _, info = orch._parse_racecard_meta(card)
    official = {k for k, e in info.items() if str(k).isdigit() and not orch._is_withdrawn_runner(e)}
    assert official == {"1"}



def test_empty_class_line_does_not_swallow_next_line():
    """EXP-20261112-14：空白「班次:」唔可以食咗下一行做班次。"""
    text = "#### 第一部分：賽事資料 (Race Info)\n場次: 第1場\n班次: \n\n#### 第二部分：馬匹資料 (Horse Info)\n馬號: 1\n馬名: 甲\n"
    race_class, _info = orch._parse_racecard_meta(text)
    assert race_class == ""


def test_class_line_value():
    race_class, _info = orch._parse_racecard_meta("班次: 第三班\n馬號: 1\n馬名: 甲\n")
    assert race_class == "第三班"
