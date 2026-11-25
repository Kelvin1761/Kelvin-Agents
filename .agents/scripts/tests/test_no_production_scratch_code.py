"""正式 code 唔准行／import repo 入面 `scratch/*.py`（系統升級第二輪第 7 項，2026-11-25）。

`scratch/` 係一次性研究腳本，冇測試、冇人維護；正式排程依賴佢 = 一改就靜靜壞。寫結果檔去 scratch/（json／csv／md）唔計。
真係要用就搬入正式位置加測試；凍結嘅預先登記評估腳本（路徑寫死喺協議）先可以列入 ALLOWED，要寫原因。
"""
from __future__ import annotations

import ast
import re
import warnings
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
ROOTS = (".agents", "Horse_Racing_Dashboard", "tennis-wong-choi")
SKIP = {"tests", "scratch", "archive", "node_modules", ".venv", "patches", "__pycache__"}
ALLOWED = {
    ".agents/skills/au_racing/au_daily_auto/au_forward_tracker.py":
        "EXP-20261016-03 S2 forward：凍結評估腳本 scratch/au_s2_forward_shadow_20261016.py，協議寫死路徑",
}
PY_IN_SCRATCH = re.compile(r"(^|/)scratch/[^'\"]*\.py$")


def _scratch_code_refs(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and PY_IN_SCRATCH.search(node.value):
            return True
        # REPO / "scratch" / "x.py"
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            parts, cur = [], node
            while isinstance(cur, ast.BinOp) and isinstance(cur.op, ast.Div):
                if isinstance(cur.right, ast.Constant) and isinstance(cur.right.value, str):
                    parts.append(cur.right.value)
                cur = cur.left
            parts.reverse()
            if "scratch" in parts and parts[-1].endswith(".py"):
                return True
    return False


class NoProductionScratchCodeTest(unittest.TestCase):
    def test_no_new_production_dependency_on_scratch_code(self):
        found = set()
        for root in ROOTS:
            for path in (REPO / root).rglob("*.py"):
                rel = path.relative_to(REPO)
                if SKIP & set(rel.parts) or rel.name.startswith("test_"):
                    continue
                try:
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        tree = ast.parse(path.read_text(encoding="utf-8"))
                except (SyntaxError, UnicodeDecodeError):
                    continue
                if _scratch_code_refs(tree):
                    found.add(rel.as_posix())
        self.assertEqual(sorted(found - set(ALLOWED)), [],
                         "正式 code 唔准行 scratch/*.py：搬入正式位置加測試，或者（凍結協議腳本）列入 ALLOWED 寫原因")


if __name__ == "__main__":
    unittest.main()
