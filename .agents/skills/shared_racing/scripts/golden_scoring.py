#!/usr/bin/env python3
"""Golden-file regression test for the scoring layer.

WHY THIS EXISTS
---------------
Weights, formulas and display gains are entangled: `MATRIX_WEIGHTS`,
`MATRIX_FORMULAS` and `MATRIX_DISPLAY_GAINS` all multiply into the same ranking,
so a change meant for one dimension routinely moves three.  Reading the diff
does not tell you that — only re-scoring real horses does.

This freezes a sample of REAL horses (their feature scores, straight out of
scored races) together with the dimension scores and ability score the current
code gives them.  Change anything in the scoring path and the test prints
exactly which horses moved, on which dimension, by how much.

It is deliberately confined to the pure, deterministic part of the engine —
features in, ability out.  No scrapers, no data root, no network, so it runs in
under a second and never flakes.

⚠️ WHAT THIS DOES **NOT** COVER — read before treating a green run as proof.
The fixtures are frozen feature vectors lifted out of already-scored Logic
files.  Everything UPSTREAM of `feature_scores` is invisible here:

  * Formguide / Racecard parsing (`_parse_formguide_pf_metrics`, PF tokens,
    margin, in-running positions)
  * anything that changes what a leaf CONSUMES rather than how it combines
  * **the overlays.** `ability` here is `60 + (core-60)/MATRIX_ABILITY_SCALE`
    — the pure matrix score. The real engine's 綜合戰力分 is
    `pure_7d + wet_form_feature + proven_class_feature`. Both overlays are
    OUTSIDE this file. 2026-08-31: `WET_FORM_PRIOR` was corrected 0.5 → 0.3758
    (the measured pooled wet place rate); 43.7% of runners' overlay moved and
    this file still said "120 匹馬全部一致".
    Coverage lives in `au_wong_choi_auto/tests/test_confidence_radar.py`
    (`WetOverlayGoingSpecificTests`).

2026-08-31 worked example: `pace_figure_score` was changed to individualise a
race-level L600 with the runner's own beaten margin.  Live scoring moved on
half the field, and this file still reported "120 匹馬全部一致" — because the
frozen Logic fixtures carry no `margin`, so the new code path never ran.
Coverage for that layer lives in
`au_wong_choi_auto/tests/test_pace_figure_individualised.py`.

Rule of thumb: green here means "the combination maths did not move".  It does
NOT mean "scoring did not move".

Usage
-----
    python golden_scoring.py --platform au --record    # after an INTENDED change
    python golden_scoring.py --platform au             # verify

One platform per process: AU and HKJC both ship a top-level `scoring` module.
"""
from __future__ import annotations

import argparse
import glob
import importlib
import json
import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]

PLATFORMS = {
    "au": {
        "engine": REPO_ROOT / ".agents/skills/au_racing/au_wong_choi_auto/scripts/au_racing_engine",
        "golden": REPO_ROOT / ".agents/skills/au_racing/au_wong_choi_auto/tests/golden/scoring_golden.json",
        "data_root_attr": "AU_RACING",
    },
    "hkjc": {
        "engine": REPO_ROOT / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts/hkjc_racing_engine",
        "golden": REPO_ROOT / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/tests/golden/scoring_golden.json",
        "data_root_attr": "HK_RACING",
    },
}

SAMPLE_SIZE = 120
SAMPLE_SEED = 20260821          # fixed so re-recording keeps the same horses
TOLERANCE = 0.005               # scores are rounded to 2dp; anything larger is real


def load(platform: str):
    """Import the platform's engine PACKAGE (never its loose modules).

    AU and HKJC used to both expose a top-level `scoring`; importing by bare
    name silently gave whichever landed on sys.path first.  Going through the
    uniquely-named package makes that impossible.
    """
    engine = PLATFORMS[platform]["engine"]
    sys.path.insert(0, str(engine.parent))
    package = engine.name
    scoring = importlib.import_module(f"{package}.scoring")
    matrix_mapper = importlib.import_module(f"{package}.matrix_mapper")
    return scoring, matrix_mapper


def score_one(scoring, matrix_mapper, features: dict) -> dict:
    matrix = matrix_mapper.map_features_to_matrix_scores(features)
    weights = scoring.MATRIX_WEIGHTS
    core = sum(float(matrix.get(k, 60.0)) * w for k, w in weights.items())
    # AU 2026-08-26 起 ability 軸多咗一個 `MATRIX_ABILITY_SCALE` 除法（抵銷
    # pace_perf gain 修正之後嘅權重歸一，見 au_racing_engine/scoring.py）。
    # HKJC 冇呢個常數，所以 getattr 預設 1.0 —— 兩個平台行同一段 code。
    # ⚠️ ability 呢條式喺 repo 入面有幾份複本（engine_core、au_eval、
    # au_matrix_refit、呢度）。改其中一份就要四份一齊改，否則 golden 同 A/B
    # 會靜靜同真引擎分岔。
    ability = 60.0 + (core - 60.0) / float(getattr(scoring, "MATRIX_ABILITY_SCALE", 1.0))
    return {
        "matrix": {k: round(float(v), 4) for k, v in sorted(matrix.items())},
        "ability": round(ability, 4),
        "grade": scoring.compute_grade(ability),
    }


def collect_samples(platform: str) -> list[dict]:
    """Pull real feature vectors out of the scored corpus."""
    sys.path.insert(0, str(REPO_ROOT))
    import wongchoi_paths
    root = getattr(wongchoi_paths, PLATFORMS[platform]["data_root_attr"])
    # Include archived meetings — see corpus_paths for why one level is not enough.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from corpus_paths import logic_files as corpus_logic_files
    paths = corpus_logic_files(root)

    rows = []
    for path in paths:
        if len(rows) >= SAMPLE_SIZE * 8:
            break
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception:
            continue
        meeting = Path(path).parent.name
        race = Path(path).stem
        for number, horse in (data.get("horses") or {}).items():
            features = horse.get("python_auto", {}).get("feature_scores") or {}
            if not features:
                continue
            rows.append({
                "id": f"{meeting}/{race}/#{number}",
                "features": {k: round(float(v), 4) for k, v in sorted(features.items())
                             if isinstance(v, (int, float))},
            })
    random.Random(SAMPLE_SEED).shuffle(rows)
    return rows[:SAMPLE_SIZE]


def record(platform: str) -> int:
    scoring, matrix_mapper = load(platform)
    samples = collect_samples(platform)
    if len(samples) < 20:
        print(f"只搵到 {len(samples)} 匹馬，唔夠做基準", file=sys.stderr)
        return 2
    cases = [{**row, "expected": score_one(scoring, matrix_mapper, row["features"])} for row in samples]
    golden = {
        "platform": platform,
        "note": "由真實已評分賽事抽樣。改動評分邏輯之後，先確認下面嘅變化係你想要嘅，"
                "再跑 --record 更新呢個檔。",
        "sample_size": len(cases),
        "cases": cases,
    }
    path = PLATFORMS[platform]["golden"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(golden, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"記錄咗 {len(cases)} 匹馬 → {path}")
    return 0


def verify(platform: str, quiet: bool = False) -> tuple[int, list[str]]:
    path = PLATFORMS[platform]["golden"]
    if not path.exists():
        return 2, [f"未有基準檔：{path}（先跑 --record）"]
    golden = json.loads(path.read_text(encoding="utf-8"))
    scoring, matrix_mapper = load(platform)

    problems = []
    moved_horses = 0
    per_dimension = {}
    for case in golden["cases"]:
        actual = score_one(scoring, matrix_mapper, case["features"])
        expected = case["expected"]
        deltas = []
        for key, want in expected["matrix"].items():
            got = actual["matrix"].get(key)
            if got is None:
                deltas.append(f"{key}: 維度消失")
                per_dimension[key] = per_dimension.get(key, 0) + 1
            elif abs(got - want) > TOLERANCE:
                deltas.append(f"{key} {want:.2f}→{got:.2f} ({got - want:+.2f})")
                per_dimension[key] = per_dimension.get(key, 0) + 1
        for key in set(actual["matrix"]) - set(expected["matrix"]):
            deltas.append(f"{key}: 新維度")
            per_dimension[key] = per_dimension.get(key, 0) + 1
        if abs(actual["ability"] - expected["ability"]) > TOLERANCE:
            deltas.append(f"綜合戰力分 {expected['ability']:.2f}→{actual['ability']:.2f} "
                          f"({actual['ability'] - expected['ability']:+.2f})")
        if actual["grade"] != expected["grade"]:
            deltas.append(f"Grade {expected['grade']}→{actual['grade']}")
        if deltas:
            moved_horses += 1
            if len(problems) < 12:
                problems.append(f"{case['id']}\n      " + "\n      ".join(deltas))

    if not moved_horses:
        if not quiet:
            print(f"✅ {platform.upper()} 評分golden：{len(golden['cases'])} 匹馬全部一致")
        return 0, []

    summary = [
        f"{moved_horses}/{len(golden['cases'])} 匹馬嘅分數變咗。",
        "受影響維度：" + "、".join(f"{k}×{v}" for k, v in sorted(per_dimension.items(), key=lambda x: -x[1])),
        "",
    ]
    summary.extend(f"  • {p}" for p in problems)
    if moved_horses > 12:
        summary.append(f"  …仲有 {moved_horses - 12} 匹馬冇列出")
    summary += [
        "",
        "如果呢個變化係你想要嘅，跑：",
        f"  python3 .agents/skills/shared_racing/scripts/golden_scoring.py --platform {platform} --record",
    ]
    return 1, summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--platform", required=True, choices=sorted(PLATFORMS))
    parser.add_argument("--record", action="store_true")
    args = parser.parse_args(argv)

    if args.record:
        return record(args.platform)
    status, messages = verify(args.platform)
    if messages:
        print(f"\n❌ {args.platform.upper()} 評分 golden 唔一致\n")
        print("\n".join(messages))
        print()
    return status


if __name__ == "__main__":
    raise SystemExit(main())
