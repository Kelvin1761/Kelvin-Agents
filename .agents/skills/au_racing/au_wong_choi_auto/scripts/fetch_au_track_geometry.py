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

racinglife 做主，justhorseracing 補漏兼覆核。
  horise.com          —— 2026-11-13 加：「circumference of 1,840m … 300m home straight」文字。
                         racinglife 回防機械人頁之後，補數改為 horise 做主。

  Sportsbet cache   —— 2026-11-13 加：賽事頁「Track Details … Straight: N metres Circumference: N」，
                         由本機 sportsbetform cache 讀，**唔發請求**。實測同現有數只有 68/97 喺容差內
                         （Gunnedah 寫 200/200、Northam 1500、Gawler 2000/220），所以**只補其他三個都冇嘅空格**，
                         而且要過合理範圍同「同一場地多頁一致」。

次序：racinglife → horise → justhorseracing → Sportsbet cache（只補空格）。justhorseracing 實測有過期數（Gawler 寫 2030／220，
馬會官方同 horise 都係 1840／300），所以只有前兩個都冇先用佢。實測 justhorseracing 有幾個
**過期**條目（Pakenham 仲係搬去 Tynong 之前嘅 1400m 舊場、Rockhampton 1600m），
所以分歧一律以 racinglife 為準，同時將兩邊數字都寫入 `conflict` 留低證據。

    python3 fetch_au_track_geometry.py                 # 全部場地
    python3 fetch_au_track_geometry.py --venue Wyong   # 單一場地，覆核用
    python3 fetch_au_track_geometry.py --dry-run       # 唔寫檔，只印
    python3 fetch_au_track_geometry.py --fill-missing  # 只補現有檔入面冇直路／周長嘅場地（唔郁其他行）

⚠️ 全量重跑會用今次抓到嘅數覆蓋成個檔，包括 `backfill_track_classification_from_ra.py`
補落去嘅級別。2026-11-13 racinglife 回防機械人頁（~100 bytes），全量重跑會洗走大部分數據 ——
所以補數一律用 `--fill-missing`；`--venue` 亦只會更新嗰幾行（以前會將成個檔寫剩嗰幾行）。
"""
from __future__ import annotations

import argparse
import html
import json
import os
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
    "horise": {
        "Launceston": ["launceston", "mowbray"],
        "Rosehill Gardens": ["rosehill-gardens", "rosehill"],
        "Mt Isa": ["mount-isa", "mt-isa"],
    },
    "justhorseracing": {
        "Launceston": ["launceston", "mowbray"],
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

# racinglife 2026-11 起對 script 回 ~100 bytes 嘅防機械人頁（200 狀態碼）。當冇資料，唔好當「冇周長」。
RACINGLIFE_MIN_BODY = 2000

# 補數時要保留嘅欄位（由其他腳本寫入，生成器唔知）。
PRESERVE_FIELDS = ("classification", "classification_source")

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
    "Broome", "Carnarvon", "Emerald", "Gympie", "Katherine",
    "Mt Isa", "Narrandera", "Roma",  # Caulfield Heath、Tuncurry 2026-11-13 由 Sportsbet cache 補咗
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
        if code != "200" or len(body) < RACINGLIFE_MIN_BODY:
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


# horise 句式唔統一（「circumference of around 1,600m」「1,735m in circumference」「home straight measuring close to 300m」）。
# 直路一定要見到「home straight」先收，避免「600m 位入直路」呢類句誤當直路長度。
HORISE_CIRC = (re.compile(r"(?<![\d,])circumference of (?:about |approximately |around |roughly |just over |just under )?([\d,]{3,5}) ?m", re.I),
               re.compile(r"(?<![\d,])([\d,]{3,5}) ?m(?:etres?)? (?:in )?circumference", re.I))
HORISE_STRAIGHT = (re.compile(r"(?<![\d,])([\d,]{3}) ?m(?:etres?)? (?:(?!(?:and|or|with|into|onto|to|the|from|of|at|on|in|down|along|before|after)\b)[a-z-]+ ){0,3}home straight", re.I),
                   re.compile(r"home straight (?:of|measuring|measures|that measures|is|which is|stretching)"
                              r"(?: (?:about|approximately|around|roughly|close to|just over|just under|some))? (?<![\d,])([\d,]{3}) ?m", re.I))


def _first(patterns, text):
    for pat in patterns:
        m = pat.search(text)
        if m:
            return int(m.group(1).replace(",", ""))
    return None


def fetch_horise(venue: str) -> dict:
    for slug in SLUG_OVERRIDES["horise"].get(venue, [slugify(venue)]):
        code, body = curl(f"https://www.horise.com/track/{slug}/")
        if code != "200":
            continue
        text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", body)))
        circ, straight = _first(HORISE_CIRC, text), _first(HORISE_STRAIGHT, text)
        if circ and straight and 1000 <= circ <= 3500 and 150 <= straight <= 700:
            direction = ("anticlockwise" if re.search(r"anti-?clockwise|left-handed", text, re.I)
                         else "clockwise" if re.search(r"\bclockwise|right-handed", text, re.I) else "")
            return {"slug": slug, "circumference_m": circ, "straight_m": straight, "direction": direction}
    return {}


SPORTSBET_CACHE = Path(os.environ.get("WC_SB_CACHE") or (Path(__file__).resolve().parents[2] / ".sportsbet_cache"))
SB_TRACK = re.compile(r"Track:\s*([^,]+),.{0,120}?Straight:\s*([\d,]+)\s*metres\s*Circumference:\s*([\d,]+)")
SB_MIN_PAGES = 3
SB_MIN_SHARE = 0.8
_SB_INDEX: dict | None = None


def sportsbet_cache_index(cache_dir: Path = SPORTSBET_CACHE) -> dict:
    """{場地 slug: {"straight_m", "circumference_m", "pages", "share"}}；唔一致／唔合理嘅場地唔收。"""
    global _SB_INDEX
    if _SB_INDEX is not None:
        return _SB_INDEX
    counts: dict = {}
    if cache_dir.is_dir():
        for path in cache_dir.glob("*.html"):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            at = text.find("Circumference")
            if at < 0:
                continue
            seg = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text[max(0, at - 1500):at + 200])))
            m = SB_TRACK.search(seg)
            if m:
                key = slugify(m.group(1).strip())
                val = (int(m.group(2).replace(",", "")), int(m.group(3).replace(",", "")))
                counts.setdefault(key, {}).setdefault(val, 0)
                counts[key][val] += 1
    index = {}
    for key, vals in counts.items():
        (straight, circ), top = max(vals.items(), key=lambda kv: kv[1])
        total = sum(vals.values())
        if total >= SB_MIN_PAGES and top / total >= SB_MIN_SHARE and 1000 <= circ <= 3500 and 150 <= straight <= 700:
            index[key] = {"straight_m": straight, "circumference_m": circ, "pages": total, "share": round(top / total, 3)}
    _SB_INDEX = index
    return index


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


def merge(venue: str, primary: dict, secondary: dict, tertiary: dict | None = None) -> dict:
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
    elif tertiary and tertiary.get("circumference_m"):
        row.update({
            "circumference_m": tertiary["circumference_m"],
            "straight_m": tertiary.get("straight_m") or 0,
            "direction": normalise_direction(tertiary.get("direction")) or normalise_direction(secondary.get("direction")),
        })
        row["sources"].append("horise")
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

    if not row["circumference_m"]:
        sb = sportsbet_cache_index().get(slugify(venue))
        if sb:
            row.update({"circumference_m": sb["circumference_m"], "straight_m": sb["straight_m"]})
            row["sources"].append("sportsbet")
            row["sportsbet_pages"] = sb["pages"]
    elif not row["straight_m"]:
        sb = sportsbet_cache_index().get(slugify(venue))
        if sb and abs(sb["circumference_m"] - row["circumference_m"]) <= CIRC_TOLERANCE_M:
            row["straight_m"] = sb["straight_m"]
            row["sources"].append("sportsbet")
            row["sportsbet_pages"] = sb["pages"]

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

    seen = {name: src for name, src in (("racinglife", primary), ("horise", tertiary or {}),
                                         ("justhorseracing", secondary)) if src.get("circumference_m")}
    if len(seen) >= 2:
        vals = {name: [src["circumference_m"], src.get("straight_m")] for name, src in seen.items()}
        circs = [v[0] for v in vals.values()]
        straights = [v[1] or 0 for v in vals.values()]
        if max(circs) - min(circs) > CIRC_TOLERANCE_M or max(straights) - min(straights) > STRAIGHT_TOLERANCE_M:
            row["conflict"] = vals
    if tertiary and tertiary.get("circumference_m") and "horise" not in row["sources"]:
        row["sources"].append("horise")
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--venue", action="append", help="只抽呢個場地（可重複）")
    parser.add_argument("--dry-run", action="store_true", help="唔寫檔")
    parser.add_argument("--sleep", type=float, default=0.3)
    parser.add_argument("--fill-missing", action="store_true",
                        help="只抽現有檔入面未有周長＋直路嘅場地，其他行原封不動")
    args = parser.parse_args()

    existing = {}
    if RESOURCE_PATH.exists():
        existing = json.loads(RESOURCE_PATH.read_text(encoding="utf-8")).get("venues", {})
    if args.fill_missing:
        venues = [row.get("venue") or key for key, row in sorted(existing.items())
                  if not (row.get("circumference_m") and row.get("straight_m"))]
    else:
        venues = args.venue or VENUES
    rows = {}
    for i, venue in enumerate(venues, 1):
        primary = fetch_racinglife(venue)
        time.sleep(args.sleep)
        secondary = fetch_justhorseracing(venue)
        time.sleep(args.sleep)
        tertiary = fetch_horise(venue)
        time.sleep(args.sleep)
        row = merge(venue, primary, secondary, tertiary)
        prev = existing.get(slugify(venue)) or {}
        for field in PRESERVE_FIELDS:
            if prev.get(field) and not row.get(field):
                row[field] = prev[field]
        if (args.fill_missing or args.venue) and prev.get("circumference_m") and not row["circumference_m"]:
            row = prev  # 今次抓唔到 → 保留舊行，唔好用空行蓋過
        rows[slugify(venue)] = row
        flag = "⚠" if row["conflict"] else ("✓" if row["circumference_m"] else "✗")
        print(
            f"{i:3d}/{len(venues)} {flag} {venue:22s} "
            f"{row['circumference_m'] or '':>6} {row['straight_m'] or '':>5} "
            f"{row['direction']:16s} {','.join(row['sources'])}",
            file=sys.stderr, flush=True,
        )

    if args.fill_missing or args.venue:
        rows = {**existing, **rows}  # 部分更新：未抽嘅場地原封不動
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
