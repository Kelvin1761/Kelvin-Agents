#!/usr/bin/env python3
"""EXP-20261016-02：Sportsbet 全程速度（情境標準）。G0–G2 量度 + G3 輸入。

規格：docs/experiments/EXP-20261016-02-au-sportsbet-total-speed-protocol.md —— 唔准喺度改。

構造全部沿用 live `full_time_speed`：RUN regex、試閘剔除、`ContextStandard`、
`context_lookup`（同日變異）、`aggregate`、`zscores`。唯一改動係輸入：
本駒時間 = Sportsbet 頭馬時間 + 負距 × 0.17。

`SparseContextStandard` 只係 `ContextStandard` 嘅稀疏矩陣算法（同一條正規方程、
同一組 penalty、同一個 IRLS），`--check-sparse` 會同原版逐個預測比較。

唯讀。
"""
from __future__ import annotations

import argparse
import json
import math
import random
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy import sparse

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS.parents[2] / "shared_racing" / "scripts"))

from au_racing_engine import full_time_speed as fts  # noqa: E402
from au_racing_engine.engine_core import _formguide_run_context  # noqa: E402
from corpus_paths import meeting_dirs  # noqa: E402

SEC_PER_LENGTH = 0.17
CLEAN_SINCE = "2026-08-05"
TRIAL_RE = re.compile(r"\*\*\(TRIAL\)\*\*|\$0\s|(?:TRIAL|TRL|JUMP.?OUT)", re.I)  # same as prepare_field
HEADER_RE = re.compile(r"^\[(\d+)\]\s+(.+?)\s+\(\d+\)\s*$", re.M)
MARGIN_RE = re.compile(r"margin:\s*(-?[\d.]+)\s*L?\b")


# ── 稀疏版 ContextStandard（同一條式）─────────────────────────────────────
class SparseContextStandard(fts.ContextStandard):
    def __init__(self, events, segment):  # noqa: D401 - mirrors parent exactly
        self.segment = segment
        self.keys = []
        self.penalties = [1e-6, 1.0, 1.0]
        for kind, penalty in (("track", 20.0), ("going", 40.0), ("track_band", 30.0),
                              ("track_going", 40.0), ("rating", 20.0), ("track_rail", 40.0),
                              ("class", 20.0)):
            for key in sorted({self.category(event, kind) for event in events}):
                self.keys.append((kind, key))
                self.penalties.append(penalty)
        self.index = {key: i + 3 for i, key in enumerate(self.keys)}
        rows, cols, vals = [], [], []
        for r, event in enumerate(events):
            logd = math.log(event["distance"] / 1400)
            for c, v in ((0, 1.0), (1, logd), (2, logd * logd)):
                rows.append(r); cols.append(c); vals.append(v)
            for kind in ("track", "going", "track_band", "track_going", "rating", "track_rail", "class"):
                i = self.index.get((kind, self.category(event, kind)))
                if i is not None:
                    rows.append(r); cols.append(i); vals.append(1.0)
        x = sparse.csr_matrix((vals, (rows, cols)), shape=(len(events), len(self.index) + 3))
        y = np.array([math.log(event[segment] / self.length(event)) for event in events])
        weights = np.ones(len(events))
        pen = np.diag(self.penalties)
        for _ in range(3):
            xtw = x.T.multiply(weights[None, :]).tocsr()
            self.beta = np.linalg.solve((xtw @ x).toarray() + pen, xtw @ y)
            residual = np.abs(y - x @ self.beta)
            weights = np.minimum(1.0, 0.03 / np.maximum(residual, 1e-9))


# ── Sportsbet 事件 ─────────────────────────────────────────────────────────
def corpus_sources(root):
    """(target_date, label, folder) for every corpus meeting."""
    out = []
    for meeting in meeting_dirs(root):
        date_m = re.search(r"(\d{4}-\d{2}-\d{2})", meeting.name)
        if date_m:
            out.append((date_m[1], meeting.name, meeting))
    return out


def parse_corpus(root, sources=None):
    """→ events {key: event}, histories {(date, label, race, norm_name): [keys]}, audit.

    `sources` overrides the corpus with explicit (target_date, label, folder) tuples
    (the forward shadow adds pre-race snapshot folders). Every event records
    `first_seen` = earliest target date of a page that listed it, so a caller can
    keep only events that were visible on or before a given day.
    """
    raw = defaultdict(lambda: {"wt": set(), "rows": {}, "going": set(), "rating": set(), "class": set(),
                               "first_seen": "9999-99-99"})
    histories = {}
    audit = Counter()
    for target_date, label, meeting in (sources if sources is not None else corpus_sources(root)):
        for fg in sorted(meeting.glob("*Race * Formguide.md")):
            race_m = re.search(r"Race (\d+) Formguide", fg.name)
            if not race_m:
                audit["formguide_name_unparsed"] += 1
                continue
            text = fg.read_text(encoding="utf-8", errors="replace")
            heads = list(HEADER_RE.finditer(text))
            for i, h in enumerate(heads):
                body = text[h.end(): heads[i + 1].start() if i + 1 < len(heads) else len(text)]
                name = fts.norm(h[2])
                keys = []
                for line in body.splitlines():
                    run = fts.RUN.match(line)
                    if not run:
                        continue
                    audit["form_lines"] += 1
                    if TRIAL_RE.search(line) or "ResultStatus:NON_STANDARD" in line:
                        audit["trial_or_nonstandard"] += 1
                        continue
                    run_date = run[3]
                    if run_date >= target_date:
                        continue
                    audit["page_has_wt"] += "WinningTime:" in line
                    ctx = _formguide_run_context(line)
                    margin = MARGIN_RE.search(line)
                    if "winning_time" not in ctx or margin is None:
                        audit["no_wt_or_margin"] += 1
                        continue
                    audit["parsed_wt"] += 1
                    key = (fts.normalize_venue_name(run[1]), run_date, int(run[2]), int(run[4]))
                    ev = raw[key]
                    ev["first_seen"] = min(ev["first_seen"], target_date)
                    ev["wt"].add(ctx["winning_time"])
                    cond = run[5]
                    ev["going"].add(fts.condition_key(re.sub(r"\d+$", "", cond) or cond))
                    rating = re.search(r"(10|[1-9])$", cond)
                    ev["rating"].add(rating[1] if rating else "unknown")
                    ev["class"].add(fts.class_key(line))
                    ev["rows"][name] = ctx["winning_time"] + float(margin[1]) * SEC_PER_LENGTH
                    keys.append(key)
                histories[(target_date, label, int(race_m[1]), name)] = sorted(
                    set(keys), key=lambda k: k[1], reverse=True)
    events = {}
    for key, ev in raw.items():
        if len(ev["wt"]) != 1:
            audit["conflict_events"] += 1
            continue
        if not 8 < key[3] / next(iter(ev["wt"])) < 22:
            audit["implausible_speed_events"] += 1
            continue
        events[key] = {
            "key": key, "track": key[0], "date": key[1], "distance": key[3],
            "going": sorted(ev["going"])[0], "rating": sorted(ev["rating"])[0], "rail": "unknown",
            "class": sorted(ev["class"])[0], "total": next(iter(ev["wt"])), "first_seen": ev["first_seen"],
            "rows": [{"horse": h, "time": t, "distance": key[3], "key": key} for h, t in ev["rows"].items()],
        }
    audit["events"] = len(events)
    return events, histories, audit


def context_lookup(events, target_date):
    """`fts.context_lookup` with the sparse solver swapped in."""
    original = fts.ContextStandard
    fts.ContextStandard = SparseContextStandard
    try:
        return fts.context_lookup(events, target_date)
    finally:
        fts.ContextStandard = original


# ── 主流程 ─────────────────────────────────────────────────────────────────
def compute_asb(dump, events, histories):
    """→ {(date, meeting, race, n): {raw, reliability, runs, z, s1}} for every dumped runner."""
    ev_list = sorted(events.values(), key=lambda e: e["date"])
    out = {}
    by_date = defaultdict(list)
    for race in dump["races"]:
        by_date[race["date"]].append(race)
    for target_date in sorted(by_date):
        if target_date < CLEAN_SINCE:
            continue
        lookup, _n = context_lookup(ev_list, target_date)
        for race in by_date[target_date]:
            dm = re.search(r"\d{3,5}", str(race["rows"][0].get("distance") or "")) if race["rows"] else None
            distance = int(dm[0]) if dm else 0
            going = fts.condition_key(re.sub(r"\s*\d+$", "", str(race["rows"][0].get("going") or "")))
            details = []
            for row in race["rows"]:
                runs = histories.get((target_date, race["meeting"], race["race"], fts.norm(row["name"])), [])
                values, n, rel = fts.aggregate(runs, fts.norm(row["name"]), target_date,
                                               distance or 1400, going, lookup)
                details.append({"raw": values["A"], "reliability": rel["A"], "runs": n})
            for d, z in zip(details, fts.zscores([d["raw"] for d in details])):
                d["z"] = z
                d["s1"] = round(fts.FULL_TIME_SPEED_GAIN * z * d["reliability"], 8)
            for row, d in zip(race["rows"], details):
                out[f"{target_date}|{race['meeting']}|{race['race']}|{row['n']}"] = d
        print(f"  {target_date}: lookup {len(lookup)}", flush=True)
    return out


def check_sparse(events):
    ev = sorted(events.values(), key=lambda e: e["date"])[:4000]
    dense, sp = fts.ContextStandard(ev, "total"), SparseContextStandard(ev, "total")
    diff = max(abs(dense.predict(e, c) - sp.predict(e, c)) for e in ev for c in (False, True))
    return diff


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--check-sparse", action="store_true")
    args = ap.parse_args()
    root = Path(open(HERE.parent / ".wongchoi_au_data_root").read().strip())
    events, histories, audit = parse_corpus(root)
    print("G0 audit", dict(audit), flush=True)
    if args.check_sparse:
        print("sparse vs dense max |Δpredict| on 4,000 events:", check_sparse(events), flush=True)
    dump = json.loads(Path(args.dump).read_text(encoding="utf-8"))
    asb = compute_asb(dump, events, histories)
    Path(args.out).write_text(json.dumps({"audit": dict(audit), "asb": asb,
                                          "events": len(events)}), encoding="utf-8")
    print(f"→ {args.out}  runners {len(asb)}")


if __name__ == "__main__":
    main()
