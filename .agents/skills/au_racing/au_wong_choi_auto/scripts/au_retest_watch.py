#!/usr/bin/env python3
"""預先登記嘅重測條件到期冇？

點解要有呢個檔。2026-08-26 有三個候選係「證據方向一致但功效唔夠」——
唔係死咗，係語料未夠厚。每個都喺 `docs/experiments/` 寫死咗重測門檻。
問題係冇人會記得返嚟睇，於是「等數據」實際上等於「永遠唔會再試」。

呢個腳本每次跑都答一條問題：**邊個候選而家夠數重測？**

⚠️ 佢**唔會**自己改模型，亦唔會自己跑 A/B。佢淨係報「夠數喇，去跑邊條命令」。
自動重跑一個會改排名嘅候選 = 冇人睇過 golden diff 就改模型，違反交嘢紀律。

用法：
    python3 au_retest_watch.py            # 人睇
    python3 au_retest_watch.py --json     # 俾 健康.sh / 排程食
    退出碼 0 = 冇嘢到期；10 = 有候選夠數（方便 shell 判斷）
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
import unicodedata
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parents[2] / "shared_racing" / "scripts"))
sys.path.insert(0, str(SCRIPT_DIR.parents[4]))

# ── 預先登記嘅門檻。改呢度 = 改判決條件，要當一個獨立改動論證。────────────
REGISTERED = []

# 已到期並由人手處理嘅登記。留喺 code 入面做 audit trail，但唔再反覆令
# 健康檢查退出 10。詳細證據喺 resolution_exp；呢度唔重寫判決。
RESOLVED = [
    {
        "id": "class_score",
        "exp": "EXP-20260826-06",
        "resolution_exp": "EXP-20260927-01",
        "outcome": "OBSOLETE / NOT SHIPPED",
        "why": "舊候選依賴已退役 display gain，而且登記嘅 scratch harness 從未入 git。",
    },
    {
        "id": "speed_figure",
        "exp": "EXP-20260826-04",
        "resolution_exp": "EXP-20260927-01",
        "outcome": "REJECT / NOT SHIPPED",
        "why": "2,090 場完整賽日重測；terminal Good、winner@3、t3prec 回歸。",
    },
]


def _norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", name or "").lower()
    s = re.sub(r"\([^)]*\)", "", s)
    return re.sub(r"[^a-z0-9]", "", s)


# Contract date eligibility is necessary, not proof of PIT. CSV date matches and
# WinningTime token counts cannot certify captured inputs or label availability.
CLEAN_FROM = "2026-08-05"

# Follow-ups are not executable experimental registrations. Thresholds/families
# must be preregistered after source/PIT validation; do not invent them here.
# Existing speed/class forward profiles retain their own unchanged rules.
PENDING_REGISTRATIONS = [
    {
        "id": "class_label_oos",
        "owner": "AU full-model audit",
        "source": "docs/audits/AU_FULL_MODEL_AUDIT_EXECUTION_PLAN_2026-10-11.md#12-phase-4",
        "status": "PENDING_REGISTRATION",
        "review_after": None,
        "required": ["RA label captured-at", "eligible complete-day corpus",
                     "frozen OOS family and power/forward rules"],
        "why": "November is an old estimate, not a readiness threshold; existing class forward review is separate.",
    },
    {
        "id": "people_asof_oos",
        "owner": "AU full-model audit",
        "source": "docs/experiments/EXP-20260901-02-au-people-database-unlocked.md",
        "status": "PENDING_REGISTRATION",
        "review_after": None,
        "required": ["dated people snapshots", "source availability and coverage",
                     "frozen OOS family and power/forward rules"],
        "why": "Current career/monthly summaries alone do not certify historical availability.",
    },
    {
        "id": "race_shape_start_position",
        "owner": "AU full-model audit",
        "source": "docs/audits/AU_FULL_MODEL_AUDIT_PLAN_ORIGINAL_2026-10-11.md",
        "status": "PENDING_REGISTRATION",
        "review_after": "2026-11-22",
        "required": ["original registration artifact", "speedmap captured-at",
                     "frozen samples, metric and reveal rules"],
        "why": "Original plan mentions this review date; date alone is not authorization to reveal or run.",
    },
]

MEET_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\s+(.+?)\s+Race\s")


def measure(data_root: Path) -> dict:
    from corpus_paths import logic_files

    results: dict[tuple, dict] = {}
    csv_path = data_root / "AU_Historical_Raw_Race_Results.csv"
    if csv_path.exists():
        with open(csv_path, encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                date = row.get("﻿Date") or row.get("Date")
                try:
                    pos = int(str(row["Pos"]).strip())
                except (ValueError, TypeError, KeyError):
                    continue
                key = (date, _norm(row["Track"]), str(int(float(row["Race"]))))
                results.setdefault(key, {})[_norm(row["Horse"])] = pos

    clean = 0
    for path in logic_files(data_root):
        p = Path(path)
        m = MEET_RE.match(p.parent.name)
        rn = re.search(r"Race_(\d+)_Logic", p.name)
        if not (m and rn) or m.group(1) < CLEAN_FROM:
            continue
        if results.get((m.group(1), _norm(m.group(2)), rn.group(1))):
            clean += 1

    # 速度評分覆蓋。⚠️ 要數**逐匹馬**，唔係逐條往績行。
    # 2026-08-26 第一版數錯咗：往績行覆蓋 52.1%，但排名語料嘅**runner** 覆蓋
    # 只有 25–30%（一匹馬要有夠往績行、而且個 track×distance 要夠樣本砌到標準，
    # 先計到速度評分）。用行覆蓋做門檻會提早成年報「夠數」。
    head = re.compile(r"^\[(\d+)\]\s+(.+?)\s*\(\d+\)\s*$", re.M)
    runners = with_time = 0
    for fg in data_root.rglob("*Formguide.md"):
        text = fg.read_text(encoding="utf-8", errors="replace")
        starts = [m.start() for m in head.finditer(text)]
        for index, match in enumerate(head.finditer(text)):
            end = starts[index + 1] if index + 1 < len(starts) else len(text)
            block = text[match.start():end]
            runners += 1
            # 要至少三條先砌到 `speed_fig_best3`
            if block.count("WinningTime:") >= 3:
                with_time += 1
    return {
        "clean_races": None,
        "date_matched_races": clean,
        "fit_date_from": CLEAN_FROM,
        "readiness_status": "NOT_ESTABLISHED",
        "diagnostic_only_metrics": ["date_matched_races", "speedfig_coverage_pct"],
        "readiness_limits": [
            "Date/race matches do not prove complete rosters or PIT.",
            "WinningTime tokens are not computed speed-score coverage or source availability.",
            "An independently verified eligible corpus is required before readiness.",
        ],
        "speedfig_coverage_pct": (round(100.0 * with_time / runners, 1)
                                  if runners else 0.0),
        "_runners": runners,
    }


def partition_retests(stats: dict, registered: list[dict]) -> tuple[list, list]:
    """Fail closed on diagnostics, missing metrics or unestablished eligibility."""
    due, waiting = [], []
    for item in registered:
        metric = item["metric"]
        now = stats.get(metric)
        threshold = item["threshold"]
        valid_now = (isinstance(now, (int, float)) and not isinstance(now, bool)
                     and math.isfinite(now))
        valid_threshold = (isinstance(threshold, (int, float))
                           and not isinstance(threshold, bool)
                           and math.isfinite(threshold) and threshold > 0)
        blockers = []
        if stats.get("readiness_status") != "VERIFIED":
            blockers.append("eligible_corpus_not_verified")
        if metric in stats.get("diagnostic_only_metrics", []):
            blockers.append("diagnostic_metric_not_readiness")
        if not valid_now:
            blockers.append("metric_missing_or_invalid")
        if not valid_threshold:
            blockers.append("threshold_missing_or_invalid")
        row = {**item, "now": now,
               "pct": round(100.0 * now / threshold, 1)
               if valid_now and valid_threshold else None,
               "readiness_blockers": blockers}
        (due if not blockers and now >= threshold else waiting).append(row)
    return due, waiting


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-root", type=Path)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    root = args.data_root
    if root is None:
        import wongchoi_paths
        root = Path(wongchoi_paths.AU_RACING)

    stats = measure(root)
    due, waiting = partition_retests(stats, REGISTERED)

    if args.json:
        print(json.dumps({"stats": stats, "due": due, "waiting": waiting,
                          "resolved": RESOLVED,
                          "pending_registrations": PENDING_REGISTRATIONS},
                         ensure_ascii=False, indent=2))
    else:
        print(f"日期／場號匹配（{CLEAN_FROM} 起，未核證 PIT）: {stats['date_matched_races']}")
        print("乾淨 PIT 場次：未建立，不能由日期匹配推定。")
        print(f"WinningTime token runner 覆蓋（≥3 條；非速度評分／PIT 覆蓋）: {stats['speedfig_coverage_pct']}%"
              f"  （{stats['_runners']} 匹）\n")
        for row in due:
            print(f"✅ 夠數重測：{row['id']}（{row['exp']}）")
            print(f"   {row['what']}")
            print(f"   {row['metric']} = {row['now']} ≥ {row['threshold']}")
            print(f"   跑：{row['cmd']}\n")
        for row in waiting:
            print(f"⏳ 未夠：{row['id']}（{row['exp']}）"
                  f" {row['metric']} {row['now']} / {row['threshold']}（{row['pct']}%）")
            print(f"   {row['why']}")
            if row["readiness_blockers"]:
                print(f"   阻止就緒：{', '.join(row['readiness_blockers'])}")
        for row in PENDING_REGISTRATIONS:
            print(f"待完成預登記：{row['id']} — {row['why']}")
        if not due:
            print("\n冇候選到期。")
    return 10 if due else 0


if __name__ == "__main__":
    raise SystemExit(main())
