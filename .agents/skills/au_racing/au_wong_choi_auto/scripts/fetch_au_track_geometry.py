#!/usr/bin/env python3
"""抽 AU 賽道幾何（周長 / 直路 / 方向）並寫成 `resources/au_track_geometry.json`。

點解要有呢個腳本：呢批數以前係九份人手寫 markdown，2026-09-02 實測發現
85 個場地印緊合集檔第一節（Canterbury）嘅數，而連手寫嗰批本身都有錯
（Morphettville 寫 2000/350，真值 2339/334；Ascot 寫 1860/350，真值 2022/294）。
資料要有來源、有抓取日期、可以重跑覆核，所以改為生成，唔再手寫。

兩個來源，逐個場地交叉核對：
  racinglife.com.au   —— `<dt>Circumference</dt><dd>2,224m</dd>` 結構，數據較新
  justhorseracing.com.au —— `<meta name=description>` 入面
                             `State: … Circumference: … Direction: … Straight: … <評語>`

racinglife 做主，justhorseracing 補漏兼覆核。實測 justhorseracing 有幾個
**過期**條目（Pakenham 仲係搬去 Tynong 之前嘅 1400m 舊場、Rockhampton 1600m），
所以分歧一律以 racinglife 為準，同時將兩邊數字都寫入 `conflict` 留低證據。

    python3 fetch_au_track_geometry.py                 # 全部場地
    python3 fetch_au_track_geometry.py --venue Wyong   # 單一場地，覆核用
    python3 fetch_au_track_geometry.py --dry-run       # 唔寫檔，只印
"""
from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

RESOURCE_PATH = Path(__file__).resolve().parent.parent / "resources" / "au_track_geometry.json"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36"

# 兩個站嘅 slug 唔一定同場地名一樣。留空 list 代表用預設 slug。
SLUG_OVERRIDES = {
    "racinglife": {
        "Sandown": ["sandown-hillside"],
        "Mt Isa": ["mount-isa", "mt-isa"],
        "Devonport": ["devonport-synthetic", "devonport"],
        "Wagga": ["wagga", "wagga-wagga"],
        "Belmont": ["belmont", "belmont-park"],
        "Canterbury": ["canterbury", "canterbury-park"],
        "Mount Gambier": ["mount-gambier", "mt-gambier"],
    },
    "justhorseracing": {
        "Sandown": ["sandown-hillside"],
        "Mt Isa": ["mount-isa", "mt-isa"],
        "Devonport": ["devonport-synthetic", "devonport"],
        "Wagga": ["wagga-wagga", "wagga"],
        "Belmont": ["belmont-park", "belmont"],
        "Canterbury": ["canterbury-park", "canterbury"],
        "Kembla Grange": ["kembla-grange", "kembla"],
        "Rosehill Gardens": ["rosehill-gardens", "rosehill"],
    },
}

# 一場地一行。呢個 list 係「我哋跑過或者可能跑」嘅場地，唔係全澳所有賽場。
VENUES = [
    "Albury", "Alice Springs", "Ascot", "Ballarat", "Ballarat Synthetic", "Ballina",
    "Bathurst", "Beaudesert", "Belmont", "Bendigo", "Broome", "Bunbury", "Cairns",
    "Canberra", "Canterbury", "Carnarvon", "Casino", "Casterton", "Caulfield",
    "Caulfield Heath", "Coffs Harbour", "Corowa", "Cranbourne", "Dalby", "Devonport",
    "Doomben", "Dubbo", "Eagle Farm", "Echuca", "Emerald", "Flemington", "Geelong",
    "Gold Coast", "Gosford", "Goulburn", "Grafton", "Gunnedah", "Gympie", "Hawkesbury",
    "Hobart", "Ipswich", "Kalgoorlie", "Katherine", "Kembla Grange", "Kensington",
    "Kilcoy", "Mackay", "Mildura", "Moe", "Moonee Valley", "Moree", "Morphettville",
    "Moruya", "Mount Gambier", "Mt Isa", "Mudgee", "Murray Bridge", "Murtoa",
    "Murwillumbah", "Muswellbrook", "Narrandera", "Narromine", "Newcastle", "Northam",
    "Nowra", "Pakenham", "Pakenham Synthetic", "Pinjarra", "Pinjarra Scarpside",
    "Port Augusta", "Port Macquarie", "Quirindi", "Randwick", "Rockhampton", "Roma",
    "Rosehill Gardens", "Sale", "Sandown", "Sandown Lakeside", "Scone", "Seymour",
    "Strathalbyn", "Sunshine Coast", "Tamworth", "Taree", "Toowoomba", "Townsville",
    "Tuncurry", "Wagga", "Wangaratta", "Warracknabeal", "Warrnambool", "Warwick Farm",
    "Wellington", "Wodonga", "Wyong",
]

# 分歧門檻：低過呢個當量度差異，唔算衝突。
CIRC_TOLERANCE_M = 60
STRAIGHT_TOLERANCE_M = 30

# 兩個站都冇、但人手查證到嘅場地。**要寫明來源同查證日期** —— 冇來源嘅數字同
# 之前嗰批手寫檔冇分別。冇查證到就唔好填：留空係「唔知」，亂填係「講大話」。
MANUAL_OVERRIDES = {
    "Northam": {
        "circumference_m": 2017, "straight_m": 425, "direction": "anticlockwise",
        "source": "races.com.au / progroupracing 場地頁（2026-09-02 查證）",
    },
    "Ballarat Synthetic": {
        "circumference_m": 1900, "straight_m": 375, "direction": "anticlockwise",
        "source": "Racing Victoria 合成跑道規格（2026-09-02 查證）；草地跑道係 1900/450，唔好撈亂",
    },
    "Pakenham Synthetic": {
        "circumference_m": 2000, "straight_m": 0, "direction": "anticlockwise",
        "source": "2014 Tynong 新場公告：合成跑道周長 2000m，1400/1600m 有 chute；直路長度未見公佈",
    },
}

# 兩邊都搵唔到、人手都查唔到嘅場地。寫低係為咗唔好次次重新查一次。
KNOWN_UNDOCUMENTED = {
    "Broome", "Carnarvon", "Caulfield Heath", "Emerald", "Gympie", "Katherine",
    "Mt Isa", "Narrandera", "Roma", "Tuncurry",
}


def normalise_direction(value: str) -> str:
    """`anti-clockwise` / `Anticlockwise` / `anti clockwise` 全部收成一個值。"""
    text = re.sub(r"[^a-z]", "", str(value or "").lower())
    if text.startswith("anti") or text.startswith("counter"):
        return "anticlockwise"
    if text.startswith("clock"):
        return "clockwise"
    return ""


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def curl(url: str) -> tuple[str, str]:
    result = subprocess.run(
        ["curl", "-sL", "--max-time", "25", "-A", UA, "-w", "\n%{http_code}", url],
        capture_output=True, text=True,
    )
    body, _, code = result.stdout.rpartition("\n")
    return code.strip(), body


def _first_int(text: str) -> int | None:
    match = re.search(r"([\d,]+)", text or "")
    return int(match.group(1).replace(",", "")) if match else None


def fetch_racinglife(venue: str) -> dict:
    for slug in SLUG_OVERRIDES["racinglife"].get(venue, [slugify(venue)]):
        code, body = curl(f"https://www.racinglife.com.au/tracks/{slug}")
        if code != "200":
            continue
        fields = {}
        for label in ("Classification", "Direction", "Surface", "Circumference", "Home straight", "Region"):
            match = re.search(rf"<dt[^>]*>{re.escape(label)}</dt><dd[^>]*>([^<]+)</dd>", body)
            if match:
                fields[label] = html.unescape(match.group(1)).strip()
        if fields.get("Circumference"):
            return {
                "slug": slug,
                "circumference_m": _first_int(fields.get("Circumference")),
                "straight_m": _first_int(fields.get("Home straight")),
                "direction": fields.get("Direction", "").lower(),
                "classification": fields.get("Classification", ""),
                "surface": fields.get("Surface", ""),
                "region": fields.get("Region", ""),
            }
    return {}


JHR_SPEC = re.compile(
    r"State:\s*(?P<state>\w+)\s*Circumference:\s*(?P<circ>[\d,]+)\s*"
    r"Direction:\s*(?P<direction>[\w\s-]+?)\s*Straight:\s*(?P<straight>[\d,]+)\s*(?P<note>.*)$"
)


def fetch_justhorseracing(venue: str) -> dict:
    for slug in SLUG_OVERRIDES["justhorseracing"].get(venue, [slugify(venue)]):
        code, body = curl(f"https://www.justhorseracing.com.au/tracks/{slug}-racecourse")
        if code != "200":
            continue
        match = re.search(r'name="description" content="([^"]*)"', body)
        if not match:
            continue
        spec = JHR_SPEC.match(html.unescape(match.group(1)))
        if spec:
            return {
                "slug": slug,
                "state": spec.group("state"),
                "circumference_m": int(spec.group("circ").replace(",", "")),
                "straight_m": int(spec.group("straight").replace(",", "")),
                "direction": spec.group("direction").strip().lower(),
                "note": spec.group("note").strip(),
            }
    return {}


def merge(venue: str, primary: dict, secondary: dict) -> dict:
    """racinglife 做主。分歧唔靜靜取其一 —— 兩邊都寫低。"""
    row = {
        "venue": venue,
        "circumference_m": 0,
        "straight_m": 0,
        "direction": "",
        "classification": "",
        "surface": "",
        "state": "",
        "note": "",
        "sources": [],
        "conflict": None,
    }
    if primary.get("circumference_m"):
        row.update({
            "circumference_m": primary["circumference_m"],
            "straight_m": primary.get("straight_m") or 0,
            "direction": normalise_direction(primary.get("direction")),
            "classification": primary.get("classification", ""),
            "surface": primary.get("surface", ""),
        })
        row["sources"].append("racinglife")
        # racinglife 有時得周長冇直路（Hawkesbury）。缺嗰半用第二個源補返，
        # 唔好因為主源缺一格就整個場地當冇資料。
        if not row["straight_m"] and secondary.get("straight_m"):
            row["straight_m"] = secondary["straight_m"]
    elif secondary.get("circumference_m"):
        row.update({
            "circumference_m": secondary["circumference_m"],
            "straight_m": secondary.get("straight_m") or 0,
            "direction": normalise_direction(secondary.get("direction")),
        })
        row["sources"].append("justhorseracing")

    if secondary:
        row["state"] = secondary.get("state", "") or row["state"]
        row["note"] = secondary.get("note", "") or row["note"]
        if "justhorseracing" not in row["sources"]:
            row["sources"].append("justhorseracing")

    override = MANUAL_OVERRIDES.get(venue)
    if override and not row["circumference_m"]:
        row.update({
            "circumference_m": override["circumference_m"],
            "straight_m": override.get("straight_m") or 0,
            "direction": normalise_direction(override.get("direction")),
        })
        row["sources"].append("manual")
        row["note"] = override["source"]
    if not row["circumference_m"] and venue in KNOWN_UNDOCUMENTED:
        row["undocumented"] = True

    if primary.get("circumference_m") and secondary.get("circumference_m"):
        d_circ = abs(primary["circumference_m"] - secondary["circumference_m"])
        d_str = abs((primary.get("straight_m") or 0) - (secondary.get("straight_m") or 0))
        if d_circ > CIRC_TOLERANCE_M or d_str > STRAIGHT_TOLERANCE_M:
            row["conflict"] = {
                "racinglife": [primary["circumference_m"], primary.get("straight_m")],
                "justhorseracing": [secondary["circumference_m"], secondary.get("straight_m")],
            }
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--venue", action="append", help="只抽呢個場地（可重複）")
    parser.add_argument("--dry-run", action="store_true", help="唔寫檔")
    parser.add_argument("--sleep", type=float, default=0.3)
    args = parser.parse_args()

    venues = args.venue or VENUES
    rows = {}
    for i, venue in enumerate(venues, 1):
        primary = fetch_racinglife(venue)
        time.sleep(args.sleep)
        secondary = fetch_justhorseracing(venue)
        time.sleep(args.sleep)
        row = merge(venue, primary, secondary)
        rows[slugify(venue)] = row
        flag = "⚠" if row["conflict"] else ("✓" if row["circumference_m"] else "✗")
        print(
            f"{i:3d}/{len(venues)} {flag} {venue:22s} "
            f"{row['circumference_m'] or '':>6} {row['straight_m'] or '':>5} "
            f"{row['direction']:16s} {','.join(row['sources'])}",
            file=sys.stderr, flush=True,
        )

    known = sum(1 for r in rows.values() if r["circumference_m"] and r["straight_m"])
    payload = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": {
            "racinglife": "https://www.racinglife.com.au/tracks/<slug>",
            "justhorseracing": "https://www.justhorseracing.com.au/tracks/<slug>-racecourse",
        },
        "resolution_rule": "racinglife 做主；justhorseracing 補漏兼覆核；分歧記入 conflict 但採用 racinglife",
        "venues_total": len(rows),
        "venues_with_geometry": known,
        "venues": dict(sorted(rows.items())),
    }
    print(f"\n有齊周長+直路：{known}/{len(rows)}", file=sys.stderr)
    conflicts = [v for v in rows.values() if v["conflict"]]
    if conflicts:
        print(f"分歧（已取 racinglife，證據留喺 conflict）：{len(conflicts)} —— "
              + ", ".join(v["venue"] for v in conflicts), file=sys.stderr)

    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=1))
        return 0
    RESOURCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESOURCE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"寫入 {RESOURCE_PATH}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
