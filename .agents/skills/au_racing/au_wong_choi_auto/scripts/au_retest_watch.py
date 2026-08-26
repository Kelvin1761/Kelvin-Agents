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
import re
import sys
import unicodedata
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parents[2] / "shared_racing" / "scripts"))
sys.path.insert(0, str(SCRIPT_DIR.parents[4]))

# ── 預先登記嘅門檻。改呢度 = 改判決條件，要當一個獨立改動論證。────────────
REGISTERED = [
    {
        "id": "class_score",
        "exp": "EXP-20260826-06",
        "what": "class_score 加返 class_weight 維度（rating .70 + class .60）",
        "metric": "clean_races",
        "threshold": 2000,
        "why": "七個獨立測試 dev 全部正（+0.0023~+0.0030），但 holdout 227 場跨 0。",
        "cmd": "python3 scratchpad/class_revival.py v2_pf   # gain 喺 dev 重 fit",
    },
    {
        "id": "speed_figure",
        "exp": "EXP-20260826-04",
        "what": "WinningTime 速度評分（speed_fig_best3）",
        "metric": "speedfig_coverage_pct",
        "threshold": 45.0,
        "why": "過 dev 5-fold 閘，但主裁判九個配置全部跨 0；runner 覆蓋只有 25–30%。",
        "cmd": "AU_SPEED_STD_ROOT=<data root> python3 au_feature_ab.py "
               "--scored <data root> --features speed_fig_best3 --min-depth 0",
    },
]


def _norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", name or "").lower()
    s = re.sub(r"\([^)]*\)", "", s)
    return re.sub(r"[^a-z0-9]", "", s)


# 乾淨 point-in-time 起點。2026-06-06 之前嘅歸檔係**賽後**先重新評分嘅
# （見 memory `au-archive-rescored-post-race`），leaf 值反映咗較後狀態，
# 所以唔可以攞嚟 fit 任何常數。呢個唔係保守 —— 2026-08-26 實測過，
# 用全語料 fit gain 會令 class_score 出現一個假嘅「過閘」。
CLEAN_FROM = "2026-06-06"
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
        "clean_races": clean,
        "speedfig_coverage_pct": (round(100.0 * with_time / runners, 1)
                                  if runners else 0.0),
        "_runners": runners,
    }


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
    due, waiting = [], []
    for item in REGISTERED:
        now = stats.get(item["metric"], 0)
        row = {**item, "now": now, "pct": round(100.0 * now / item["threshold"], 1)}
        (due if now >= item["threshold"] else waiting).append(row)

    if args.json:
        print(json.dumps({"stats": stats, "due": due, "waiting": waiting},
                         ensure_ascii=False, indent=2))
    else:
        print(f"乾淨 point-in-time 場次（{CLEAN_FROM} 起）: {stats['clean_races']}")
        print(f"速度評分 runner 覆蓋（≥3 條 WinningTime）: {stats['speedfig_coverage_pct']}%"
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
        if not due:
            print("\n冇候選到期。")
    return 10 if due else 0


if __name__ == "__main__":
    raise SystemExit(main())
