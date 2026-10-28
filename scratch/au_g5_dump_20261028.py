#!/usr/bin/env python3
"""EXP-20261028-14：設定 career5_placed_bonus 之後跑 `au_fq_weight_class_dump_20261028.py`（真引擎路徑）。

    python3 au_g5_dump_20261028.py --bonus 3.5 --out dump_g5_3.5.json

`engine_core` import 嘅係同一個 dict，所以喺 import 引擎之後原地改就生效。
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / ".agents/skills/au_racing/au_wong_choi_auto/scripts"))
sys.path.insert(0, str(HERE))
from au_racing_engine import engine_core  # noqa: E402
from au_racing_engine.scoring import CLASS_MICRO_WEIGHTS  # noqa: E402

args = sys.argv[1:]
i = args.index("--bonus")
value = float(args[i + 1])
del args[i:i + 2]
assert engine_core.CLASS_MICRO_WEIGHTS is CLASS_MICRO_WEIGHTS
CLASS_MICRO_WEIGHTS["career5_placed_bonus"] = value
sys.argv = [sys.argv[0]] + args
import au_fq_weight_class_dump_20261028 as dump  # noqa: E402
dump.main()
