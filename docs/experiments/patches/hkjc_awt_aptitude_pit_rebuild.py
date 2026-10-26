#!/usr/bin/env python3
"""EXP-20261027-03 — rebuild PIT AWT evidence from archived formguides.

Takes a `hkjc_eval_harness.py run --dump-matrix` baseline file and writes one
candidate file per arm.  Only Sha Tin all-weather races change; every other
row is copied verbatim, so the harness `compare` pairs on identical turf rows.

Evidence is rebuilt with production code only: `parse_hkjc_formguide(...,
as_of_date=race date)`, the meeting's horse-profile cache through
`filter_profile_as_of`, `_merge_profile_history_for_stats`, and
`compute_distance_suitability_v2`.  The blend is the engine's own
`_build_distance_suitability_v2_shadow` formula with the pre-registered
AWT profile (w=0.08, cap=4, EXP-20261007-05).

    python3 hkjc_awt_aptitude_pit_rebuild.py base.jsonl --out-dir DIR
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / ".agents/scripts"))
sys.path.insert(0, str(REPO / ".agents/skills/shared_racing"))
import inject_hkjc_fact_anchors as inj  # noqa: E402
from eval_metrics import race_metrics  # noqa: E402

WEIGHT, CAP = 0.08, 4.0
ROOT = Path("/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/HK_Racing")
METRIC_KEYS = ("gold", "gold_strict", "good_positional", "champion",
               "top3_capture_at5", "ndcg_at5", "competitive_recall_at5")


def _race_file(meeting: Path, race: int, suffix: str) -> Path | None:
    hits = [p for p in meeting.glob(f"* Race {race} {suffix}") if "Prediction" not in str(p)]
    return hits[0] if hits else None


def _awt_distance(meeting: Path, race: int) -> int | None:
    card = _race_file(meeting, race, "排位表.md")
    if not card:
        return None
    text = card.read_text(encoding="utf-8")
    if "場地: 全天候跑道" not in text:
        return None
    match = re.search(r"(\d{4})米", text)
    return int(match.group(1)) if match else None


def surface_residual_score(rows: list, distance: int, anchor: datetime) -> tuple[float, float]:
    """Arm B: AWT posterior minus all-HK-surface posterior, same ±200m rows."""
    sums = {"awt": [0.0, 0.0], "all": [0.0, 0.0]}
    for row in rows:
        dt = row.get("date_dt")
        try:
            dist, finish, field = int(row.get("distance") or 0), int(row.get("finish") or 0), int(row.get("field_size") or 0)
        except (TypeError, ValueError):
            continue
        if not dt or dt >= anchor or field < 4 or not 1 <= finish <= field or abs(dist - distance) > 200:
            continue
        age = (anchor - dt).days
        if age <= 0 or age > 730:
            continue
        key = inj._history_surface_key(row)
        if not key:
            continue
        w = 2.0 ** (-age / 365.0)
        perf = 1.0 - (finish - 1.0) / max(field - 1.0, 1.0)
        sums["all"][0] += w * perf
        sums["all"][1] += w
        if key == "沙田AWT":
            sums["awt"][0] += w * perf
            sums["awt"][1] += w
    if sums["awt"][1] <= 0:
        return 60.0, 0.0
    post = {k: (s + 2.0) / (n + 4.0) for k, (s, n) in sums.items()}
    return max(40.0, min(80.0, 60.0 + 40.0 * (post["awt"] - post["all"]))), sums["awt"][1]


def evidence_for_race(meeting: Path, race: int, distance: int, date: str) -> tuple[dict, int]:
    formguide = _race_file(meeting, race, "賽績.md")
    parsed = inj.parse_hkjc_formguide(str(formguide), as_of_date=date) if formguide else {"horses": []}
    cache_path = meeting / ".hkjc_cache" / "profile_cache.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    anchor = datetime.strptime(date, "%Y-%m-%d")
    out, future_rows = {}, 0
    for horse in parsed.get("horses", []):
        cached = cache.get(str(horse.get("brand_no") or "")) or {}
        profile = inj.filter_profile_as_of(cached.get("data") or {}, date) if cached else {}
        history = inj._merge_profile_history_for_stats(horse.get("races") or [], (profile or {}).get("entries", []))
        future_rows += sum(1 for r in history if r.get("date_dt") and r["date_dt"] >= anchor)
        v2 = inj.compute_distance_suitability_v2(history, "沙田AWT", distance, date,
                                                 overseas_races=horse.get("pdf_overseas_races") or [])
        b_score, b_n = surface_residual_score(history, distance, anchor)
        out[int(horse["num"])] = {"A": float(v2["score"]), "A_n": float(v2["target_effective_n"]),
                                  "B": b_score, "B_n": b_n}
    return out, future_rows


def blend(raw: float, score: float) -> float:
    component = 60.0 + max(-CAP, min(CAP, score - 60.0))
    return (1.0 - WEIGHT) * raw + WEIGHT * component


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline")
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    out_dir = Path(args.out_dir)
    rows = [json.loads(line) for line in Path(args.baseline).read_text(encoding="utf-8").splitlines()]
    writers = {arm: open(out_dir / f"cand_{arm}.jsonl", "w", encoding="utf-8") for arm in ("A", "B")}
    audit = {"awt_races": 0, "future_rows": 0, "races_with_evidence": {"A": 0, "B": 0},
             "top4_changed": {"A": 0, "B": 0}, "per_race": []}
    for row in rows:
        distance = None
        if "error" not in row and row.get("horses"):
            distance = _awt_distance(ROOT / row["meeting"], row["race"])
        if not distance:
            for writer in writers.values():
                writer.write(json.dumps(row, ensure_ascii=False) + "\n")
            continue
        audit["awt_races"] += 1
        evidence, future = evidence_for_race(ROOT / row["meeting"], row["race"], distance, row["date"])
        audit["future_rows"] += future
        positions = {h["n"]: h["pos"] for h in row["horses"] if h.get("pos")}
        detail = {"meeting": row["meeting"], "race": row["race"], "distance": distance}
        for arm, writer in writers.items():
            scored = []
            for h in row["horses"]:
                ev = evidence.get(h["n"], {})
                scored.append((-blend(h["raw"], ev.get(arm, 60.0)), h["n"]))
            picks = [n for _s, n in sorted(scored)]
            if any(ev.get(f"{arm}_n", 0) > 0 for ev in evidence.values()):
                audit["races_with_evidence"][arm] += 1
            if picks[:4] != row["picks"][:4]:
                audit["top4_changed"][arm] += 1
            metrics = race_metrics(picks, [n for n, p in positions.items() if p <= 3], actual_pos=positions)
            metrics["mean_top3_model_rank"] = metrics.get("top3_mean_model_rank")
            cand = dict(row, arm=f"awt_{arm}", picks=picks, awt=True,
                        **{k: metrics.get(k) for k in (*METRIC_KEYS, "mean_top3_model_rank")})
            writer.write(json.dumps(cand, ensure_ascii=False) + "\n")
            detail[arm] = {"top4": picks[:4], "base_top4": row["picks"][:4],
                           "evidence_horses": sum(1 for ev in evidence.values() if ev.get(f"{arm}_n", 0) > 0),
                           "field": len(row["horses"])}
        detail["scores"] = evidence
        audit["per_race"].append(detail)
    for writer in writers.values():
        writer.close()
    (out_dir / "audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in audit.items() if k != "per_race"}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
