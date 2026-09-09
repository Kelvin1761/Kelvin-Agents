"""四個排程 + control plane 讀 subprocess 輸出唔可以用嚴格 UTF-8。

點解要有呢個 test
-----------------
2026-08-13：AU 晚更俾一個 `UnicodeDecodeError` 殺死 —— `stderr=STDOUT` 把兩條
stream 合併，兩個寫入者交錯切開咗一個多位元組字元，於是出現孤立嘅 0xef。
當時修好咗 `au_daily_schedule.run_cmd`（加 `encoding="utf-8", errors="replace"`）
並且寫低咗完整原因。

2026-09-09：**同一件事再嚟一次，但今次係喺冇搬過個修正嘅三個 runner。**
`deploy.sh` 一句 `PYTHON_BIN\\xef: unbound variable` 入面嗰個孤立 0xef，令

    hkjc  prerace  2026-09-09 08:00  →  failed
    tennis card    2026-09-09 09:00  →  failed

兩個 run 一齊死喺
`UnicodeDecodeError: 'utf-8' codec can't decode byte 0xef in position 161`。
AU 同一日撞到同一個 byte，因為佢有 `errors="replace"`，照樣行完並且**如實把
嗰句 shell 錯誤印咗出嚟**，所以先至查得到真兇。

兩個教訓：
1. subprocess 輸出係俾人睇嘅 log，永遠唔應該有能力令 run 死。
2. `UnicodeDecodeError: ... position 161` 連係邊條命令、真正壞咗咩都冇講 ——
   佢用一個清楚嘅失敗換成一個查極都查唔到嘅失敗。

`text=True` 兩個問題都有份：佢係嚴格 UTF-8，而且喺 launchd 嘅 POSIX locale
之下會退去 ASCII。所以呢度要求明寫 `encoding=` 同 `errors=`。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]

# 每個自動化 run 都會經過呢幾個 runner —— 一個 raise 就係成個 run 死。
SCHEDULER_RUNNERS = (
    ".agents/skills/au_racing/au_daily_auto/au_daily_schedule.py",
    ".agents/skills/hkjc_racing/hkjc_daily_auto/hkjc_daily_schedule.py",
    ".agents/skills/nba/nba_daily_auto/nba_daily_schedule.py",
    ".agents/skills/shared_wong_choi/command_adapter.py",
    "tennis-wong-choi/scripts/tennis_daily_schedule.py",
)

CALL = re.compile(r"subprocess\.(?:run|Popen|check_output)\(")


def _call_blocks(text: str):
    """每個 subprocess 呼叫嘅引數段落（由 `(` 數到括號平衡為止）。"""
    for match in CALL.finditer(text):
        depth = 0
        start = match.end() - 1
        for index in range(start, len(text)):
            if text[index] == "(":
                depth += 1
            elif text[index] == ")":
                depth -= 1
                if depth == 0:
                    yield match.start(), text[start:index + 1]
                    break


@pytest.mark.parametrize("relative", SCHEDULER_RUNNERS)
def test_scheduler_subprocess_output_is_decoded_leniently(relative: str) -> None:
    path = REPO_ROOT / relative
    assert path.is_file(), f"{relative} 唔見咗 —— 改咗路徑就要同時改呢個 test"
    text = path.read_text(encoding="utf-8")

    offenders: list[str] = []
    for offset, block in _call_blocks(text):
        captures = ("stdout=subprocess.PIPE" in block
                    or "capture_output=True" in block
                    or "check_output" in text[max(0, offset - 30):offset + 30])
        if not captures:
            # 冇 capture = 輸出直接去 parent，Python 根本冇 decode 過。
            continue
        if "errors=" in block and "encoding=" in block:
            continue
        line = text[:offset].count("\n") + 1
        offenders.append(f"{relative}:{line}")

    assert not offenders, (
        "排程讀 subprocess 輸出要明寫 `encoding=\"utf-8\", errors=\"replace\"`：\n  "
        + "\n  ".join(offenders)
        + "\n`text=True` 係嚴格 UTF-8（launchd 嘅 POSIX locale 仲會退去 ASCII），"
          "一個孤立 0xef 就足以殺死成個 run —— 2026-08-13 AU、2026-09-09 HKJC "
          "同 Tennis 各中過一次。"
    )


def test_a_lone_continuation_byte_survives_replace_but_not_strict() -> None:
    """釘實個機制本身，唔淨係釘寫法。"""
    raw = b"PYTHON_BIN\xef: unbound variable"
    with pytest.raises(UnicodeDecodeError):
        raw.decode("utf-8")
    assert "unbound variable" in raw.decode("utf-8", errors="replace")
