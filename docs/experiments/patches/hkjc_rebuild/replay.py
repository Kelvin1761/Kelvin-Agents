#!/usr/bin/env python3
"""HKJC rebuild freeze/replay — prove a refactor changes nothing.

`dump` scores every archived meeting through the real orchestrator
`score_race` (no writes, no network) and records, per race, the full scored
Logic (every horse's python_auto, verdict, shadow verdicts), the rendered
Markdown and the CSV.  `diff` compares two dumps field by field (floats within
1e-9) and prints the first differing paths.

    PYTHONDONTWRITEBYTECODE=1 python3 replay.py dump --out old.jsonl [--no-pit]
    PYTHONDONTWRITEBYTECODE=1 python3 replay.py dump --out new.jsonl [--no-pit]
    python3 replay.py diff old.jsonl new.jsonl [--ignore-text]

Volatile keys (run contract fingerprint, timestamps) are dropped.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
HARNESS = REPO / ".agents/skills/hkjc_racing/hkjc_reflector/scripts"
AUTO = REPO / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts"
for p in (HARNESS, AUTO, REPO, REPO / ".agents/skills/shared_racing"):
    sys.path.insert(0, str(p))

VOLATILE = {"python_auto_run_contract", "generated_at", "scored_at", "timestamp"}


def _strip(obj):
    if isinstance(obj, dict):
        return {k: _strip(v) for k, v in obj.items() if k not in VOLATILE}
    if isinstance(obj, list):
        return [_strip(v) for v in obj]
    return obj


def dump(args) -> int:
    os.environ["WC_DISABLE_HKJC_PROFILE_ENRICH"] = "1"
    os.environ["WC_DISABLE_POST_SUCCESS_DEPLOY"] = "1"
    import hkjc_auto_orchestrator as orch
    import hkjc_eval_harness as harness
    import pit_backtest
    import rescore_backtest

    captured = {}
    orch._atomic_write_json = lambda *a, **k: None

    def _capture(prepared):
        md_path, markdown, csv_path, csv_text = prepared
        captured["md"], captured["csv"] = markdown, csv_text
        return md_path, csv_path

    orch.write_prepared_race_outputs = _capture
    orch.HKJCAutoOrchestrator._emit_event = lambda *a, **k: None
    root = Path(args.meeting_root) if args.meeting_root else harness._default_root()
    meetings = harness.discover_meetings(root, args.since, args.until)
    all_rows = None if args.no_pit else pit_backtest.load_all_rows()
    shadows = args.shadow or ""
    n = 0
    with open(args.out, "w", encoding="utf-8") as out:
        for md in meetings:
            day = harness.MEETING_RE.match(md.name).group(1)
            if all_rows is not None:
                pit_backtest.inject_as_of(all_rows, day)
            o = orch.HKJCAutoOrchestrator(md, shadow_profile=shadows)
            for race_file in sorted(md.glob("Race_*_Logic.json"), key=rescore_backtest.race_num_from_path):
                captured.clear()
                row = {"meeting": md.name, "race": rescore_backtest.race_num_from_path(race_file)}
                try:
                    with contextlib.redirect_stdout(io.StringIO()):
                        logic = o.score_race(race_file)
                    row["logic"] = _strip(logic) if logic else None
                    row["md"] = captured.get("md")
                    row["csv"] = captured.get("csv")
                except Exception as exc:
                    row["error"] = f"{type(exc).__name__}: {exc}"[:300]
                out.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
                n += 1
            print(f"{md.name}", file=sys.stderr)
    print(f"wrote {n} races → {args.out}", file=sys.stderr)
    return 0


def _walk(a, b, path, diffs, tol):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                diffs.append((f"{path}.{k}", "missing" if k not in b else "added"))
            else:
                _walk(a[k], b[k], f"{path}.{k}", diffs, tol)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            diffs.append((path, f"len {len(a)}→{len(b)}"))
        for i, (x, y) in enumerate(zip(a, b)):
            _walk(x, y, f"{path}[{i}]", diffs, tol)
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        if abs(float(a) - float(b)) > tol:
            diffs.append((path, f"{a}→{b}"))
    elif a != b:
        diffs.append((path, f"{str(a)[:60]!r}→{str(b)[:60]!r}"))


def diff(args) -> int:
    def load(p):
        return {(r["meeting"], r["race"]): r for r in map(json.loads, open(p, encoding="utf-8"))}
    old, new = load(args.old), load(args.new)
    keys = sorted(old.keys() & new.keys() if args.common else old.keys() | new.keys())
    bad, kinds, examples, text_kinds = 0, Counter(), [], Counter()
    for key in keys:
        a, b = old.get(key, {}), new.get(key, {})
        if args.ignore_text:
            a = {k: v for k, v in a.items() if k not in ("md", "csv")}
            b = {k: v for k, v in b.items() if k not in ("md", "csv")}
        d = []
        _walk(a, b, "", d, args.tol)
        if args.ignore:
            import re as _re
            d = [(p, w) for p, w in d if not _re.search(args.ignore, p)]
        if args.text_lines:
            for field in ("md", "csv"):
                if any(p == f".{field}" for p, _ in d):
                    old_lines = set((a.get(field) or "").splitlines())
                    new_lines = set((b.get(field) or "").splitlines())
                    for line in sorted(old_lines - new_lines)[:50]:
                        text_kinds[(field, "-", line[:90])] += 1
                    for line in sorted(new_lines - old_lines)[:50]:
                        text_kinds[(field, "+", line[:90])] += 1
        if d:
            bad += 1
            for path, _ in d:
                import re
                kinds[re.sub(r"\[\d+\]|\.\d+(?=\.|$)", "[]", path)] += 1
            examples.append((key, d[:5]))
    print(f"races {len(keys)}  differing {bad}")
    for k, c in kinds.most_common(30):
        print(f"  {c:6d}  {k}")
    for (field, sign, line), c in text_kinds.most_common(args.show_text):
        print(f"  {field} {sign} x{c}: {line}")
    for key, d in examples[: args.show]:
        print(key)
        for path, what in d:
            print(f"    {path}: {what}")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("dump")
    d.add_argument("--out", required=True)
    d.add_argument("--meeting-root")
    d.add_argument("--since")
    d.add_argument("--until")
    d.add_argument("--no-pit", action="store_true")
    d.add_argument("--shadow", help="comma list of shadow profiles to score too")
    c = sub.add_parser("diff")
    c.add_argument("old")
    c.add_argument("new")
    c.add_argument("--tol", type=float, default=1e-9)
    c.add_argument("--ignore-text", action="store_true")
    c.add_argument("--show", type=int, default=5)
    c.add_argument("--common", action="store_true", help="only races present in both dumps")
    c.add_argument("--ignore", help="regex of paths to ignore")
    c.add_argument("--text-lines", action="store_true", help="summarise changed Markdown/CSV lines")
    c.add_argument("--show-text", type=int, default=25)
    a = ap.parse_args()
    return dump(a) if a.cmd == "dump" else diff(a)


if __name__ == "__main__":
    raise SystemExit(main())
