#!/usr/bin/env python3
"""三個已退役嘅權重搜索工具一定要拒絕跑。

點解要有呢個 test：`au_matrix_weight_search.py` / `au_clean_7d_weight_search.py` /
`au_weight_improvement_search.py` 全部係 coordinate descent／argmax，實測會 overfit
（dev good_pos +3.80 但 holdout 舊 any-one 指標 −5.61）。`au_matrix_refit.py` 個
docstring 明文寫住佢取代咗呢三個。

但「檔案仍然可以跑」＝ 下一個 agent（或者下一個我）照樣會跑，然後攞住一個
overfit 嘅結果當證據。2026-08-21 加咗拒絕閘。呢個 test 鎖住佢 —— 冇 test 嘅話，
拒絕閘可以被靜靜移走而冇人知，而呢個 repo 已經有多過一個 agent 同時寫。

**唔鎖死具體字句**，只鎖三件事：exit 非零、講咗係退役、指去代替品。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"

RETIRED = (
    "au_matrix_weight_search.py",
    "au_clean_7d_weight_search.py",
    "au_weight_improvement_search.py",
)


def _run(name: str, *, opt_in: bool) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    if opt_in:
        env["WC_ALLOW_RETIRED_WEIGHT_SEARCH"] = "1"
    else:
        env.pop("WC_ALLOW_RETIRED_WEIGHT_SEARCH", None)
    return subprocess.run(
        [sys.executable, str(SCRIPTS / name)],
        capture_output=True, text=True, env=env, cwd=str(SCRIPTS), timeout=120,
    )


@pytest.mark.parametrize("name", RETIRED)
def test_retired_tool_refuses_to_run(name: str) -> None:
    result = _run(name, opt_in=False)
    output = result.stdout + result.stderr
    assert result.returncode != 0, f"{name} 冇拒絕就跑咗"
    assert "退役" in output, f"{name} 冇講自己已退役：{output[:200]}"
    assert "au_matrix_refit" in output, f"{name} 冇指去代替品：{output[:200]}"
    # 拒絕係喺 argparse 之前，所以唔應該印 usage
    assert "usage:" not in output, f"{name} 行到 argparse 就太遲：{output[:200]}"


@pytest.mark.parametrize("name", RETIRED)
def test_the_opt_in_escape_hatch_exists(name: str) -> None:
    """保留歷史對照能力 —— 但要明確 opt in。

    **呢個 test 刻意唔真跑 opt-in 路徑。** 2026-08-21 試過，兩個原因：

      * `au_clean_7d_weight_search.py` 同 `au_weight_improvement_search.py`
        喺 argparse 之前就載入全 archive —— 一次 2 分鐘，單元測試唔可以咁。
      * `au_weight_improvement_search.py` opt-in 之後直接爆
        `KeyError: 'race_shape'`（`scripts:157`，`sum(... for k in KEYS)`）。
        即係佢**唔止過時，本身已經爛** —— 又一個唔應該再跑佢嘅理由。

    所以呢度只確認逃生門存在同係一個 early return；真正嘅行為由上面
    `test_retired_tool_refuses_to_run` 覆蓋（嗰個快，因為拒絕喺任何重活之前）。
    """
    text = (SCRIPTS / name).read_text(encoding="utf-8")
    assert "WC_ALLOW_RETIRED_WEIGHT_SEARCH" in text
    guard = text[text.index("def _refuse_if_retired"):]
    body = guard[:guard.index("raise SystemExit")]
    assert "return" in body, f"{name} 嘅 opt-in 唔係 early return"


def test_the_replacement_actually_exists() -> None:
    """拒絕訊息叫人去用 `au_matrix_refit.py` —— 佢一定要真係存在。"""
    assert (SCRIPTS / "au_matrix_refit.py").is_file()


@pytest.mark.parametrize("name", RETIRED)
def test_guard_is_before_the_main_body(name: str) -> None:
    """`_refuse_if_retired()` 要係 `__main__` 之後第一句，唔可以喺工作之後。"""
    text = (SCRIPTS / name).read_text(encoding="utf-8")
    _, tail = text.rsplit('if __name__ == "__main__":', 1)
    first = next(line.strip() for line in tail.splitlines() if line.strip())
    assert first == "_refuse_if_retired()", f"{name} 第一句係 {first!r}"
