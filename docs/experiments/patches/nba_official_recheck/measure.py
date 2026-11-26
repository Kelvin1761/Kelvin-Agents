#!/usr/bin/env python3
"""EXP-20261127-01：重新量度 NBA 官方傷停報告（11-02 EXP-20261101-60 剷走）對大細盤精選有冇用。只量度，唔改模型。

預先登記（結果出之前寫死）：
  * 日子：target_date 2026-11-03 → 2026-11-26（剷走之後、精選開始前後都包埋）。
  * 兩個時間點（每場波）：bet = 21:00 production 快照（精選凍結嗰刻）；late = 開波前最後一份 final_refresh 快照。
    官方報告 = 嗰個快照時間或者之前最新一份（每 15 分鐘一份，向前搵最多 6 小時）。
  * 球員 = 嗰個快照有開盤（model_obs）嘅球員。ESPN 級別 = 同一快照 availability_obs（冇列出 = ok）；
    官方級別 = 報告入面同隊、同 US 比賽日（冇列出 = ok）。級別：out（Out／Doubtful）> dtd（Questionable）> ok（Probable／Available）。
  * 結果：DNP = 嗰個球員所有腿結算 void；低分鐘 = 上陣 < 15 分鐘；bad = DNP 或者低分鐘。
  * 判斷：「官方有標、ESPN 冇標（ESPN ok、官方 out／dtd）」嘅 bad 率 − 兩邊都 ok 嘅 bad 率 ≥ 20pp、Wilson 差值 CI 唔包 0，
    而且影響開盤腿 ≥ 1% 或者精選 ≥ 3 注 → 建議重新接返做精選安全欄（Kelvin 決定）；否則 → 確認停用（known_retired_fields）。

    PYTHONDONTWRITEBYTECODE=1 python3 measure.py --cache <dir> --out result.json
"""
from __future__ import annotations

import argparse
import io
import json
import math
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[4]
NBA = REPO / ".agents" / "skills" / "nba"
sys.path.insert(0, str(NBA))
sys.path.insert(0, str(NBA / "nba_daily_auto"))

from nba_identity import availability_name_key as name_key  # noqa: E402  （同 ledger 同一個 key）

EASTERN = ZoneInfo("America/New_York")
URL = "https://ak-static.cms.nba.com/referee/injury/Injury-Report_{d}_{h:02d}_{m:02d}{ap}.pdf"
STATUS_LEVEL = {"out": "out", "doubtful": "out", "questionable": "dtd", "probable": "ok", "available": "ok"}
COLUMNS = ("GameDate", "GameTime", "Matchup", "Team", "PlayerName", "CurrentStatus", "Reason")
TEAM_NICKNAMES = {
    "76ers": "PHI", "Bucks": "MIL", "Bulls": "CHI", "Cavaliers": "CLE", "Celtics": "BOS", "Clippers": "LAC",
    "Grizzlies": "MEM", "Hawks": "ATL", "Heat": "MIA", "Hornets": "CHA", "Jazz": "UTA", "Kings": "SAC",
    "Knicks": "NYK", "Lakers": "LAL", "Magic": "ORL", "Mavericks": "DAL", "Nets": "BKN", "Nuggets": "DEN",
    "Pacers": "IND", "Pelicans": "NOP", "Pistons": "DET", "Raptors": "TOR", "Rockets": "HOU", "Spurs": "SAS",
    "Suns": "PHX", "Thunder": "OKC", "Timberwolves": "MIN", "TrailBlazers": "POR", "Warriors": "GSW",
    "Wizards": "WAS",
}
LOW_MIN = 15


# ---------------------------------------------------------------- 官方報告（解析照搬 11-02 剷走嘅 nba_official_injuries.py）

def _team(cell):
    text = re.sub(r"\s+", "", str(cell or ""))
    hits = [a for n, a in TEAM_NICKNAMES.items() if text.endswith(n)]
    return hits[0] if len(hits) == 1 else None


def parse_words(pages):
    rows, bounds = [], None
    carry = {"GameDate": None, "GameTime": None, "Matchup": None, "Team": None}
    for words in pages:
        header = {w["text"]: w["x0"] for w in words if w["text"] in COLUMNS}
        if len(header) == len(COLUMNS):
            xs = [header[c] - 2 for c in COLUMNS] + [10 ** 6]
            bounds = [(COLUMNS[i], xs[i], xs[i + 1]) for i in range(len(COLUMNS))]
            header_top = max(w["top"] for w in words if w["text"] in COLUMNS)
        elif bounds is None:
            raise ValueError("header not found")
        else:
            header_top = -1
        title_top = min((w["top"] for w in words if w["text"] == "Report:"), default=None)
        lines = {}
        for w in words:
            if (w["top"] <= header_top + 1 or (title_top is not None and abs(w["top"] - title_top) < 2)
                    or re.fullmatch(r"Page\d+of\d+", w["text"])):
                continue
            lines.setdefault(round(w["top"], 0), []).append(w)
        for top in sorted(lines):
            cells = {}
            for w in sorted(lines[top], key=lambda w: w["x0"]):
                col = next((c for c, lo, hi in bounds if lo <= w["x0"] < hi), None)
                if col:
                    cells[col] = cells.get(col, "") + w["text"]
            for col in carry:
                if cells.get(col):
                    carry[col] = cells[col]
            player = cells.get("PlayerName", "")
            status = cells.get("CurrentStatus", "").strip().lower()
            if player and status in STATUS_LEVEL and "," in player:
                rows.append({"game_date": carry["GameDate"], "team": _team(carry["Team"]), "player": player,
                             "key": name_key(player), "status": status, "level": STATUS_LEVEL[status]})
    return rows


def report_at(t_utc: datetime, cache: Path, max_back_hours: float = 6.0):
    """t_utc 或之前最新一份報告：(報告時間, rows) 或 (None, None)。PDF 落 cache，唔重抓。"""
    import pdfplumber
    import requests
    et = t_utc.astimezone(EASTERN)
    et = et.replace(minute=et.minute - et.minute % 15, second=0, microsecond=0)
    for i in range(int(max_back_hours * 4) + 1):
        cand = et - timedelta(minutes=15 * i)
        h12 = cand.hour % 12 or 12
        url = URL.format(d=cand.date().isoformat(), h=h12, m=cand.minute, ap="AM" if cand.hour < 12 else "PM")
        f = cache / url.rsplit("/", 1)[1]
        miss = cache / (f.name + ".404")
        if miss.exists():
            continue
        if not f.exists():
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
            time.sleep(0.5)                                   # 禮貌
            if r.status_code != 200 or not r.content.startswith(b"%PDF"):
                miss.write_text(str(r.status_code))
                continue
            f.write_bytes(r.content)
        with pdfplumber.open(io.BytesIO(f.read_bytes())) as pdf:
            return cand, parse_words([p.extract_words() for p in pdf.pages])
    return None, None


# ---------------------------------------------------------------- ledger

def _ledger(day: str):
    import nba_market_ledger as L
    return L.read_rows(Path(L.ledger_root()), day)


def _minutes(v):
    if v in (None, ""):
        return None
    s = str(v)
    try:
        if ":" in s:
            a, b = s.split(":", 1)
            return int(a) + int(b) / 60
        return float(s)
    except ValueError:
        return None


def collect(day: str, cache: Path) -> list[dict]:
    rows = _ledger(day)
    sel = defaultdict(list)          # game_tag -> [(role, created_at, snapshot_id, tip)]
    for r in rows:
        if r.get("row_type") == "selection_obs" and not r.get("post_tip") and not r.get("late_write"):
            sel[r["game_tag"]].append((r.get("snapshot_role"), r.get("snapshot_created_at"), r.get("snapshot_id"),
                                       r.get("tip_off")))
    settle = defaultdict(list)
    for r in rows:
        if r.get("row_type") == "settlement":
            settle[(r.get("game_tag"), name_key(r.get("player")))].append(r)
    out = []
    for game, snaps in sel.items():
        views = {}
        prod = sorted((s for s in snaps if s[0] == "production"), key=lambda s: str(s[1]))
        late = sorted((s for s in snaps if s[0] in ("final_refresh", "production")), key=lambda s: str(s[1]))  # 按時間，唔係按名
        if prod:
            views["bet"] = prod[-1]
        if late:
            views["late"] = late[-1]
        for view, (_role, created, sid, tip) in views.items():
            t = datetime.fromisoformat(created).astimezone(timezone.utc)
            rep_time, rep = report_at(t, cache)
            us_day = datetime.fromisoformat(tip.replace("Z", "+00:00")).astimezone(EASTERN).strftime("%m/%d/%Y") if tip else None
            official = {(r["team"], r["key"]): r for r in (rep or []) if r.get("game_date") == us_day}
            espn = {(r.get("team"), r.get("name_key")): r.get("espn_level") for r in rows
                    if r.get("row_type") == "availability_obs" and r.get("snapshot_id") == sid}
            players = {}
            for r in rows:
                if r.get("row_type") == "model_obs" and r.get("snapshot_id") == sid and r.get("game_tag") == game:
                    players.setdefault((r.get("team"), name_key(r.get("player"))), r.get("player"))
            for (team, key), player in players.items():
                st = settle.get((game, key)) or []
                if not st:
                    continue
                dnp = all(s.get("outcome") == "void" for s in st)
                mins = max((_minutes(s.get("minutes")) or 0) for s in st)
                off = official.get((team, key))
                out.append({"day": day, "game": game, "view": view, "player": player, "team": team,
                            "espn": espn.get((team, key)) or "ok", "official": off["level"] if off else "ok",
                            "official_status": off["status"] if off else None,
                            "report": rep_time.isoformat() if rep_time else None, "dnp": dnp,
                            "low": (not dnp) and mins < LOW_MIN, "minutes": mins,
                            "legs": sum(1 for r in rows if r.get("row_type") == "model_obs" and r.get("snapshot_id") == sid
                                        and name_key(r.get("player")) == key)})
    return out


# ---------------------------------------------------------------- 統計

def wilson(k, n, z=1.96):
    if not n:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 4), round(c + h, 4)]


def summarise(items: list[dict]) -> dict:
    out = {}
    for view in ("bet", "late"):
        xs = [x for x in items if x["view"] == view]
        cells = defaultdict(lambda: [0, 0])
        for x in xs:
            bad = x["dnp"] or x["low"]
            cells[(x["espn"], x["official"])][0] += bad
            cells[(x["espn"], x["official"])][1] += 1
        table = {f"espn={e}|official={o}": {"bad": b, "n": n, "rate": round(b / n, 4), "ci": wilson(b, n)}
                 for (e, o), (b, n) in sorted(cells.items())}
        only = [x for x in xs if x["espn"] == "ok" and x["official"] != "ok"]
        both_ok = [x for x in xs if x["espn"] == "ok" and x["official"] == "ok"]
        r1 = sum(x["dnp"] or x["low"] for x in only) / len(only) if only else None
        r0 = sum(x["dnp"] or x["low"] for x in both_ok) / len(both_ok) if both_ok else None
        diff_ci = None
        if only and both_ok:
            se = math.sqrt(r1 * (1 - r1) / len(only) + r0 * (1 - r0) / len(both_ok))
            diff_ci = [round(r1 - r0 - 1.96 * se, 4), round(r1 - r0 + 1.96 * se, 4)]
        legs_all = sum(x["legs"] for x in xs)
        legs_only = sum(x["legs"] for x in only)
        out[view] = {"players": len(xs), "table": table, "official_only": len(only),
                     "official_only_bad_rate": None if r1 is None else round(r1, 4),
                     "both_ok_bad_rate": None if r0 is None else round(r0, 4), "diff_ci": diff_ci,
                     "official_only_leg_share": round(legs_only / legs_all, 4) if legs_all else None,
                     "official_only_examples": [{k: x[k] for k in ("day", "game", "player", "official_status", "dnp",
                                                                    "minutes")} for x in only[:25]],
                     "reports_found": sum(1 for x in xs if x["report"]) }
    return out


def featured_effect(items: list[dict]) -> list[dict]:
    sys.path.insert(0, str(REPO / "Horse_Racing_Dashboard" / "backend"))
    from services.nba_tracking import export_tracking
    bet = {(x["day"], x["game"], name_key(x["player"])): x for x in items if x["view"] == "bet"}
    out = []
    for f in export_tracking(REPO).get("featured_records") or []:
        leg = (f.get("legs") or [{}])[0]
        x = bet.get((f.get("day"), f.get("game_tag"), name_key(leg.get("player"))))
        if x and (x["official"] != "ok" or x["espn"] != "ok"):
            out.append({"day": f.get("day"), "pick": f"{leg.get('player')} {leg.get('stat')} {leg.get('side')} {leg.get('ou_line')}",
                        "espn": x["espn"], "official": x["official"], "official_status": x["official_status"],
                        "state": f.get("state"), "minutes": x["minutes"], "dnp": x["dnp"]})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--since", default="2026-11-03")
    ap.add_argument("--until", default="2026-11-26")
    a = ap.parse_args(argv)
    cache = Path(a.cache)
    cache.mkdir(parents=True, exist_ok=True)
    items = []
    d, end = date.fromisoformat(a.since), date.fromisoformat(a.until)
    while d <= end:
        try:
            got = collect(d.isoformat(), cache)
        except FileNotFoundError:
            got = []
        items += got
        print(d, len(got), flush=True)
        d += timedelta(days=1)
    res = {"experiment": "EXP-20261127-01", "items": len(items), "summary": summarise(items),
           "featured": featured_effect(items)}
    Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=1))
    Path(a.out).with_suffix(".items.json").write_text(json.dumps(items, ensure_ascii=False))
    print(json.dumps({k: v for k, v in res["summary"].items()}, ensure_ascii=False, indent=1)[:4000])
    print("featured affected:", len(res["featured"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
