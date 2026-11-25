#!/usr/bin/env python3
"""預先登記 forward（shadow）測試 EXP-20261125-11：H1 試閘＋備戰分份量太細（EXP-20261125-06）。

候選（2026-11-25 凍結，之後**永遠唔再 fit**）：
    候選 ability = live ability + w_trial·z(trial_score) + w_prep·z(preparation_score)
    z = 場內標準化（(x − 場均) / 場內母體 SD；SD < 1e-9 → 0）
    w 嚟自 `docs/experiments/patches/au_h1_forward/frozen.json`（`fit_frozen.py` 一次過 fit，BASE ≤ 2026-11-25）；
    載入時核對 sha256 = FROZEN_SHA256，唔對就拋錯（即係改過 = 唔准用）。
live 排名完全唔郁：呢度只係讀已發佈嘅賽前快照、喺記憶體入面加 shift。

數據（防洩漏）：每個場次用 `unified_reflector_core.select_prerace_snapshot`（同覆盤／失手體檢／校準機率
`model_probability.py` 同一個揀法：悉尼時間賽日 11:30 前最後一份已發佈快照），讀快照入面嘅
`Race_*_Auto_Scoring.csv` 嘅 `ability_score`、`trial_score`、`preparation_score`；快照經
`wongchoi_paths.prediction_snapshot_dir`。冇賽前快照嘅場次**唔用**（唔會退返去賽後 meeting 目錄）。
賽果（名次、SP）由 `find_existing_results_file` ＋ `load_structured_results`。

判法（合約 m3 追市場軌，預先登記）：
  * 樣本：START_DATE（2026-11-26）起，第一次同時夠 TARGET_DAYS（30）個賽日**同** TARGET_RACES（1,000）場嗰日做 cutoff；
    只計 START_DATE ≤ 日期 ≤ cutoff 嘅場。之前（2026-08-05 起）嘅快照場次只做 walk-forward 校準 warm-up，唔計分。
  * 排名尺：`au_logloss_ruler.evaluate(base, cand, version="v2")`（只計 forward 賽日）。
  * 市場尺：`market_ruler.evaluate(base, cand, price_key="sp", score_window=(START_DATE, cutoff))`。
  * KEEP 候選（追市場軌）= 排名尺 PASS **而且** `paired.gap_change` 點估計 ≤ 0。另報市場尺 A（候選有冇市場以外資訊）。
  * 判一次就凍結（status 檔有 `evaluation` 之後唔再算）。PASS 都唔會自動上線 —— Kelvin 決定。

盲測：未夠數 `status` 只報數量（賽日、場數、快照來源），**冇任何表現指標**；`outcomes_visible=false`。

    python3 au_h1_forward.py status   --output STATUS.json [--data-root AU_RACING]
    python3 au_h1_forward.py evaluate --output STATUS.json [--data-root AU_RACING]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
SKILLS = SCRIPT_DIR.parents[2]
REPO = SKILLS.parents[1]
for _p in (str(SCRIPT_DIR), str(SKILLS / "shared_racing"), str(SKILLS / "shared_racing" / "scripts"), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

EXPERIMENT_ID = "EXP-20261125-11"
SOURCE_EXPERIMENT = "EXP-20261125-06"
START_DATE = "2026-11-26"      # 凍結之後第一個賽日
TARGET_DAYS = 30
TARGET_RACES = 1000
CALIBRATION_SINCE = "2026-08-05"   # = au_logloss_ruler.CLEAN_SINCE
FEATURES = ("trial_score", "preparation_score")
FROZEN_PATH = REPO / "docs" / "experiments" / "patches" / "au_h1_forward" / "frozen.json"
FROZEN_SHA256 = "b497ca53ef7ec786d12386d214d97e3fcf98acac619823ffc535684084380b1c"
SOURCE_TAG = "prerace_snapshot"


class FrozenParamsChanged(RuntimeError):
    """frozen.json 唔係登記嗰份（sha256 唔對）。"""


def load_frozen(path: Path = FROZEN_PATH, expected: str = FROZEN_SHA256) -> dict:
    raw = Path(path).read_bytes()
    got = hashlib.sha256(raw).hexdigest()
    if got != expected:
        raise FrozenParamsChanged(f"{path}: sha256 {got} ≠ 登記 {expected}（凍結參數唔准改／重 fit）")
    frozen = json.loads(raw)
    return {f: float(frozen["weights"][f]) for f in FEATURES}


def race_z(values) -> np.ndarray:
    v = np.asarray(values, float)
    sd = v.std()
    return (v - v.mean()) / sd if sd > 1e-9 else np.zeros_like(v)


def candidate(races: list[dict], weights: dict) -> list[dict]:
    """→ 同次序嘅場次，ability 換成候選；其他欄唔變（市場尺要 name／pos／sp 一樣先配對）。"""
    out = []
    for r in races:
        shift = sum(weights[f] * race_z([x[f] for x in r["rows"]]) for f in FEATURES)
        out.append(dict(r, rows=[dict(x, ability=float(x["ability"] + s)) for x, s in zip(r["rows"], shift)]))
    return out


# ---------------------------------------------------------------- 讀賽前快照 + 賽果

def _core():
    sys.path.insert(0, str(SKILLS / "shared_racing" / "race_reflector" / "scripts"))
    import unified_reflector_core as core  # noqa: E402
    return core


def _float(v):
    try:
        f = float(str(v).replace("$", "").strip())
    except (TypeError, ValueError):
        return None
    return f if np.isfinite(f) else None


def collect_meeting(meeting_dir: Path, core) -> tuple[list[dict], dict]:
    """→ (場次 list, 計數)。計數 keys：source（snapshot／no_snapshot／offline／no_results／excluded）、
    skipped_races（預測唔齊／冇 trial／prep）。只用賽前快照；冇就成個場次唔要。"""
    from live_record_exclusions import is_excluded
    from wongchoi_paths import SnapshotArchiveOffline

    info = {"source": "snapshot", "skipped_races": 0}
    if is_excluded("au", meeting_dir.name):
        return [], dict(info, source="excluded")
    results_file = core.find_existing_results_file("au", meeting_dir)
    if not results_file:
        return [], dict(info, source="no_results")
    try:
        snapshot, created, cutoff = core.select_prerace_snapshot(meeting_dir, "au")
    except SnapshotArchiveOffline:
        return [], dict(info, source="offline")
    if snapshot is None:
        return [], dict(info, source="no_snapshot")   # 唔退返去 meeting 目錄（嗰份可能係賽後重評）
    if created is None or cutoff is None or created >= cutoff:
        return [], dict(info, source="no_snapshot")
    results = core.load_structured_results("au", Path(results_file))
    preds = core.load_prediction_rows(Path(snapshot), "au")
    date_s = meeting_dir.name[:10]
    races = []
    for race_num in sorted(results):
        scratched = set(results[race_num].get("scratched_horse_numbers") or [])
        actual = {r["horse_no"]: r for r in results[race_num].get("results") or []
                  if r.get("horse_no") and r["horse_no"] not in scratched and 0 < int(r.get("placing") or 0) < 90}
        scored = {p["horse_no"]: p for p in preds.get(race_num, []) if p.get("ability_score") is not None}
        rows = []
        for n, p in sorted(scored.items()):
            if n not in actual:
                continue
            fs = p.get("factor_scores") or {}
            if any(fs.get(f) is None for f in FEATURES):
                rows = None
                break
            rows.append({"n": n, "name": p.get("horse_name"), "ability": float(p["ability_score"]),
                         "trial_score": float(fs["trial_score"]), "preparation_score": float(fs["preparation_score"]),
                         "pos": int(actual[n]["placing"]), "sp": _float(actual[n].get("odds"))})
        # 有結果但冇預測／冇 trial、prep 嘅馬 = 預測唔齊，成場唔要（同 model_probability 一樣）
        if not rows or len(rows) < 2 or len(rows) != len(actual):
            info["skipped_races"] += 1
            continue
        races.append({"date": date_s, "meeting": meeting_dir.name, "race": int(race_num), "rows": rows,
                      "source": SOURCE_TAG, "snapshot": Path(snapshot).name,
                      "published_at": created.isoformat()})
    return races, info


def meeting_list(root: Path, since: str, until: str | None = None) -> list[Path]:
    from corpus_paths import meeting_dirs
    return [m for m in meeting_dirs(root) if m.name[:10] >= since and (until is None or m.name[:10] <= until)]


def collect(meetings, core=None) -> tuple[list[dict], dict]:
    core = core or _core()
    races, sources, skipped, offline = [], defaultdict(int), 0, []
    for m in meetings:
        got, info = collect_meeting(Path(m), core)
        sources[info["source"]] += 1
        skipped += info["skipped_races"]
        if info["source"] == "offline":
            offline.append(Path(m).name)
        races.extend(got)
    races = [r for r in races if r.get("source") == SOURCE_TAG]
    return sorted(races, key=lambda r: (r["date"], r["meeting"], r["race"])), \
        {"meetings": dict(sources), "skipped_races": skipped, "offline": offline}


# ---------------------------------------------------------------- 計數（盲）同 cutoff

def _eligible(races):
    import au_logloss_ruler as L
    return L.eligible(races)


def forward_counts(races: list[dict]) -> dict:
    fwd = [r for r in _eligible(races) if r["date"] >= START_DATE]
    by_day = defaultdict(int)
    for r in fwd:
        by_day[r["date"]] += 1
    cutoff, days, total = None, 0, 0
    for d in sorted(by_day):
        days += 1
        total += by_day[d]
        if days >= TARGET_DAYS and total >= TARGET_RACES:
            cutoff = d
            break
    return {"races": len(fwd), "days": len(by_day), "cutoff": cutoff,
            "races_at_cutoff": total if cutoff else None, "days_at_cutoff": days if cutoff else None}


def status(races: list[dict], sources: dict, weights: dict) -> dict:
    """盲：只有數量，冇名次／命中／log-loss。"""
    c = forward_counts(races)
    fwd = [r for r in races if r["date"] >= START_DATE]
    shift = [abs(x["ability"] - y["ability"]) for r, cr in zip(fwd, candidate(fwd, weights))
             for x, y in zip(r["rows"], cr["rows"])]
    ready = c["cutoff"] is not None
    return {"experiment": EXPERIMENT_ID, "source": SOURCE_EXPERIMENT, "start_date": START_DATE,
            "target_races": TARGET_RACES, "target_days": TARGET_DAYS,
            "races_collected": c["races"], "race_days": c["days"], "ready": ready,
            "cutoff_date": c["cutoff"], "frozen_sha256": FROZEN_SHA256, "weights": weights,
            "data_source": "賽前快照 select_prerace_snapshot（悉尼 11:30 前）Race_*_Auto_Scoring.csv",
            "sources": sources,
            "interim": {"mean_abs_shift": float(np.mean(shift)) if shift else None,
                        "note": "盲測：未判之前只報數量（shift 唔睇賽果）"},
            "outcomes_visible": False, "state": "ready" if ready else "collecting",
            "generated_at": datetime.now(timezone.utc).isoformat()}


# ---------------------------------------------------------------- 判決（只做一次）

def evaluate(races: list[dict], weights: dict, *, nnull: int = 200) -> dict:
    """races = 2026-08-05 起所有賽前快照場次（之前嘅只做校準）。→ evaluation dict。"""
    import au_logloss_ruler as L
    import market_ruler as M

    if any(r.get("source") != SOURCE_TAG for r in races):
        raise ValueError("evaluate 只收賽前快照場次")
    c = forward_counts(races)
    if c["cutoff"] is None:
        raise ValueError("未夠數，唔准判")
    cutoff = c["cutoff"]
    base = _eligible([r for r in races if r["date"] <= cutoff])
    cand = candidate(base, weights)

    full = L.calibrations

    def forward_only(rs, version="v1"):
        return {d: v for d, v in full(rs, version).items() if d >= START_DATE}

    L.calibrations = forward_only      # 只計 forward 賽日；之前嘅只做 walk-forward 校準
    try:
        rank = L.evaluate(base, cand, nnull=nnull, version="v2")
    finally:
        L.calibrations = full
    market = M.evaluate(base, cand, price_key="sp", since=CALIBRATION_SINCE, score_window=(START_DATE, cutoff))
    gap = (market.get("paired") or {}).get("gap_change") or {}
    gap_point = gap.get("dll_per_race")
    keep = rank["verdict"] == "PASS" and gap_point is not None and gap_point <= 0
    arm = (market.get("arms") or {}).get("candidate") or {}
    return {"rule": "m3 追市場軌：排名尺 v2 PASS 而且 market_ruler paired.gap_change 點估計 ≤ 0",
            "cutoff_date": cutoff, "forward_races": c["races_at_cutoff"], "forward_days": c["days_at_cutoff"],
            "verdict": "PASS" if keep else "FAIL",
            "ranking_ruler": rank,
            "market_ruler": {"gap_change": gap, "paired_judge": {k: (market.get("paired") or {}).get(k)
                                                                  for k in ("verdict", "checks", "win_positive_blocks")},
                             "candidate_has_info_beyond_market": arm.get("has_info_beyond_market"),
                             "candidate_arm": {k: arm.get(k) for k in ("win", "top3", "gap_to_market")},
                             "common_races": market.get("common_races"), "skipped": market.get("skipped"),
                             "version": market.get("version")},
            "next": "PASS = Kelvin 決定上唔上線（要另一個改動＋model-regression-gate）；FAIL = 記錄，唔准喺同一批數據重試",
            "evaluated_at": datetime.now(timezone.utc).isoformat()}


# ---------------------------------------------------------------- CLI

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["status", "evaluate"])
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--output", required=True)
    args = ap.parse_args(argv)
    from wongchoi_paths import AU_RACING

    root = Path(args.data_root) if args.data_root else Path(AU_RACING)
    out_path = Path(args.output)
    previous = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}
    if previous.get("evaluation"):
        print(f"{EXPERIMENT_ID} forward 已判（凍結）：{previous['evaluation'].get('verdict')}")
        return 0
    weights = load_frozen()
    since = START_DATE if args.command == "status" else CALIBRATION_SINCE
    races, sources = collect(meeting_list(root, since))
    st = status(races, sources, weights)
    if args.command == "evaluate" and st["ready"]:
        offline = sources["offline"]
        if offline:   # 校準或者 forward 場次讀唔到（外置碟冇插）→ 唔判，聽晚再試
            st["state"] = "blocked_offline"
            st["blocked"] = offline[:20]
        else:
            st["evaluation"] = evaluate(races, weights)
            st["outcomes_visible"] = True
            st["state"] = "evaluated"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in st.items() if k != "evaluation"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
