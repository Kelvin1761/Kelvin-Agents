#!/usr/bin/env python3
"""crawl_hkjc_jockey_trainer.py — HKJC 官方騎練排名 vs 我哋賽果庫對數

用途（2026-10-14 起，見 docs/audits/hkjc-jockey-trainer-ranking-reconcile-20261014.md）：
  **只係數據質素檢查，唔入評分。**

  官方騎師／練馬師排名頁（racing.hkjc.com/{zh-hk,en-us}/local/info/{jockey,trainer}-ranking）
  係 client-side render；HTML 入面一行數據都冇。資料嚟自 HKJC GraphQL
  （info.cld.hkjc.com/graphql/base/，operation `rw_GetJockeyRanking` /
  `rw_GetTrainerRanking`，只開本季同上季）。舊版 crawler 爬 HTML table +
  __NEXT_DATA__，喺新站永遠攞到 0 行，而且由來冇 caller。

  官方本季頭馬／二／三／四／五／出賽次數，同我哋由 `hkjc results YYYY YY/*/
  full_day_results.json` 自己數出嚟嘅應該逐個人一樣（2026/27 季 22/22 騎師、
  23/23 練馬師完全一致）。對唔上 = 我哋賽果庫漏咗賽日／場次（2026-08 曾經
  「有 reader 冇 writer」停咗七週冇人知）。

點解唔入評分：
  官方表係「而家」嘅快照，回測舊賽日用佢 = 前視；而同一份資訊我哋已經可以由
  賽果按日期 point-in-time 重建（trainer_signal 就係咁做）。頁面冇我哋冇嘅欄位
  （海外策騎明寫唔計；場地／泥草分拆我哋自己都有）。

用法：
  python3 crawl_hkjc_jockey_trainer.py                 # 對本季，印報告
  python3 crawl_hkjc_jockey_trainer.py --json          # 機讀報告
  python3 crawl_hkjc_jockey_trainer.py --season 25/26  # 對上季
  python3 crawl_hkjc_jockey_trainer.py --dump out.json # 另存官方原始排名

永遠唔會令 pipeline 失敗：攞唔到官方數據 → status=unavailable。
"""
from __future__ import annotations

import os

os.environ.setdefault("PYTHONUTF8", "1")

import argparse
import gzip
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable

GRAPHQL_URL = "https://info.cld.hkjc.com/graphql/base/"
HEADERS = {
    "Origin": "https://racing.hkjc.com",
    "Referer": "https://racing.hkjc.com/",
    "Content-Type": "application/json",
    "Accept-Encoding": "gzip",
}

# HKJC GraphQL 有白名單（WHITELIST_ERROR）：自己砌嘅 query 會被拒，要用網站
# 本身嘅 operation 形狀。以下抄自 racing.hkjc.com 前端 bundle（2026-10-14）。
_STAT_FIELDS = """
      numFirst
      numSecond
      numThird
      numFourth
      numFifth
      numStarts
      stakeWon
      trk
      ven"""
QUERY_JOCKEY = f"""
query rw_GetJockeyRanking($season: String) {{
  jockeyStat(season: $season) {{
    code
    name_ch
    name_en
    status
    id
    isCurSsn
    season
    ssnStat {{{_STAT_FIELDS}
    }}
    dhStat {{{_STAT_FIELDS}
    }}
  }}
}}
"""
QUERY_TRAINER = f"""
query rw_GetTrainerRanking($season: String) {{
  trainerStat(season: $season) {{
    code
    name_ch
    name_en
    status
    id
    isCurSsn
    season
    visitingIndex
    ssnStat {{{_STAT_FIELDS}
    }}
    dhStat {{{_STAT_FIELDS}
    }}
  }}
}}
"""
QUERY_LAST_MEETING = """
query rw_LastMeeting($venueCodes: [String!]) {
  lastMeeting(venueCodes: $venueCodes) {
    date
    season
  }
}
"""

KINDS = {
    "jockey": ("rw_GetJockeyRanking", QUERY_JOCKEY, "jockeyStat", "jockey"),
    "trainer": ("rw_GetTrainerRanking", QUERY_TRAINER, "trainerStat", "trainer"),
}

# 退出／冇出閘：唔計出賽。PU／UR／DNF／DISQ／FE 有出閘，官方計出賽次數
# （2026/27 季逐人核對過）。
NOT_A_RIDE = {"", "---", "WV", "WV-A", "WX", "WX-A", "WXNR", "TNP"}

# 超過一場滿閘（14 匹）嘅出賽差 = 起碼漏咗一場，唔係個別名次爭議。
STARTS_GAP_WARN = 14

PostFn = Callable[[str, str, dict], dict]


def _post_graphql(operation: str, query: str, variables: dict, timeout: int = 30) -> dict:
    body = json.dumps(
        {"operationName": operation, "query": query, "variables": variables}
    ).encode("utf-8")
    try:
        from curl_cffi import requests as cffi_requests

        resp = cffi_requests.post(
            GRAPHQL_URL, data=body, headers=HEADERS, impersonate="chrome120", timeout=timeout
        )
        return resp.json()
    except ImportError:
        pass
    import urllib.request

    req = urllib.request.Request(GRAPHQL_URL, data=body, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 固定 HKJC URL
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip" or raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
    return json.loads(raw.decode("utf-8"))


def _data(payload: dict, key: str) -> Any:
    errors = payload.get("errors")
    value = (payload.get("data") or {}).get(key)
    if value is None and errors:
        raise RuntimeError(f"HKJC GraphQL {key}: {errors}")
    return value


def fetch_last_meeting(post: PostFn = _post_graphql) -> dict:
    """{'date': 'YYYY-MM-DD', 'season': '26/27'}"""
    return _data(
        post("rw_LastMeeting", QUERY_LAST_MEETING, {"venueCodes": ["ST", "HV"]}),
        "lastMeeting",
    ) or {}


def fetch_rankings(kind: str, season: str, post: PostFn = _post_graphql) -> list[dict]:
    operation, query, key, _ = KINDS[kind]
    return list(_data(post(operation, query, {"season": season}), key) or [])


def official_totals(rows: list[dict]) -> dict[str, dict]:
    """官方 ssnStat 入面 trk=ALL / ven=ALL 嗰行；冇出賽嘅人略過。key = 中文名。"""
    out: dict[str, dict] = {}
    for row in rows:
        overall = next(
            (s for s in row.get("ssnStat") or [] if s.get("trk") == "ALL" and s.get("ven") == "ALL"),
            None,
        )
        if not overall or not int(overall.get("numStarts") or 0):
            continue
        name = str(row.get("name_ch") or "").strip()
        if not name:
            continue
        out[name] = {
            "name_en": row.get("name_en"),
            "counts": [
                int(overall.get(k) or 0)
                for k in ("numFirst", "numSecond", "numThird", "numFourth", "numFifth", "numStarts")
            ],
        }
    return out


def results_dir_for_season(db_root: Path, season: str) -> Path:
    """'26/27' -> <db_root>/hkjc results 2026 27"""
    start, end = season.split("/")
    return Path(db_root) / f"hkjc results 20{start} {end}"


def _position(raw: Any) -> int | None:
    """回傳名次；唔係出賽（退出）回 None；有出閘但冇名次（PU/UR/DNF…）回 0。"""
    text = str(raw if raw is not None else "").strip()
    if text.upper() in NOT_A_RIDE:
        return None
    digits = re.match(r"\d+", text)  # 「1 平頭馬」= 平頭第一
    return int(digits.group()) if digits else 0


def our_totals(results_dir: Path, through_date: str | None = None) -> dict:
    """由 full_day_results.json 數返每個騎師／練馬師 [1st..5th, starts]。"""
    totals = {"jockey": {}, "trainer": {}}
    meetings: list[str] = []
    if not Path(results_dir).is_dir():
        return {**totals, "meetings": meetings}
    for day_dir in sorted(Path(results_dir).iterdir()):
        if not day_dir.is_dir() or (through_date and day_dir.name > through_date):
            continue
        path = day_dir / "full_day_results.json"
        if not path.is_file():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        meetings.append(day_dir.name)
        for race in payload.values():
            if not isinstance(race, dict):
                continue
            for row in race.get("results") or []:
                pos = _position(row.get("pos"))
                if pos is None:
                    continue
                for kind in ("jockey", "trainer"):
                    name = str(row.get(kind) or "").strip()
                    counts = totals[kind].setdefault(name, [0] * 6)
                    counts[5] += 1
                    if 1 <= pos <= 5:
                        counts[pos - 1] += 1
    return {**totals, "meetings": meetings}


def reconcile(official: dict[str, dict], ours: dict[str, list[int]]) -> dict:
    mismatches = []
    matched = 0
    for name, item in sorted(official.items(), key=lambda kv: -kv[1]["counts"][5]):
        mine = ours.get(name)
        if mine == item["counts"]:
            matched += 1
            continue
        mismatches.append({"name": name, "name_en": item["name_en"],
                           "official": item["counts"], "ours": mine})
    official_starts = sum(item["counts"][5] for item in official.values())
    our_starts = sum(counts[5] for counts in ours.values())
    official_wins = sum(item["counts"][0] for item in official.values())
    our_wins = sum(counts[0] for counts in ours.values())
    return {
        "compared": len(official),
        "matched": matched,
        "mismatches": mismatches,
        "ours_only": sorted(n for n in ours if n not in official),
        "official_starts": official_starts,
        "our_starts": our_starts,
        "starts_gap": official_starts - our_starts,
        "official_wins": official_wins,
        "our_wins": our_wins,
    }


def build_report(db_root: Path, season: str | None = None, post: PostFn = _post_graphql) -> dict:
    """永遠回 dict，唔拋 exception：status = ok / warn / unavailable。"""
    try:
        last = fetch_last_meeting(post)
        season = season or last.get("season")
        if not season:
            return {"status": "unavailable", "reason": "官方冇 lastMeeting／season"}
        # 官方統計只計到 lastMeeting；我哋多咗嘅新賽日唔好當差異。
        through = last.get("date") if last.get("season") == season else None
        results_dir = results_dir_for_season(db_root, season)
        ours = our_totals(results_dir, through)
        report: dict[str, Any] = {
            "season": season,
            "official_last_meeting": through,
            "our_meetings": len(ours["meetings"]),
            "our_last_meeting": ours["meetings"][-1] if ours["meetings"] else None,
        }
        for kind in KINDS:
            report[kind] = reconcile(official_totals(fetch_rankings(kind, season, post)), ours[kind])
    except Exception as exc:  # noqa: BLE001 —— 外部網站，任何失敗都只係「今次冇得對」
        return {"status": "unavailable", "reason": f"{type(exc).__name__}: {exc}"}
    if not report["jockey"]["compared"]:
        return {**report, "status": "unavailable", "reason": "官方排名 0 行"}
    problems = []
    if through and report["our_last_meeting"] != through:
        problems.append(f"官方最近賽日 {through}，賽果庫最後係 {report['our_last_meeting']}")
    gap = report["jockey"]["starts_gap"]
    if abs(gap) > STARTS_GAP_WARN:
        problems.append(f"騎師出賽總數差 {gap:+d}（官方 {report['jockey']['official_starts']}）")
    wins_gap = report["jockey"]["official_wins"] - report["jockey"]["our_wins"]
    if wins_gap:
        problems.append(f"頭馬總數差 {wins_gap:+d}")
    report["problems"] = problems
    report["status"] = "warn" if problems else "ok"
    return report


def format_report(report: dict, max_rows: int = 5) -> str:
    if report.get("status") == "unavailable":
        return f"官方騎練排名對數：⚪ 今次攞唔到（{report.get('reason')}）"
    j, t = report["jockey"], report["trainer"]
    head = (
        f"官方騎練排名對數（{report['season']}，至 {report.get('official_last_meeting')}）："
        f"騎師 {j['matched']}/{j['compared']}、練馬師 {t['matched']}/{t['compared']} 完全一致"
    )
    if report["status"] == "ok":
        return "✅ " + head
    lines = ["⚠️ " + head, "賽果庫可能漏咗賽日／場次：" + "；".join(report["problems"])]
    for item in j["mismatches"][:max_rows]:
        lines.append(f"  {item['name']}：官方 {item['official']} vs 我哋 {item['ours']}")
    lines.append("（[頭,二,三,四,五,出賽]；查 hkjc results 資料夾同 results-db writer）")
    return "\n".join(lines)


def _default_db_root() -> Path:
    repo = Path(__file__).resolve().parents[5]
    sys.path.insert(0, str(repo))
    from wongchoi_paths import HK_RACING  # noqa: E402

    return HK_RACING / "HKJC_Race_Results_Database"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="HKJC 官方騎練排名 vs 賽果庫對數（只做數據質素檢查）")
    parser.add_argument("--season", help="例如 26/27；預設 = 官方最近賽日所屬季度")
    parser.add_argument("--db-root", type=Path, help="HKJC_Race_Results_Database 路徑")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--dump", type=Path, help="另存官方原始騎練排名 JSON")
    args = parser.parse_args(argv)
    db_root = args.db_root or _default_db_root()
    report = build_report(db_root, args.season)
    if args.dump and report.get("season"):
        raw = {kind: fetch_rankings(kind, report["season"]) for kind in KINDS}
        args.dump.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_report(report, max_rows=50))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
