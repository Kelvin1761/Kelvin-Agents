#!/usr/bin/env python3
"""EXP-20261111-21 —「潘頓同場揀咗另一匹」凍結篩選（唯讀，唔郁評分）。

定義喺 `.agents/skills/hkjc_racing/hkjc_daily_auto/hkjc_purton_rival.py`（追蹤表用同一個）。

兩個模式（規則 2026-11-11 預先登記，睇結果之前寫；唔准改）：

  retro    舊季（2019-09-01 → 2024-07-31，`_research_old_season_results`）——呢個分法冇喺度揀過。
           只有市場鏡頭（舊季冇賽前資料可以回放模型）。
  forward  2026-11-11 起嘅賽日。主判決係模型鏡頭（要 `--model-run`，即 `hkjc_eval_harness.py run --since 2026-11-11`）。

統計量（兩個模式一樣）：
  * case vs 全場其他已完成出賽馬，上名（頭三）率分層加權差（權重 n₁n₀/(n₁+n₀)）。
    市場鏡頭按最終獨贏賠率分層：≤3／3–6／6–12／12–25／>25。模型鏡頭按模型排名每兩名一段：1–2…9–10、11+。
  * 另報勝出 A/E（實際頭馬 ÷ 去水後市場隱含勝率總和）。
  * 推論：以賽日做單位 bootstrap 2000 次，seed 0。
判決：
  retro    市場鏡頭 CI 上界 < 0 → CONFIRMED_NEGATIVE；CI 下界 > 0 → REVERSED；其他 → NOT_CONFIRMED。
  forward  模型鏡頭 CI 上界 < 0 → PASS_SCREEN（可以開預先登記嘅 −0.5 原始分排名 arm）；其他 → REJECT。

    python3 docs/experiments/patches/hkjc_screen_purton_rival.py retro
    python3 docs/experiments/patches/hkjc_screen_purton_rival.py forward --model-run <base.jsonl>
"""
from __future__ import annotations

import argparse
import collections
import json
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / ".agents/skills/hkjc_racing/hkjc_daily_auto"))
import hkjc_purton_rival as pr  # noqa: E402

HK_ROOT = Path((REPO / ".wongchoi_hk_data_root").read_text(encoding="utf-8").strip())
OLD = HK_ROOT / "_research_old_season_results"
WINDOWS = {"retro": ("2019-09-01", "2024-07-31"), "forward": ("2026-11-11", "9999-12-31")}
BOOT, SEED = 2000, 0


def odds_band(o):
    return None if not o else (0 if o <= 3 else 1 if o <= 6 else 2 if o <= 12 else 3 if o <= 25 else 4)


def gap(rows, band_key):
    cells = collections.defaultdict(lambda: [0, 0, 0, 0])
    for r in rows:
        b = r.get(band_key)
        if b is None:
            continue
        c = cells[b]
        if r["purton_rival"]:
            c[0] += r["plc"]; c[1] += 1
        else:
            c[2] += r["plc"]; c[3] += 1
    num = den = 0.0
    for a, n1, b, n0 in cells.values():
        if n1 and n0:
            w = n1 * n0 / (n1 + n0); num += w * (a / n1 - b / n0); den += w
    return 100 * num / den if den else float("nan")


def ae(rows):
    rows = [r for r in rows if r["purton_rival"] and r.get("imp") is not None]
    e = sum(r["imp"] for r in rows)
    return sum(r["pos"] == 1 for r in rows) / e if e else float("nan")


def boot(rows, stat):
    rng = random.Random(SEED); by = collections.defaultdict(list)
    for r in rows:
        by[r["date"]].append(r)
    keys = sorted(by)
    out = sorted(stat([x for k in rng.choices(keys, k=len(keys)) for x in by[k]]) for _ in range(BOOT))
    out = [x for x in out if x == x]
    return out[int(0.025 * len(out))], out[int(0.975 * len(out)) - 1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=sorted(WINDOWS))
    ap.add_argument("--model-run", type=Path)
    args = ap.parse_args()
    start, end = WINDOWS[args.mode]
    extra = [OLD] if args.mode == "retro" else []
    tagged = pr.tag_runs(pr.load_runs(HK_ROOT, extra))
    rows = [r for r in tagged if start <= r["date"] <= end]
    races = collections.defaultdict(list)
    for r in rows:
        r["plc"] = r["pos"] <= 3
        r["oband"] = odds_band(r["odds"])
        races[(r["date"], r["race"])].append(r)
    for rs in races.values():
        if all(r["odds"] and r["odds"] > 1 for r in rs):
            t = sum(1 / r["odds"] for r in rs)
            for r in rs:
                r["imp"] = (1 / r["odds"]) / t
    if args.model_run:
        rank = {}
        for line in args.model_run.read_text(encoding="utf-8").splitlines():
            race = json.loads(line) if line.strip() else {}
            if "date" not in race:
                continue
            for i, no in enumerate(race["picks"]):
                rank[(race["date"], race["race"], str(no))] = i + 1
        for r in rows:
            k = rank.get((r["date"], r["race"], r["horse_no"]))
            r["mband"] = None if k is None else min((k - 1) // 2, 5)
    cases = [r for r in rows if r["purton_rival"]]
    print(f"{args.mode}: {start} → {end}  {len({r['date'] for r in rows})} 個賽日  {len(races)} 場  {len(rows)} 匹  case {len(cases)}")
    if not cases:
        print("冇 case。")
        return 1
    plc = 100 * sum(r["plc"] for r in cases) / len(cases)
    print(f"  case 上名率 {plc:.1f}%  勝率 {100 * sum(r['pos'] == 1 for r in cases) / len(cases):.1f}%")
    g, (lo, hi) = gap(rows, "oband"), boot(rows, lambda s: gap(s, "oband"))
    a, (alo, ahi) = ae(rows), boot(rows, ae)
    print(f"  市場鏡頭  分層上名率差 {g:+.1f}pp [{lo:+.1f}, {hi:+.1f}]   勝出 A/E {a:.3f} [{alo:.3f}, {ahi:.3f}]")
    verdict = None
    if args.mode == "retro":
        verdict = "CONFIRMED_NEGATIVE" if hi < 0 else ("REVERSED" if lo > 0 else "NOT_CONFIRMED")
    if args.model_run:
        mrows = [r for r in rows if r.get("mband") is not None]
        mg, (mlo, mhi) = gap(mrows, "mband"), boot(mrows, lambda s: gap(s, "mband"))
        print(f"  模型鏡頭  分層上名率差 {mg:+.1f}pp [{mlo:+.1f}, {mhi:+.1f}]（對到模型排名 case "
              f"{sum(r['purton_rival'] for r in mrows)}）")
        if args.mode == "forward":
            verdict = "PASS_SCREEN" if mhi < 0 else "REJECT"
    if verdict:
        print(f"\nVERDICT {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
