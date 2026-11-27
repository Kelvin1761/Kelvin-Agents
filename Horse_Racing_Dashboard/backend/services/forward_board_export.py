"""Forward 測試總板 → dashboard snapshot（Portfolio 頁「🧪 Forward 測試」）。

只重用 `.agents/skills/shared_wong_choi/forward_board.py` 嘅 `board()` 同 `summary()`，
唔重寫狀態排序或 stale 門檻（AGENTS.md：一樣嘢只准有一個標準）。
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1
_SKILLS_DIR = Path(__file__).resolve().parents[3] / ".agents" / "skills"


def _load_forward_board():
    added = str(_SKILLS_DIR)
    inserted = added not in sys.path
    if inserted:
        sys.path.insert(0, added)
    try:
        from shared_wong_choi import forward_board
        return forward_board
    finally:
        if inserted and added in sys.path:
            sys.path.remove(added)


def export_forward_board(root: Path | None = None) -> dict:
    fb = _load_forward_board()
    b = fb.board(root=root)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "valid",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "domains": b,
        "summary": fb.summary(b),
        "statuses": list(fb.STATUSES),   # 排序同摘要次序跟 forward_board，前端唔另寫一套
    }
