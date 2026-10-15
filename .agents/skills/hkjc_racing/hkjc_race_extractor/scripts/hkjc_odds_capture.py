#!/usr/bin/env python3
"""HKJC 賽前獨贏／位置賠率快照 —— forward-only，**唔入分析**。

點解要有：HKJC 之前只有賽果頁嗰個最終 `win_odds`（`fast_extract_results.py`、
`extract_results.py`），冇任何帶時間戳嘅賽前賠率。冇呢樣嘢，市場混合、去水、
位置 vs 獨贏一致性、尾段落飛訊號全部冇得測。歷史補唔返，所以只可以由今日起
逐次影低。

來源：bet.hkjc.com 官方投注網自己用緊嘅公開 GraphQL（`GlobalConfig.js` 嘅
`GRAPHQL_URL` = `https://info.cld.hkjc.com/graphql/base-get/`，GET）。唔使登入、
冇 CAPTCHA。⚠️ 個 server 有 query **白名單**：自己寫嘅 query 會回
`WHITELIST_ERROR`，一定要用官方網頁 bundle 入面嗰條 `sp4e_racing_pmPool`
原文，再照網頁咁做 `stripIgnoredCharacters`（graphql-js）。一次請求
（`raceNo: 0`）就攞晒全日每場 WIN + PLA，所以每次快照只係一個 GET。

⚠️ **紅線**：快照寫入 meeting folder 嘅 `HKJC_Odds_History.json`，唔係
`*Facts.md`、唔係 `Race_*_Logic.json`，亦唔喺 prediction snapshot 嘅
`SNAPSHOT_PATTERNS`。`tests/test_hkjc_odds_capture.py` 釘死評分引擎唔准讀佢
—— 市場排序一入分就會主導成個模型（AU 實測 AUC 0.7393 vs 我哋 0.6530），
呢個係產品定位決定，唔可以靜靜咁發生。

⚠️ **追加唔覆蓋**：一個時間點冇用，一連串先睇得出市場點郁。每個快照帶
`captured_at`（ISO，有時區）同 `label`（邊個排程格影嘅）。每場另記投注池狀態；
`pre_race` 只喺 WIN 同 PLA 兩個池都仲係 `START_SELL` 先係 True —— 已經停售
嘅場次個價係開跑後嘅，回測一定要用 `pre_race` 過濾。
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import sys
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Callable

GRAPHQL_GET_URL = "https://info.cld.hkjc.com/graphql/base-get/"
ODDS_HISTORY = "HKJC_Odds_History.json"
SOURCE = "bet.hkjc.com GraphQL sp4e_racing_pmPool (WIN, PLA)"
SELLING = "START_SELL"

# 原文抄自 bet.hkjc.com `static/js/main.*.js`（2026-10-14）。白名單比對嘅係
# strip 之後嘅 token 序列，所以縮排無所謂，但**欄位同次序一個都唔可以改**。
PM_POOL_QUERY = """
      query sp4e_racing_pmPool($date: String, $venueCode: String, $oddsTypes: [OddsType], $raceNo: Int) {
          raceMeetings(date: $date, venueCode: $venueCode)
          {
            pmPools(oddsTypes: $oddsTypes, raceNo: $raceNo) {
              id
              status
              sellStatus
              oddsType
              lastUpdateTime
              oddsLastUpdateTime
              guarantee
              minTicketCost
              name_en
              name_ch
              leg {
                number
                races
              }
              cWinSelections {
                composite
                name_ch
                name_en
                starters
              }
              oddsNodes {
                combString
                oddsValue
                hotFavourite
                oddsDropValue
                bankerOdds {
                  combString
                  oddsValue
                }
              }
            }
          }
      }
"""

_TOKEN = re.compile(
    r'\.\.\.|[!$&():=@\[\]{}|]|[_A-Za-z][_0-9A-Za-z]*|-?\d+(?:\.\d+)?|"(?:[^"\\]|\\.)*"'
)
_PUNCT = re.compile(r'\.\.\.|[!$&():=@\[\]{}|]')


class OddsCaptureError(RuntimeError):
    """抓唔到／回應唔啱。呼叫者要當失敗報，但唔可以拖冧預測 pipeline。"""


def strip_ignored(source: str) -> str:
    """graphql-js `stripIgnoredCharacters` 嘅最小版本（夠用於冇 block string 嘅 query）。

    逗號同空白係 ignored token；兩個非標點 token 之間先需要一個空格。
    """
    out: list[str] = []
    prev_word = False
    for token in _TOKEN.findall(source.replace(",", " ")):
        word = not _PUNCT.fullmatch(token)
        if prev_word and (word or token == "..."):
            out.append(" ")
        out.append(token)
        prev_word = word
    return "".join(out)


def build_url(race_date: str, venue_code: str) -> str:
    variables = {"date": race_date, "venueCode": venue_code.upper(),
                 "raceNo": 0, "oddsTypes": ["WIN", "PLA"]}
    return GRAPHQL_GET_URL + "?" + urllib.parse.urlencode({
        "query": strip_ignored(PM_POOL_QUERY),
        "variables": json.dumps(variables, separators=(",", ":")),
    })


def _http_get(url: str, timeout: float = 20.0) -> bytes:
    request = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": "https://bet.hkjc.com",
        "Referer": "https://bet.hkjc.com/",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    })
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def fetch_pools(race_date: str, venue_code: str, *,
                getter: Callable[[str], bytes] | None = None) -> dict:
    """一個 GET → 原始 GraphQL payload。任何問題都拋 `OddsCaptureError`。"""
    try:
        raw = (getter or _http_get)(build_url(race_date, venue_code))
    except Exception as exc:  # noqa: BLE001 — 網絡層任何錯都係「抓唔到」
        raise OddsCaptureError(f"HTTP 失敗：{type(exc).__name__}: {exc}") from exc
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise OddsCaptureError(f"回應唔係 JSON：{raw[:120]!r}") from exc
    if payload.get("errors"):
        # WHITELIST_ERROR = 官方網頁改咗 query，要重新由 bundle 抄過。
        message = "; ".join(str(e.get("message")) for e in payload["errors"])
        raise OddsCaptureError(f"GraphQL 錯誤：{message}")
    return payload


def _price(value) -> float | None:
    try:
        price = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return price if price > 0 else None


def parse_pools(payload: dict) -> dict[str, dict]:
    """→ `{場號: {"runners": {馬號: {"win", "place"}}, "scratched", 池狀態...}}`。

    馬號用 `int` 再轉 str（`"01"` → `"1"`），同 Logic 嘅馬號一致。賠率唔係數字
    （`SCR` 等）就當退出，唔會寫一個假價。
    """
    meetings = ((payload.get("data") or {}).get("raceMeetings")) or []
    races: dict[str, dict] = {}
    for meeting in meetings:
        for pool in (meeting or {}).get("pmPools") or []:
            kind = {"WIN": "win", "PLA": "place"}.get(str(pool.get("oddsType")))
            legs = ((pool.get("leg") or {}).get("races")) or []
            if kind is None or len(legs) != 1:
                continue
            race = races.setdefault(str(int(legs[0])), {"runners": {}, "scratched": []})
            race[f"{kind}_status"] = pool.get("sellStatus") or pool.get("status")
            race[f"{kind}_updated"] = pool.get("oddsLastUpdateTime") or pool.get("lastUpdateTime")
            for node in pool.get("oddsNodes") or []:
                comb = str(node.get("combString") or "").strip()
                if not comb.isdigit():
                    continue
                horse = str(int(comb))
                price = _price(node.get("oddsValue"))
                if price is None:
                    if horse not in race["scratched"]:
                        race["scratched"].append(horse)
                    continue
                race["runners"].setdefault(horse, {})[kind] = price
    for race in races.values():
        race["scratched"] = sorted(race["scratched"], key=int)
        for horse in race["scratched"]:
            race["runners"].pop(horse, None)
        race["pre_race"] = (race.get("win_status") == SELLING
                            and race.get("place_status") == SELLING)
    return {k: races[k] for k in sorted(races, key=int) if races[k]["runners"]}


def _atomic_write(path: Path, payload: dict) -> None:
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=1)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def write_snapshot(meeting_dir: Path, *, race_date: str, venue: str, venue_code: str,
                   races: dict[str, dict], label: str,
                   captured_at: datetime | None = None) -> Path:
    """追加一個快照入 `HKJC_Odds_History.json`。舊快照永遠唔會被改寫。"""
    path = meeting_dir / ODDS_HISTORY
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict) or not isinstance(doc.get("snapshots"), list):
            raise ValueError("bad shape")
    except FileNotFoundError:
        doc = None
    except (OSError, ValueError) as exc:
        # 壞檔唔可以默默覆蓋 —— 嗰度可能有幾日嘅歷史。改名留證，再開新檔。
        backup = path.with_name(f"{path.name}.corrupt-{datetime.now():%Y%m%dT%H%M%S}")
        os.replace(path, backup)
        print(f"⚠️ {path.name} 讀唔到（{exc}），已移去 {backup.name}", file=sys.stderr)
        doc = None
    if doc is None:
        doc = {
            "schema_version": 1,
            "platform": "hkjc",
            "date": race_date,
            "venue": venue,
            "venue_code": venue_code,
            "source": SOURCE,
            "scoring_input": False,
            "snapshots": [],
        }
    at = captured_at or datetime.now().astimezone()
    doc["snapshots"].append({
        "captured_at": at.isoformat(timespec="seconds"),
        "label": label,
        "races": races,
    })
    meeting_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, doc)
    return path


def capture_meeting(meeting_dir: Path, *, race_date: str, venue: str, venue_code: str,
                    label: str, getter: Callable[[str], bytes] | None = None,
                    captured_at: datetime | None = None) -> dict:
    """抓一次、寫一次。→ `{"status": "ok"|"not_open", ...}`；失敗拋 `OddsCaptureError`。

    `not_open` = 投注池未開（通常係賽前一日太早）；`closed` = 全日每場都已停售
    （賽後）。兩者都唔寫檔、唔當失敗 —— 收市價賽果頁已經有，唔使重複影。
    """
    races = parse_pools(fetch_pools(race_date, venue_code, getter=getter))
    if not races:
        return {"status": "not_open", "races": 0, "runners": 0, "pre_race_races": 0}
    if not any(r["pre_race"] for r in races.values()):
        return {"status": "closed", "races": len(races), "runners": 0, "pre_race_races": 0}
    path = write_snapshot(meeting_dir, race_date=race_date, venue=venue,
                          venue_code=venue_code, races=races, label=label,
                          captured_at=captured_at)
    return {
        "status": "ok",
        "races": len(races),
        "runners": sum(len(r["runners"]) for r in races.values()),
        "pre_race_races": sum(1 for r in races.values() if r["pre_race"]),
        "path": str(path),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--venue-code", required=True, choices=("ST", "HV", "st", "hv"))
    parser.add_argument("--meeting-dir", type=Path, required=True)
    parser.add_argument("--label", default="manual")
    args = parser.parse_args(argv)
    code = args.venue_code.upper()
    try:
        result = capture_meeting(
            args.meeting_dir, race_date=args.date,
            venue="ShaTin" if code == "ST" else "HappyValley",
            venue_code=code, label=args.label)
    except OddsCaptureError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
