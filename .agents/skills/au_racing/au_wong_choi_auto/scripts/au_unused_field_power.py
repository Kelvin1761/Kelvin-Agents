#!/usr/bin/env python3
"""抽咗但**冇任何 leaf 讀**嘅欄位，逐個量場內判別力。

Sportsbet 帶咗一批欄位入嚟，寫咗落賽事檔但暫時零 leaf 讀；不過 career overview
會賽後刷新，所以歷史研究只量 `Days`、`SpeedPos` 同由日期已截斷往績行重建嘅
路程／人馬／試閘／段速／定位訊號。`Ave $`、J/H、WinRange、up-record outcome
summary 一律封鎖。加上往績行入面新攞到嘅 `@Settled`（起步定位）。

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
import statistics
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


# ── 速度評分：track×distance 標準時間（2026-08-26）────────────────────────
# 同 `_STANDARD_600M` 一樣係一個**靜態參考尺**，唔係逐匹馬嘅結果資料 ——
# 「Flemington 1200m 中位頭馬時間」唔會編碼今日邊隻贏。掃一次全部 Formguide
# 就 cache 住。設 `AU_SPEED_STD_ROOT` 指去 scored root；冇設就淨係用距離基準。
_SPEED_STD = None
_SPEED_GOING = None


def _speed_standards():
    global _SPEED_STD, _SPEED_GOING
    if _SPEED_STD is not None:
        return _SPEED_STD, _SPEED_GOING
    import os
    import collections
    _SPEED_STD, _SPEED_GOING = {}, {}
    root = os.environ.get("AU_SPEED_STD_ROOT")
    if not root or not Path(root).exists():
        return _SPEED_STD, _SPEED_GOING
    per = collections.defaultdict(list)
    for fg in Path(root).rglob("*Formguide.md"):
        for ln in fg.read_text(encoding="utf-8", errors="replace").splitlines():
            if "WinningTime:" not in ln or "**(TRIAL)**" in ln:
                continue
            m = re.match(r"^(\S.*?)\sR\d+\s\d{4}-\d{2}-\d{2}\s+(\d+)m\s+cond:(\S+)", ln)
            w = re.search(r"WinningTime:(?:(\d+):)?([\d.]+)", ln)
            if not (m and w):
                continue
            sec = (int(w.group(1)) * 60 if w.group(1) else 0) + float(w.group(2))
            if not (25.0 < sec < 260.0):
                continue
            per[(m.group(1).strip(), int(m.group(2)))].append((sec, m.group(3)))
    _SPEED_STD = {k: statistics.median([s for s, _ in v])
                  for k, v in per.items() if len(v) >= 10}
    dev = collections.defaultdict(list)
    for (tr, d), v in per.items():
        base = _SPEED_STD.get((tr, d))
        if base is None:
            continue
        for sec, cond in v:
            dev[cond].append(sec - base)
    _SPEED_GOING = {k: statistics.median(v) for k, v in dev.items() if len(v) >= 40}
    return _SPEED_STD, _SPEED_GOING


def _speed_figure(run):
    """一條往績行 → 每公里快過標準幾多秒（越大越好）。攞唔到就 None。"""
    if run.get("wt_sec") is None or not run.get("dist"):
        return None
    std, going = _speed_standards()
    base = std.get((run.get("track"), run["dist"]))
    if base is None:
        return None
    # 個體時間 = 頭馬時間 + 輸幾多長度 × 每長度秒數（1 長度 ≈ 2.4m）
    spl = 2.4 / (run["dist"] / run["wt_sec"])
    mine = run["wt_sec"] + (run.get("margin") or 0.0) * spl
    adj = mine - base - going.get(run.get("cond"), 0.0)
    return -adj / (run["dist"] / 1000.0)


def runner_features(block, today_dist, horse_name="", today_jockey=""):
    """一匹馬 → {特徵名: 值}。攞唔到就唔放，唔會用 0 頂替。"""
    def field(label):
        m = re.search(rf"{re.escape(label)}\s+(.+?)(?:\s{{2,}}|$)", block, re.M)
        return (m.group(1).strip() if m else "")

    out = {}
    days = _num(field("Days:"))
    if days is not None:
        out["days_since_last"] = days
    # Outcome-derived overview summaries are forbidden in historical research.
    # Sportsbet has been proven to refresh J/H and WinRange with the target race;
    # Ave $ and the 1st/2nd/3rd-up records are built from the same mutable career
    # overview and can therefore contain the answer too.  Live pre-race display
    # may safely show them, but a post-race archive cannot validate them.  Build
    # candidate signals only from the dated run rows censored before race day.
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
        # ── 全程時間（2026-08-26 加）───────────────────────────────────
        # `WinningTime:` 由 2026-08-09 起就寫喺每條往績行，但由頭到尾冇人讀
        # （`inject_fact_anchors` 0 個引用、引擎 0 個引用）。即係成個模型冇
        # 任何**絕對時間**速度評分 —— 唯一同時間有關嘅 `_STANDARD_600M`
        # 係尾 600m 分段，唔係全程。
        # 呢度由**已經censor 過嘅往績行**自己砌，同 `dist_place_rate` 一樣
        # 構造上唔可能中毒（唔掂網站嗰啲會賽後刷新嘅總結欄位）。
        _wt = re.search(r"WinningTime:(\d+):([\d.]+)|WinningTime:([\d.]+)", ln)
        _mg = re.search(r"margin:(-?[\d.]+)L", ln)
        _wtsec = None
        if _wt:
            if _wt.group(1):
                _wtsec = int(_wt.group(1)) * 60 + float(_wt.group(2))
            elif _wt.group(3):
                _wtsec = float(_wt.group(3))
        opp = lines[i + 1] if i + 1 < len(lines) else ""
        placed = bool(re.match(r"^([123])-", opp) and
                      re.search(rf"[123]-{re.escape(horse_name)}\b", opp))
        jk = re.search(r"\$[\d,]+\s+(.+?)\s+\(", ln)
        runs.append({"dist": int(m.group(3)),
                     "l600": float(l6.group(1)) if l6 else None,
                     "trial": "**(TRIAL)**" in m.group(1),
                     "jockey": (jk.group(1) if jk else ""),
                     "placed": placed,
                     "track": m.group(1).strip(),
                     "cond": (re.search(r"cond:(\S+)", ln).group(1)
                              if re.search(r"cond:(\S+)", ln) else None),
                     "wt_sec": _wtsec,
                     "margin": float(_mg.group(1)) if _mg else None})
    official = [r for r in runs if not r["trial"]]

    # ── 近期窗口往績（2026-08-26）─────────────────────────────────────────
    # 網站有 `12 Month:` / `Season:` / `3rd Up:` / `Turf:` 而引擎冇讀。但嗰啲
    # 全部係**會賽後刷新嘅 career overview** 出品 —— 同已證實洩漏嘅 `J/H`
    # （場內 AUC 0.850）同 `WinRange`（holdout +17.58pp）同一個 block。
    # 2026-08-26 量過：未撞 10 行上限嘅 13,589 匹入面，`Career:` 數字大過我哋
    # censor 後數到嘅有 56.7%，而「多出恰好 1 仗」只佔全體 4.2%（多出 2–6 仗
    # 嘅一樣多）—— 即係大部分差異係頁面冇列晒，唔係今日嗰仗。分唔清，
    # 所以照 `dist_place_rate` 嗰個做法：**由我哋自己 censor 過嘅往績行數**，
    # 構造上就唔可能中毒。
    if official:
        recent = []
        for r in official:
            pass
        # 12 個月窗口：由往績行日期自己數
        import datetime as _dt
        _dates = re.findall(r"\sR\d+\s(\d{4}-\d{2}-\d{2})\s", block)
        if _dates and len(_dates) >= len(official):
            newest = max(_dates)
            y, mth = int(newest[:4]), int(newest[5:7])
            in12 = []
            for r, dstr in zip(official, _dates[:len(official)]):
                gap = (y - int(dstr[:4])) * 12 + (mth - int(dstr[5:7]))
                if gap < 12:
                    in12.append(r)
            if len(in12) >= 2:
                out["pre12m_place_rate"] = sum(1 for r in in12 if r["placed"]) / len(in12)
                out["pre12m_starts"] = float(len(in12))

    # ── 絕對時間速度評分（2026-08-26）────────────────────────────────────
    sf = [v for v in (_speed_figure(r) for r in official) if v is not None]
    if sf:
        out["speed_fig_best"] = max(sf)
        out["speed_fig_mean"] = sum(sf) / len(sf)
        out["speed_fig_recent"] = sf[0]                     # runs 已經係新→舊
        if len(sf) >= 3:
            out["speed_fig_best3"] = sum(sorted(sf)[-3:]) / 3.0
    if today_dist:
        sfd = [v for r in official
               if abs(r["dist"] - today_dist) <= 200
               and (v := _speed_figure(r)) is not None]
        if sfd:
            out["speed_fig_at_dist"] = max(sfd)

    if today_dist and official:
        near = [r for r in official if abs(r["dist"] - today_dist) <= 100]
        if len(near) >= 2:                       # ← 兩次以上先計
            out["dist_place_rate"] = sum(1 for r in near if r["placed"]) / len(near)
            out["dist_places"] = float(sum(1 for r in near if r["placed"]))

    # ── 人馬配搭：由**我哋自己嘅往績行**數，唔用網站個 `J/H` ──────────────
    # 網站個 `J/H` 包含今日嗰仗（見 au_unused_field_power 上面嘅註）。加個
    # 「至少兩次」門檻**唔會**解決問題 —— 五次入面仍然有一次係今日。要真正
    # 乾淨，就要同 `dist_place_rate` 一樣，由已經隔走賽後行嘅往績自己數。
    if today_jockey:
        jl = today_jockey.split()[-1].lower()
        mine = [r for r in official if jl and jl in r["jockey"].lower()]
        if len(mine) >= 2:                       # Kelvin 提出嘅門檻
            out["jh_pre_place_rate"] = sum(1 for r in mine if r["placed"]) / len(mine)

    # ── 試閘：只喺**淺資歷**馬身上有意義？ ────────────────────────────────
    # Kelvin 嘅假設：5 仗以上嘅馬，正式賽成績同段速已經講晒，試閘係噪音；
    # 淺資歷馬先要靠試閘。呢度分開兩組量，睇個假設成唔成立。
    trials = [r for r in runs if r["trial"]]
    if trials:
        tl = [r["l600"] for r in trials if r["l600"] is not None]
        if tl:
            out["trial_l600_best"] = -min(tl)
            out["trial_l600_mean"] = -sum(tl) / len(tl)
        out["trial_placed"] = float(sum(1 for r in trials if r["placed"]))
        # Kelvin：試閘嘅**時間同路程**應該重要過名次。
        # 名次淨係話你贏咗嗰班對手，時間話你跑得幾快 —— 而試閘對手質素差好遠。
        near_t = [r["l600"] for r in trials
                  if r["l600"] is not None and today_dist
                  and abs(r["dist"] - today_dist) <= 200]
        if near_t:
            out["trial_l600_at_dist"] = -min(near_t)
        # 試閘路程同今日差幾遠（短途試閘講唔到長途能力）
        if today_dist:
            out["trial_dist_gap"] = -min(abs(r["dist"] - today_dist) for r in trials)
        # 最近一次試閘幾耐之前（用往績行嘅相對位置做代理）
        out["trial_count"] = float(len(trials))
    out["_career_runs"] = float(len(official))   # 分組用，唔係特徵

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

    # PI 嘅替代品：Settled 只有 26% 覆蓋，但 400m 走位有 74%。
    # `inject_fact_anchors` 已經算咗 l400_pi = pos_400 − finish（18 處），
    # 但**引擎一個字都冇讀**。呢度先量佢有冇訊號，再講改唔改。
    # 名次由對手線推（自己出現喺 1-/2-/3- 就係上名），冇對手線就冇 finish。
    pi400, pi800 = [], []
    for i, ln in enumerate(lines):
        if not re.match(r"^(\S.*?)\sR\d+\s\d{4}-\d{2}-\d{2}\s+\d+m\s+cond:", ln):
            continue
        if "**(TRIAL)**" in ln:
            continue
        opp = lines[i + 1] if i + 1 < len(lines) else ""
        fin = None
        for m2 in re.finditer(r"([123])-([A-Za-z][^(,]*)", opp):
            if horse_name and horse_name.lower() in m2.group(2).strip().lower():
                fin = int(m2.group(1))
                break
        if fin is None:
            continue
        m4 = re.search(r"(\d+)\w*@400m", ln)
        m8 = re.search(r"(\d+)\w*@800m", ln)
        if m4:
            pi400.append(int(m4.group(1)) - fin)
        if m8:
            pi800.append(int(m8.group(1)) - fin)
    if pi400:
        out["l400_pi_mean"] = sum(pi400) / len(pi400)     # 正數 = 追前
    if pi800:
        out["l800_pi_mean"] = sum(pi800) / len(pi800)

    # Kelvin：試閘名次 + 時間**合併**試下
    if trials:
        tl2 = [r["l600"] for r in trials if r["l600"] is not None]
        if tl2:
            # 名次（上名數）同時間（最好 L600 delta）各佔一半，都先場內標準化唔到，
            # 所以用簡單相加：上名數 − 最好 delta（細 = 快）
            out["trial_rank_plus_time"] = (
                sum(1 for r in trials if r["placed"]) - min(tl2))

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

    from sb_backfill_archive import load_meeting_ids, scored_meeting_index

    depth = {}
    meeting_dirs = scored_meeting_index(args.scored)
    cj = Path(args.scored).parent / "source_compare.json"
    if cj.exists():
        depth = {d["meeting"]: d.get("form_depth", 0) for d in json.loads(cj.read_text())}

    acc, races = {}, 0
    for name, meta in sorted(load_meeting_ids().items(), key=lambda kv: kv[1]["date"]):
        mdir = meeting_dirs.get(name)
        if mdir is None:
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
                blk = text[m.start():end]
                jm = re.search(r"\|\s*J:\s*([^(\n|]+)", blk)
                feats.append((runner_features(blk, dist, m.group(2),
                                              (jm.group(1).strip() if jm else "")),
                              pos <= 3))
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
