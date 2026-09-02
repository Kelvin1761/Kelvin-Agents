#!/usr/bin/env python3
"""馬匹往績索引 —— `claw_profile_scraper.py` 嘅替代品（賽績線用）。

**點解要換。** `inject_fact_anchors` 靠 shell out 去 `claw_profile_scraper.py` 查
「呢個對手之後有冇再出賽、有冇贏」。嗰個係 Racenet，而 Racenet 已經全封：

    $ python3 claw_profile_scraper.py --names "Stage 'n' Screen"
    {"stage-n-screen": {"error": "HTTP 202"}}

實測 2026-08-01 Flemington：**307/307 條對手行「查冊失敗」**，
`_formline_support_summary()` 見到 valid_rows=0，賽績線全場坐 60。
呢個唔止影響 Sportsbet —— 由封鎖嗰日起，**任何**新場次都一樣。

**點解唔用 `/Competitor/{id}/`。** 嗰版有齊 career/月度/場地狀況/路程統計，
但**冇逐場清單**（冇日期、冇馬場），而賽績線要嘅正正係「喺某個日期之後」。
月度統計最多做到月為單位，而且冇馬場就分唔到 Metro／省賽。

**點解呢個做法唔使多打一個請求。** 我哋每抓一場，`parse_runner_blocks` 已經
連埋每匹馬**成個往績清單**（日期、馬場、名次、馬群大細）。即係話索引係抽取嘅
副產品：抓過邊隻馬，就有嗰隻馬嘅完整往績。對手只要喺我哋抓過嘅任何一場出過賽，
就查得到 —— 唔使再去打對手嘅個人頁。

輸出格式**照抄** `claw_profile_scraper.py`，所以係 drop-in：

    {"stage-n-screen": {"runs": [{"date","date_full","venue","finish",
                                  "starters","is_placed","class"}, ...]}}

用法：
    python3 sb_horse_index.py --names "Stage 'n' Screen,Cherish Me"
    python3 sb_horse_index.py --stats
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

DEFAULT_INDEX = Path(os.environ.get("WC_SB_HORSE_INDEX", "")) if os.environ.get(
    "WC_SB_HORSE_INDEX") else Path(__file__).resolve().parent / ".sb_horse_index.json"

# 同 claw_profile_scraper.infer_class 一致 —— 賽績線嘅 Metro 判斷靠佢
METRO_VENUES = ("randwick", "rosehill", "flemington", "caulfield", "moonee valley",
                "eagle farm", "doomben", "sandown", "canterbury", "kensington",
                "warwick farm")


def build_slug(name: str) -> str:
    """'Stage 'n' Screen (NZL)' → 'stage-n-screen'。同舊 scraper 逐字一致。"""
    clean = re.sub(r"\s*\([^)]+\)", "", name or "")
    return re.sub(r"[^a-z0-9]+", "-", clean.lower().strip()).strip("-")


def infer_class(venue: str) -> str:
    if not venue:
        return "-"
    v = venue.lower().strip()
    return "Metro" if any(m in v for m in METRO_VENUES) else "省賽"


def _run_record(run: dict) -> dict | None:
    """由 `parse_runner_blocks` 嘅 run dict 砌一條索引記錄。"""
    from claw_sportsbet_form import run_date

    date = run_date(run)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date or ""):
        return None
    venue = ((run.get("header") or {}).get("track") or "").strip()
    try:
        finish = int(run["pos"]) if run.get("pos") else None
    except (TypeError, ValueError):
        finish = None
    try:
        starters = int(run["field"]) if run.get("field") else None
    except (TypeError, ValueError):
        starters = None
    return {"date": date, "date_full": date, "venue": venue, "finish": finish,
            "starters": starters,
            "is_placed": finish is not None and 1 <= finish <= 3,
            "class": infer_class(venue)}


def load(path=DEFAULT_INDEX) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save(index: dict, path=DEFAULT_INDEX) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)          # atomic —— 中途死唔會留半個索引


_ORD = {"1st": 1, "2nd": 2, "3rd": 3}


def _opponent_records(run):
    """由一條往績行嘅對手名單砌記錄 —— **零額外請求**。

    往績行「Newcastle R7 2026-03-06 … / 1-Emery, 2-Beaumista, 3-Gogmagog」
    同時話咗我哋知 Emery 喺嗰日嗰個馬場贏咗。即係每一條往績行都係三隻**對手**
    嘅 run 記錄，而唔止係嗰匹馬自己嘅。

    ⚠️ **呢啲記錄係有系統性偏差嘅** —— 我哋只會喺對手入到前三嗰陣見到佢。
    佢跑第八嗰次係隱形嘅。所以標記 `partial: True`：
      * `future_wins` / `future_places` 只代表已觀察到嘅勝出／上名次數，
        唔保證涵蓋全部出賽。
      * `future_runs`（做分母算上名率）**用唔得** —— 會永遠得出 100%。
    消費者要按 `partial` 分開處理，見 `inject_fact_anchors.compute_form_lines_via_api`。
    """
    from claw_sportsbet_form import run_date

    h = run.get("header") or {}
    date = run_date(run)
    venue = (h.get("track") or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date or ""):
        return
    try:
        starters = int(run["field"]) if run.get("field") else None
    except (TypeError, ValueError):
        starters = None
    for o in run.get("opponents") or []:
        finish = _ORD.get(o.get("ord"))
        name = (o.get("name") or "").strip()
        if not finish or not name:
            continue
        yield name, {"date": date, "date_full": date, "venue": venue,
                     "finish": finish, "starters": starters, "is_placed": True,
                     "class": infer_class(venue), "partial": True}


def _merge(entry, rec):
    """(date, venue) 去重。完整記錄永遠蓋過 partial 記錄。"""
    key = (rec["date"], rec["venue"])
    for i, r in enumerate(entry["runs"]):
        if (r["date"], r["venue"]) == key:
            if r.get("partial") and not rec.get("partial"):
                entry["runs"][i] = rec       # 升級：見到完整嗰版就換走
                return True
            return False
    entry["runs"].append(rec)
    return True


def update(blocks, index=None, path=DEFAULT_INDEX, save_now=True,
           opponents=True) -> dict:
    """把一場（或一個馬場）嘅 runner blocks 併入索引。回傳統計。

    同一匹馬喺多場出現會逐次補；用 (date, venue) 做 key 去重，所以重跑係冪等。

    `opponents=True` 額外由每條往績行嘅對手名單砌記錄。實測呢個係最大嘅
    覆蓋來源：836 個 Formguide 引用咗 **15,713 隻**唯一對手，而由 runner
    block 砌嘅索引只有 5,583 隻 —— 即係只命中 12.8%。對手記錄唔使多打一個
    請求就補到餘下嗰批。
    """
    index = load(path) if index is None else index
    horses = added = opp_added = 0
    for blk in blocks or []:
        slug = build_slug(blk.get("name"))
        if not slug:
            continue
        horses += 1
        entry = index.setdefault(slug, {"name": blk.get("name"), "runs": []})
        for run in blk.get("runs", []):
            rec = _run_record(run)
            if rec and _merge(entry, rec):
                added += 1
            if not opponents:
                continue
            for oname, orec in _opponent_records(run):
                oslug = build_slug(oname)
                if not oslug:
                    continue
                oentry = index.setdefault(oslug, {"name": oname, "runs": []})
                if _merge(oentry, orec):
                    opp_added += 1
    for entry in index.values():
        entry["runs"].sort(key=lambda r: r["date"], reverse=True)
    if save_now:
        save(index, path)
    return {"horses": horses, "runs_added": added,
            "opponent_runs_added": opp_added, "index_size": len(index)}


def lookup(names, path=DEFAULT_INDEX, as_of="") -> dict:
    """`--names` 嘅查詢。查唔到就出 `{"error": ...}`，同舊 scraper 一致 ——
    上游會譯做「查冊失敗」，唔會靜靜當成「未有出賽」（0 勝）而扣分。

    ⚠️ `as_of` = 我哋要預測嗰場嘅日期，**當日或之後嘅往績一律剔走**。索引係由
    賽後頁面砌嘅，入面有埋當日賽果；唔設呢個閘，對手今日贏咗嗰場會被
    `compute_form_lines_via_api` 當成「後續走勢」計入賽績線 —— 同表格頁嗰個
    賽後洩漏一模一樣，只係由另一道門入。
    """
    index = load(path)
    out = {}
    for name in names:
        slug = build_slug(name)
        if not slug:
            continue
        hit = index.get(slug)
        if not hit:
            out[slug] = {"error": "not in index"}
            continue
        runs = hit["runs"]
        if as_of:
            runs = [r for r in runs if r["date"] < as_of]
        # Reclassify cached venue labels without rewriting the history or
        # changing the as-of boundary. Old indexes omitted Warwick Farm.
        out[slug] = {"runs": [{**r, "class": infer_class(r.get("venue", ""))}
                             for r in runs]}
    return out


def main():
    ap = argparse.ArgumentParser(description="Sportsbet 馬匹往績索引")
    ap.add_argument("--names", help="逗號分隔嘅馬名")
    ap.add_argument("--slugs", help="逗號分隔嘅 slug")
    ap.add_argument("--index", default=str(DEFAULT_INDEX))
    ap.add_argument("--as-of", default="",
                    help="場次日期 YYYY-MM-DD —— 當日或之後嘅往績會被剔走")
    ap.add_argument("--stats", action="store_true")
    args = ap.parse_args()

    if args.stats:
        idx = load(args.index)
        runs = sum(len(v.get("runs") or []) for v in idx.values())
        print(f"索引：{len(idx):,} 匹馬、{runs:,} 條往績 → {args.index}")
        return 0

    names = []
    if args.names:
        names += [n.strip() for n in args.names.split(",") if n.strip()]
    if args.slugs:
        names += [s.strip() for s in args.slugs.split(",") if s.strip()]
    if not names:
        print(json.dumps({"error": "No names provided"}))
        return 1
    print(json.dumps(lookup(names, args.index, args.as_of), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
