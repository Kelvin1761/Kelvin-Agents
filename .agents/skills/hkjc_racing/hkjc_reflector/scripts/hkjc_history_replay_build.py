"""HKJC 歷史引擎回放：由歷史數據生成每個賽日嘅原始輸入（docs/plans/2026-11-13-hkjc-historic-engine-replay.md）。

生成（每場）`MM-DD Race N 排位表.md`、`MM-DD Race N 賽績.md`，（每日）`YYYY-MM-DD_<Venue>_全日賽果.json`，
格式同 live 抽取器一樣；之後交畀真流程（inject_hkjc_fact_anchors → skeleton → 引擎），唔仿寫 Facts／Logic。

來源（全部喺外置碟 hkjc-history/ 或者賽果庫）：
  分段頁（parsed/sectionals.jsonl.gz）：班次、路程、跑道、賽道、場地狀況、每匹馬號↔馬匹 ID、逐段時間
  賽果庫（_research_old_season_results + HKJC_Race_Results_Database）：騎師、練馬師、實際負磅、排位體重、檔位、名次、事件報告
  馬匹頁（parsed/horses.jsonl.gz，有「所有往績」版就用佢）：逐仗評分、配備、場地、名次……；靜態：父系、母系、性別
as-of：每匹馬只取賽日**之前**嘅往績（最多 7 仗，同 HKJC formguide 一樣）；今仗評分 = 馬匹頁今仗嗰行嘅評分（賽前已定）。
攞唔到 → 留空（中性）：SpeedPRO 能量、走位短評同 (XW) 走位寬度、晨操、優先參賽次序、海外往績。
短評改用競賽事件報告入面關於嗰匹馬嘅句子（醫療關鍵字仍然捉到）。

用法：
  python3 hkjc_history_replay_build.py index                    # 建索引（cache 去外置碟）
  python3 hkjc_history_replay_build.py build --since 2026-04-01 --until 2026-11-12 [--out <root>]
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import json
import pickle
import re
import sys
from collections import defaultdict
from pathlib import Path

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[5]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / ".agents/scripts"))

BASE = Path("/Volumes/Kelvin Hardisk 1/WongChoi-Archive/hkjc-history")
PARSED = BASE / "parsed"
REPLAY = BASE / "replay"
INDEX = BASE / "analysis" / "replay_index.pkl"
VENUE_DIR = {"沙田": "ShaTin", "跑馬地": "HappyValley"}
MAX_RUNS = 7


def _iso(d: str) -> str:            # DD/MM/YYYY → YYYY-MM-DD
    return f"{d[6:10]}-{d[3:5]}-{d[0:2]}"


def _dmy(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}/{iso[0:4]}"


def _venue_cn(v: str) -> str:
    v = str(v or "")
    return "跑馬地" if ("跑馬地" in v or "Happy" in v or v == "HV") else "沙田"


def _code(name: str) -> str | None:
    m = re.search(r"\(([A-Z]\d{3})\)", name or "")
    return m.group(1) if m else None


def _strip_code(name: str) -> str:
    return re.sub(r"\s*\([A-Z]\d{3}\)", "", name or "").strip()


# ---------------------------------------------------------------- 索引
def _normalise_new_schema(race: dict, fp: Path) -> dict | None:
    """賽果庫有一個賽日（2026-05-03）用咗另一個格式：冇 racedate／venue，欄名 actual_weight／declared_weight／margin，
    事件報告係 list。換返舊格式；賽日取資料夾名，場地取 live 賽日資料夾（冇就跳過，唔估）。"""
    day = fp.parent.name
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        return None
    import wongchoi_paths
    live = sorted(Path(wongchoi_paths.HK_RACING).glob(f"{day}_*"))
    venue = {"ShaTin": "沙田", "HappyValley": "跑馬地"}.get(live[0].name.split("_", 1)[1] if live else "", None)
    if venue is None:
        return None
    rows = [dict(r, actual_wt=r.get("actual_wt", r.get("actual_weight", "")), horse_wt=r.get("horse_wt", r.get("declared_weight", "")),
                 lbw=r.get("lbw", r.get("margin", ""))) for r in race.get("results", [])]
    inc = race.get("incident_report")
    if isinstance(inc, str) and inc.strip().startswith("["):
        import ast
        try:
            inc = ast.literal_eval(inc)
        except (ValueError, SyntaxError):
            inc = []
    if isinstance(inc, list):
        inc = " ".join(f"{i.get('pos', '')} {i.get('horse_no', '')} {i.get('horse_name', '')} {i.get('comment', '')}" for i in inc)
    return dict(race, racedate=day, venue=venue, results=rows, incident_report=inc or "")


def build_index() -> dict:
    import build_comprehensive_stats as bcs

    sect = {}
    for line in gzip.open(PARSED / "sectionals.jsonl.gz", "rt", encoding="utf-8"):
        r = json.loads(line)
        sect[(r["date"], int(r["race_no"]))] = r
    results = {}
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
            if not race.get("racedate"):
                race = _normalise_new_schema(race, fp)
                if race is None:
                    continue
            m = re.search(r"\d+", str(race.get("race_no") or key))
            if m:
                try:
                    header = bcs.race_header(race)
                except Exception:      # 新格式冇 header 表；分段頁有班次／路程
                    header = {}
                race = dict(race, _header=header)
                results[(str(race["racedate"]), int(m.group()))] = race
    horses = {}
    for line in gzip.open(PARSED / "horses.jsonl.gz", "rt", encoding="utf-8"):
        h = json.loads(line)
        h["runs"] = [dict(r, iso=_iso(r["date"])) for r in h["runs"] if r.get("date")]
        h["runs"].sort(key=lambda r: r["iso"], reverse=True)
        horses[h["horse_id"]] = h
    idx = {"sect": sect, "results": results, "horses": horses}
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    with open(INDEX, "wb") as fh:
        pickle.dump(idx, fh)
    print(f"索引：分段頁 {len(sect)} 場、賽果 {len(results)} 場、馬匹 {len(horses)} 匹 → {INDEX}")
    return idx


def load_index() -> dict:
    with open(INDEX, "rb") as fh:
        return pickle.load(fh)


# ---------------------------------------------------------------- 單場
def _incident_by_horse(text: str) -> dict:
    """事件報告：'1 8 上市魅力 (H196) 賽後須抽取樣本檢驗。 2 11 樂天派 (E166) …' → {code: 句子}。"""
    out = {}
    parts = re.split(r"(?=\b\d{1,2}\s+\d{1,2}\s+\S+\s*\([A-Z]\d{3}\))", text or "")
    for p in parts:
        m = re.match(r"\d{1,2}\s+\d{1,2}\s+\S+\s*\(([A-Z]\d{3})\)\s*(.*)", p.strip(), re.S)
        if m:
            out[m.group(1)] = re.sub(r"\s+", " ", m.group(2)).strip()
    return out


def _track_label(venue_track: str) -> str:
    """'沙田草地"A"' → '沙田 "A"'；'沙田全天候' → '沙田 "AWT"'。"""
    vt = venue_track or ""
    ven = "跑馬地" if "跑馬地" in vt else "沙田"
    if "全天候" in vt:
        return f'{ven} "AWT"'
    m = re.search(r'"([^"]+)"', vt)
    return f'{ven} "{m.group(1)}"' if m else ven


def _started(row: dict) -> bool:
    pos = str(row.get("pos") or "").strip()
    return bool(row.get("horse_no")) and pos not in ("", "退出", "WV", "WV-A", "WX", "WX-A", "W")


def _ran(run: dict) -> bool:
    """往績要真係出咗賽：退出（WV／WX…）同無效賽（VOID）唔計 —— 同 HKJC formguide 一樣（2026-10-01 R1 核對）。"""
    pos = str(run.get("pos") or "").strip().upper()
    return bool(pos) and not pos.startswith("W") and pos != "VOID"


def race_inputs(idx: dict, date: str, race_no: int) -> dict | None:
    res = idx["results"].get((date, race_no))
    sec = idx["sect"].get((date, race_no))
    if not res or not sec:
        return None
    no2id = {str(h.get("horse_no")): h.get("horse_id") for h in sec["horses"]}
    incidents = {}
    runners = []
    for row in res.get("results", []):
        if not _started(row):
            continue
        hid = no2id.get(str(row["horse_no"]))
        horse = idx["horses"].get(hid) if hid else None
        runs = [r for r in (horse or {}).get("runs", []) if r["iso"] < date and _ran(r)]
        today = next((r for r in (horse or {}).get("runs", []) if r["iso"] == date), None)
        runners.append({"row": row, "hid": hid, "horse": horse, "past": runs, "today": today})
    runners.sort(key=lambda rn: int(rn["row"]["horse_no"]) if str(rn["row"]["horse_no"]).isdigit() else 99)
    return {"date": date, "race_no": race_no, "res": res, "sec": sec, "runners": runners, "incidents": incidents}


def _past_field_and_sections(idx: dict, run: dict, hid: str) -> tuple[str, str, str]:
    """往績嗰仗：出賽匹數、分段時間（同分段頁）、事件報告句。"""
    for (d, n), sec in _SECT_BY_DATE.get(run["iso"], []):
        for h in sec["horses"]:
            if h.get("horse_id") == hid:
                secs = ", ".join(f"{s['time']:.2f}" for s in h["sections"] if s.get("time") is not None)
                res = idx["results"].get((d, n)) or {}
                field = sum(1 for r in res.get("results", []) if _started(r)) or len(sec["horses"])
                note = _incident_by_horse(res.get("incident_report") or "").get(_code_of(idx, hid), "")
                return str(field), secs, note
    return "", "", ""


_SECT_BY_DATE: dict = {}


def _code_of(idx: dict, hid: str) -> str | None:
    m = re.search(r"_([A-Z]\d{3})$", hid or "")
    return m.group(1) if m else None


def formguide_md(idx: dict, ri: dict) -> str:
    sec, res = ri["sec"], ri["res"]
    hdr = res.get("_header") or {}
    surface = "全天候跑道" if sec.get("surface") == "全天候" else "草地"
    course = f' - {sec["course"]} 賽道' if sec.get("course") and surface == "草地" else ""
    venue = _venue_cn(res.get("venue"))
    lines = ["#### 賽事概覽 (Race Overview)",
             f"- 賽事日期 / 場次 / 跑道及場地狀況: {_dmy(ri['date'])} / 第{ri['race_no']}場 / {venue} {surface}{course} "
             f"{sec.get('class') or hdr.get('RaceClass') or ''} {sec.get('distance') or ''}米",
             "", "#### 全場馬匹分析 (Full Field Analysis)"]
    for rn in ri["runners"]:
        row = rn["row"]
        lines += [f"馬號: {row['horse_no']}", f"馬名: {_strip_code(row['horse_name'])}", f"檔位: {row.get('draw', '')}",
                  f"騎師: {row.get('jockey', '')}", f"負磅: {row.get('actual_wt', '')}", f"排位體重: {row.get('horse_wt', '')}",
                  "", "往績紀錄:"]
        past = rn["past"][:MAX_RUNS]
        if not past:
            lines.append("  (無往績紀錄)")
        for i, run in enumerate(past, 1):
            prev = rn["past"][i] if i < len(rn["past"]) else None
            days = (dt.date.fromisoformat(run["iso"]) - dt.date.fromisoformat(prev["iso"])).days if prev else 0
            field, secs, note = _past_field_and_sections(idx, run, rn["hid"])
            pos = str(run.get("pos") or "").lstrip("0") or run.get("pos", "")
            lines += [f"  [{i}] {run['date']} | 日數: {days} | {_track_label(run['venue_track'])} {run['distance']} {run['going']}",
                      f"      檔位: {run['draw']} | 馬重: {run['body_wt']} | 負磅: {run['actual_wt']} | 騎師: {run['jockey']} | "
                      f"名次: {pos} / {field}",
                      f"      能量:  | 分段時間: {secs}",
                      f"      短評: {note}"]
        lines.append("")
    return "\n".join(lines) + "\n"


def racecard_md(idx: dict, ri: dict) -> str:
    sec, res = ri["sec"], ri["res"]
    venue = _venue_cn(res.get("venue"))
    surface = "全天候跑道" if sec.get("surface") == "全天候" else "草地"
    weekday = "一二三四五六日"[dt.date.fromisoformat(ri["date"]).weekday()]
    out = ["#### 第一部分：賽事資料 (Race Info)", f"場次: 第{ri['race_no']}場", f"日期: {ri['date']}", f"星期: 星期{weekday}",
           f"地點: {venue}", f"場地: {surface}"]
    if sec.get("course") and surface == "草地":
        out.append(f"賽道: {sec['course']} 賽道")
    out += [f"路程: {sec.get('distance') or ''}米", f"班次: {sec.get('class') or ''}", "", "#### 第二部分：馬匹資料 (Horse Info)"]
    for rn in ri["runners"]:
        row, horse, today, past = rn["row"], rn["horse"] or {}, rn["today"] or {}, rn["past"]
        code = _code(row["horse_name"]) or _code_of(idx, rn["hid"]) or ""
        rating = today.get("rating") or ""
        prev_rating = next((r.get("rating") for r in past if str(r.get("rating") or "").isdigit()), None)
        chg = (int(rating) - int(prev_rating)) if str(rating).isdigit() and prev_rating else ""
        prof = horse.get("profile") or {}
        sex = (prof.get("毛色 / 性別") or "").split("/")[-1].strip()
        last6 = "/".join((str(r.get("pos") or "").lstrip("0") or "-") for r in past[:6])
        out += [f"馬號: {row['horse_no']}", f"馬名: {_strip_code(row['horse_name'])}", f"賽績: {last6}", f"烙號: {code}",
                f"HKJC馬匹ID: {rn['hid'] or ''}",
                f"官方馬匹資料: https://racing.hkjc.com/zh-hk/local/information/horse?horseid={rn['hid'] or ''}",
                f"負磅: {row.get('actual_wt', '')}", f"騎師: {row.get('jockey', '')}", f"檔位: {row.get('draw', '')}",
                f"練馬師: {row.get('trainer', '')}", f"評分: {rating}", f"評分+/-: {chg}", f"排位體重: {row.get('horse_wt', '')}",
                f"性別: {sex}",
                f"上賽距今日數: {(dt.date.fromisoformat(ri['date']) - dt.date.fromisoformat(past[0]['iso'])).days if past else ''}",
                f"配備: {today.get('gear') or ''}", f"父系: {prof.get('父系') or ''}", f"母系: {prof.get('母系') or ''}", ""]
    return "\n".join(out) + "\n"


def build(idx: dict, since: str, until: str, out_root: Path) -> None:
    _SECT_BY_DATE.clear()
    for (d, n), sec in idx["sect"].items():
        _SECT_BY_DATE.setdefault(d, []).append(((d, n), sec))
    days = defaultdict(list)
    for (d, n) in idx["results"]:
        if since <= d <= until:
            days[d].append(n)
    made = skipped = 0
    for d in sorted(days):
        races = sorted(days[d])
        venue = _venue_cn(idx["results"][(d, races[0])].get("venue"))
        md = out_root / f"{d}_{VENUE_DIR[venue]}"
        md.mkdir(parents=True, exist_ok=True)
        payload = {}
        for n in races:
            ri = race_inputs(idx, d, n)
            if ri is None or not ri["runners"]:
                skipped += 1
                continue
            mmdd = d[5:7] + "-" + d[8:10]
            (md / f"{mmdd} Race {n} 排位表.md").write_text(racecard_md(idx, ri), encoding="utf-8")
            (md / f"{mmdd} Race {n} 賽績.md").write_text(formguide_md(idx, ri), encoding="utf-8")
            r = idx["results"][(d, n)]
            payload[str(n)] = {"racedate": d, "race_no": n, "venue": VENUE_DIR[venue], "results": r.get("results", [])}
            made += 1
        (md / f"{d}_{VENUE_DIR[venue]}_全日賽果.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"生成 {made} 場（跳過 {skipped}）→ {out_root}")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("index")
    b = sub.add_parser("build")
    b.add_argument("--since", required=True)
    b.add_argument("--until", required=True)
    b.add_argument("--out", default=str(REPLAY))
    a = ap.parse_args()
    if a.cmd == "index":
        build_index()
    else:
        build(load_index(), a.since, a.until, Path(a.out))


if __name__ == "__main__":
    main()
