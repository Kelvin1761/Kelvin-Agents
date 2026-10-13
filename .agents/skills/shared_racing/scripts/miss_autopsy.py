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
                   觸發咗、涉事馬匹證據薄（AU ≥4 個 leaf fallback／missing；
                   HKJC ≥3 個缺數記號）、上名馬冇評分、賽果有行被丟走
    crowded        輸入正常，但頭幾名分數擠埋一齊（confidence_tier == tight 或
                   top_pick_tied）—— 本身就難估
    model_wrong    輸入正常、分差清楚，模型都判錯

規則同門檻係**預先寫死**嘅，全部取自 engine 現有常數或者只用賽前輸入量出嚟嘅
基準觸發率（2026-09-2x～10-0x 760 場：每條 ≤10%），**冇用過賽果去調**。

HKJC：Logic 冇 `confidence_tier`，所以 `crowded` 由 verdict ranking 嘅 `rank_score`
（HKJC 排序用嘅分數，唔係顯示用嘅 `ability_score`）自己計，門檻見 `DERIVED_CROWD`。
唔可以搬 AU 嘅 2.0／0.5：HKJC 綜合分被壓窄，頭三名分差中位數得 2.56。
HKJC 亦冇 `feature_evidence_state`，所以「證據薄」改數來源同風險旗（見 `HKJC_THIN`）；
冇 `pace_figure_coverage`／證據厚度安全欄，嗰兩條觸發只限 AU。

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

# HKJC 冇 `feature_evidence_state`，改數結構化「冇數據」記號：
#   score_provenance 係 missing_neutral／career_tag 嘅 leaf（唔計 track_going_score ——
#   佢 100% 係 missing_neutral／policy_neutral，屬政策中性），加風險旗
#   debut_race_experience_unknown／medical_record_unknown。
# 4,645 匹賽前基準（2025-09 起）：≥2 = 14.1%、≥3 = 5.7%（對齊 AU ≥4 嘅 ~6%）、≥4 = 0.2%。
# ≥3 嘅組成：初出馬 150 匹（班次＋路程 career_tag＋初出旗），冇近績／路程數據兼
# 醫療紀錄不明 115 匹 —— 兩類都真係證據薄。量度只用咗賽前輸入。
HKJC_THIN = {
    "missing_provenance": frozenset({"missing_neutral", "career_tag"}),
    "policy_leaves": frozenset({"track_going_score"}),
    "flags": frozenset({"debut_race_experience_unknown", "medical_record_unknown"}),
    "min": 3,
}

# 冇 `confidence_tier` 嘅平台，由 ranking 分數自己計「擠迫」。
# 門檻 = 令觸發率對齊 AU 嘅 quantile，只用賽前分數分佈量，冇用賽果：
#   AU 2026-08-05 起 2,797 場：tight（頭三差 <2.0）9.2%、tied（頭兩差 <0.5）11.1%。
#   HKJC 2025-09 起 371 場（rank_score）：9.2% 分位 0.97、11.1% 分位 0.26；
#   前後兩半時間分別係 0.99／0.87 同 0.24／0.26。取 1.0／0.25 → 實際 10.5%／10.8%。
DERIVED_CROWD = {
    "hkjc": {"score": "rank_score", "tight": 1.0, "tied": 0.25},
}

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
    "thin_evidence_horse": "涉事馬匹證據薄",
    "unscored_placegetter": "上名馬冇評分",
    "dropped_result_rows": "賽果有行被丟走",
    "short_result": "賽果唔夠三名",
    "tight": "頭三名分差細（AU < 2／HKJC < 1）",
    "tied": "頭兩名分差細（AU < 0.5／HKJC < 0.25）",
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


def _thin_markers(python_auto: dict, platform: str = "au") -> tuple[list[str], int]:
    """→ (冇證據記號, 門檻)。AU 用 evidence state；HKJC 用來源同風險旗。"""
    if platform == "hkjc":
        cfg = HKJC_THIN
        marks = sorted(f"{leaf}:{source}" for leaf, source in (python_auto.get("score_provenance") or {}).items()
                       if source in cfg["missing_provenance"] and leaf not in cfg["policy_leaves"])
        marks += sorted(flag for flag in python_auto.get("risk_flags") or [] if flag in cfg["flags"])
        return marks, cfg["min"]
    return _weak_leaves(python_auto), THIN_HORSE_WEAK_LEAVES


def _weak_leaves(python_auto: dict) -> list[str]:
    return sorted(k for k, v in (python_auto.get("feature_evidence_state") or {}).items() if v in WEAK_STATES)


def _active_predictions(prediction_list: list[dict], scratched: set[int]) -> list[dict]:
    """同 core.build_race_performances 一樣：剔走退出馬再排過。"""
    rows = [dict(row) for row in prediction_list if row["horse_no"] not in scratched]
    for index, row in enumerate(rows, start=1):
        row["derived_rank"] = index
    return rows


def crowd_context(verdict: dict, platform: str = "au") -> dict:
    """→ {tier, tied, top1_top3_gap, top1_top2_gap}。

    AU 直接用 renderer 寫好嘅 `confidence_tier`／`top_pick_tied`。其他平台冇呢兩欄，
    就由 ranking 分數按 `DERIVED_CROWD` 計；分數唔齊就當「唔知」（唔會判擠迫）。
    """
    if "confidence_tier" in verdict or platform not in DERIVED_CROWD:
        return {"tier": verdict.get("confidence_tier"), "tied": bool(verdict.get("top_pick_tied")),
                "top1_top3_gap": verdict.get("top1_top3_gap"), "top1_top2_gap": verdict.get("top1_top2_gap")}
    cfg = DERIVED_CROWD[platform]
    scores = [row.get(cfg["score"]) for row in verdict.get("ranking") or []]
    if len(scores) < 3 or any(not isinstance(v, (int, float)) for v in scores[:3]):
        return {"tier": None, "tied": False, "top1_top3_gap": None, "top1_top2_gap": None}
    gap3 = round(scores[0] - scores[2], 4)
    gap2 = round(scores[0] - scores[1], 4)
    return {"tier": "tight" if gap3 < cfg["tight"] else "derived", "tied": gap2 < cfg["tied"],
            "top1_top3_gap": gap3, "top1_top2_gap": gap2}


def classify_race(race_num: int, logic: dict, predictions: list[dict], actual_rows: list[dict],
                  *, health_issues: list | None = None, dropped_rows: int = 0,
                  platform: str = "au") -> dict:
    """一場失手嘅體檢。純函數：所有輸入由 caller 提供，方便測試。"""
    verdict = logic.get("python_auto_verdict") or {}
    context = crowd_context(verdict, platform)
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
        weak, minimum = _thin_markers((horses.get(str(horse_no)) or {}).get("python_auto") or {}, platform)
        if len(weak) >= minimum:
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
    if context["tier"] == "tight":
        crowd.append({"rule": "tight", "value": context["top1_top3_gap"]})
    if context["tied"]:
        crowd.append({"rule": "tied", "value": context["top1_top2_gap"]})

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
        "confidence_tier": context["tier"],
        "top1_top3_gap": context["top1_top3_gap"],
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
            platform=platform,
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
