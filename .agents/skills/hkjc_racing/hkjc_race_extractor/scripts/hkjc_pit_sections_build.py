"""段速 FT 組件嘅 as-of 表（pit_sections.json）：每季標準、每日快慢、正常段數、z 常數。

定義同 EXP-20261114-04 用嘅 `docs/experiments/patches/hkjc_hist_sectional_features_v2.py` 一樣；
live 計法喺 `hkjc_racing_engine/pit_sections.py`（同一份表）。忠實度：回放 2023-09..10 1,431 匹 speed_score 1,426 匹一致。
來源：外置碟 `hkjc-history/parsed/sectionals.jsonl.gz`（`backfill_history.py parse`）。輸出寫本機資料根
`HK_Racing/HKJC_Sections/pit_sections.json`（live 讀；唔放外置碟 —— 拔碟唔可以令 live 靜靜失效）。

用法：
  python3 hkjc_pit_sections_build.py build                # 由現有解析檔重建表
  python3 hkjc_pit_sections_build.py update               # 賽後：補抓新賽日分段頁（慢速）→ 解析 → 重建；失敗推 Telegram（primary）
z 常數固定（2024-08 前 first_v／total_v，EXP-20261114-04 arm 用嘅值），唔隨重建改。
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
sys.path.insert(0, str(REPO))
VOLUME = Path("/Volumes/Kelvin Hardisk 1")
PARSED = VOLUME / "WongChoi-Archive" / "hkjc-history" / "parsed" / "sectionals.jsonl.gz"
CLS = {"第一班": "C1", "第二班": "C2", "第三班": "C3", "第四班": "C4", "第五班": "C5"}
Z_FIXED = {"first_v": [-0.023181854486679126, 0.4010729497842783], "total_v": [0.047211873313238485, 0.17955878369564107]}


def season_of(d: str) -> int:
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def out_path() -> Path:
    import wongchoi_paths
    return Path(wongchoi_paths.HK_RACING) / "HKJC_Sections" / "pit_sections.json"


def load_rows(parsed: Path = PARSED) -> list[dict]:
    rows = []
    for line in gzip.open(parsed, "rt", encoding="utf-8"):
        r = json.loads(line)
        H = r.get("horses") or []
        if not H or not r.get("distance"):
            continue
        nsec = len(H[0]["sections"])
        if nsec < 3:
            continue
        ven = "HV" if "跑馬地" in str(r.get("venue")) or "Happy" in str(r.get("venue")) else "ST"
        track = "AWT" if r.get("surface") == "全天候" else ven
        for h in H:
            t = [s.get("time") for s in h["sections"]]
            if len(t) != nsec or any(x is None for x in t) or not h.get("code"):
                continue
            fin = str(h.get("finish", "")).split()[0]
            rows.append({"date": r["date"], "season": season_of(r["date"]), "track": track, "dist": r["distance"],
                         "cls": CLS.get(r.get("class") or "", "OT"), "fin": int(fin) if fin.isdigit() else None, "secs": t})
    return rows


def build(rows: list[dict]) -> dict:
    seasons = sorted({r["season"] for r in rows})
    standards = {}
    for s in seasons + [max(seasons) + 1]:
        cell, cell_all = defaultdict(list), defaultdict(list)
        for r in rows:
            if r["season"] < s and r["fin"] is not None and r["fin"] <= 3:
                for i, v in enumerate(r["secs"]):
                    cell[(r["track"], r["dist"], r["cls"], i)].append(v)
                    cell_all[(r["track"], r["dist"], "ALL", i)].append(v)
        st = {f"{k[0]}|{k[1]}|{k[2]}|{k[3]}": float(np.median(v)) for k, v in cell.items() if len(v) >= 20}
        st.update({f"{k[0]}|{k[1]}|{k[2]}|{k[3]}": float(np.median(v)) for k, v in cell_all.items() if len(v) >= 20})
        if st:
            standards[str(s)] = st
    var = defaultdict(lambda: defaultdict(list))
    cnt = defaultdict(lambda: defaultdict(int))
    for r in rows:
        cnt[f"{r['track']}|{r['dist']}"][len(r["secs"])] += 1
        st = standards.get(str(r["season"])) or {}
        n = len(r["secs"])
        sv = [st.get(f"{r['track']}|{r['dist']}|{r['cls']}|{i}") or st.get(f"{r['track']}|{r['dist']}|ALL|{i}") for i in range(n)]
        if any(x is None for x in sv):
            continue
        dv = [a - b for a, b in zip(r["secs"], sv)]
        first_len = r["dist"] - 400 * (n - 1)
        var[f"{r['date']}|{r['track']}"]["first"].append(dv[0] / (first_len / 400))
        var[f"{r['date']}|{r['track']}"]["l400"].append(dv[-1])
    return {"version": 1, "seasons": sorted(standards), "last_date": max(r["date"] for r in rows), "z": Z_FIXED,
            "standards": standards, "variant": {k: {kk: float(np.median(vv)) for kk, vv in v.items()} for k, v in var.items()},
            "nsec": {k: max(v, key=v.get) for k, v in cnt.items()}}


def write(table: dict) -> Path:
    p = out_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(table, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)
    return p


def notify(msg: str) -> None:
    try:
        sys.path.insert(0, str(REPO / ".agents/skills/shared_racing/scripts"))
        import racing_telegram
        racing_telegram.send_message(msg, audience="primary")
    except Exception as exc:  # 通知失敗唔可以令更新扮成功
        print(f"[notify failed] {exc}: {msg}", file=sys.stderr)


def update() -> int:
    # 同一時間只准一個更新（一次覆盤完成幾個賽日會叫幾次）—— 唔好有兩個抓取器同時打 HKJC
    import fcntl
    lock = open(out_path().parent.with_name("pit_sections_update.lock") if out_path().parent.exists()
                else Path("/tmp/pit_sections_update.lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("另一個段速表更新跑緊，今次唔做")
        return 0
    if not os.path.ismount(VOLUME):
        notify("⚠️ HKJC 段速表冇更新：外置碟冇掛載（live 繼續用上一版 pit_sections.json）")
        return 2
    bf = [sys.executable, str(HERE / "backfill_history.py")]
    for args in (["tasks"], ["run", "--kinds", "sectional"], ["parse"]):
        r = subprocess.run(bf + args, capture_output=True, text=True)
        if r.returncode != 0:
            notify(f"⚠️ HKJC 段速表冇更新：backfill {' '.join(args)} 失敗（{r.stderr[-300:]}）；live 繼續用上一版")
            return 1
    table = build(load_rows())
    p = write(table)
    print(f"段速表更新到 {table['last_date']} → {p}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("build", "update"))
    a = ap.parse_args()
    if a.cmd == "update":
        return update()
    table = build(load_rows())
    print(f"標準季 {table['seasons']}；當日快慢 {len(table['variant'])}；到 {table['last_date']} → {write(table)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
