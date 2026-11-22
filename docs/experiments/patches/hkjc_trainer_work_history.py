#!/usr/bin/env python3
"""EXP-20261121-41 練馬師／副練馬師親自操（上仗至今）有冇訊號 —— 重抓歷史馬匹晨操頁。唯讀研究。

HKJC 每匹馬嘅晨操頁（trackworkresult）有大約半年以上紀錄，入面包埋「出賽」行。
步驟：
  fetch   逐匹（2026-05 起有晨操檔嘅馬）抓晨操頁，解析後存 <out>/rows/<horseid>.json（已有就跳過）
  measure 每場出賽：上仗（頁內最近一行出賽，日期 < 今仗）至今仗前一日，數練馬師／副練馬師親自快操＋試閘；
          上仗早過晨操頁最早紀錄 = 窗口唔齊，唔計。對照最終賠率分段同模型排名分段（賽日 bootstrap）。

    python3 hkjc_trainer_work_history.py fetch --out <dir> [--workers 4]
    python3 hkjc_trainer_work_history.py measure --out <dir> --model-run <hkjc_eval_harness run 輸出>
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import glob
import json
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / ".agents/skills/hkjc_racing/hkjc_race_extractor/scripts"))
import extract_trackwork as xt  # noqa: E402

ROOT = Path((REPO / ".wongchoi_hk_data_root").read_text(encoding="utf-8").strip())
SINCE = "2026-05-01"
ROLES = ("練馬師", "副練馬師")


def horses_from_trackwork() -> dict[str, dict]:
    out = {}
    for f in glob.glob(str(ROOT / "20*_*" / "*晨操.json")):
        if Path(f).parent.name[:10] < SINCE:
            continue
        for h in (json.loads(Path(f).read_text(encoding="utf-8")).get("horses") or {}).values():
            if h.get("horseid"):
                out.setdefault(h["horseid"], {"horseid": h["horseid"], "horse_name": h.get("horse_name", ""),
                                              "trainer": h.get("trainer", ""), "jockey": ""})
    return out


def fetch_one(horse: dict, rows_dir: Path) -> str:
    target = rows_dir / f"{horse['horseid']}.json"
    if target.exists():
        return "cached"
    for attempt in range(3):
        try:
            html = xt.fetch_url(xt.trackworkresult_url(horse["horseid"]))
            rows = xt.parse_trackwork_rows(html, horse, dt.date.today() + dt.timedelta(days=1), 400)
            target.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
            return "ok"
        except Exception:  # noqa: BLE001
            time.sleep(2 * (attempt + 1))
    return "failed"


def cmd_fetch(args) -> int:
    rows_dir = args.out / "rows"
    rows_dir.mkdir(parents=True, exist_ok=True)
    horses = list(horses_from_trackwork().values())
    print(f"{len(horses)} 匹馬", flush=True)
    done = collections.Counter()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for i, status in enumerate(pool.map(lambda h: fetch_one(h, rows_dir), horses), 1):
            done[status] += 1
            if i % 100 == 0:
                print(f"  {i}/{len(horses)} {dict(done)}", flush=True)
    print(f"done {dict(done)}", flush=True)
    return 0


def load_results() -> dict:
    res = {}
    for f in glob.glob(str(ROOT / "20*_*" / "*全日賽果.json")):
        date = Path(f).parent.name[:10]
        if date < SINCE:
            continue
        for rk, race in json.loads(Path(f).read_text(encoding="utf-8")).items():
            if not isinstance(race, dict):
                continue
            for x in race.get("results") or []:
                try:
                    brand = str(x["horse_name"]).split("(")[-1].rstrip(")")
                    res[(date, int(race.get("race_no") or rk), brand)] = (int(x["pos"]), float(x["win_odds"]), int(x["horse_no"]))
                except (KeyError, ValueError, TypeError):
                    pass
    return res


def band(o):
    return 0 if o <= 3 else 1 if o <= 6 else 2 if o <= 12 else 3 if o <= 25 else 4


def gap(rows, key, sel):
    cells = collections.defaultdict(lambda: [0, 0, 0, 0])
    for r in rows:
        b = r[key]
        if b is None:
            continue
        c = cells[b]
        if sel(r):
            c[0] += r["plc"]; c[1] += 1
        else:
            c[2] += r["plc"]; c[3] += 1
    num = den = 0.0
    for a, n1, b, n0 in cells.values():
        if n1 and n0:
            w = n1 * n0 / (n1 + n0); num += w * (a / n1 - b / n0); den += w
    return 100 * num / den if den else float("nan")


def ci(rows, key, sel, n=2000):
    rng = random.Random(0); by = collections.defaultdict(list)
    for r in rows:
        by[r["date"]].append(r)
    ks = sorted(by)
    out = sorted(gap([x for k in rng.choices(ks, k=len(ks)) for x in by[k]], key, sel) for _ in range(n))
    out = [o for o in out if o == o]
    return out[int(.025 * len(out))], out[int(.975 * len(out)) - 1]


def cmd_measure(args) -> int:
    res = load_results()
    rank = {}
    if args.model_run:
        for line in args.model_run.read_text(encoding="utf-8").splitlines():
            r = json.loads(line) if line.strip() else {}
            if "date" in r:
                for i, no in enumerate(r["picks"]):
                    rank[(r["date"], r["race"], no)] = i + 1
    trainers = {h["horseid"]: h["trainer"] for h in horses_from_trackwork().values()}
    rows_out, skipped = [], collections.Counter()
    for f in sorted((args.out / "rows").glob("*.json")):
        hid = f.stem
        entries = json.loads(f.read_text(encoding="utf-8"))
        for e in entries:
            e["rider_role"] = xt.classify_rider_role(e.get("rider", ""), e.get("details", ""), trainers.get(hid, ""))
        earliest = min((e["date"] for e in entries), default="")
        races = sorted({e["date"] for e in entries if xt.is_race_row(e)})
        brand = hid[-4:]
        for i, day in enumerate(races):
            if day < SINCE:
                continue
            hit = [k for k in res if k[0] == day and k[2] == brand]
            if not hit:
                skipped["no_result"] += 1
                continue
            prev = races[i - 1] if i else None
            if prev is None:
                skipped["no_prev_race_in_page"] += 1   # 上仗早過晨操頁最早紀錄 → 窗口唔齊
                continue
            start21 = (dt.date.fromisoformat(day) - dt.timedelta(days=21)).isoformat()
            windows = {"上仗至今": [e for e in entries if prev < e["date"] < day and not xt.is_race_row(e)],
                       "近21日": [e for e in entries if start21 <= e["date"] < day and not xt.is_race_row(e)]}
            pos, odds, no = res[hit[0]]
            r = {"date": day, "plc": pos <= 3, "oband": band(odds), "days": (dt.date.fromisoformat(day) - dt.date.fromisoformat(prev)).days}
            for wname, window in windows.items():
                for role in ROLES:
                    r[(wname, role)] = sum(1 for e in window if e.get("rider_role") == role and e.get("type") in ("gallop", "trial"))
            k = rank.get((day, hit[0][1], no))
            r["mband"] = None if k is None else min((k - 1) // 2, 5)
            rows_out.append(r)
    print(f"出賽 {len(rows_out)} 次（{min(r['date'] for r in rows_out)} → {max(r['date'] for r in rows_out)}）；略過 {dict(skipped)}")
    print(f"  上仗至今日數中位 {sorted(r['days'] for r in rows_out)[len(rows_out)//2]} 日")
    for wname, role in [(w, ro) for w in ("近21日", "上仗至今") for ro in ROLES]:
        for thr in (1, 2, 3):
            sel = lambda r, key=(wname, role), thr=thr: r[key] >= thr
            a = [r for r in rows_out if sel(r)]; b = [r for r in rows_out if not sel(r)]
            if len(a) < 20:
                continue
            g1, (l1, h1) = gap(rows_out, "oband", sel), ci(rows_out, "oband", sel)
            m = [r for r in rows_out if r["mband"] is not None]
            g2, (l2, h2) = gap(m, "mband", sel), ci(m, "mband", sel)
            pa = 100 * sum(r["plc"] for r in a) / len(a); pb = 100 * sum(r["plc"] for r in b) / len(b)
            print(f"[{wname}] {role}親自快操／試閘 ≥{thr}：n={len(a)}（{100*len(a)/len(rows_out):.1f}%）上名 {pa:.1f}% vs {pb:.1f}% ｜"
                  f"控制賠率 {g1:+.1f}pp [{l1:+.1f}, {h1:+.1f}] ｜控制模型排名 {g2:+.1f}pp [{l2:+.1f}, {h2:+.1f}]"
                  f"（模型樣本 {sum(1 for r in m if sel(r))}）")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("fetch", "measure"))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--model-run", type=Path)
    args = ap.parse_args()
    return cmd_fetch(args) if args.cmd == "fetch" else cmd_measure(args)


if __name__ == "__main__":
    raise SystemExit(main())
