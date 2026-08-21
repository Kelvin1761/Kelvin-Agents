#!/usr/bin/env python3
"""Re-score evaluable AU meetings (Flemington/Randwick — the only tracks with
results) through the live engine, then evaluate Top-3 metrics. Use before/after
an engine change to measure real impact.

  python au_rescore_and_eval.py --rescore   # re-run engine then evaluate
  python au_rescore_and_eval.py             # evaluate current CSVs only
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from collections import Counter
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.append(str(SCRIPT_DIR))

from au_archive_calibrator import (  # noqa: E402
    ARCHIVE_ROOT,
    HISTORICAL_RESULTS_CSV,
    MATRIX_KEYS,
    choose_track_rows,
    detect_meeting_date,
    load_scoring_rows,
    load_historical_results,
    normalize_horse_name,
    normalize_track_name,
    parse_int,
)
from au_metric_contract import ranked_performance  # noqa: E402


def _corpus_meeting_dirs(root):
    """Meeting folders under `root` AND under `root/Archive`, oldest first.

    `root.iterdir()` used to be enough. It is not: the daily schedule files
    finished meetings into `<root>/Archive/`, and on 2026-08-21 that hid 751 of
    1,530 scored AU races (49.1%) — including 16 of the 17 dates that are clean
    point-in-time. Any number this harness printed before this change was
    measured on the older, post-race-rescored half of the corpus.
    """
    import sys as _sys
    from pathlib import Path as _Path
    _shared = _Path(__file__).resolve()
    for _ in range(6):
        _shared = _shared.parent
        _cand = _shared / "shared_racing" / "scripts"
        if (_cand / "corpus_paths.py").exists():
            if str(_cand) not in _sys.path:
                _sys.path.insert(0, str(_cand))
            break
    from corpus_paths import meeting_dirs as _meeting_dirs
    return sorted(_meeting_dirs(root))


AUTO_ORCH = SCRIPT_DIR / "au_auto_orchestrator.py"
EVAL_TRACKS = {"flemington", "randwick"}


def mtrack(md: Path) -> str:
    n = md.name
    if n[:10].count("-") == 2:
        n = n[11:]
    for s in (" Race 1-10", " Race 1-9", " Race 1-8", " Race 1-7", " Race 1-6"):
        n = n.replace(s, "")
    return n.strip()


def af(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def evaluable_meetings() -> list[Path]:
    out = []
    for md in _corpus_meeting_dirs(ARCHIVE_ROOT):
        if normalize_track_name(mtrack(md)) in EVAL_TRACKS:
            out.append(md)
    return out


def rescore(meetings: list[Path]) -> None:
    for i, md in enumerate(meetings, 1):
        print(f"  re-score {i}/{len(meetings)} {md.name}", flush=True)
        r = subprocess.run([sys.executable, str(AUTO_ORCH), str(md)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            sys.stderr.write(f"   !! failed: {md.name}\n{r.stderr[-400:]}\n")


def evaluate(meetings: list[Path]) -> dict:
    historical = load_historical_results(HISTORICAL_RESULTS_CSV)
    b = Counter()
    for md in meetings:
        mdate = detect_meeting_date(md)
        mt = mtrack(md)
        if not mdate:
            continue
        for sp in sorted(md.glob("Race_*_Auto_Scoring.csv")):
            rno = parse_int(sp.stem)
            if not rno:
                continue
            rr = choose_track_rows(historical.get((mdate, rno), []), mt)
            if not rr:
                continue
            lookup = {r["horse_slug"]: r for r in rr}
            joined = []
            for srow in load_scoring_rows(sp):
                res = lookup.get(normalize_horse_name(srow.get("horse_name", "")))
                if res:
                    joined.append({"ability": af(srow.get("ability_score")),
                                   "pos": int(res["pos"]),
                                   "num": parse_int(srow.get("horse_number")) or 0})
            if len(joined) < 4 or sum(1 for j in joined if j["pos"] <= 3) < 3:
                continue
            ranked = sorted(joined, key=lambda j: (-j["ability"], j["num"]))
            performance = ranked_performance(ranked, horse_key="num", position_key="pos")
            hits = int(performance["hits"])
            b["n"] += 1
            b["top3_hits"] += hits
            b["gold"] += int(performance["gold"])
            b["good"] += int(performance["good_positional"])
            b["pass"] += int(performance["pass"])
            b["miss"] += 1 if hits == 0 else 0
            b["win_t3"] += int(performance["winner_in_top3"])
            b["top2_both"] += int(performance["good_positional"])
            b["pick1_placed"] += int(ranked[0]["pos"] <= 3)
            b["pick1_won"] += int(performance["champion"])
    n = max(1, b["n"])
    return {"races": b["n"], "good_rate": b["good"] / n * 100, "pass_rate": b["pass"] / n * 100,
            "top3": b["top3_hits"] / (3 * n) * 100,
            "win_t3": b["win_t3"] / n * 100, "gold": b["gold"], "good": b["good"],
            "pass": b["pass"], "miss": b["miss"],
            "top2_both": b["top2_both"] / n * 100, "top2_both_n": b["top2_both"],
            "pick1_placed": b["pick1_placed"] / n * 100, "pick1_won": b["pick1_won"] / n * 100}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rescore", action="store_true")
    ap.add_argument("--tag", default="")
    args = ap.parse_args()
    meetings = evaluable_meetings()
    print(f"Evaluable meetings (Flemington/Randwick): {len(meetings)}", flush=True)
    if args.rescore:
        print("Re-scoring through live engine...", flush=True)
        rescore(meetings)
    m = evaluate(meetings)
    tag = f" [{args.tag}]" if args.tag else ""
    print("\n" + "=" * 56)
    print(f"EVAL{tag}  —  {m['races']} races")
    print("=" * 56)
    print(f"  Gold% (actual Top3 in model Top4): {m['gold']/max(1, m['races'])*100:.2f}   ({m['gold']} races)")
    print(f"  Good% (#1 & #2 both placed)      : {m['good_rate']:.2f}   ({m['good']} races)")
    print(f"  Pass% (any 2 of model Top3)      : {m['pass_rate']:.2f}   ({m['pass']} races)")
    print(f"  Pick#1 placed%                   : {m['pick1_placed']:.2f}")
    print(f"  Pick#1 won%                      : {m['pick1_won']:.2f}")
    print(f"  Top3%  (precision of 3 picks)    : {m['top3']:.2f}")
    print(f"  Winner-in-top3-picks%            : {m['win_t3']:.2f}")
    print(f"  Miss (0/3)                       : {m['miss']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
