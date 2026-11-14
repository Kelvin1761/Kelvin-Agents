"""HKJC 歷史引擎回放：喺回放語料行 hkjc_eval_harness，騎練 PIT 評分用 2019 起嘅舊季。

同 `hkjc_eval_harness.py` 參數一樣（run／compare），只係 run 之前將 `pit_backtest.load_all_rows`
換成 `hkjc_history_replay_pit.load_all_rows_extended`。as-of 仍然由 harness 逐賽日做。
例：python3 hkjc_history_replay_eval.py run --meeting-root <replay root> --dump-matrix --out base.jsonl
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent))

import hkjc_eval_harness  # noqa: E402
import hkjc_history_replay_pit  # noqa: E402
import pit_backtest  # noqa: E402

pit_backtest.load_all_rows = hkjc_history_replay_pit.load_all_rows_extended

if __name__ == "__main__":
    raise SystemExit(hkjc_eval_harness.main())
