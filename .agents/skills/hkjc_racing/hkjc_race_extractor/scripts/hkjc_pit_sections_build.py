"""段速 FT 組件嘅 as-of 表（pit_sections.json）：每季標準、每日快慢、正常段數、z 常數。

定義同 EXP-20261114-04 用嘅 `docs/experiments/patches/hkjc_hist_sectional_features_v2.py` 一樣；
live 計法喺 `hkjc_racing_engine/pit_sections.py`（同一份表）。忠實度：回放 2023-09..10 1,431 匹 speed_score 1,426 匹一致。
來源：外置碟 `hkjc-history/parsed/sectionals.jsonl.gz`（`backfill_history.py parse`）。輸出寫本機資料根
`HK_Racing/HKJC_Sections/pit_sections.json`（live 讀；唔放外置碟 —— 拔碟唔可以令 live 靜靜失效）。

用法：
  python3 hkjc_pit_sections_build.py build                # 由現有解析檔重建表
  python3 hkjc_pit_sections_build.py update               # 賽後：補抓新賽日分段頁（慢速）→ 解析 → 重建；失敗推 Telegram（primary）
另外生成 `debut_trainer.json`（初出馬練馬師紀錄，決定 3，見 hkjc_racing_engine/debut_trainer.py）。
z 常數固定（2024-08 前 first_v／total_v，EXP-20261114-04 arm 用嘅值），唔隨重建改。
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / ".agents/scripts"))
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


def _trainer_map() -> dict:
    """(日期, 場次, 馬號) → 練馬師，由賽果庫（舊季研究檔＋現行庫，兩種格式）攞。"""
    import build_comprehensive_stats as bcs
    out = {}
    files = sorted((bcs.HK_RACING / "_research_old_season_results").glob("*.json"))
    files += sorted(bcs.DB_ROOT.glob("hkjc results */*/full_day_results.json"))
    for fp in files:
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for key, race in data.items():
            if not isinstance(race, dict):
                continue
            day = str(race.get("racedate") or fp.parent.name)[:10]
            m = re.search(r"\d+", str(race.get("race_no") or key))
            if not m:
                continue
            for row in race.get("results", []):
                if row.get("horse_no") and row.get("trainer"):
                    out[(day, int(m.group()), str(row["horse_no"]))] = row["trainer"]
    return out


def debut_events(parsed: Path = PARSED) -> list:
    """初出馬事件 [[日期, 練馬師, 入頭三]]（決定 3，EXP-20261114-06）：分段頁第一次出現、喺 2020-09-01 或之後。"""
    races = []
    for line in gzip.open(parsed, "rt", encoding="utf-8"):
        r = json.loads(line)
        races.append((r["date"], int(r["race_no"]), r.get("horses") or []))
    races.sort(key=lambda t: (t[0], t[1]))
    tmap = _trainer_map()
    seen, events = set(), []
    for d, n, H in races:
        for h in H:
            code = h.get("code")
            if not code or code in seen:
                continue
            seen.add(code)
            tr = tmap.get((d, n, str(h.get("horse_no"))))
            fin = str(h.get("finish", "")).split()[0] if h.get("finish") else ""
            if d >= "2020-09-01" and tr:
                events.append([d, tr, int(fin.isdigit() and int(fin) <= 3)])
    return events


def write_debut(events: list) -> Path:
    p = out_path().parent / "debut_trainer.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({"version": 1, "events": events}, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)
    return p


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


def market_history_table() -> dict:
    """上仗賠率表（EXP-20261115-07）：每匹馬每仗嘅 HKJC 最終獨贏賠率（舊季研究檔＋現行庫，同回放一樣嘅來源）。"""
    sys.path.insert(0, str(REPO / ".agents/skills/hkjc_racing/hkjc_reflector/scripts"))
    import hkjc_history_replay_pit
    df = hkjc_history_replay_pit.load_all_rows_extended()
    df = df[df["Odds"].notna() & df["HorseID"].notna() & df["Rank"].notna()]
    horses: dict[str, list] = {}
    for r in df.itertuples():
        horses.setdefault(str(r.HorseID), []).append([str(r.Date)[:10], float(r.Odds)])
    for v in horses.values():
        v.sort()
    return {"version": 1, "last_date": max(str(d)[:10] for d in df["Date"]), "horses": horses}


def write_market_history(table: dict) -> Path:
    p = out_path().with_name("market_history.json")
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(table, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)
    return p


def incident_history_table() -> dict:
    """上仗事件報告表（EXP-20261116-06）：每匹馬每仗嘅事件報告旗（W 走外疊冇遮擋／M 醫療；null = 嗰場冇報告）。
    來源同回放索引一樣（舊季研究賽果＋賽果庫 full_day_results.json），本機資料根，唔使外置碟。"""
    import json as _json
    sys.path.insert(0, str(REPO / ".agents/skills/hkjc_racing/hkjc_reflector/scripts"))
    sys.path.insert(0, str(REPO / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts"))
    import build_comprehensive_stats as bcs
    import hkjc_history_replay_build as rb
    from hkjc_racing_engine.incident_history import flags
    files = sorted((bcs.HK_RACING / "_research_old_season_results").glob("*.json"))
    files += sorted(bcs.DB_ROOT.glob("hkjc results */*/full_day_results.json"))
    races = {}
    for fp in files:
        try:
            data = _json.loads(fp.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for key, race in data.items():
            if not isinstance(race, dict):
                continue
            if not race.get("racedate"):
                race = rb._normalise_new_schema(race, fp)
                if race is None:
                    continue
            m = re.search(r"\d+", str(race.get("race_no") or key))
            if m:
                races[(str(race["racedate"])[:10], int(m.group()))] = race
    horses: dict[str, list] = {}
    for (d, _n), race in sorted(races.items()):
        inc = race.get("incident_report")
        per = rb._incident_by_horse(inc) if inc else None
        for row in race.get("results", []):
            code = rb._code(str(row.get("horse_name") or ""))
            if not code or not rb._started(row):
                continue
            horses.setdefault(code, []).append([d, None if per is None else flags(per.get(code, ""))])
    for v in horses.values():
        v.sort(key=lambda r: r[0])
    return {"version": 1, "last_date": max(d for d, _ in races) if races else None, "horses": horses}


def write_incident_history(table: dict) -> Path:
    p = out_path().with_name("incident_history.json")
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(table, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)
    return p


def win_ratings_table() -> dict:
    """贏馬評分表（EXP-20261115-15 降班＋評分跌返贏馬分）：HKJC 馬匹頁每次贏馬嘅 [日期, 評分]。
    live 近 6 仗以外嘅贏馬靠呢個表；近 6 仗由 Logic rating_trend 補。"""
    horses: dict[str, list] = {}
    path = PARSED.with_name("horses.jsonl.gz")
    for line in gzip.open(path, "rt", encoding="utf-8"):
        r = json.loads(line)
        code = str(r.get("horse_id") or "").rsplit("_", 1)[-1]
        for x in r.get("runs") or []:
            pos, rating = str(x.get("pos") or "").strip(), str(x.get("rating") or "").strip()
            try:
                dd, mm, yy = str(x.get("date") or "").split("/")
            except ValueError:
                continue
            if pos.lstrip("0") == "1" and rating.isdigit():
                horses.setdefault(code, []).append([f"{yy}-{mm}-{dd}", int(rating)])
    for v in horses.values():
        v.sort()
    return {"version": 1, "horses": horses}


def write_win_ratings(table: dict) -> Path:
    p = out_path().with_name("win_ratings.json")
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(table, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)
    return p


def run_style_table() -> dict:
    """跑法歷史表（EXP-20261116-01 檔位 × 跑法）：每匹馬每仗「第一個沿途位置 ÷ 完成匹數」（同回放 freeze.py 一樣嘅來源同計法）。"""
    sys.path.insert(0, str(REPO / ".agents/skills/hkjc_racing/hkjc_reflector/scripts"))
    import hkjc_history_replay_pit
    df = hkjc_history_replay_pit.load_all_rows_extended()
    df = df[df["Rank"].notna()].copy()
    df["d"] = df["Date"].astype(str).str[:10]
    df["F"] = df.groupby(["d", "RaceNo"])["Rank"].transform("count")
    horses: dict[str, list] = {}
    for r in df.itertuples():
        rp = str(r.RunningPos or "").split()
        if r.HorseID is None or r.HorseID != r.HorseID or not rp or not rp[0].isdigit() or not r.F:
            continue
        horses.setdefault(str(r.HorseID), []).append([r.d, round(int(rp[0]) / float(r.F), 4)])
    for v in horses.values():
        v.sort()
    return {"version": 1, "last_date": str(df["d"].max()), "horses": horses}


def battlefield_table() -> dict:
    """戰場全景歷史表（Kelvin 2026-11-17「呢個場地呢個距離，歷史上利放頭／守中／後上？利內中外檔？」）。

    場地 × 路程（谷草／田草／泥地 × 米數），2019/20 起全部賽果：
      實際走位 = 第一個沿途位 ÷ 完成匹數（同 run_style.py 同一個標準：≤30% 放頭、≤60% 守中、其餘後上）
      檔位段  = 1–4 內、5–9 中、10+ 外（同 draw_style.draw_band 一樣）
    每格：馬次、上名率（頭三）、勝出率；`base` = 全部馬次上名率。純顯示（戰場全景），唔入分。
    """
    import sys
    sys.path.insert(0, str(REPO / ".agents/skills/hkjc_racing/hkjc_reflector/scripts"))
    sys.path.insert(0, str(REPO / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts"))
    import hkjc_history_replay_pit
    from hkjc_racing_engine.run_style import classify, fraction
    df = hkjc_history_replay_pit.load_all_rows_extended()
    df = df[df["Rank"].notna()].copy()
    df["d"] = df["Date"].astype(str).str[:10]
    df["F"] = df.groupby(["d", "RaceNo"])["Rank"].transform("count")
    acc: dict = {}
    races: dict = {}
    for r in df.itertuples():
        surface = "泥地" if str(r.Track) == "AWT" else ("谷草" if str(r.Venue) == "跑馬地" else "田草")
        try:
            dist = int(float(r.Distance))
        except (TypeError, ValueError):
            continue
        key = f"{surface}|{dist}"
        cell = acc.setdefault(key, {"all": [0, 0, 0], "style": {}, "draw": {}})
        races.setdefault(key, set()).add((r.d, r.RaceNo))
        placed, won = float(r.Rank <= 3), float(r.Rank == 1)

        def add(slot):
            slot[0] += 1; slot[1] += placed; slot[2] += won
        add(cell["all"])
        rp = str(r.RunningPos or "").split()
        style = classify(fraction(rp[0], r.F)) if rp and rp[0].isdigit() else None
        if style:
            add(cell["style"].setdefault(style, [0, 0, 0]))
        try:
            d = int(float(r.Draw))
        except (TypeError, ValueError):
            d = 0
        if d > 0:
            band = "內檔" if d <= 4 else ("中檔" if d <= 9 else "外檔")
            add(cell["draw"].setdefault(band, [0, 0, 0]))

    def fmt(v):
        return {"n": int(v[0]), "place": round(v[1] / v[0], 4), "win": round(v[2] / v[0], 4)} if v[0] else None
    cells = {}
    for key, c in acc.items():
        if len(races[key]) < 20:
            continue
        cells[key] = {"races": len(races[key]), "base": fmt(c["all"]),
                      "style": {k: fmt(v) for k, v in c["style"].items() if v[0] >= 30},
                      "draw": {k: fmt(v) for k, v in c["draw"].items() if v[0] >= 30}}
    return {"version": 1, "since": str(df["d"].min()), "last_date": str(df["d"].max()), "cells": cells}


def write_battlefield(table: dict) -> Path:
    p = out_path().with_name("battlefield.json")
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(table, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)
    return p


def write_run_style(table: dict) -> Path:
    p = out_path().with_name("run_style.json")
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(table, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)
    return p


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
    for args in (["tasks"], ["run", "--kinds", "sectional", "--quiet"], ["parse"]):
        r = subprocess.run(bf + args, capture_output=True, text=True)
        if r.returncode != 0:
            notify(f"⚠️ HKJC 段速表冇更新：backfill {' '.join(args)} 失敗（{r.stderr[-300:]}）；live 繼續用上一版")
            return 1
    table = build(load_rows())
    p = write(table)
    write_debut(debut_events())
    mh = market_history_table()
    write_market_history(mh)
    write_win_ratings(win_ratings_table())
    write_run_style(run_style_table())
    write_battlefield(battlefield_table())
    ih = incident_history_table()
    write_incident_history(ih)
    sys.path.insert(0, str(REPO / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts"))
    from hkjc_racing_engine.incident_history import wording_check
    for warn in wording_check(ih):
        notify(f"⚠️ {warn}")
    print(f"段速表更新到 {table['last_date']} → {p}；上仗賠率表到 {mh['last_date']}（{len(mh['horses'])} 匹）")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("build", "update"))
    a = ap.parse_args()
    if a.cmd == "update":
        return update()
    table = build(load_rows())
    print(f"標準季 {table['seasons']}；當日快慢 {len(table['variant'])}；到 {table['last_date']} → {write(table)}")
    mh = market_history_table()
    print(f"上仗賠率表 {len(mh['horses'])} 匹、到 {mh['last_date']} → {write_market_history(mh)}")
    rs = run_style_table()
    print(f"跑法歷史表 {len(rs['horses'])} 匹、到 {rs['last_date']} → {write_run_style(rs)}")
    bf = battlefield_table()
    print(f"戰場全景歷史表 {len(bf['cells'])} 個場地路程、{bf['since']} → {bf['last_date']} → {write_battlefield(bf)}")
    ih = incident_history_table()
    print(f"上仗事件報告表 {len(ih['horses'])} 匹、到 {ih['last_date']} → {write_incident_history(ih)}")
    ev = debut_events()
    print(f"初出馬事件 {len(ev)} → {write_debut(ev)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
