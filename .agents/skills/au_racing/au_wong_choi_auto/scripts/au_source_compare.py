#!/usr/bin/env python3
"""同一部引擎、同一組權重，兩個數據源逐場對比。

呢個工具存在嘅原因，係上一次「Sportsbet 好過現有源」嘅結論係錯嘅 —— 嗰個
量度用咗帶賽後洩漏嘅檔案，而且冇一個可以重跑嘅 harness，所以錯咗都冇人接得住。
呢度三樣嘢都寫死：

  1. **賽果由 cache 嘅賽事頁抽**，唔靠任何 CSV。cache 入面每匹馬嘅往績都有
     `Finished x/y`，包括我哋要預測嗰場 —— 嗰行**評分嗰陣一定要丟走**
     （`write_meeting` 做咗），但**攞嚟做標準答案係啱嘅**。呢個分別要記住。
  2. **只比兩邊都評到分嘅場次**，唔夠場數就講明，唔會靜靜用唔同分母。
  3. 樣本細嘅時候**照講唔確定性** —— 9 場 27 個位嘅差別係噪音，唔係幅度。

用法：
    python3 au_source_compare.py --new /tmp/sb_archive --old "<archive root>"
    python3 au_source_compare.py --new /tmp/sb_archive --old ... --only Flemington
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
sys.path.insert(0, str(AU_RACING.parent / "shared_racing"))

from eval_metrics import exclusive_label, race_metrics, summarize_races  # noqa: E402

KEYS = ("gold", "good_positional", "pass", "champion", "winner_in_top3")


def norm(name):
    """馬名比對用。國別後綴同標點喺兩個源之間唔一致。"""
    s = unicodedata.normalize("NFKD", name or "").lower()
    s = re.sub(r"\([^)]*\)", "", s)
    return re.sub(r"[^a-z0-9]", "", s)


def results_from_cache(meeting):
    """由 cache 嘅賽事頁抽賽果 → {race_no: {norm_name: pos}}。

    ⚠️ 用嘅正正係 `write_meeting` 評分時丟走嗰啲行。做標準答案啱，做輸入唔啱。
    """
    from claw_sportsbet_form import (BASE, SportsbetFormFetcher, parse_race,
                                     parse_runner_blocks, run_date)

    f = SportsbetFormFetcher(delay=0.0, verbose=False)
    out = {}
    for rid in meeting["races"]:
        url = f"{BASE}/{meeting['meetingId']}/{rid}/"
        if not f._cache_path(url).exists():      # 只讀 cache，絕不出網
            continue
        html = f.get(url)
        pr = parse_race(html)
        rno = pr["meta"].get("race_number")
        if rno is None:
            continue
        res = {}
        for blk in parse_runner_blocks(html):
            for run in blk.get("runs", []):
                h = run.get("header") or {}
                if run_date(run) == meeting["date"] and str(h.get("race")) == str(rno):
                    try:
                        res[norm(blk["name"])] = int(run["pos"])
                    except (TypeError, ValueError, KeyError):
                        pass
        if res:
            out[rno] = res
    return out


def form_depth(meeting):
    """每匹馬平均保留到幾多仗**賽前**往績。

    ⚠️ 呢個係歷史重抽最硬嘅限制，而且係單調隨年齡衰減。Sportsbet 每匹馬只出
    最近十幾仗，所以場次愈舊，嗰十幾仗入面愈多係**賽後**跑嘅，時點過濾之後
    剩返嘅賽前往績就愈少：

        2026-08 → 8.8 仗/匹      2026-02 → 4.8
        2026-04 → 6.0            2025-08 → 1.6

    1.6 仗嘅馬，近績趨勢／PI 平均／段速聚合／班次變化全部算唔出。所以舊場次
    重抽返嚟**唔會**好過現有 archive —— 現有嗰批係當時賽前抓嘅，深度完整。
    唔分開睇嘅話，「Sportsbet 差啲」其實只係「我哋手上往績少咗」。
    """
    from claw_sportsbet_form import (BASE, SportsbetFormFetcher,
                                     parse_runner_blocks, run_date)
    f = SportsbetFormFetcher(delay=0.0, verbose=False)
    kept = horses = 0
    for rid in meeting["races"]:
        url = f"{BASE}/{meeting['meetingId']}/{rid}/"
        if not f._cache_path(url).exists():
            continue
        for blk in parse_runner_blocks(f.get(url)):
            horses += 1
            kept += sum(1 for r in blk.get("runs", [])
                        if run_date(r) and run_date(r) < meeting["date"])
    return (kept / horses) if horses else 0.0


def picks_from_meeting(meeting_dir):
    """Meeting_Auto_Scoring.csv → {race_no: [norm_name 由第一位排落去]}。"""
    p = Path(meeting_dir) / "Meeting_Auto_Scoring.csv"
    if not p.exists():
        return {}
    by_race = {}
    with open(p, encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            try:
                by_race.setdefault(int(row["race_number"]), []).append(
                    (int(row["rank"]), norm(row["horse_name"])))
            except (TypeError, ValueError, KeyError):
                continue
    return {r: [n for _, n in sorted(v)] for r, v in by_race.items()}


def grade(picks_by_race, results):
    rows = []
    for rno, res in sorted(results.items()):
        picks = picks_by_race.get(rno)
        if not picks or not res:
            continue
        top3 = {h for h, p in res.items() if p <= 3}
        winner = next((h for h, p in res.items() if p == 1), None)
        if not top3 or winner is None:
            continue
        rows.append(race_metrics(picks, top3, winner=winner, actual_pos=res,
                                 field_size=max(res.values())))
    return rows


def report(label, rows):
    if not rows:
        print(f"{label}: 冇可評場次")
        return None
    s = summarize_races(rows)["counts"]
    n = len(rows)
    hits = sum(r["hits"] for r in rows)
    slots = sum(min(3, len(r["picks"])) for r in rows)
    out = {k: s[k] for k in KEYS}
    out.update(races=n, t3prec=hits / slots if slots else 0.0)
    # 互斥標籤（Gold / Good / Pass / 1 Hit / Miss，加起嚟等於場數）。
    # `KEYS` 係累積 KPI，而且 Gold 係 capture-at-4，唔可以由 Pass / Good
    # 簡單相減推出互斥分類。`race_metrics` 已經算好互斥標籤，直接數就得。
    lab = {}
    for row in rows:
        k = row["exclusive_label"]
        lab[k] = lab.get(k, 0) + 1
    out["labels"] = lab
    return out


def main():
    ap = argparse.ArgumentParser(description="兩個數據源逐場對比")
    ap.add_argument("--new", required=True, help="Sportsbet 重抽嘅 out-root")
    ap.add_argument("--old", help="現有 archive root（唔畀就只評 new）")
    ap.add_argument("--only", help="淨係做名入面含呢個字嘅場次")
    ap.add_argument("--json", help="把逐場結果寫落呢個檔")
    ap.add_argument("--min-depth", type=float, default=4.0,
                    help="每匹馬最少幾多仗賽前往績先當可比（預設 4）")
    args = ap.parse_args()

    from sb_backfill_archive import load_meeting_ids

    ids = load_meeting_ids()
    per_meeting = []
    agg = {"new": [], "old": []}          # 深度足夠
    thin = {"new": [], "old": []}         # 深度唔夠，分開報
    for name, meta in sorted(ids.items(), key=lambda kv: kv[1]["date"]):
        if args.only and args.only.lower() not in name.lower():
            continue
        new_dir = Path(args.new) / name
        if not (new_dir / "Meeting_Auto_Scoring.csv").exists():
            continue
        results = results_from_cache(meta)
        if not results:
            print(f"⚠️ {name}：cache 冇賽果，跳過")
            continue
        new_rows = grade(picks_from_meeting(new_dir), results)
        old_rows = []
        if args.old:
            for root in (Path(args.old), Path(args.old) / "Archive"):
                if (root / name / "Meeting_Auto_Scoring.csv").exists():
                    old_rows = grade(picks_from_meeting(root / name), results)
                    break
        # ⚠️ 只計兩邊都評到嘅場次，否則分母唔同，個對比會靜靜咁講大話
        if args.old and old_rows and len(new_rows) != len(old_rows):
            common = min(len(new_rows), len(old_rows))
            print(f"⚠️ {name}：new {len(new_rows)} 場 / old {len(old_rows)} 場，"
                  f"只取頭 {common} 場")
            new_rows, old_rows = new_rows[:common], old_rows[:common]
        depth = form_depth(meta)
        bucket = agg if depth >= args.min_depth else thin
        bucket["new"] += new_rows
        bucket["old"] += old_rows
        per_meeting.append({"meeting": name, "races": len(new_rows),
                            "form_depth": round(depth, 2),
                            "new": report(name, new_rows),
                            "old": report(name, old_rows) if old_rows else None})

    def block(title, pair):
        print(f"\n{title}")
        print(f"{'':30}{'Sportsbet':>12}{'現有源':>12}")
        n_, o_ = report("new", pair["new"]), report("old", pair["old"])
        if not n_:
            print("  （冇場次）")
            return None, None
        for k, lab in labels:
            ov_ = f"{o_[k]:>12}" if o_ else f"{'-':>12}"
            print(f"{lab:30}{n_[k]:>12}{ov_}")
        ov_ = f"{o_['t3prec']:>11.1%}" if o_ else f"{'-':>12}"
        print(f"{'前三精準':30}{n_['t3prec']:>11.1%}{ov_}")
        # 互斥標籤 —— 呢個先係可以直接當百分比讀嘅
        print(f"{'  ── 互斥標籤（%）':30}")
        rn = n_.get("races") or 1
        ro = (o_.get("races") or 1) if o_ else 1
        for k in ("Gold", "Good", "Pass", "1 Hit", "Miss"):
            a = n_.get("labels", {}).get(k, 0)
            b = o_.get("labels", {}).get(k, 0) if o_ else None
            bs = f"{100*b/ro:>11.1f}%" if b is not None else f"{'-':>12}"
            print(f"{'  ' + k:30}{100*a/rn:>11.1f}%{bs}")
        return n_, o_

    labels = [("races", "場次"), ("gold", "Gold Top4 包辦前三"),
              ("good_positional", "Good Top2 兩馬上名"),
              ("pass", "Pass Top3 任二上名"),
              ("champion", "首選=頭馬"), ("winner_in_top3", "頭馬入前三")]
    n, o = block(f"■ 往績深度 ≥{args.min_depth} 仗/匹（可比）", agg)
    if thin["new"]:
        block(f"■ 往績深度 <{args.min_depth} 仗/匹 —— Sportsbet 手上往績太少，"
              f"呢度嘅差距量緊數據量唔係數據源", thin)
    if not n:
        print("冇任何可評場次 —— 先跑 sb_backfill_archive.py --run")
        return 1

    races = n["races"]
    if races < 60:
        print(f"\n⚠️ 得 {races} 場（{races*3} 個前三位）。呢個樣本量度唔到幾個"
              f"百分點嘅差別 —— 當方向睇，唔好當幅度引用。")
    if args.json:
        Path(args.json).write_text(json.dumps(per_meeting, ensure_ascii=False,
                                              indent=1), encoding="utf-8")
        print(f"\n逐場結果 → {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
