"""HKJC 歷史數據補抓（docs/plans/2026-11-13-hkjc-historic-backfill.md）。

抓兩類頁（2019-09 起）：
  sectional  分段時間及位置（每場一頁）：每匹每段時間、走位、落後頭馬距離、尾段每 200 米
  horse      馬匹資料頁（每匹一頁，連退役馬）：逐仗評分、配備、體重、欄位、場地狀況……
（試閘頁只有近一季日期，舊日期會靜靜返最新一頁 → 唔抓，見計劃。）

安全（Kelvin 2026-11-13：「唔好太快，唔好俾馬會 block」）：
  一次一個請求；每個請求之間隨機 4–8 秒；每 100 頁休息 2–3 分鐘；
  香港賽馬時段暫停（週三 17:00–23:59、週六日 11:00–19:30 HKT）；
  頁面唔似預期（block／驗證碼／空白）或 HTTP 錯 → 等 15 分鐘；連續 3 次 → 停並推 Telegram（primary）。
儲存（Kelvin：「所有數據去 harddrive」）：全部寫 /Volumes/Kelvin Hardisk 1/WongChoi-Archive/hkjc-history/；
  外置碟冇掛載就拒絕執行（唔會靜靜寫返 Mac 內置碟）。

用法：
  python3 backfill_history.py tasks            # 由賽果庫砌場次清單
  python3 backfill_history.py run              # 長跑（斷點續抓）；先 sectional 後 horse
  python3 backfill_history.py parse            # 原始頁 → parsed/*.jsonl.gz
  python3 backfill_history.py status
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import gzip
import json
import os
import random
import re
import sys
import time
from pathlib import Path

VOLUME = Path("/Volumes/Kelvin Hardisk 1")
BASE = VOLUME / "WongChoi-Archive" / "hkjc-history"
RAW = BASE / "raw"
PARSED = BASE / "parsed"
STATE = BASE / "state"
REPO = Path(__file__).resolve().parents[5]
SECT_URL = "https://racing.hkjc.com/racing/information/Chinese/Racing/DisplaySectionalTime.aspx?RaceDate={d}&RaceNo={n}"
HORSE_URL = "https://racing.hkjc.com/zh-hk/local/information/horse?horseid={h}"
DELAY = (4.0, 8.0)
LONG_PAUSE_EVERY, LONG_PAUSE = 100, (120.0, 180.0)
FAIL_WAIT, MAX_CONSEC_FAIL = 15 * 60, 3
HKT = dt.timezone(dt.timedelta(hours=8))


def require_volume() -> None:
    if not os.path.ismount(VOLUME):
        sys.exit(f"❌ 外置碟 {VOLUME} 冇掛載 —— 唔寫（避免靜靜寫返 Mac 內置碟）")
    for p in (RAW / "sectional", RAW / "horse", RAW / "horse_all", PARSED, STATE):
        p.mkdir(parents=True, exist_ok=True)


def notify(msg: str) -> None:
    try:
        sys.path.insert(0, str(REPO / ".agents/skills/shared_racing/scripts"))
        import racing_telegram
        racing_telegram.send_message(msg, audience="primary")
    except Exception as exc:  # 通知失敗唔可以令抓取扮成功；記 log
        print(f"[notify failed] {exc}: {msg}", flush=True)


def log(msg: str) -> None:
    line = f"{dt.datetime.now(HKT):%Y-%m-%d %H:%M:%S} HKT {msg}"
    print(line, flush=True)
    with open(STATE / "run.log", "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


# ---------------------------------------------------------------- 任務清單
def results_races() -> list[dict]:
    sys.path.insert(0, str(REPO))
    import wongchoi_paths
    root = Path(wongchoi_paths.HK_RACING)
    files = sorted(glob.glob(str(root / "_research_old_season_results/*.json"))) + \
        sorted(glob.glob(str(root / "HKJC_Race_Results_Database/hkjc results */*/*.json")))
    seen, out = set(), []
    for f in files:
        try:
            payload = json.loads(Path(f).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for key, race in payload.items():
            if not isinstance(race, dict) or not race.get("racedate"):
                continue
            no = str(race.get("race_no") or key).strip()
            m = re.search(r"\d+", no)
            if not m:
                continue
            rid = (str(race["racedate"]), int(m.group()))
            if rid in seen:
                continue
            seen.add(rid)
            out.append({"date": rid[0], "race_no": rid[1], "venue": str(race.get("venue") or "")})
    out.sort(key=lambda r: (r["date"], r["race_no"]), reverse=True)    # 新到舊：先抓同現有賽績檔重疊嘅，方便即刻核對
    return out


def cmd_tasks(_args) -> None:
    races = results_races()
    (STATE / "races.json").write_text(json.dumps(races, ensure_ascii=False), encoding="utf-8")
    print(f"{len(races)} 場；{races[-1]['date']} → {races[0]['date']}")


def sect_path(r: dict) -> Path:
    return RAW / "sectional" / r["date"][:4] / f"{r['date']}_R{r['race_no']:02d}.html.gz"


def horse_path(h: str) -> Path:
    return RAW / "horse" / f"{h}.html.gz"


def horse_all_path(h: str) -> Path:
    return RAW / "horse_all" / f"{h}.html.gz"


def horse_ids_from_sectionals() -> list[str]:
    ids = set()
    for p in sorted((RAW / "sectional").rglob("*.html.gz")):
        ids.update(re.findall(r"horseid=(HK_\d{4}_[A-Z]\d{3})", gzip.open(p, "rt", encoding="utf-8", errors="ignore").read()))
    return sorted(ids)


# ---------------------------------------------------------------- 抓取
def in_race_hours(now: dt.datetime) -> bool:
    t = now.hour * 60 + now.minute
    if now.weekday() == 2:                       # 週三夜馬
        return t >= 17 * 60
    if now.weekday() in (5, 6):                  # 週六日日馬
        return 11 * 60 <= t <= 19 * 60 + 30
    return False


def looks_valid(kind: str, html: str) -> str | None:
    """返回 'ok' / 'empty'（頁面話未有資料）/ None（唔似預期 → 當失敗）。"""
    if kind == "sectional":
        if "race_table" in html and "分段時間" in html:
            return "ok"
        if "稍後公佈" in html and "分段時間及位置" in html:
            return "empty"
        return None
    if kind == "horse_all" and "所有往績紀錄" not in html:
        return None
    if "horseProfile" in html and "往績紀錄" in html:
        return "ok"
    return None


def fetch(url: str) -> tuple[int, str]:
    from curl_cffi import requests as cffi_requests
    resp = cffi_requests.get(url, impersonate="chrome120", timeout=40)
    return resp.status_code, resp.text


def cmd_run(args) -> None:
    races = json.loads((STATE / "races.json").read_text(encoding="utf-8"))
    empty_file = STATE / "empty.json"
    empty = set(json.loads(empty_file.read_text())) if empty_file.exists() else set()
    count = consec = 0
    started = time.time()

    def jobs():
        for r in races:
            p = sect_path(r)
            if not p.exists() and str(p) not in empty:
                d = f"{r['date'][8:10]}/{r['date'][5:7]}/{r['date'][:4]}"
                yield "sectional", SECT_URL.format(d=d, n=r["race_no"]), p
        if "horse" in args.kinds:
            for h in horse_ids_from_sectionals():
                p = horse_path(h)
                if not p.exists() and str(p) not in empty:
                    yield "horse", HORSE_URL.format(h=h), p
        if "horse_all" in args.kinds:
            # 現役馬預設只顯示近三季；2024/25 季前已出賽嘅要「所有往績」版（Option=1）。
            # 清單由 state/horse_all_ids.json 提供（見 EXP-20261113 回放計劃）
            ids_file = STATE / "horse_all_ids.json"
            for h in (json.loads(ids_file.read_text()) if ids_file.exists() else []):
                p = horse_all_path(h)
                if not p.exists() and str(p) not in empty:
                    yield "horse_all", HORSE_URL.format(h=h) + "&Option=1", p

    kinds = set(args.kinds.split(","))
    log(f"開始：kinds={sorted(kinds)}")
    for kind, url, path in jobs():
        if kind not in kinds:
            continue
        while in_race_hours(dt.datetime.now(HKT)):
            log("香港賽馬時段，暫停 10 分鐘")
            time.sleep(600)
        try:
            status, html = fetch(url)
            verdict = looks_valid(kind, html) if status == 200 else None
        except Exception as exc:  # 網絡錯誤當失敗計
            status, html, verdict = -1, str(exc), None
        if verdict is None:
            consec += 1
            log(f"⚠️ 失敗 {consec}/{MAX_CONSEC_FAIL}：HTTP {status} {url}（{len(html)} bytes）")
            (STATE / "last_failure.html").write_text(html[:200000], encoding="utf-8", errors="ignore")
            if consec >= MAX_CONSEC_FAIL:
                msg = (f"🛑 HKJC 歷史補抓停咗：連續 {consec} 次失敗（最後 HTTP {status}）。已抓 {count} 頁。"
                       f"可能俾網站限制；等幾個鐘再跑 `backfill_history.py run`（斷點續抓）。")
                log(msg)
                notify(msg)
                sys.exit(2)
            time.sleep(FAIL_WAIT)
            continue
        consec = 0
        if verdict == "empty":
            empty.add(str(path))
            empty_file.write_text(json.dumps(sorted(empty)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            with gzip.open(tmp, "wt", encoding="utf-8") as fh:
                fh.write(html)
            tmp.rename(path)
        count += 1
        if count % 25 == 0:
            log(f"已抓 {count} 頁（{kind}），{(time.time() - started) / count:.1f} 秒／頁")
        time.sleep(random.uniform(*DELAY))
        if count % LONG_PAUSE_EVERY == 0:
            time.sleep(random.uniform(*LONG_PAUSE))
    msg = f"✅ HKJC 歷史補抓完成（{sorted(kinds)}）：今次抓咗 {count} 頁。"
    log(msg)
    notify(msg)


# ---------------------------------------------------------------- 解析
def _txt(el) -> str:
    return el.get_text(" ", strip=True).replace("\xa0", " ") if el is not None else ""


def parse_sectional(html: str) -> dict | None:
    from bs4 import BeautifulSoup
    s = BeautifulSoup(html, "html.parser")
    table = s.find("table", class_="race_table")
    if table is None:
        return None
    text = s.get_text(" ", strip=True).replace("\xa0", " ")
    head = re.search(r"第\s*(\d+)\s*場\s+(.*?)\s+時間\s*:", text)
    meta = head.group(2) if head else ""
    dist = re.search(r"(\d{3,4})米", meta)
    cls = re.search(r"(第[一二三四五]班|一級賽|二級賽|三級賽|國際\S*|新馬\S*|條件\S*)", meta)
    g = re.search(r"(?:賽道|跑道|全天候)\s*-\s*(\S+)", meta)
    going = g.group(1) if g else ""
    course = re.search(r"\"([A-C](?:\+\d)?)\"\s*賽道", meta)
    surface = "全天候" if "全天候" in meta else "草地"
    horses = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 5:
            continue
        a = tr.find("a", href=re.compile(r"horseid=", re.I))
        if a is None:
            continue
        hid = re.search(r"horseid=(HK_\d{4}_[A-Z]\d{3})", a["href"], re.I)
        sections = []
        for td in tds[3:-1]:
            ps = td.find_all("p")
            if not ps:
                continue
            pos = ps[0].find("span")
            mar = ps[0].find("i")
            leaves = [sp for sp in ps[1].find_all("span") if sp.find("span") is None] if len(ps) > 1 else []   # 只取最內層（外層 span 包住兩個 200 米）
            sub = [float(x) for sp in leaves for x in re.findall(r"\d+\.\d+", _txt(sp))]
            tm = re.match(r"\s*(\d+\.\d+)", ps[1].get_text(" ") if len(ps) > 1 else "")
            if not tm:
                continue
            sections.append({"pos": int(_txt(pos)) if _txt(pos).isdigit() else None, "margin": _txt(mar) or None,
                             "time": float(tm.group(1)), "sub200": sub})
        name = _txt(a)
        code = re.search(r"\(([A-Z]\d{3})\)", name)
        horses.append({"finish": _txt(tds[0]), "horse_no": _txt(tds[1]), "horse_id": hid.group(1) if hid else None,
                       "code": code.group(1) if code else None, "name": re.sub(r"\s*\([A-Z]\d{3}\)", "", name),
                       "sections": sections, "finish_time": _txt(tds[-1])})
    return {"race_no": int(head.group(1)) if head else None, "meta": meta, "distance": int(dist.group(1)) if dist else None,
            "class": cls.group(1) if cls else None, "course": course.group(1) if course else None, "surface": surface,
            "going": going,
            "horses": horses}


def parse_horse(html: str) -> dict | None:
    from bs4 import BeautifulSoup
    s = BeautifulSoup(html, "html.parser")
    prof = s.find("table", class_="horseProfile")
    runs_t = s.find("table", class_="bigborder")
    if prof is None:
        return None
    cells = [_txt(td) for td in prof.find_all("td") if td.find("td") is None]
    kv = {cells[i - 1]: cells[i + 1] for i in range(1, len(cells) - 1) if cells[i] == ":"}
    static = ("出生地", "毛色 / 性別", "進口類別", "父系", "母系", "外祖父")
    profile = {k: kv.get(k) for k in static}
    # 其餘欄（總獎金、冠-亞-季-總出賽次數、現時／季初／最後評分、馬主、同父系馬…）係「抓取當日」快照：
    # 回測用會有前視，所以分開放；季初評分、各跑道成績要由 runs 按賽日 as-of 計
    snapshot = {k: v for k, v in kv.items() if k not in static}
    runs, season = [], None
    if runs_t is not None:
        for tr in runs_t.find_all("tr"):
            c = [_txt(td) for td in tr.find_all("td")]
            if len(c) == 1 and "馬季" in c[0]:
                season = c[0].replace("馬季", "").strip()
                continue
            dm = re.match(r"(\d{2})/(\d{2})/(\d{2}|\d{4})$", c[2] or "") if len(c) >= 18 else None
            if not dm:
                continue
            # 現役馬頁面用兩位數年份（01/11/26），退役馬用四位數 —— 統一做四位數
            c[2] = f"{dm.group(1)}/{dm.group(2)}/{dm.group(3) if len(dm.group(3)) == 4 else '20' + dm.group(3)}"
            runs.append({"season": season, "race_idx": c[0], "pos": c[1], "date": c[2], "venue_track": c[3], "distance": c[4],
                         "going": c[5], "class": c[6], "draw": c[7], "rating": c[8], "trainer": c[9], "jockey": c[10],
                         "lbw": c[11], "win_odds": c[12], "actual_wt": c[13], "running_pos": c[14], "finish_time": c[15],
                         "body_wt": c[16], "gear": c[17]})
    return {"profile": profile, "snapshot": snapshot, "runs": runs}


def cmd_parse(_args) -> None:
    races = {(r["date"], r["race_no"]): r for r in json.loads((STATE / "races.json").read_text(encoding="utf-8"))}
    n_ok = n_bad = 0
    with gzip.open(PARSED / "sectionals.jsonl.gz", "wt", encoding="utf-8") as out:
        for p in sorted((RAW / "sectional").rglob("*.html.gz")):
            m = re.match(r"(\d{4}-\d{2}-\d{2})_R(\d+)", p.name)
            d = parse_sectional(gzip.open(p, "rt", encoding="utf-8", errors="ignore").read())
            if not d or not d["horses"]:
                n_bad += 1
                continue
            r = races.get((m.group(1), int(m.group(2)))) or {}
            out.write(json.dumps({"date": m.group(1), "race_no": int(m.group(2)), "venue": r.get("venue"), **d}, ensure_ascii=False) + "\n")
            n_ok += 1
    print(f"sectional：解析 {n_ok}，失敗 {n_bad}")
    n_ok = n_bad = 0
    with gzip.open(PARSED / "horses.jsonl.gz", "wt", encoding="utf-8") as out:
        for p in sorted((RAW / "horse").glob("*.html.gz")):
            full = horse_all_path(p.name.split(".")[0])     # 有「所有往績」版就用佢
            d = parse_horse(gzip.open(full if full.exists() else p, "rt", encoding="utf-8", errors="ignore").read())
            if not d:
                n_bad += 1
                continue
            out.write(json.dumps({"horse_id": p.name.split(".")[0], **d}, ensure_ascii=False) + "\n")
            n_ok += 1
    print(f"horse：解析 {n_ok}，失敗 {n_bad}")


def cmd_status(_args) -> None:
    races = json.loads((STATE / "races.json").read_text(encoding="utf-8")) if (STATE / "races.json").exists() else []
    got = sum(1 for _ in (RAW / "sectional").rglob("*.html.gz"))
    empty = len(json.loads((STATE / "empty.json").read_text())) if (STATE / "empty.json").exists() else 0
    print(f"sectional {got}+{empty} 空 / {len(races)}；horse {sum(1 for _ in (RAW / 'horse').glob('*.html.gz'))}")


def main() -> None:
    require_volume()
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("tasks")
    r = sub.add_parser("run")
    r.add_argument("--kinds", default="sectional,horse")
    sub.add_parser("parse")
    sub.add_parser("status")
    args = ap.parse_args()
    {"tasks": cmd_tasks, "run": cmd_run, "parse": cmd_parse, "status": cmd_status}[args.cmd](args)


if __name__ == "__main__":
    main()
