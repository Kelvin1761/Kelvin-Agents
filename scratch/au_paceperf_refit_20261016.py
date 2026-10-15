#!/usr/bin/env python3
"""喺同一個研究變體下跑 `au_walkforward_refit.py`（EXP-20261016-01）。

變體一定要喺 import refit 工具**之前**套用：工具 import 嗰陣記低 anchor 權重。

用法：python3 scratch/au_paceperf_refit_20261016.py --variant base predict --data X --out Y
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE))

if __name__ == "__main__":
    argv = sys.argv[1:]
    if len(argv) < 2 or argv[0] != "--variant":
        raise SystemExit(__doc__)
    import au_paceperf_variants_20261016 as variants
    variants.apply(argv[1])
    import au_walkforward_refit
    au_walkforward_refit.main(argv[2:])
