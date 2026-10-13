#!/usr/bin/env python3
"""Give every bare-number Margin in the AU results corpus its `L` unit (`5.22` -> `5.22L`).

Format only: the value never changes, `—`/blank/already-`L`/anything else is left alone,
and every other column is verified byte-identical before the file is replaced.
Dry-run by default; `--apply` takes a timestamped backup and writes atomically.

Why: `au_results_ingest.load_sb_csv` writes `<n>L`, but the dated repair tool wrote the
source value as-is, and April-June 2026 rows already carried bare numbers. Harnesses
that parse `([-+]?\\d+(?:\\.\\d+)?)\\s*L` read those as "no margin".
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

BARE = re.compile(r"^\d+(?:\.\d+)?$")


def normalise(value: str) -> str:
    text = value.strip()
    return f"{text}L" if BARE.match(text) else value


def run(path: Path, apply: bool) -> dict:
    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    fieldnames = reader.fieldnames
    rows = list(reader)
    changed = Counter()
    out_rows = []
    for row in rows:
        new = dict(row)
        before = row.get("Margin") or ""
        after = normalise(before)
        if after != before:
            changed[(row.get("Date") or "")[:7]] += 1
            new["Margin"] = after
        out_rows.append(new)

    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\r\n" if "\r\n" in text[:4096] else "\n")
    writer.writeheader()
    writer.writerows(out_rows)
    rendered = buffer.getvalue()

    # Verify: same rows, same order, every non-Margin cell identical, Margin only gained "L".
    check = list(csv.DictReader(io.StringIO(rendered, newline="")))
    assert len(check) == len(rows), "row count changed"
    for old, new in zip(rows, check):
        for key in fieldnames:
            if key == "Margin":
                assert new[key] == old[key] or new[key] == f"{old[key].strip()}L", (old, new)
            else:
                assert new[key] == old[key], (key, old, new)

    result = {"rows": len(rows), "normalised": sum(changed.values()), "by_month": dict(sorted(changed.items())),
              "mode": "apply" if apply else "dry_run", "backup": None}
    if apply and changed:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup = path.with_name(f"{path.name}.bak_{stamp}_margin_units")
        shutil.copy2(path, backup)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes((b"\xef\xbb\xbf" if bom else b"") + rendered.encode("utf-8"))
        tmp.replace(path)
        result["backup"] = str(backup)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--results-csv", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    path = args.results_csv
    if path is None:
        sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
        import wongchoi_paths
        path = Path(wongchoi_paths.au_historical_results_csv())
    print(run(path, args.apply))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
