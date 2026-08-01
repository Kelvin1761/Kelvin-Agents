#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""claw_sportsbet_form.py — AU 賽馬表格抓取（Sportsbet），Racenet 嘅替代品。

點解要換：Racenet 三條 transport 全部封死（profile 403、results 202 攔截頁、
Playwright 202）。Sportsbet 用返我哋一直用嗰套 `curl_cffi` chrome120 TLS 指紋
就攞到，而且**帶埋三樣 Racenet 從來冇畀過我哋嘅數據**：

    In running 800m/400m   逐場定位  ← 「settling position」，實測值 14–20pp 前三
    Sectionals 600m        逐場末段  ← pace_figure 而家 480/713 場零覆蓋
    每場往績嘅 1st/2nd/3rd  具名對手  ← 賽績線嘅 88.5% 缺口

架構（照 `nba_data_extractor/scripts/claw_sportsbet_odds.py` 嗰套）：
    curl_cffi Session(impersonate="chrome120") → 直接攞 server-rendered HTML

⚠️ 兩個已知陷阱，唔好踩：
  1. `sportsbetform.com.au/` **首頁 403**（CloudFront 只擋 root），但
     `/{meetingId}/{raceId}/` 賽事頁 200。所以 ID 發現唔可以靠首頁。
  2. **會 rate limit** —— 連續請求之後，一個啱啱通到嘅頁面會突然 403。
     預設每個請求隔 `--delay` 秒，而且抓到就落 cache，重跑唔會再打。

用法：
    # 單場抓取 + 覆蓋率量度（唔寫任何 meeting 檔）
    python3 claw_sportsbet_form.py --race-url https://www.sportsbetform.com.au/446213/3394476/ --probe
    python3 claw_sportsbet_form.py --meeting 446213 --race 3394476 --probe
"""
import argparse
import hashlib
import json
import re
import time
from pathlib import Path

try:
    from curl_cffi import requests
except ImportError:  # pragma: no cover - 環境問題，唔應該靜靜失敗
    print("❌ 缺少 curl_cffi 套件。請執行: pip install curl_cffi")
    sys.exit(1)

BASE = "https://www.sportsbetform.com.au"
DEFAULT_DELAY = 6.0
DEFAULT_RETRIES = 3
CACHE_DIR = Path(os.environ.get("WC_SB_CACHE", "")) if os.environ.get("WC_SB_CACHE") \
    else Path(__file__).resolve().parent / ".sportsbet_cache"


# ── 抓取 ────────────────────────────────────────────────────────────────────
class SportsbetFormFetcher:
    def __init__(self, delay=DEFAULT_DELAY, retries=DEFAULT_RETRIES, cache_dir=CACHE_DIR,
                 use_cache=True, verbose=True):
        self.session = requests.Session(impersonate="chrome120")
        self.delay = delay
        self.retries = retries
        self.cache_dir = Path(cache_dir)
        self.use_cache = use_cache
        self.verbose = verbose
        self._last_request = 0.0
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, url):
        return self.cache_dir / (hashlib.sha1(url.encode()).hexdigest() + ".html")

    def get(self, url):
        """回傳 HTML；失敗回 None（絕不 raise —— 一場攞唔到唔應該炸咗成個馬場）。"""
        cp = self._cache_path(url)
        if self.use_cache and cp.exists():
            if self.verbose:
                print(f"   （cache）{url}")
            return cp.read_text(encoding="utf-8")
        for attempt in range(1, self.retries + 1):
            wait = self.delay - (time.time() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            try:
                r = self.session.get(url, timeout=45)
            except Exception as exc:  # noqa: BLE001 — 網絡問題唔應該中斷抽取
                if self.verbose:
                    print(f"   ⚠️ {type(exc).__name__} ({attempt}/{self.retries}) {url}")
                self._last_request = time.time()
                continue
            self._last_request = time.time()
            if r.status_code == 200 and len(r.text) > 5000:
                cp.write_text(r.text, encoding="utf-8")
                if self.verbose:
                    print(f"   ✅ {len(r.text):,} bytes  {url}")
                return r.text
            if self.verbose:
                print(f"   ⚠️ HTTP {r.status_code} len={len(r.text)} "
                      f"({attempt}/{self.retries}) {url}")
            # 撞到 rate limit 就退避得更耐，唔好死𠝹爛𠝹
            self.delay = min(self.delay * 1.8, 60.0)
        return None

    def race(self, meeting_id, race_id):
        return self.get(f"{BASE}/{meeting_id}/{race_id}/")


# ── 解析 ────────────────────────────────────────────────────────────────────
def to_text(html):
    """HTML → 單行空白正規化嘅純文字。Sportsbet 係 server-rendered，唔使跑 JS。"""
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    t = re.sub(r"<br\s*/?>", "\n", t, flags=re.I)
    t = re.sub(r"</(tr|div|p|li|table)>", "\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = (t.replace("&nbsp;", " ").replace("&amp;", "&")
         .replace("&#39;", "'").replace("&quot;", '"'))
    return "\n".join(re.sub(r"[ \t]+", " ", l).strip() for l in t.splitlines())


RE_RUN = re.compile(
    r"Finished\s+(?P<pos>\d+)\s*/\s*(?P<field>\d+)"
    r"(?:\s+(?P<margin>[\d.]+)L)?"
    r".*?Jockey\s+(?P<jockey>[^,]+?),\s*Barrier\s+(?P<barrier>\d+),"
    r"\s*Weight\s+(?P<weight>[\d.]+)kg(?:\s+(?P<sp>[\d.]+))?", re.S)
RE_INRUN = re.compile(r"In running\s+800m\s+(?P<p800>\w+),\s*400m\s+(?P<p400>\w+)")
RE_SECT = re.compile(r"Sectionals\s+600m\s+(?P<l600>[\d.]+)s")
# ⚠️ 場地係寫成 "Flemington ( Soft ) 20/06/2026"（括號入面有空格），
# 唔容許空格就成條 header 都 match 唔到（實測覆蓋率會由 92% 跌到 0%）。
RE_HDR = re.compile(
    r"(?P<track>[A-Z][A-Za-z' \-]+?)\s*\(\s*(?P<going>[A-Za-z]+(?:\s*\d+)?)\s*\)\s*"
    r"(?P<date>\d{2}/\d{2}/\d{4})\s*Race\s*(?P<race>\d+)\s*(?P<dist>\d{3,4})m\s*(?P<cls>[^|]{0,40})")
RE_OPP = re.compile(r"(?P<ord>1st|2nd|3rd)\s+(?P<name>[A-Z][A-Za-z'\- ]+?)\s*"
                    r"\((?P<jockey>[^)]*?)\s(?P<wt>[\d.]+)kg\)(?:\s*(?P<mgn>[\d.]+)L)?")
RE_STAT = re.compile(r"(?P<k>1st Up|2nd Up|3rd Up|Distance|Track|Trk/Dist|Firm|Good|Soft|"
                     r"Heavy|Synthetic|Turf|Career|Jockey|12 months)\s+(?P<v>\d+:\s*[\d\-]+)")


def parse_overview(html):
    """總覽表：編號／名／練／騎／A-S／Days／Ave$／Career／Win%／Place%／Last6／Rating／賠率。

    ⚠️ 一定要行 HTML table 而唔係扁平文字 —— Sportsbet 逐格一行，而且會有
    HTML 屬性殘骸漏出嚟（實測見到 `14 : 5-0-4">`），純文字切法對唔齊欄。
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return {}
    soup = BeautifulSoup(html, "lxml")
    cols = ("name", "trainer", "jockey", "age_sex", "days", "ave_prize", "career",
            "win_pct", "place_pct", "last6", "rating", "fixed_win")
    out = {}
    for tr in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(("td", "th"))]
        if len(cells) < 8 or not re.fullmatch(r"\d{1,2}[a-z]?", cells[0]):
            continue
        num = int(re.sub(r"\D", "", cells[0]))
        if num in out:
            continue
        rec = dict(zip(cols, cells[1:]))
        rec["jockey"] = re.sub(r"\s*\([^)]*\)\s*$", "", rec.get("jockey", "")).strip()
        rec["scratched"] = "scr" in str(rec.get("fixed_win", "")).lower()
        out[num] = rec
    return out


def parse_race(html):
    """由賽事頁 HTML 抽出 meta + 逐匹馬 + 逐場往績。"""
    txt = to_text(html)
    flat = re.sub(r"\s+", " ", txt)
    meta = {}
    m = re.search(r"Track:\s*([A-Za-z]+\s*\d*)", flat)
    if m:
        meta["track_condition"] = m.group(1).strip()
    m = re.search(r"^\s*([A-Z][A-Za-z' \-]+?)\s+Race\s+(\d+)\s*-\s*(\d{2}:\d{2})", txt, re.M)
    if m:
        meta.update(venue=m.group(1).strip(), race_number=int(m.group(2)), start=m.group(3))
    m = re.search(r"(\d{3,4})m\s", flat)
    if m:
        meta["distance"] = int(m.group(1))

    overview = parse_overview(html)

    # 逐場往績：由 "Finished x/y" 錨定，向後掃同一段落
    runs = []
    for m in RE_RUN.finditer(flat):
        seg = flat[m.start(): m.start() + 900]
        hdr = None
        back = flat[max(0, m.start() - 260): m.start()]
        hm = None
        for hm in RE_HDR.finditer(back):
            pass                      # 取最接近 Finished 嗰個 header
        if hm:
            hdr = hm.groupdict()
        ir = RE_INRUN.search(seg)
        sc = RE_SECT.search(seg)
        opps = [o.groupdict() for o in RE_OPP.finditer(seg)][:3]
        runs.append({**m.groupdict(),
                     "header": hdr,
                     "p800": ir.group("p800") if ir else None,
                     "p400": ir.group("p400") if ir else None,
                     "l600": sc.group("l600") if sc else None,
                     "opponents": opps})
    return {"meta": meta, "overview": overview, "runs": runs, "text": txt}


# ── 覆蓋率量度 ──────────────────────────────────────────────────────────────
def coverage(parsed):
    runs = parsed["runs"]
    n = len(runs)
    if not n:
        return {"runs": 0}
    def pct(k):
        return 100.0 * sum(1 for r in runs if r.get(k)) / n
    return {
        "runners": len(parsed["overview"]),
        "runs": n,
        "in_running_pct": pct("p800"),
        "sectional_600_pct": pct("l600"),
        "opponent_lines_pct": 100.0 * sum(1 for r in runs if len(r["opponents"]) >= 1) / n,
        "opponent_full_top3_pct": 100.0 * sum(1 for r in runs if len(r["opponents"]) >= 3) / n,
        "header_pct": pct("header"),
        "sp_pct": pct("sp"),
        "margin_pct": pct("margin"),
    }


def probe(parsed, label=""):
    c = coverage(parsed)
    m = parsed["meta"]
    print(f"\n{'='*72}\n{label or m.get('venue','?')} R{m.get('race_number','?')}"
          f"  {m.get('distance','?')}m  場地 {m.get('track_condition','?')}\n{'='*72}")
    if not c.get("runs"):
        print("  ❌ 解析唔到任何往績"); return c
    print(f"  出賽馬 {c['runners']}   往績場數 {c['runs']}")
    rows = [("In running 800m/400m（定位）", c["in_running_pct"], "settling position"),
            ("Sectionals 600m（末段）", c["sectional_600_pct"], "pace_figure"),
            ("對手線 至少一個", c["opponent_lines_pct"], "賽績線"),
            ("對手線 完整前三", c["opponent_full_top3_pct"], "賽績線"),
            ("賽事 header（場地/班次/路程）", c["header_pct"], ""),
            ("SP 賠率", c["sp_pct"], ""), ("輸距", c["margin_pct"], "")]
    for name, v, use in rows:
        bar = "█" * int(v / 4)
        print(f"    {name:30}{v:>6.1f}%  {bar}{('  ← ' + use) if use else ''}")
    ex = next((r for r in parsed["runs"] if r.get("p800") and r.get("l600")), None)
    if ex:
        h = ex["header"] or {}
        print(f"\n  樣本：{h.get('track','?')} ({h.get('going','?')}) {h.get('date','?')} "
              f"{h.get('dist','?')}m {h.get('cls','')[:24]}")
        print(f"        名次 {ex['pos']}/{ex['field']}  輸距 {ex.get('margin')}L  "
              f"檔 {ex['barrier']}  負磅 {ex['weight']}kg  SP {ex.get('sp')}")
        print(f"        定位 800m {ex['p800']} → 400m {ex['p400']}   末段 600m {ex['l600']}s")
        for o in ex["opponents"]:
            print(f"        {o['ord']} {o['name']} ({o['jockey']} {o['wt']}kg)"
                  + (f" {o['mgn']}L" if o.get("mgn") else ""))
    return c


# ── 寫成 Racenet 格式（drop-in）─────────────────────────────────────────────
# 下游（inject_fact_anchors → Facts.md → engine）食嘅係 Racenet crawler 嗰套文字
# 格式，所以呢度要逐個欄位對返齊，唔可以自創格式。已核實嘅解析點：
#   ` starters:N`                 → 馬群大細（form_score 百分位化靠佢）
#   ` PF[Last600: X ...]`         → 段速實速（X 係**同基準嘅差值**，唔係原始秒數）
#   `Nth@800m Nth@400m`           → 定位（settling position）
#   `(LY: 288:53-39-35)`          → 騎練去年 starts:1st-2nd-3rd
_POS_ORD = {"1st": 1, "2nd": 2, "3rd": 3}


def _ord_to_int(text):
    if not text:
        return None
    if text in _POS_ORD:
        return _POS_ORD[text]
    m = re.match(r"(\d+)", str(text))
    return int(m.group(1)) if m else None


def _l600_delta(raw_seconds, track, distance_m):
    """Sportsbet 畀原始 600m 秒數，但下游要嘅係**同場地標準嘅差值**。

    用引擎自己嗰張標準表換算，咁 live 同重跑 archive 先係同一把尺。
    攞唔到標準就回 None —— 寧可唔寫，唔好寫個假 delta 落去。
    """
    if raw_seconds is None or not track or not distance_m:
        return None
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent
                               / "au_wong_choi_auto" / "scripts" / "racing_engine"))
        from engine_core import _lookup_standard_l600
    except Exception:  # noqa: BLE001 — 抽取唔應該因為 import 死
        return None
    std = _lookup_standard_l600(track, int(distance_m))
    if not std:
        return None
    return round(float(raw_seconds) - float(std), 3)


def run_line(run):
    """砌一條 Racenet 格式嘅往績行。"""
    h = run.get("header") or {}
    track = (h.get("track") or "").strip()
    dist = h.get("dist")
    cond = (h.get("going") or "").strip()
    parts = [f"{track} R{h.get('race','?')} {h.get('date','')} {dist or '?'}m cond:{cond}"]
    parts.append(f"{(run.get('jockey') or '').strip()} ({run.get('barrier','?')})"
                 f" {run.get('weight','?')}kg")
    if run.get("sp"):
        parts.append(f"Flucs:$- ${run['sp']}")
    pos = []
    if run.get("p800"):
        pos.append(f"{run['p800']}@800m")
    if run.get("p400"):
        pos.append(f"{run['p400']}@400m")
    tail = " ".join(pos) + "."
    if run.get("margin"):
        tail += f" margin:{run['margin']}L"
    if run.get("field"):
        tail += f" starters:{run['field']}"
    delta = _l600_delta(run.get("l600"), track, dist)
    if delta is not None:
        tail += f" PF[Last600: {delta}]"
    line = " ".join(parts) + " " + tail
    opp = run.get("opponents") or []
    def fmt(o, i):
        if i >= len(opp):
            return f"{i+1}-"
        x = opp[i]
        s = f"{i+1}-{x['name']} ({x['wt']}kg)"
        return s + (f" {x['mgn']}L" if x.get("mgn") else "")
    return line, ", ".join(fmt(opp, i) for i in range(3))


def main():
    ap = argparse.ArgumentParser(description="Sportsbet AU 賽馬表格抓取")
    ap.add_argument("--race-url", help="完整賽事頁 URL")
    ap.add_argument("--meeting", help="meetingId")
    ap.add_argument("--race", help="raceId")
    ap.add_argument("--probe", action="store_true", help="只做覆蓋率量度，唔寫檔")
    ap.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--dump-text", help="把純文字寫去呢個路徑（debug 用）")
    args = ap.parse_args()

    if args.race_url:
        url = args.race_url
    elif args.meeting and args.race:
        url = f"{BASE}/{args.meeting}/{args.race}/"
    else:
        ap.error("要 --race-url 或者 --meeting + --race")

    f = SportsbetFormFetcher(delay=args.delay, use_cache=not args.no_cache)
    html = f.get(url)
    if not html:
        print("❌ 攞唔到頁面（可能撞咗 rate limit，隔陣再試）")
        return 1
    parsed = parse_race(html)
    if args.dump_text:
        Path(args.dump_text).write_text(parsed["text"], encoding="utf-8")
    probe(parsed, label=url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
