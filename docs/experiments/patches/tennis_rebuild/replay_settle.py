"""Settlement replay: run one tree's settle step on a copy of a slim DB, dump prop_tracker.

  python3 replay_settle.py --src <tree>/tennis-wong-choi/src --db settle_base.db --out old_settle.json [--legacy]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import tempfile

PINNED = "2026-11-06T00:00:00+00:00"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--src", required=True)
    p.add_argument("--db", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--legacy", action="store_true")
    a = p.parse_args()
    sys.path.insert(0, a.src)
    try:  # tree layout after 2026-11-06 / before
        import tennis_wc.model.features.common as common
    except ImportError:
        import tennis_wc.features.common as common
    common.utc_now = lambda: PINNED
    work = tempfile.mktemp(suffix=".db", dir=str(__import__("pathlib").Path(a.out).parent))
    shutil.copy(a.db, work)
    conn = sqlite3.connect(work)
    conn.row_factory = sqlite3.Row
    if a.legacy:
        import tennis_wc.props.settlement as s
        s.utc_now = lambda: PINNED
        summary = s.settle_props(conn, today="2026-11-06")
    else:
        import tennis_wc.settle.props as s
        s.utc_now = lambda: PINNED
        summary = s.settle_props(conn, today="2026-11-06")
    rows = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM prop_tracker ORDER BY id")}
    with open(a.out, "w") as f:
        json.dump({"summary": summary, "rows": rows}, f, sort_keys=True, default=str)
    conn.close()
    __import__("os").remove(work)
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
