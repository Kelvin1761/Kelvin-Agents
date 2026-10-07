#!/usr/bin/env python3
"""Audit overseas-surface and pedigree fallback for HKJC AWT runners."""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd


REPO = Path(__file__).resolve().parents[3]
PATCHES = Path(__file__).resolve().parent
for path in (PATCHES, REPO):
    sys.path.insert(0, str(path))

import hkjc_surface_shape_ml as surface_ml  # noqa: E402


def _load_facts_module():
    path = REPO / ".agents/scripts/inject_hkjc_fact_anchors.py"
    spec = importlib.util.spec_from_file_location("hkjc_fact_overseas_audit", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


facts = _load_facts_module()


def _racecard_path(meeting: str, race_no: int) -> Path | None:
    paths = sorted(Path(meeting).glob(f"* Race {race_no} 排位表.md"))
    return paths[0] if paths else None


def _pdf_path(meeting: str) -> Path | None:
    paths = sorted(Path(meeting).glob("*全日出賽馬匹資料 (PDF).md"))
    return paths[0] if paths else None


def _horse_block(path: Path | None, horse_no: int) -> str:
    if path is None:
        return ""
    text = path.read_text(encoding="utf-8")
    match = re.search(
        rf"(?:^|\n)馬號:\s*{horse_no}\s*\n(.*?)(?=\n馬號:\s*\d+\s*\n|\Z)",
        text,
        re.DOTALL,
    )
    return match.group(1) if match else ""


def _pedigree(block: str) -> tuple[str, str]:
    sire = re.search(r"^父系:\s*(.+)$", block, re.MULTILINE)
    dam = re.search(r"^母系:\s*(.+)$", block, re.MULTILINE)
    return (
        sire.group(1).strip() if sire else "",
        dam.group(1).strip() if dam else "",
    )


def _foreign_quality(rows: list[dict], target_date: str, target_distance: int) -> tuple[float, float, int]:
    weighted = 0.0
    total = 0.0
    used = 0
    anchor = pd.Timestamp(target_date)
    for row in rows:
        if str(row.get("Surface") or "").upper() not in {"DIRT", "SYNTHETIC"}:
            continue
        try:
            distance = int(row.get("Distance") or 0)
            finish = int(row.get("Placing") or 0)
            field = int(row.get("Field_Size") or 0)
            date = pd.Timestamp(facts.parse_date(row.get("Date") or ""))
        except (TypeError, ValueError):
            continue
        age = (anchor - date).days
        if age <= 0 or age > 1095 or abs(distance - target_distance) > 200 or field < 4 or not 1 <= finish <= field:
            continue
        weight = 2.0 ** (-age / 365.0)
        weighted += weight * (1.0 - (finish - 1.0) / (field - 1.0))
        total += weight
        used += 1
    return ((weighted + 2.0) / (total + 4.0), total, used) if total else (0.5, 0.0, 0)


def _sire_quality(
    history: dict[str, list[dict]],
    sire_members: dict[str, set[str]],
    sire: str,
    target_horse: str,
    target_date: str,
    target_distance: int,
) -> tuple[float, float, int, int]:
    weighted = 0.0
    total = 0.0
    used = 0
    contributing_horses = set()
    anchor = pd.Timestamp(target_date)
    for horse_id in sire_members.get(sire, set()):
        if horse_id == target_horse:
            continue
        for row in history.get(horse_id, []):
            if row["date"] >= target_date or row["surface"] != "ST_AWT":
                continue
            if abs(int(row["distance"]) - target_distance) > 200:
                continue
            age = (anchor - pd.Timestamp(row["date"])).days
            if age <= 0 or age > 1095:
                continue
            weight = 2.0 ** (-age / 365.0)
            weighted += weight * float(row["perf"])
            total += weight
            used += 1
            contributing_horses.add(horse_id)
    # Much stronger shrinkage than individual performance: pedigree is a weak fallback.
    return (
        ((weighted + 6.0) / (total + 12.0), total, used, len(contributing_horses))
        if total else (0.5, 0.0, 0, 0)
    )


def _pairwise_auc(df: pd.DataFrame, column: str) -> dict:
    concordant = 0.0
    pairs = 0
    races = 0
    for _key, race in df.groupby("race_key", sort=False):
        race_pairs = 0
        rows = list(race.itertuples(index=False))
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                a, b = rows[i], rows[j]
                va, vb = float(getattr(a, column)), float(getattr(b, column))
                if abs(va - vb) <= 1e-12 or a.finish_pos == b.finish_pos:
                    continue
                better_a = a.finish_pos < b.finish_pos
                concordant += float((va > vb) == better_a)
                pairs += 1
                race_pairs += 1
        races += int(race_pairs > 0)
    return {"auc": round(concordant / pairs, 6) if pairs else None, "pairs": pairs, "races": races}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    df = pd.read_csv(args.dataset)
    df["race_key"] = df["meeting"].astype(str) + "::" + df["race_number"].astype(str)
    history = surface_ml._load_prior_runs()
    df = surface_ml._add_surface_features(df, history)

    pedigree_map: dict[str, tuple[str, str]] = {}
    foreign_map: dict[tuple[str, int, int], list[dict]] = {}
    pdf_cache: dict[str, Path | None] = {}
    card_cache: dict[tuple[str, int], Path | None] = {}
    for row in df.itertuples(index=False):
        card_key = (str(row.meeting), int(row.race_number))
        if card_key not in card_cache:
            card_cache[card_key] = _racecard_path(*card_key)
        block = _horse_block(card_cache[card_key], int(row.horse_number))
        sire, dam = _pedigree(block)
        if row.horse_id and (sire or dam):
            pedigree_map[str(row.horse_id)] = (sire, dam)
        meeting = str(row.meeting)
        if meeting not in pdf_cache:
            pdf_cache[meeting] = _pdf_path(meeting)
        foreign_map[(meeting, int(row.race_number), int(row.horse_number))] = facts.parse_pdf_overseas_races(
            pdf_cache[meeting], str(row.horse_id), str(row.horse_name)
        ) if pdf_cache[meeting] else []

    sire_members: dict[str, set[str]] = defaultdict(set)
    for horse_id, (sire, _dam) in pedigree_map.items():
        if sire:
            sire_members[sire].add(horse_id)

    awt = df[df["surface_key"].eq("ST_AWT")].copy()
    foreign_quality = []
    foreign_n = []
    foreign_runs = []
    sire_quality = []
    sire_n = []
    sire_runs = []
    sire_horses = []
    sire_present = []
    true_overseas_rows = []
    for row in awt.itertuples(index=False):
        key = (str(row.meeting), int(row.race_number), int(row.horse_number))
        overseas = foreign_map.get(key, [])
        fq, fn, fr = _foreign_quality(overseas, str(row.date), int(row.distance_num))
        sire = pedigree_map.get(str(row.horse_id), ("", ""))[0]
        sq, sn, sr, sh = _sire_quality(
            history,
            sire_members,
            sire,
            str(row.horse_id),
            str(row.date),
            int(row.distance_num),
        ) if sire else (0.5, 0.0, 0, 0)
        foreign_quality.append(fq - 0.5)
        foreign_n.append(fn)
        foreign_runs.append(fr)
        sire_quality.append(sq - 0.5)
        sire_n.append(sn)
        sire_runs.append(sr)
        sire_horses.append(sh)
        sire_present.append(bool(sire))
        true_overseas_rows.append(len(overseas))
    awt["foreign_quality"] = foreign_quality
    awt["foreign_eff_n"] = foreign_n
    awt["foreign_runs"] = foreign_runs
    awt["sire_awt_quality"] = sire_quality
    awt["sire_awt_eff_n"] = sire_n
    awt["sire_awt_runs"] = sire_runs
    awt["sire_awt_horses"] = sire_horses
    awt["sire_present"] = sire_present
    awt["true_overseas_rows"] = true_overseas_rows
    awt["hierarchical_quality"] = awt["surface_quality"]
    no_local = awt["surface_target_eff_n"].le(0)
    awt.loc[no_local & awt["foreign_eff_n"].gt(0), "hierarchical_quality"] = awt["foreign_quality"]
    awt.loc[no_local & awt["foreign_eff_n"].le(0) & awt["sire_awt_eff_n"].gt(0), "hierarchical_quality"] = awt["sire_awt_quality"]

    report = {
        "contract": {
            "awt_races": int(awt["race_key"].nunique()),
            "awt_runners": int(len(awt)),
            "date_min": str(awt["date"].min()) if len(awt) else "",
            "date_max": str(awt["date"].max()) if len(awt) else "",
            "decision": "UNRESOLVABLE_SHADOW" if awt["race_key"].nunique() < 30 else "ELIGIBLE_FOR_GATE",
        },
        "coverage": {
            "pdf_available_meetings": int(sum(path is not None for path in pdf_cache.values())),
            "meetings": len(pdf_cache),
            "pedigree_all_runners": round(len(pedigree_map) / max(df["horse_id"].nunique(), 1), 6),
            "awt_local_history": round(float(awt["surface_target_eff_n"].gt(0).mean()), 6) if len(awt) else 0.0,
            "awt_true_overseas_rows": round(float(awt["true_overseas_rows"].gt(0).mean()), 6) if len(awt) else 0.0,
            "awt_foreign_dirt_synthetic": round(float(awt["foreign_eff_n"].gt(0).mean()), 6) if len(awt) else 0.0,
            "awt_no_local_foreign_fallback": round(float((no_local & awt["foreign_eff_n"].gt(0)).mean()), 6) if len(awt) else 0.0,
            "awt_sire_present": round(float(awt["sire_present"].mean()), 6) if len(awt) else 0.0,
            "awt_sire_evidence": round(float(awt["sire_awt_eff_n"].gt(0).mean()), 6) if len(awt) else 0.0,
            "awt_sire_only_fallback": round(float((no_local & awt["foreign_eff_n"].le(0) & awt["sire_awt_eff_n"].gt(0)).mean()), 6) if len(awt) else 0.0,
        },
        "pairwise_auc": {
            column: _pairwise_auc(awt, column)
            for column in ("surface_quality", "foreign_quality", "sire_awt_quality", "hierarchical_quality")
        },
        "examples": awt.loc[
            awt["foreign_eff_n"].gt(0),
            ["date", "race_number", "horse_name", "horse_id", "finish_pos", "foreign_runs", "foreign_eff_n", "foreign_quality"],
        ].head(20).to_dict(orient="records"),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
