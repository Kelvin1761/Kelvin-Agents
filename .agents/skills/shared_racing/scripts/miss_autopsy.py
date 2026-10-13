#!/usr/bin/env python3
"""失手場自動體檢 —— 每場失手，先問「啲輸入有冇問題」。

點解要有呢個
------------
呢個 repo 最貴嘅 bug 全部係「數據靜靜錯」，冇一個係「公式唔夠聰明」。今日
（2026-10-13）`Finished -3/7` 被 regex 丟走，就係由一場失手追返出嚟。但之前
每次都係人手追。

反過嚟，「由失手場搵規律再改權重」已經試過好多次，次次過唔到 holdout：
EXP-20260905-02（全 miss 場日，九個特徵冇一個企得住）、EXP-20261013-01
（失手共識搬去下一段 dev，Gold −2.49／−4.12pp）。

所以呢個工具**只做分類，唔做建議**：

    input_anomaly  輸入有問題：Data_Health 有 issue、PF 覆蓋警報、證據厚度安全欄
                   觸發咗、涉事馬匹 ≥4 個 leaf fallback／missing、上名馬冇評分、
                   賽果有行被丟走
    crowded        輸入正常，但頭幾名分數擠埋一齊（confidence_tier == tight 或
                   top_pick_tied）—— 本身就難估
    model_wrong    輸入正常、分差清楚，模型都判錯

規則同門檻係**預先寫死**嘅，全部取自 engine 現有常數或者只用賽前輸入量出嚟嘅
基準觸發率（2026-09-2x～10-0x 760 場：每條 ≤10%），**冇用過賽果去調**。

HKJC 限制：HKJC Logic 冇 `feature_evidence_state`、`confidence_tier`、
`pace_figure_coverage`，所以 HKJC 暫時只有 Data_Health／上名馬冇評分／賽果
三類觸發，`crowded` 永遠唔會出。唔好將 AU 嘅分差門檻（2.0／0.5）搬過去 ——
HKJC 綜合分係另一把尺。

⚠️ 硬規矩：呢度嘅輸出只做診斷。**唔准**用嚟擇參、調權重、或者揀 leaf。
（AGENTS.md「唔准只針對最近一日／一個場次去調」。）

Usage
-----
    python miss_autopsy.py --platform au --meeting <dir>
    python miss_autopsy.py --platform au --meeting <dir> --write --append-report
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "race_reflector" / "scripts"))
import unified_reflector_core as core  # noqa: E402

BUCKETS = ("input_anomaly", "crowded", "model_wrong")
SUCCESS_LABELS = frozenset({"Gold", "Good"})
WEAK_STATES = frozenset({"fallback", "missing"})
CROWD_RULES = frozenset({"tight", "tied"})

# 一匹馬 ≥4 個 leaf 係 fallback／missing 先當「證據薄」。
# 760 場賽前基準：≥2 有 28% 馬匹觸發（太鬆，例如 rating_score fallback 好常見），
# ≥4 只有約 6%（大部分係初出馬）。量度只用咗賽前輸入。
THIN_HORSE_WEAK_LEAVES = 4

LEDGER_NAMES = {"au": "AU_Miss_Autopsy.jsonl", "hkjc": "HKJC_Miss_Autopsy.jsonl"}
REPORT_BEGIN = "<!-- miss-autopsy:begin -->"
REPORT_END = "<!-- miss-autopsy:end -->"

BUCKET_LABELS = {
    "input_anomaly": "輸入有問題",
    "crowded": "分數擠迫，本身難估",
    "model_wrong": "輸入正常，模型判錯",
}
TRIGGER_LABELS = {
    "data_health_issue": "Data_Health 有 issue",
    "pace_figure_alert": "PF 覆蓋警報",
    "thin_evidence_swap": "證據厚度安全欄觸發",
    "thin_evidence_horse": f"涉事馬匹 ≥{THIN_HORSE_WEAK_LEAVES} 個 leaf 冇證據",
    "unscored_placegetter": "上名馬冇評分",
    "dropped_result_rows": "賽果有行被丟走",
    "short_result": "賽果唔夠三名",
    "tight": "頭三名分差 < 2",
    "tied": "頭兩名分差 < 0.5",
}


def _load_json(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _logic(meeting_dir: Path, race_num: int) -> dict:
    return _load_json(meeting_dir / f"Race_{race_num}_Logic.json")


def _data_health_issues(meeting_dir: Path) -> dict[int, list]:
    payload = _load_json(meeting_dir / "Data_Health.json")
    issues = {}
    for race in payload.get("races") or []:
        try:
            issues[int(race.get("race"))] = list(race.get("issues") or [])
        except (TypeError, ValueError):
            continue
    return issues


def _dropped_result_rows(results_file: Path | None) -> dict[int, int]:
    """AU JSON 賽果入面，冇退出但名次 ≤0 嘅行。core 嘅 loader 會靜靜丟走佢哋。"""
    if not results_file or Path(results_file).suffix.lower() != ".json":
        return {}
    data = _load_json(results_file)
    dropped: dict[int, int] = {}
    for race_key, rows in (data.get("results") or {}).items():
        try:
            race_num = int(race_key)
        except (TypeError, ValueError):
            continue
        count = 0
        for row in rows or []:
            if row.get("is_scratched"):
                continue
            try:
                placing = int(row.get("finish_position") or 99)
            except (TypeError, ValueError):
                continue
            if placing <= 0:
                count += 1
        if count:
            dropped[race_num] = count
    return dropped


def _weak_leaves(python_auto: dict) -> list[str]:
    return sorted(k for k, v in (python_auto.get("feature_evidence_state") or {}).items() if v in WEAK_STATES)


def _active_predictions(prediction_list: list[dict], scratched: set[int]) -> list[dict]:
    """同 core.build_race_performances 一樣：剔走退出馬再排過。"""
    rows = [dict(row) for row in prediction_list if row["horse_no"] not in scratched]
    for index, row in enumerate(rows, start=1):
        row["derived_rank"] = index
    return rows


def classify_race(race_num: int, logic: dict, predictions: list[dict], actual_rows: list[dict],
                  *, health_issues: list | None = None, dropped_rows: int = 0) -> dict:
    """一場失手嘅體檢。純函數：所有輸入由 caller 提供，方便測試。"""
    verdict = logic.get("python_auto_verdict") or {}
    horses = logic.get("horses") or {}
    model_top2 = [row["horse_no"] for row in predictions[:2]]
    actual_top3 = [row["horse_no"] for row in actual_rows[:3]]
    rank_of = {row["horse_no"]: row.get("derived_rank") for row in predictions}

    triggers: list[dict] = []
    if health_issues:
        triggers.append({"rule": "data_health_issue", "value": health_issues[:5]})
    pf = verdict.get("pace_figure_coverage") or {}
    if pf.get("alert"):
        triggers.append({"rule": "pace_figure_alert", "value": pf.get("pct")})
    swap = (verdict.get("decision_trace") or {}).get("thin_evidence_swap")
    if swap:
        triggers.append({"rule": "thin_evidence_swap", "value": swap})
    thin = {}
    for horse_no in dict.fromkeys(model_top2 + actual_top3):
        weak = _weak_leaves((horses.get(str(horse_no)) or {}).get("python_auto") or {})
        if len(weak) >= THIN_HORSE_WEAK_LEAVES:
            thin[str(horse_no)] = weak
    if thin:
        triggers.append({"rule": "thin_evidence_horse", "value": thin})
    unscored = [h for h in actual_top3 if h not in rank_of]
    if unscored:
        triggers.append({"rule": "unscored_placegetter", "value": unscored})
    if dropped_rows:
        triggers.append({"rule": "dropped_result_rows", "value": dropped_rows})
    if len(actual_rows) < 3:
        triggers.append({"rule": "short_result", "value": len(actual_rows)})

    crowd = []
    if verdict.get("confidence_tier") == "tight":
        crowd.append({"rule": "tight", "value": verdict.get("top1_top3_gap")})
    if verdict.get("top_pick_tied"):
        crowd.append({"rule": "tied", "value": verdict.get("top1_top2_gap")})

    if triggers:
        bucket = "input_anomaly"
    elif crowd:
        bucket = "crowded"
    else:
        bucket = "model_wrong"
    return {
        "race": race_num,
        "bucket": bucket,
        "triggers": triggers + crowd,
        "confidence_tier": verdict.get("confidence_tier"),
        "top1_top3_gap": verdict.get("top1_top3_gap"),
        "model_top2": model_top2,
        "actual_top3": actual_top3,
        "actual_top3_model_ranks": [rank_of.get(h) for h in actual_top3],
    }


def autopsy_meeting(platform: str, meeting_dir: Path) -> dict:
    meeting_dir = Path(meeting_dir)
    results_file = core.find_existing_results_file(platform, meeting_dir)
    base = {"platform": platform, "meeting": meeting_dir.name,
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    if not results_file:
        return {**base, "status": "no_results", "races": [], "summary": {}}
    # 同 reflector 一樣評「開跑之前」嗰個版本。meeting 目錄嘅 CSV／Logic 可能係
    # 開跑後重評（2026-10-07 跑馬地 21:05 HKT 重評，第一場 18:35）。
    snapshot, _created, _post = core.select_prerace_snapshot(meeting_dir, platform)
    analysis_dir = snapshot or meeting_dir
    base["evaluated"] = str(analysis_dir.relative_to(meeting_dir)) if snapshot else "meeting_dir（搵唔到賽前快照）"
    results = core.load_structured_results(platform, Path(results_file))
    predictions = core.load_prediction_rows(analysis_dir, platform)
    health = _data_health_issues(analysis_dir if (analysis_dir / "Data_Health.json").exists() else meeting_dir)
    dropped = _dropped_result_rows(Path(results_file))

    races, labels = [], Counter()
    for race_num in sorted(results):
        actual_rows = results[race_num].get("results") or []
        prediction_list = predictions.get(race_num) or []
        if not actual_rows or not prediction_list:
            continue
        scratched = set(results[race_num].get("scratched_horse_numbers") or [])
        active = _active_predictions(prediction_list, scratched)
        label = core.performance_label_from_rows(active[:4], actual_rows[:3])
        labels[label] += 1
        if label in SUCCESS_LABELS:
            continue
        entry = classify_race(
            race_num, _logic(analysis_dir, race_num), active, actual_rows,
            health_issues=health.get(race_num), dropped_rows=dropped.get(race_num, 0),
        )
        entry["label"] = label
        races.append(entry)

    buckets = Counter(r["bucket"] for r in races)
    rules = Counter(t["rule"] for r in races if r["bucket"] == "input_anomaly"
                    for t in r["triggers"] if t["rule"] not in CROWD_RULES)
    return {
        **base, "status": "ok", "races": races,
        "summary": {
            "scored_races": sum(labels.values()),
            "labels": dict(labels),
            "misses": len(races),
            "buckets": {b: buckets.get(b, 0) for b in BUCKETS},
            "input_rules": dict(rules.most_common()),
        },
    }


# ── 輸出 ──────────────────────────────────────────────────────────────────────

def render_markdown(result: dict) -> str:
    summary = result.get("summary") or {}
    lines = [REPORT_BEGIN, "", "## 失手體檢（只做診斷，唔准用嚟調權重）", ""]
    if result.get("status") != "ok":
        lines += ["未有賽果，跳過。", "", REPORT_END]
        return "\n".join(lines)
    buckets = summary.get("buckets") or {}
    lines += [f"評估版本：{result.get('evaluated', '?')}", ""]
    lines.append(f"{summary.get('scored_races', 0)} 場入面 {summary.get('misses', 0)} 場唔係 Gold／Good："
                 + "、".join(f"{BUCKET_LABELS[b]} {buckets.get(b, 0)}" for b in BUCKETS))
    lines.append("")
    if result.get("races"):
        lines += ["| 場 | 標籤 | 分類 | 觸發 | 實際頭三嘅模型排名 |", "|---:|---|---|---|---|"]
        for race in result["races"]:
            rules = "、".join(TRIGGER_LABELS.get(t["rule"], t["rule"]) for t in race["triggers"]) or "—"
            ranks = "／".join("?" if r is None else str(r) for r in race["actual_top3_model_ranks"])
            lines.append(f"| {race['race']} | {race['label']} | {BUCKET_LABELS[race['bucket']]} | {rules} | {ranks} |")
        lines.append("")
    lines.append(REPORT_END)
    return "\n".join(lines)


def append_report(report_path: Path, block: str) -> bool:
    if not report_path.exists():
        return False
    text = report_path.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(REPORT_BEGIN) + r".*?" + re.escape(REPORT_END), re.S)
    text = pattern.sub(lambda _m: block, text) if pattern.search(text) else text.rstrip() + "\n\n" + block + "\n"
    report_path.write_text(text, encoding="utf-8")
    return True


def write_ledger(path: Path, result: dict) -> None:
    """(meeting, race) 做 key；重跑同一個場次會覆蓋，唔會重複。"""
    path = Path(path)
    keep = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("meeting") != result["meeting"]:
                keep.append(row)
    match = re.search(r"(\d{4}-\d{2}-\d{2})", result["meeting"])
    date = match.group(1) if match else None
    week = None
    if date:
        year, num, _ = dt.date.fromisoformat(date).isocalendar()
        week = f"{year}-W{num:02d}"
    new_rows = [{
        "meeting": result["meeting"], "date": date, "week": week, "kind": "summary",
        **(result.get("summary") or {}),
    }]
    for race in result.get("races") or []:
        new_rows.append({"meeting": result["meeting"], "date": date, "week": week, "kind": "race",
                         "race": race["race"], "label": race["label"], "bucket": race["bucket"],
                         "rules": [t["rule"] for t in race["triggers"]]})
    rows = keep + new_rows
    rows.sort(key=lambda r: (r.get("date") or "", r.get("meeting") or "", r.get("kind") != "summary", r.get("race") or 0))
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    os.replace(tmp, path)


def ledger_path(platform: str) -> Path | None:
    root = {"au": core.AU_RACING, "hkjc": core.HK_RACING}.get(platform)
    return Path(root) / LEDGER_NAMES[platform] if root else None


def run(platform: str, meeting_dir: Path, *, write: bool = False, append: bool = False,
        ledger: Path | None = None) -> dict:
    result = autopsy_meeting(platform, meeting_dir)
    if write and result.get("status") == "ok":
        (Path(meeting_dir) / "Miss_Autopsy.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        target = ledger or ledger_path(platform)
        if target:
            write_ledger(target, result)
    if append:
        append_report(core.default_report_path(platform, Path(meeting_dir)), render_markdown(result))
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--platform", required=True, choices=sorted(LEDGER_NAMES))
    parser.add_argument("--meeting", required=True, type=Path)
    parser.add_argument("--write", action="store_true", help="寫 Miss_Autopsy.json 同 ledger")
    parser.add_argument("--append-report", action="store_true", help="喺 Reflector report 尾加／更新一節")
    parser.add_argument("--ledger", type=Path, help="覆寫 ledger 路徑（測試用）")
    args = parser.parse_args(argv)
    result = run(args.platform, args.meeting, write=args.write, append=args.append_report, ledger=args.ledger)
    print(render_markdown(result).replace(REPORT_BEGIN, "").replace(REPORT_END, "").strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
