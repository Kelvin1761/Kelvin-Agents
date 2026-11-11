#!/usr/bin/env python3
"""HKJC 換配備訊號：逐個配備 × 逐種變動（初戴 1／除去 -／重戴 2）量表現。

診斷用，唔入分（EXP-20261111-15）。數據 = 排程 cache 入面嘅逐駒往績頁
（`.hkjc_cache/profile_cache.json`），HKJC 自己喺配備欄標咗變動：
    B1 = 第一次戴   B- = 今仗除去   B2 = 除去之後重戴

三把尺，全部同「冇任何配備變動嘅仗」（control）比：
  1. 對市場：實際入位（頭三）率 − 同賠率段 control 嘅入位率。> 0 = 市場低估。
  2. 對自己上仗：今仗輸距 − 「上仗輸距相同嘅 control 今仗輸距」。< 0 = 進步多過
     單純均值回歸（換配備通常喺跑差之後，所以唔可以直接比上仗）。
  3. 原始入位率／勝率（冇調整，只供參考）。
CI = 以馬匹做 cluster 嘅 bootstrap；p 值做 Holm 修正。

    python3 gear_events.py [--min-n 40] [--since 2024-09-01] [--json out.json]
"""
from __future__ import annotations

import argparse
import glob
import json
import re
from collections import defaultdict
from pathlib import Path

import numpy as np

HK_ROOT = Path("/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/HK_Racing")
SCHED_CACHE = Path("/Users/imac/wongchoi-scheduler/.hkjc_cache/profile_cache.json")
TOKEN_RE = re.compile(r"([A-Z]+)([12-])?")
GEAR_ZH = {"B": "眼罩", "BO": "單邊眼罩", "CP": "羊毛面箍", "TT": "綁繫舌帶", "H": "頭罩", "V": "開縫眼罩",
           "XB": "交叉鼻箍", "SR": "鼻箍", "PC": "半掩防沙眼罩", "P": "防沙眼罩", "E": "耳塞", "SB": "羊毛額箍"}
EVENT_ZH = {"1": "初戴", "-": "除去", "2": "重戴", "1+1": "初戴後第二仗"}
MARGIN_BINS = [0.0, 0.01, 1, 2, 3.5, 5, 7.5, 10, 15, 99]
RNG = np.random.default_rng(20261111)


def load_profiles() -> dict:
    files = glob.glob(str(HK_ROOT / "*" / ".hkjc_cache" / "profile_cache.json")) + [str(SCHED_CACHE)]
    horses: dict = {}
    for f in files:
        try:
            data = json.load(open(f, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for hid, rec in data.items():
            if hid not in horses or rec.get("_ts", 0) > horses[hid].get("_ts", 0):
                horses[hid] = rec
    return horses


def parse_gear(raw: str) -> list[tuple[str, str]]:
    out = []
    for tok in re.split(r"[/,]", raw or ""):
        m = TOKEN_RE.fullmatch(tok.strip())
        if m:
            out.append((m.group(1), m.group(2) or ""))
    return out


def beaten(e: dict) -> float | None:
    if e.get("placing") == 1:
        return 0.0
    m = e.get("margin_numeric")
    return None if m is None else min(float(m), 25.0)


def build_rows(horses: dict, since: str, until: str = "9999") -> list[dict]:
    rows = []
    for hid, rec in horses.items():
        es = [e for e in rec["data"].get("entries", []) if e.get("race_date_full") and e.get("placing")]
        es.sort(key=lambda e: (e["race_date_full"], e.get("race_no") or 0))
        prev_first: set[str] = set()
        for i, e in enumerate(es):
            toks = parse_gear(e.get("gear", ""))
            events = [(b, s) for b, s in toks if s]
            second = prev_first & {b for b, s in toks if not s}   # 初戴後第二仗（仲戴緊、冇新標記）
            prev_first = {b for b, s in toks if s == "1"} if i else set()   # 初出嘅「1」唔算換配備
            d = e["race_date_full"].replace("/", "-")
            if i == 0 or d < since or d > until:
                continue
            odds = e.get("_win_odds")
            rows.append({
                "horse": hid, "date": e["race_date_full"], "placing": e["placing"],
                "top3": int(e["placing"] <= 3), "win": int(e["placing"] == 1),
                "odds": float(odds) if odds else None,
                "len": beaten(e), "prev_len": beaten(es[i - 1]), "prev_top3": int(es[i - 1]["placing"] <= 3),
                "events": events, "second": sorted(second) if not events else [],
            })
    return rows


def fit_baselines(rows: list[dict]):
    ctrl = [r for r in rows if not r["events"]]
    odds = np.array([r["odds"] for r in ctrl if r["odds"]])
    edges = np.quantile(np.log(odds), np.linspace(0, 1, 26))[1:-1]
    acc = defaultdict(lambda: [0, 0, 0])
    for r in ctrl:
        if r["odds"]:
            b = int(np.searchsorted(edges, np.log(r["odds"])))
            acc[b][0] += 1; acc[b][1] += r["top3"]; acc[b][2] += r["win"]
    mk = {b: (v[1] / v[0], v[2] / v[0]) for b, v in acc.items()}
    lacc = defaultdict(list)
    for r in ctrl:
        if r["len"] is not None and r["prev_len"] is not None:
            lacc[int(np.searchsorted(MARGIN_BINS, r["prev_len"], side="right"))].append(r["len"])
    lb = {b: float(np.mean(v)) for b, v in lacc.items()}
    for r in rows:
        r["x_top3"] = r["x_win"] = r["x_len"] = None
        if r["odds"]:
            b = int(np.searchsorted(edges, np.log(r["odds"])))
            if b in mk:
                r["x_top3"], r["x_win"] = mk[b]
        if r["len"] is not None and r["prev_len"] is not None:
            r["x_len"] = lb.get(int(np.searchsorted(MARGIN_BINS, r["prev_len"], side="right")))
    return ctrl


def cluster_ci(values: list[float], horses: list[str], n_boot: int = 4000):
    """Mean, 95% CI and two-sided p (bootstrap, resampling horses)."""
    if not values:
        return None
    idx = {h: i for i, h in enumerate(dict.fromkeys(horses))}
    s = np.zeros(len(idx)); n = np.zeros(len(idx))
    for v, h in zip(values, horses):
        s[idx[h]] += v; n[idx[h]] += 1
    pick = RNG.integers(0, len(idx), size=(n_boot, len(idx)))
    means = s[pick].sum(1) / n[pick].sum(1)
    mean = s.sum() / n.sum()
    lo, hi = np.percentile(means, [2.5, 97.5])
    p = 2 * min((means <= 0).mean(), (means >= 0).mean())
    return float(mean), float(lo), float(hi), float(min(1.0, max(p, 1 / n_boot)))


def summarise(cell_rows: list[dict]) -> dict:
    hs = [r["horse"] for r in cell_rows]
    mk = [(r["top3"] - r["x_top3"], r["horse"]) for r in cell_rows if r["x_top3"] is not None]
    wk = [(r["win"] - r["x_win"], r["horse"]) for r in cell_rows if r["x_win"] is not None]
    ln = [(r["len"] - r["x_len"], r["horse"]) for r in cell_rows if r["x_len"] is not None]
    od = [r["odds"] for r in cell_rows if r["odds"]]
    return {
        "n": len(cell_rows), "horses": len(set(hs)),
        "top3": float(np.mean([r["top3"] for r in cell_rows])), "win": float(np.mean([r["win"] for r in cell_rows])),
        "prev_top3": float(np.mean([r["prev_top3"] for r in cell_rows])),
        "median_odds": float(np.median(od)) if od else None,
        "vs_market_top3": cluster_ci([a for a, _ in mk], [b for _, b in mk]),
        "vs_market_win": cluster_ci([a for a, _ in wk], [b for _, b in wk]),
        "vs_own_len": cluster_ci([a for a, _ in ln], [b for _, b in ln]),
    }


def holm(pvals: list[float]) -> list[float]:
    order = np.argsort(pvals); m = len(pvals); out = [0.0] * m; running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * pvals[i])); out[i] = running
    return out


def fmt(ci, scale=100.0, unit="pp"):
    if ci is None:
        return "—"
    m, lo, hi, _ = ci
    return f"{m * scale:+.1f}{unit} [{lo * scale:+.1f},{hi * scale:+.1f}]"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-n", type=int, default=40)
    ap.add_argument("--since", default="2020-01-01")
    ap.add_argument("--until", default="9999-12-31")
    ap.add_argument("--json")
    args = ap.parse_args()

    horses = load_profiles()
    rows = build_rows(horses, args.since, args.until)
    ctrl = fit_baselines(rows)
    print(f"馬匹 {len(horses)}｜非初出仗 {len(rows)}（{min(r['date'] for r in rows)} → {max(r['date'] for r in rows)}）"
          f"｜control（冇變動）{len(ctrl)} 仗：入位 {np.mean([r['top3'] for r in ctrl]):.1%}、"
          f"勝 {np.mean([r['win'] for r in ctrl]):.1%}")

    cells: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        for b, s in r["events"]:
            cells[(b, s)].append(r)
        for s in {s for _, s in r["events"]}:
            cells[("任何配備", s)].append(r)
        for b in r["second"]:
            cells[(b, "1+1")].append(r)
    out = {}
    keys = [k for k, v in cells.items() if len(v) >= args.min_n]
    keys.sort(key=lambda k: ("1-2".index(k[1][0]) if k[1] != "1+1" else 9, -len(cells[k])))
    for k in keys:
        out[k] = summarise(cells[k])
    for metric in ("vs_market_top3", "vs_own_len"):
        ks = [k for k in keys if out[k][metric] and k[0] != "任何配備"]
        for k, hp in zip(ks, holm([out[k][metric][3] for k in ks])):
            out[k][metric + "_holm"] = hp

    last = None
    for k in keys:
        if k[1] != last:
            last = k[1]
            print(f"\n=== {EVENT_ZH[k[1]]} ===")
            print(f"{'配備':<16}{'n':>5} {'上仗入位':>7} {'今仗入位':>7} {'勝率':>6} {'賠率中位':>7}  "
                  f"{'對市場入位（+ = 市場低估）':<28}{'Holm':>6}  {'對自己輸距，馬位（− = 進步）':<26}{'Holm':>6}")
        o = out[k]
        name = f"{k[0]} {GEAR_ZH.get(k[0], '')}"
        print(f"{name:<16}{o['n']:>5} {o['prev_top3']:>8.1%} {o['top3']:>8.1%} {o['win']:>6.1%} "
              f"{(o['median_odds'] or 0):>8.1f}  {fmt(o['vs_market_top3']):<30}"
              f"{o.get('vs_market_top3_holm', float('nan')):>6.2f}  "
              f"{fmt(o['vs_own_len'], 1.0, ''):<28}{o.get('vs_own_len_holm', float('nan')):>6.2f}")
    if args.json:
        Path(args.json).write_text(json.dumps({f"{a}|{b}": v for (a, b), v in out.items()}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
