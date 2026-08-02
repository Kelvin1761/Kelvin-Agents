#!/usr/bin/env python3
"""抽咗但**冇任何 leaf 讀**嘅欄位，逐個量場內判別力。

Sportsbet 帶咗一批欄位入嚟，寫咗落賽事檔但暫時零 leaf 讀：`Days`（距上仗）、
`Ave $`（平均獎金）、`J/H`（人馬配搭往績）、`WinRange`（勝出距離範圍）、
`SpeedPos`（官方預測定位）。加上往績行入面新攞到嘅 `@Settled`（起步定位）。

用同一把尺量：**場內 AUC**，平手當一半，同 `au_leaf_power.py` 一致，所以個數
可以直接同現有 leaf 比。冇呢個對照，「0.54 好唔好」係答唔到嘅。

⚠️ 呢度量嘅係「有冇資訊」，唔係「加咗會唔會贏」。一個 0.56 嘅特徵可能同
`form_score` 高度重疊，加咗一分錢都唔值。所以呢個係**篩選**，過到先值得
做 isolated A/B；過唔到就唔使浪費 A/B 時間。
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
AU_RACING = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(AU_RACING))
sys.path.insert(0, str(SCRIPT_DIR))

from au_leaf_power import results_for, within_race_auc  # noqa: E402

RE_RUNNER = re.compile(r"^\[(\d+)\]\s+(.+?)\s+\(\d+\)\s*$", re.M)
RE_HDR_DIST = re.compile(r"^RACE\s+(\d+)\s*[—–-]\s*(\d{3,5})m", re.M)


def norm(name):
    s = unicodedata.normalize("NFKD", name or "").lower()
    s = re.sub(r"\([^)]*\)", "", s)
    return re.sub(r"[^a-z0-9]", "", s)


def _num(txt):
    m = re.search(r"-?[\d,]+(?:\.\d+)?", txt or "")
    return float(m.group(0).replace(",", "")) if m else None


def _wps(txt):
    """`14: 5-0-4` → (starts, w, p, s)。"""
    m = re.match(r"\s*(\d+):\s*([\d-]+)-([\d-]+)-([\d-]+)", txt or "")
    if not m:
        return None
    f = lambda x: 0 if x == "-" else int(x)          # noqa: E731
    return int(m.group(1)), f(m.group(2)), f(m.group(3)), f(m.group(4))


def runner_features(block, today_dist):
    """一匹馬 → {特徵名: 值}。攞唔到就唔放，唔會用 0 頂替。"""
    def field(label):
        m = re.search(rf"{re.escape(label)}\s+(.+?)(?:\s{{2,}}|$)", block, re.M)
        return (m.group(1).strip() if m else "")

    out = {}
    days = _num(field("Days:"))
    if days is not None:
        out["days_since_last"] = days
    ave = _num(field("Ave $:"))
    if ave:
        out["ave_prize"] = ave
    # ⚠️ **`J/H`（人馬配搭）唔可以喺歷史語料度用 —— 佢包含今日嗰仗。**
    # 實測 2026-08-01 Flemington R5：Silent Shares 顯示 `1: 0-0-1`，而 Emily
    # Pozman **賽前策騎過佢 0 次**，佢今日跑第三。嗰個「1 次 1 季」就係今日。
    # Cherish Me `1: 0-1-0` 今日第二、Sixteen Reasons `1: 0-0-0` 今日第六，
    # 全部對得上。量出嚟場內 AUC **0.850** —— 高到唔合理，因為佢就係答案。
    #
    # 分清楚：**live（賽前）用係安全嘅**，嗰陣場仲未跑，個紀錄真係賽前。
    # 但拎歷史抓取嚟 fit 或者驗證就一定中毒。所以呢度硬性剔走，唔留 flag ——
    # 一個要記得開嘅安全掣，等於冇。
    if False:  # noqa: SIM108 — 見上面，故意封死
        pass
    wr = re.search(r"WinRange:\s*(\d+)m\s*-\s*(\d+)m", block)
    if wr and today_dist:
        lo, hi = int(wr.group(1)), int(wr.group(2))
        out["in_win_range"] = 1.0 if lo <= today_dist <= hi else 0.0
        # 離自己勝出範圍幾遠（0 = 範圍內）
        out["dist_outside_range"] = -float(
            0 if lo <= today_dist <= hi else min(abs(today_dist - lo),
                                                 abs(today_dist - hi)))
    sp = _num(field("SpeedPos:"))
    if sp is not None:
        out["speedmap_pos"] = -sp                    # 細 = 前，取負令「大 = 好」

    # 起步定位：由往績行嘅 `Nth@Settled` 同 `starters:N` 算習慣位置。
    # 一定要除以馬群大細 —— 16 匹跑第 5 同 6 匹跑第 5 唔同。
    fr = []
    for m in re.finditer(r"(\d+)\w*@Settled\.?(?:[^\n]*?starters:(\d+))?", block):
        s, n = int(m.group(1)), (int(m.group(2)) if m.group(2) else None)
        if n and n > 1:
            fr.append((s - 1) / (n - 1))
    if len(fr) >= 2:
        out["settles_forward"] = -sum(fr) / len(fr)  # 取負：大 = 靠前
    return out


def main():
    ap = argparse.ArgumentParser(description="未接落引擎嘅欄位，量場內判別力")
    ap.add_argument("--scored", required=True)
    ap.add_argument("--min-depth", type=float, default=4.0)
    args = ap.parse_args()

    from sb_backfill_archive import load_meeting_ids

    depth = {}
    cj = Path(args.scored).parent / "source_compare.json"
    if cj.exists():
        depth = {d["meeting"]: d.get("form_depth", 0) for d in json.loads(cj.read_text())}

    acc, races = {}, 0
    for name, meta in sorted(load_meeting_ids().items(), key=lambda kv: kv[1]["date"]):
        mdir = Path(args.scored) / name
        if not (mdir / "Meeting_Auto_Scoring.csv").exists():
            continue
        if args.min_depth and depth.get(name, 0) < args.min_depth:
            continue
        res = results_for(meta)
        if not res:
            continue
        for fg in sorted(mdir.glob("*Formguide.md")):
            text = fg.read_text(encoding="utf-8", errors="replace")
            hm = RE_HDR_DIST.search(text)
            if not hm:
                continue
            rno, dist = int(hm.group(1)), int(hm.group(2))
            actual = res.get(rno)
            if not actual:
                continue
            races += 1
            starts = [m.start() for m in RE_RUNNER.finditer(text)]
            feats = []
            for i, m in enumerate(RE_RUNNER.finditer(text)):
                end = starts[i + 1] if i + 1 < len(starts) else len(text)
                pos = actual.get(norm(m.group(2)))
                if pos is None:
                    continue
                feats.append((runner_features(text[m.start():end], dist), pos <= 3))
            keys = {k for f, _ in feats for k in f}
            for k in keys:
                pairs = [(f[k], p) for f, p in feats if k in f]
                c, n = within_race_auc(pairs)
                a = acc.setdefault(k, [0.0, 0, 0])
                a[0] += c
                a[1] += n
                a[2] += len(pairs)

    print(f"{races} 場\n")
    print(f"{'候選特徵':26}{'場內 AUC':>10}{'可比對數':>12}{'有值匹數':>11}")
    for k, (c, n, s) in sorted(acc.items(), key=lambda kv: -(kv[1][0] / kv[1][1])
                               if kv[1][1] else 0):
        if not n:
            continue
        auc = c / n
        mark = "  ★" if auc >= 0.57 else ("  ·" if auc >= 0.53 else "  ✗")
        print(f"{k:26}{auc:>10.3f}{n:>12,}{s:>11,}{mark}")
    print("\n對照（同一把尺）：form_score 0.608 · pace_figure 0.555 · "
          "pace_map 0.533 · sectional 0.469")
    return 0


if __name__ == "__main__":
    sys.exit(main())
