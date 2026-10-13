#!/usr/bin/env python3
"""Sportsbet 賽前 Expert Tips + Selections 存檔（2026-10-14）。

點解要存：每個**賽前**賽事頁都有一段 `<div id="expert-tips">`（評述 + 3–4 匹
Selections），但賽後重抽會覆蓋 cache，而由頭到尾冇人寫低過 —— 所以佢有冇
資訊含量，我哋一直**冇得量**。呢個 module 只做一件事：賽前見到就 append 一行
JSONL，point-in-time，約三個月後先拎嚟測。

⚠️ **唔准**餵入評分引擎、Formguide.md 或 Racecard.md。一餵就改咗模型輸入同
golden；而且專家貼士好可能同市場高度重疊（見 memory「市場嗰份優勢同我哋特徵
正交」）—— 要先做 leakage / 正交性審計先可以考慮。

HTML 結構（2026-10 實測 62 頁，全部一樣）::

    <div id="expert-tips" class="sprite-expert">
      ... <h3>Expert Tips</h3>
          <p class="expert-comment-container">截短版… <a>Show more</a></p>
          <div class="full-comment">全文</div>
      <div class="selection">
        <strong class="selection-label">Selections:</strong>
        <span class="selection-runner"><span><img src="…silk.svg" …>
          <span class="runner-number active">10</span></span></span>   × 2–4
      </div>

冇作者、冇時間戳。Selections **只有馬號**（名要由同頁 runner 表對返，
caller 傳 `names=` 入嚟；冇就係 None，唔會估）。

賽前／賽後判斷（claw_sportsbet_form 本身冇呢個 flag，所以喺度定義，偏保守）：
  1. 開跑時間：頁頂 `<span class="race">Race N <abbr data-utime=…>`（UTC epoch）。
  2. 頁面攞到嘅時間：cache 檔 mtime（live 抽取幾乎一定係讀瀏覽器餵落 cache
     嘅頁，所以「而家」唔係攞頁時間）。
  3. 賽果已出：任何一匹馬嘅往績出現「) DD/MM/YYYY Race N」而日期 = 今場日期
     —— 同一匹馬同一日唔會跑兩場，所以呢個等於「今場已經跑咗」。
  `pre_race = 開跑時間已知 and 攞頁時間 < 開跑時間 and not 賽果已出`。
  任何一樣判斷唔到 → 唔係 True → **唔寫**。寧願少存，都唔好令存檔混入賽後頁。
"""
from __future__ import annotations

import hashlib
import html as _html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

FILE_NAME = "AU_Sportsbet_Expert_Tips.jsonl"

RE_BLOCK = re.compile(r'<div\s+id="expert-tips"[^>]*>(?P<body>.*?)(?=<div\s+id="full-form"|\Z)',
                      re.S | re.I)
RE_FULL = re.compile(r'<div\s+class="full-comment"[^>]*>(?P<t>.*?)</div>', re.S | re.I)
RE_SHORT = re.compile(r'<p\s+class="expert-comment-container"[^>]*>(?P<t>.*?)</p>', re.S | re.I)
RE_SELECTION = re.compile(r'<div\s+class="selection"[^>]*>(?P<s>.*?)</div>', re.S | re.I)
RE_SEL_RUNNER = re.compile(
    r'<span\s+class="selection-runner"[^>]*>(?P<r>.*?)'
    r'<span\s+class="runner-number[^"]*"[^>]*>\s*(?P<num>[^<]*?)\s*</span>',
    re.S | re.I)
RE_SILK = re.compile(r'<img[^>]*\bsrc="(?P<src>[^"]+)"', re.I)
RE_JUMP = re.compile(r'<span\s+class="race">\s*Race\s+(?P<no>\d+)\s*<abbr\s+data-utime="(?P<ut>\d+)"'
                     r'(?P<attrs>[^>]*)>', re.I)
RE_TITLE = re.compile(r"<title>\s*(?P<venue>[A-Z][A-Za-z' \-]+?)\s+Race\s+(?P<no>\d+)\s*</title>")
RE_CANON = re.compile(r'<link\s+rel="canonical"\s+href="(?P<u>[^"]+)"', re.I)
RE_IDS = re.compile(r"/(?P<mid>\d+)/(?P<rid>\d+)/?$")

# 同一個 process 入面已寫過嘅 (race_key, content_hash)
_SEEN: set = set()


def _clean(fragment: str) -> str:
    txt = re.sub(r"<[^>]+>", " ", fragment or "")
    return re.sub(r"\s+", " ", _html.unescape(txt)).strip()


def extract(html: str | None, names: dict | None = None) -> dict | None:
    """→ {"tips_text", "tips_text_truncated", "selections": [{"number","name","silk"}]}。

    冇 `expert-tips` 區塊就 None。`names` = {馬號(int): 馬名}，由 caller 提供
    （同頁 runner 表）；冇提供或對唔到就 `name: None` —— 唔會砌。
    """
    if not html:
        return None
    m = RE_BLOCK.search(html)
    if not m:
        return None
    body = m.group("body")
    full = RE_FULL.search(body)
    short = RE_SHORT.search(body)
    tips = _clean(full.group("t")) if full else None
    truncated = False
    if not tips and short:
        # 只得截短版：剝走「Show more」連結，並標明係截短，唔好扮全文
        tips = _clean(re.sub(r"<a\b.*?</a>", "", short.group("t"), flags=re.S)) or None
        truncated = bool(tips)
    selections = []
    sel = RE_SELECTION.search(body)
    if sel:
        for r in RE_SEL_RUNNER.finditer(sel.group("s")):
            raw = _html.unescape(r.group("num")).strip()
            num = int(raw) if raw.isdigit() else None
            name = None
            if names and num is not None:
                nm = names.get(num, names.get(str(num)))
                name = _html.unescape(nm).strip() if nm else None
            silk = RE_SILK.search(r.group("r"))
            selections.append({"number": num, "name": name,
                               "silk": silk.group("src") if silk else None})
    if not tips and not selections:
        return None
    return {"tips_text": tips, "tips_text_truncated": truncated, "selections": selections}


def page_meta(html: str) -> dict:
    """由頁面本身攞：場地、場次、開跑時間（UTC）、本地日期、canonical URL。"""
    out = {"venue": None, "race_number": None, "jump_utc": None,
           "race_date": None, "url": None, "meeting_id": None, "race_id": None}
    t = RE_TITLE.search(html or "")
    if t:
        out["venue"] = t.group("venue").strip()
        out["race_number"] = int(t.group("no"))
    j = RE_JUMP.search(html or "")
    if j:
        ut = int(j.group("ut"))
        out["jump_utc"] = datetime.fromtimestamp(ut, timezone.utc).isoformat()
        if out["race_number"] is None:
            out["race_number"] = int(j.group("no"))
        tt = re.search(r'title="([^"]+)"', j.group("attrs"))
        if tt:  # 例：「Wednesday, 14 October 2026 at 5:45pm」= 場地本地日期
            try:
                out["race_date"] = datetime.strptime(
                    tt.group(1).split(" at ")[0].strip(), "%A, %d %B %Y").date().isoformat()
            except ValueError:
                pass
        if out["race_date"] is None:
            try:  # 舊版頁冇 title：用悉尼日期（AU 場次唔會跨日期）
                from zoneinfo import ZoneInfo
                out["race_date"] = datetime.fromtimestamp(
                    ut, ZoneInfo("Australia/Sydney")).date().isoformat()
            except Exception:  # noqa: BLE001
                pass
    c = RE_CANON.search(html or "")
    if c:
        out["url"] = c.group("u")
        ids = RE_IDS.search(out["url"])
        if ids:
            out["meeting_id"], out["race_id"] = ids.group("mid"), ids.group("rid")
    return out


def results_present(html: str, race_date: str | None) -> bool | None:
    """今場有冇出現喺任何一匹馬嘅往績（= 已經跑咗）。日期唔知 → None。"""
    if not race_date:
        return None
    try:
        dmy = datetime.strptime(race_date, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return None
    flat = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or ""))
    return bool(re.search(r"\)\s*" + re.escape(dmy) + r"\s+Race\s+\d+", flat))


def classify(html: str, fetched_at: datetime, race_date: str | None = None) -> dict:
    """→ {"pre_race": True/False/None, "jump_utc", "results_present", "race_date", ...}"""
    meta = page_meta(html)
    if race_date:  # caller（meeting index）個日期係權威
        meta["race_date"] = race_date
    res = results_present(html, meta["race_date"])
    pre = None
    if meta["jump_utc"] and res is not None:
        jump = datetime.fromisoformat(meta["jump_utc"])
        pre = bool(fetched_at < jump and not res)
    elif res:
        pre = False
    meta.update(results_present=res, pre_race=pre)
    return meta


def default_path() -> Path:
    # 同 `sb_people_stats.cache_path()` 同一個目錄（AU_RACING 資料根）。
    root = str(Path(__file__).resolve().parents[3])
    if root not in sys.path:
        sys.path.insert(0, root)
    from wongchoi_paths import AU_RACING
    return Path(AU_RACING) / FILE_NAME


def _content_hash(rec: dict) -> str:
    key = json.dumps([rec.get("tips_text"), [s.get("number") for s in rec.get("selections") or []]],
                     ensure_ascii=False)
    return hashlib.sha1(key.encode()).hexdigest()


def _race_key(rec: dict) -> tuple:
    return (rec.get("race_date"), rec.get("venue"), rec.get("race_number"))


def _last_hash_on_disk(path: Path, key: tuple) -> str | None:
    if not path.exists():
        return None
    last = None
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if _race_key(r) == key:
                last = r.get("content_hash")
    return last


def append_capture(record: dict, path=None) -> bool:
    """Append 一行（只加唔改）。回 True = 寫咗。

    唔寫嘅情況：`pre_race` 唔係 True（存檔只收乾淨 point-in-time 賽前頁）；
    同一場最新一行內容一樣（同一 run 或者之後重抽都一樣 —— 只記**變化**）。
    """
    if record.get("pre_race") is not True:
        return False
    path = Path(path) if path else default_path()
    rec = dict(record)
    rec.setdefault("recorded_at", datetime.now(timezone.utc).isoformat())
    rec["content_hash"] = _content_hash(rec)
    key = _race_key(rec)
    if (key, rec["content_hash"]) in _SEEN:
        return False
    if _last_hash_on_disk(path, key) == rec["content_hash"]:
        _SEEN.add((key, rec["content_hash"]))
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
    _SEEN.add((key, rec["content_hash"]))
    return True


def build_record(html: str, *, fetched_at: datetime, source_url: str | None = None,
                 race_date: str | None = None, venue: str | None = None,
                 race_number: int | None = None, names: dict | None = None,
                 backfilled: bool = False) -> dict | None:
    """extract + classify 砌成一行。冇 tips 區塊 → None。"""
    tips = extract(html, names=names)
    if tips is None:
        return None
    meta = classify(html, fetched_at, race_date=race_date)
    rec = {
        "captured_at": fetched_at.astimezone(timezone.utc).isoformat(),
        "race_date": meta["race_date"],
        # 去重鍵用頁面自己嘅場地名／場次，咁 live 同 backfill 先對得上
        # （caller 個場地名係資料夾標籤，可能同頁面唔同，另存 venue_label）。
        "venue": meta["venue"] or venue,
        "venue_label": venue,
        "race_number": meta["race_number"] if meta["race_number"] is not None else race_number,
        "source_url": source_url or meta["url"],
        "meeting_id": meta["meeting_id"],
        "race_id": meta["race_id"],
        "jump_utc": meta["jump_utc"],
        "results_present": meta["results_present"],
        "pre_race": meta["pre_race"],
        "backfilled_from_cache": backfilled,
        **tips,
    }
    return rec


def capture(html, *, cache_file=None, **kw) -> bool:
    """Live 抽取用：攞頁時間 = cache 檔 mtime（冇就用而家）。"""
    fetched = datetime.now(timezone.utc)
    if cache_file is not None and Path(cache_file).exists():
        fetched = datetime.fromtimestamp(Path(cache_file).stat().st_mtime, timezone.utc)
    rec = build_record(html, fetched_at=fetched, **kw)
    return bool(rec) and append_capture(rec)


def _names_from_page(html: str) -> dict | None:
    """馬號 → 馬名，由同頁 runner 表（`parse_race` overview）。失敗就 None。"""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from claw_sportsbet_form import parse_race
        ov = parse_race(html).get("overview") or {}
        return {int(k): v.get("name") for k, v in ov.items() if v.get("name")}
    except Exception:  # noqa: BLE001 — 冇名就留 None，唔好估
        return None


def backfill(cache_dir, path=None) -> dict:
    """由現有 cache 補：只收賽前頁，captured_at = 檔案 mtime。"""
    stats = {"pages_with_tips": 0, "pre_race": 0, "written": 0}
    for f in sorted(Path(cache_dir).glob("*.html")):
        html = f.read_text(encoding="utf-8", errors="replace")
        if 'id="expert-tips"' not in html:
            continue
        meta = page_meta(html)
        # canonical URL 嘅 sha1 要對得返 cache 檔名，先當佢係嗰場嘅賽事頁
        if not meta["url"] or hashlib.sha1(meta["url"].encode()).hexdigest() != f.stem:
            continue
        stats["pages_with_tips"] += 1
        rec = build_record(html, fetched_at=datetime.fromtimestamp(f.stat().st_mtime, timezone.utc),
                           names=_names_from_page(html), backfilled=True)
        if rec and rec["pre_race"]:
            stats["pre_race"] += 1
            stats["written"] += append_capture(rec, path=path)
    return stats


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="由 Sportsbet cache 補 Expert Tips 存檔")
    ap.add_argument("--backfill", required=True, help="cache 目錄")
    ap.add_argument("--out", help="JSONL（預設 AU_RACING 下）")
    a = ap.parse_args()
    print(backfill(a.backfill, a.out))
