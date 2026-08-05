#!/usr/bin/env python3
"""Racing Australia FreeFields —— 官方賽事資料，補 Sportsbet 攞唔到嘅欄位。

**點解要呢個來源。** Sportsbet 冇官方讓磅分：1,321 匹實測 overview 個 `rating`
欄 **0% 有值**，render 後 DOM、`?view=Head`、`?view=Predictor` 都冇。於是
`rating_score` 100% 走 fallback（級數分＋場內負磅代理各半），而
`class_weight` 維度佔 7.17% 權重。Racing Australia 嘅 Acceptances 頁有
**`Hcp Rating`** 欄，實測 2026-08-05 Canterbury 87 匹有 **86.2%**。

⚠️ 86.2% 唔係抽取失敗，係**原則上限** —— 處女／未評分馬根本冇官方讓磅分。
所以 fallback 仍然要留返畀嗰批（fallback 本來就係為處女賽設計，實測 AUC 0.6078）。

**同 Sportsbet 完全唔同嘅抽取條件**（呢個係好消息）：
    Sportsbet   curl_cffi 403、headless 403 → 只可以 headed 真 Chrome，25 秒一版
    RA          curl_cffi **200** → 直接出網，唔使瀏覽器
所以兩條線互不干擾：RA 唔會食 Sportsbet 嘅 rate budget，反之亦然。

其他免費送嘅欄位（Sportsbet 全部冇或者要另外抽）：
    `Penalty`（罰磅）· `Probable Weight` · `Barrier` · `Last 10` · `Weight`
再加獨立 `Scratchings.aspx` —— 早更本來要逐場重抓 Sportsbet 賽事頁去 diff
退出馬（一個場次 8–9 版 × 25 秒），一版官方 scratchings 就搞定。

URL 格式：`?Key=<2026Aug05>,<STATE>,<RA 馬場名>`
⚠️ RA 嘅馬場名同 Sportsbet 唔一樣（`Canterbury Park` vs `Canterbury`），所以一定要
由州曆（`Calendar.aspx?State=…`）發現，唔可以砌名。
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote, unquote

sys.path.insert(0, str(Path(__file__).resolve().parent))

BASE = "https://racingaustralia.horse"
STATES = ("NSW", "VIC", "QLD", "WA", "SA", "TAS", "ACT", "NT")
CACHE_DIR = Path(os.environ.get("WC_RA_CACHE", "")) if os.environ.get("WC_RA_CACHE") \
    else Path(__file__).resolve().parent / ".ra_cache"
DEFAULT_DELAY = 6.0        # RA 冇封過我哋，但照守保守節奏
MIN_BYTES = 5000

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def ra_date(day: str) -> str:
    """`2026-08-05` → `2026Aug05`（RA 個 Key 用呢個格式）。"""
    y, m, d = day.split("-")
    return f"{y}{_MONTHS[int(m) - 1]}{d}"


class Fetcher:
    """curl_cffi + 檔案 cache。同 Sportsbet 個 cache **分開**（唔同 host、唔同節奏）。"""

    def __init__(self, delay: float = DEFAULT_DELAY, use_cache: bool = True,
                 verbose: bool = True):
        from curl_cffi import requests
        self.session = requests.Session(impersonate="chrome120")
        self.delay = max(float(delay), 2.0)
        self.use_cache = use_cache
        self.verbose = verbose
        self._last = 0.0
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _path(self, url: str) -> Path:
        return CACHE_DIR / (hashlib.sha1(url.encode()).hexdigest() + ".html")

    def get(self, url: str, force: bool = False) -> str | None:
        cp = self._path(url)
        if self.use_cache and not force and cp.exists():
            if self.verbose:
                print(f"   （cache）{url}")
            return cp.read_text(encoding="utf-8")
        wait = self.delay - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        try:
            r = self.session.get(url, timeout=45)
        except Exception as exc:  # noqa: BLE001
            print(f"   ⚠️ {type(exc).__name__} {url}")
            return None
        finally:
            self._last = time.time()
        if r.status_code != 200 or len(r.text) < MIN_BYTES:
            # 同 Sportsbet 一樣嘅紀律：撞到非 200 唔重試。
            print(f"   ⛔ HTTP {r.status_code} len={len(r.text)} {url}")
            return None
        cp.write_text(r.text, encoding="utf-8")
        if self.verbose:
            print(f"   ✅ {len(r.text):,} bytes  {url}")
        return r.text


def _tables(html: str):
    from bs4 import BeautifulSoup
    return BeautifulSoup(html, "lxml")


def meetings_for(day: str, fetcher: Fetcher | None = None,
                 states=STATES) -> list[dict]:
    """→ [{date, state, venue, key, urls…}]，由州曆發現（唔砌馬場名）。"""
    f = fetcher or Fetcher()
    stamp = ra_date(day)
    found: dict[str, dict] = {}
    for state in states:
        html = f.get(f"{BASE}/FreeFields/Calendar.aspx?State={state}")
        if not html:
            continue
        # ⚠️ 引號兩種都要food：NSW 個曆用 `href="…"`，VIC 用 `href='…'`。
        # 只認雙引號嘅話 VIC/QLD 等等會靜靜咁一個場次都搵唔到（實測只搵到 NSW）。
        for raw in re.findall(
                r"""href=["'](/FreeFields/\w+\.aspx\?Key=[^"']+)["']""", html):
            key = unquote(raw.split("Key=", 1)[1]).strip()
            if not key.startswith(stamp):
                continue
            parts = [p.strip() for p in key.split(",")]
            if len(parts) < 3 or "Trial" in parts:
                continue          # 試閘唔要
            venue = parts[2]
            found.setdefault(key, {"date": day, "state": parts[1], "venue": venue,
                                   "key": key})
    return sorted(found.values(), key=lambda m: (m["state"], m["venue"]))


def matches_venue(ra_venue: str, other: str) -> bool:
    """RA 馬場名同 Sportsbet／我哋 folder 個名對唔對得上。

    ⚠️ RA 帶**贊助商前綴**：`Southside Cranbourne`、`Canterbury Park`、
    `bet365 Traralgon`。所以一定要子字串比對，唔可以要求相等 —— 實測
    要求相等會令 5 個場次之中 4 個配唔到。
    """
    def norm(s):
        return "".join(ch for ch in str(s).lower() if ch.isalnum())
    a, b = norm(ra_venue), norm(other)
    if not a or not b:
        return False
    return a == b or a.endswith(b) or b in a or a in b


def _page_url(page: str, key: str) -> str:
    return f"{BASE}/FreeFields/{page}.aspx?Key={quote(key)}"


def acceptances(key: str, fetcher: Fetcher | None = None,
                force: bool = False) -> dict:
    """→ {race_no: {"name":…, "runners":[{no, horse, trainer, jockey, barrier,
    weight, probable_weight, penalty, hcp_rating, last10}]}}"""
    f = fetcher or Fetcher()
    html = f.get(_page_url("Acceptances", key), force=force)
    if not html:
        return {}
    soup = _tables(html)
    out: dict[int, dict] = {}
    race_no = 0
    race_name = ""
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        header = None
        for tr in rows:
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
            if not cells:
                continue
            joined = " ".join(cells)
            m = re.match(r"Race\s+(\d+)\s*-\s*[\d:APM ]*(.*)", joined)
            if m and "Hcp Rating" not in joined:
                race_no = int(m.group(1))
                race_name = re.sub(r"\s+", " ", m.group(2)).strip()
                out.setdefault(race_no, {"name": race_name, "runners": []})
                continue
            if "Hcp Rating" in joined:
                header = cells
                continue
            if header is None or race_no == 0:
                continue
            if len(cells) < len(header) - 3:
                continue
            rec = dict(zip(header, cells))

            def val(*names):
                for n in names:
                    v = str(rec.get(n) or "").strip()
                    if v and v != "-":
                        return v
                return ""

            horse = val("Horse")
            if not horse:
                continue
            rating = val("Hcp Rating")
            out[race_no]["runners"].append({
                "no": val("No"),
                "horse": re.sub(r"\s*\((?:NZ|GB|IRE|USA|JPN|FR|GER|SAF|ARG|BRZ)\)\s*$",
                                "", horse).strip(),
                "trainer": val("Trainer"),
                "jockey": re.sub(r"\s*\([^)]*\)\s*$", "", val("Jockey")).strip(),
                "barrier": val("Barrier"),
                "weight": val("Weight"),
                "probable_weight": val("Probable Weight"),
                "penalty": val("Penalty"),
                "hcp_rating": float(rating) if re.fullmatch(r"\d+(?:\.\d+)?", rating) else None,
                "last10": val("Last 10"),
            })
    return {k: v for k, v in out.items() if v["runners"]}


def scratchings(key: str, fetcher: Fetcher | None = None,
                force: bool = True) -> dict:
    """→ {race_no: [馬名, …]}。⚠️ 預設 `force=True` —— 退出馬會變到開跑前一刻。"""
    f = fetcher or Fetcher()
    html = f.get(_page_url("Scratchings", key), force=force)
    if not html:
        return {}
    soup = _tables(html)
    out: dict[int, list] = {}
    race_no = 0
    for tr in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
        if not cells:
            continue
        joined = " ".join(cells)
        m = re.search(r"Race\s+(\d+)\b", joined)
        if m and len(cells) <= 3:
            race_no = int(m.group(1))
            continue
        if race_no and len(cells) >= 2:
            # 一格通常係「6 BLENHEIM GIRL (5/8 0728)」—— 拆出號碼同名，
            # 時間戳唔要（下游只需要「邊隻退出」）。
            raw = cells[1] if len(cells) > 1 else cells[0]
            m2 = re.match(r"\s*(?P<no>\d+)(?P<em>e?)\s+(?P<horse>.+)", raw)
            no = m2.group("no") if m2 else ""
            horse = (m2.group("horse") if m2 else raw)
            horse = re.sub(r"\s*\([^)]*\)\s*$", "", horse).strip()
            horse = re.sub(r"\s*\((?:NZ|GB|IRE|USA|JPN|FR|GER|SAF|ARG|BRZ)\)\s*$",
                           "", horse).strip()
            if horse and horse.lower() not in ("horse", "scratched"):
                out.setdefault(race_no, []).append({"no": no, "horse": horse})
    return out



# ── 接線入 pipeline ────────────────────────────────────────────────────────
def apply_to_meeting(folder: Path, day: str, ra_venue_hint: str,
                     fetcher: "Fetcher | None" = None, dry_run: bool = False) -> dict:
    """把 RA 官方讓磅分寫入 meeting folder 嘅 Racecard `Rating:` 欄。

    ⚠️ 點解改 Racecard 而唔係改 Logic：`build_au_logic.py` 個 `RACECARD_META_RE`
    就係由 Racecard 嗰行 `… | Rating: <N>` 抽 `horse_rating`，而 `_horse_rating()`
    再由 Logic 讀。所以喺 Racecard 補返個數字，成條下游（Facts → Logic → 評分）
    自動接上，唔使改任何 parser。

    Sportsbet 寫落去嘅係 `Rating: -`（overview 個欄實測 1,321 匹 0% 有值），
    所以呢一步係**淨加**：只填 `-`，唔會覆蓋已經有值嘅。

    馬名配對：RA 出大寫並帶產地後綴（`NAMASTE (NZ)`），Racecard 出 title-case。
    兩邊都正規化成「只留字母數字、細寫」先比。
    """
    f = fetcher or Fetcher()
    meets = meetings_for(day, f)
    match = next((m for m in meets if matches_venue(m["venue"], ra_venue_hint)), None)
    if not match:
        return {"ok": False, "reason": f"RA 冇 {day} {ra_venue_hint}",
                "candidates": [m["venue"] for m in meets]}
    races = acceptances(match["key"], f)
    if not races:
        return {"ok": False, "reason": "Acceptances 頁 parse 唔到"}

    def norm(s):
        return "".join(ch for ch in str(s).lower() if ch.isalnum())

    rating_by_horse = {}
    for info in races.values():
        for r in info["runners"]:
            if r["hcp_rating"] is not None:
                rating_by_horse[norm(r["horse"])] = r["hcp_rating"]

    filled = blank = already = 0
    touched = []
    for card in sorted(folder.glob("* Racecard.md")):
        lines = card.read_text(encoding="utf-8").splitlines()
        changed = False
        for i, line in enumerate(lines):
            if "| Rating:" not in line:
                continue
            # 上一行係「N. HORSE NAME (檔位)」
            head = lines[i - 1] if i else ""
            hm = re.match(r"\s*\d+\.\s*(?P<horse>[^(]+)", head)
            if not hm:
                continue
            cur = line.rsplit("Rating:", 1)[1].strip()
            if cur and cur not in ("-", "None"):
                already += 1
                continue
            got = rating_by_horse.get(norm(hm.group("horse")))
            if got is None:
                blank += 1
                continue
            lines[i] = line.rsplit("Rating:", 1)[0] + f"Rating: {got:g}"
            filled += 1
            changed = True
        if changed and not dry_run:
            card.write_text("\n".join(lines) + "\n", encoding="utf-8")
            touched.append(card.name)
    return {"ok": True, "ra_venue": match["venue"], "ra_key": match["key"],
            "filled": filled, "no_official_rating": blank, "already_had": already,
            "racecards_touched": len(touched)}


def main() -> int:
    ap = argparse.ArgumentParser(description="Racing Australia FreeFields")
    ap.add_argument("day", help="YYYY-MM-DD")
    ap.add_argument("--venue", help="只做名入面含呢個字嘅場次")
    ap.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    ap.add_argument("--scratchings", action="store_true")
    args = ap.parse_args()

    f = Fetcher(delay=args.delay)
    meets = meetings_for(args.day, f)
    if args.venue:
        meets = [m for m in meets if args.venue.lower() in m["venue"].lower()]
    print(f"\n{args.day}：{len(meets)} 個場次")
    for m in meets:
        races = acceptances(m["key"], f)
        runners = [r for v in races.values() for r in v["runners"]]
        rated = [r for r in runners if r["hcp_rating"] is not None]
        extra = {k: sum(1 for r in runners if r[k]) for k in
                 ("penalty", "probable_weight", "barrier", "last10")}
        print(f"   {m['state']:4} {m['venue']:22} {len(races)} 場 {len(runners):>3} 匹  "
              f"讓磅分 {len(rated)}/{len(runners)} "
              f"({100 * len(rated) / len(runners) if runners else 0:.0f}%)  {extra}")
        if args.scratchings:
            scr = scratchings(m["key"], f)
            print(f"        退出馬：{ {k: v for k, v in sorted(scr.items())} }")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
