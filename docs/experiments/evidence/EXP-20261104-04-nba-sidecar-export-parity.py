"""EXP-20261104-04: dump every NBA dashboard export path for every day, then diff two dumps.

Covers the live snapshot (wall-clock firewall), the settlement path (no firewall, legacy
strategies), the betting-card path (firewall at the latest freeze instant) and tracking.

  PYTHONDONTWRITEBYTECODE=1 python3 <this> dump <repo_root_at_old_commit> before.json
  PYTHONDONTWRITEBYTECODE=1 python3 <this> dump <repo_root_at_new_commit> after.json
  python3 <this> diff before.json after.json
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOTS = [Path.home() / "WongChoiData" / "Wong Choi NBA Analysis", Path("/Users/imac/wongchoi-scheduler")]
LEDGER = Path.home() / "WongChoiData" / "NBA_Market_Eval"


def scrub(value):
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items() if k != "generated_at"}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


def dump(repo, out_path):
    sys.path.insert(0, str(Path(repo).resolve() / "Horse_Racing_Dashboard" / "backend"))
    from services import multisport_exporter as mx
    from services.nba_tracking import build_tracking

    def frozen_firewall(folder):
        stamps = []
        for manifest in (folder / "_prediction_snapshots").glob("*/manifest.json"):
            try:
                stamps.append(datetime.fromisoformat(json.loads(manifest.read_text())["created_at"]))
            except (ValueError, KeyError, OSError):
                pass
        if not stamps:
            return None
        at = max(stamps)
        return lambda report, sb=None: mx.nba_publication_firewall(report, sb, validation_time=at)

    out = {}
    for root in ROOTS:
        for folder in sorted(root.glob("????-??-?? NBA Analysis")):
            day = folder.name[:10]
            key = f"{root.name}/{day}"
            out[key] = {
                "default": scrub(mx.export_nba_snapshot(root, target_date=day)),
                "settlement": scrub(mx.export_nba_snapshot(root, target_date=day, firewall=mx.nba_no_firewall,
                                                           include_legacy_strategies=True)),
            }
            frozen = frozen_firewall(folder)
            if frozen:
                out[key]["card"] = scrub(mx.export_nba_snapshot(root, target_date=day, firewall=frozen))
    out["tracking"] = scrub(build_tracking([Path(repo)] + ROOTS, LEDGER, mx.nba_publication_firewall))
    Path(out_path).write_text(json.dumps(out, ensure_ascii=False, sort_keys=True, indent=1))
    print(len(out) - 1, "days;", len(out["tracking"]["records"]), "tracking records")


def diff(before_path, after_path):
    a, b = json.load(open(before_path)), json.load(open(after_path))
    diffs = {}

    def walk(x, y, p):
        if isinstance(x, dict) and isinstance(y, dict):
            for k in set(x) | set(y):
                if k not in x or k not in y:
                    diffs.setdefault(("key", k, "before-only" if k in x else "after-only"), []).append(p)
                    continue
                walk(x[k], y[k], p + "/" + k)
        elif isinstance(x, list) and isinstance(y, list):
            if len(x) != len(y):
                diffs.setdefault(("len", p), []).append((len(x), len(y)))
                return
            for i, (u, v) in enumerate(zip(x, y)):
                walk(u, v, p + f"[{i}]")
        elif x != y:
            field = re.sub(r"\[\d+\]", "[]", re.sub(r"^/[^/]+/\d{4}-\d\d-\d\d", "", p))
            diffs.setdefault(("val", field), []).append((p, x, y))

    walk(a, b, "")
    for k, v in sorted(diffs.items(), key=str):
        print(len(v), k, v[0] if k[0] != "key" else "")
    print("identical" if not diffs else f"{len(diffs)} difference groups")


if __name__ == "__main__":
    {"dump": dump, "diff": diff}[sys.argv[1]](*sys.argv[2:])
