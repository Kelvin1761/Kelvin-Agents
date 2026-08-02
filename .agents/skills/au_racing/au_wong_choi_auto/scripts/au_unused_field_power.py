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
from statistics import pstdev
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


def runner_features(block, today_dist, horse_name=""):
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
    # ⚠️ **`WinRange` 包含今日嗰仗 —— 唔可以用喺歷史語料。**
    # 實測 41 匹「今日贏、賽前從未喺呢個距離贏過」嘅馬，今日嘅路程**逐匹都
    # 啱啱好係 WinRange 嘅端點**：Zetheros 1425m 贏 → `1400m - 1425m`；
    # Shultzy 2440m 贏 → `1600m - 2440m`；De Bergerac 1100m 贏 → `1100m - 1247m`。
    # 即係「今日路程喺勝出範圍內」有一大部分係「因為佢今日贏咗」。
    #
    # 呢個係第二個**通過晒所有統計閘**嘅洩漏特徵：dev/holdout 分割、5 fold 全過、
    # holdout winner_in_top3 **+17.58pp**。統計紀律防 overfit，**唔防洩漏** ——
    # 一個含住答案嘅特徵，喺任何切法之下都會穩定地贏。
    # 唯一嘅訊號係 holdout 升幅**大過** dev（+17.58 vs +6.63）：真特徵通常反過嚟。
    sp = _num(field("SpeedPos:"))
    if sp is not None:
        out["speedmap_pos"] = -sp                    # 細 = 前，取負令「大 = 好」

    # 「第幾次出爭」× 對應嘅 1st/2nd/3rd Up 往績。
    # 單獨睇 `1st Up 9: 1-3-3` 冇意義 —— 要今日**真係** 1st up 先啱用。
    # 所以由賽前往績行嘅日期間距推今日係第幾次出爭：≥60 日當一個 spell。
    dates = sorted((d for d in re.findall(r"\sR\d+\s(\d{4}-\d{2}-\d{2})\s", block)),
                   reverse=True)
    if dates and days is not None:
        up = 1 if days >= 60 else None
        if up is None:
            up = 1
            for i in range(len(dates) - 1):
                a = [int(x) for x in dates[i].split("-")]
                b = [int(x) for x in dates[i + 1].split("-")]
                gap = (a[0]-b[0])*365 + (a[1]-b[1])*30 + (a[2]-b[2])
                if gap >= 60:
                    break
                up += 1
        rec = _wps(field(f"{min(up,3)}{'st' if up==1 else 'nd' if up==2 else 'rd'} Up:"))
        if rec and rec[0] >= 2:
            out["up_place_rate"] = (rec[1] + rec[2] + rec[3]) / rec[0]
            out["up_index"] = -float(min(up, 4))

    # ── 由**我哋自己過濾過嘅賽前往績行**砌，唔用網站嘅總結欄位 ──────────
    # 呢個係 `WinRange` 洩漏嘅正解：唔好用網站賽後先寫嘅總結，改為由我哋
    # 已經隔走賽後行嘅往績自己數 —— **構造上就唔可能中毒**。
    # Kelvin 提出嘅門檻：喺呢個路程要有**兩次以上**經驗先計，咁「今日第一次
    # 喺呢個路程贏」嗰批自然入唔到（佢哋賽前喺呢個路程係零次）。
    #
    # ⚠️ 逐行拆，唔好砌一條大 regex。試過用一條帶多個 optional group 嘅
    # pattern，lazy 量詞會令每個 optional group 都跳過，成組特徵靜靜咁全部
    # 攞唔到值 —— 表面「冇呢個特徵」，其實係 regex 壞咗。
    lines = block.splitlines()
    runs = []
    for i, ln in enumerate(lines):
        m = re.match(r"^(\S.*?)\sR\d+\s(\d{4}-\d{2}-\d{2})\s+(\d+)m\s+cond:", ln)
        if not m:
            continue
        l6 = re.search(r"PF\[L600 Delta:\s*(-?[\d.]+)\]", ln)
        opp = lines[i + 1] if i + 1 < len(lines) else ""
        placed = bool(re.match(r"^([123])-", opp) and
                      re.search(rf"[123]-{re.escape(horse_name)}\b", opp))
        runs.append({"dist": int(m.group(3)),
                     "l600": float(l6.group(1)) if l6 else None,
                     "trial": "**(TRIAL)**" in m.group(1),
                     "placed": placed})
    official = [r for r in runs if not r["trial"]]

    if today_dist and official:
        near = [r for r in official if abs(r["dist"] - today_dist) <= 100]
        if len(near) >= 2:                       # ← 兩次以上先計
            out["dist_place_rate"] = sum(1 for r in near if r["placed"]) / len(near)
            out["dist_places"] = float(sum(1 for r in near if r["placed"]))

    # ── 段速時間：現行 pace_figure 用**平均** L600 delta，呢度試其他讀法 ──
    d6 = [r["l600"] for r in official if r["l600"] is not None]
    if len(d6) >= 2:
        out["l600_best"] = -min(d6)              # 細 = 快，取負令大 = 好
        out["l600_mean"] = -sum(d6) / len(d6)    # 對照組（≈ 現行 pace_figure）
        out["l600_consistency"] = -pstdev(d6)
    if len(d6) >= 3:
        out["l600_trend"] = -((sum(d6[:2]) / 2) - (sum(d6[2:]) / len(d6[2:])))
    if today_dist:
        nd = [r["l600"] for r in official
              if r["l600"] is not None and abs(r["dist"] - today_dist) <= 100]
        if nd:
            out["l600_at_distance"] = -min(nd)

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
                feats.append((runner_features(text[m.start():end], dist, m.group(2)), pos <= 3))
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
