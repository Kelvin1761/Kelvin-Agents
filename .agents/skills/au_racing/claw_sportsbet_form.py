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
RE_PRIZE = re.compile(r"\(of\s*\$([\d,]+)\)")
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
        # ⚠️ 表尾嗰格係**投注掣**（文字 "W"），唔係賠率 —— 賠率由 JS 填，
        # static HTML 攞唔到。之前照抄就寫咗 `Flucs:$- $W` 落 Formguide。
        # 真賠率要行 sportsbet.com.au 嘅 Markets API（winPrice / placePrice）。
        if not re.fullmatch(r"\$?\d+(?:\.\d+)?", str(rec.get("fixed_win", "")).strip()):
            rec["fixed_win"] = "-"
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
        pz = RE_PRIZE.search(seg)
        runs.append({**m.groupdict(),
                     "header": hdr,
                     "prize": pz.group(1) if pz else None,
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
    # ⚠️ 下游 `inject_fact_anchors.race_simple` 要
    #     `^場地 R\d+ YYYY-MM-DD \d+m cond:\S+ \$[0-9,]+`
    # Sportsbet 出 DD/MM/YYYY，而且賽事獎金唔喺同一行。兩者任何一樣唔啱，
    # 成條往績行會被靜靜丟棄（Facts 會報「數據不足」而唔會報錯）。
    d = h.get("date", "")
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", d)
    if m:
        d = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    prize = re.sub(r"[^\d]", "", run.get("prize") or "") or "0"
    parts = [f"{track} R{h.get('race','?')} {d} {dist or '?'}m cond:{cond} ${prize}"]
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


_STAT_KEYS = ("Prizemoney", "Ave $", "Win Range", "Win", "Place", "Career", "12 months",
              "Jockey", "Turf", "Synthetic", "1st Up", "2nd Up", "3rd Up", "Distance",
              "Track", "Trk/Dist", "Firm", "Good", "Soft", "Heavy")


def parse_runner_blocks(html):
    """逐匹馬嘅統計區塊。Sportsbet 用 label 行 + value 行交替，所以掃 label→下一個非空行。

    ⚠️ `Jockey` 呢個 key 喺呢度係**人馬配搭往績**（`5: 3-1-0` = 呢位騎師策騎過呢隻馬
    5 次、3 冠 1 亞），唔係騎師本人往績。佢正正係 `jockey_horse_fit_score` 缺嘅嘢。
    """
    txt = to_text(html)
    lines = [l for l in txt.splitlines()]
    ne = [(i, l) for i, l in enumerate(lines) if l.strip()]
    blocks, cur = [], None
    for k, (i, l) in enumerate(ne):
        # ⚠️ 馬名／檔位／`T` 係**各自一行**，唔係 "Name (barrier)" 一行；
        #    而且會有 HTML 註釋殘骸（`Silent Shares -->`）。實測靠一行 regex 會 0 命中。
        if (k + 2 < len(ne)
                and re.fullmatch(r"[A-Z][A-Za-z'’\-. ()]+", l) and not l.endswith("-->")
                and re.fullmatch(r"\(\d+\)", ne[k + 1][1])
                and ne[k + 2][1] == "T"):
            cur = {"name": l.strip(), "barrier": int(ne[k + 1][1].strip("()")),
                   "stats": {}, "_start": i}
            # 負磅：`W` 標籤之後嗰行（例 `61.5kg`）。Racecard 要佢，
            # 唔攞就會寫成 `Weight: ?`。
            for j in range(k + 3, min(k + 12, len(ne))):
                if ne[j][1] == "W" and j + 1 < len(ne) and re.fullmatch(r"[\d.]+kg", ne[j + 1][1]):
                    cur["stats"]["Weight"] = ne[j + 1][1]
                    break
            blocks.append(cur)
            continue
        if cur is not None and l in _STAT_KEYS and k + 1 < len(ne):
            cur["stats"].setdefault(l, ne[k + 1][1])
        if cur is not None:
            cur["_end"] = i
        if cur is not None and "_start" not in cur:
            cur["_start"] = i
    # 往績要歸返俾對應嗰匹馬：用區塊嘅行號範圍切原文，再喺切片入面 parse
    full = "\n".join(lines)
    offsets, pos = [], 0
    for l in lines:
        offsets.append(pos)
        pos += len(l) + 1
    for b in blocks:
        s = offsets[b.get("_start", 0)]
        e = offsets[min(b.get("_end", len(lines) - 1) + 1, len(lines) - 1)]
        b["runs"] = parse_race(full[s:e])["runs"] if e > s else []
    return blocks


def write_meeting(races, out_dir, date_str, venue, verbose=True):
    """寫 Racenet 格式嘅 meeting 檔。`races` = [(race_no, parsed, blocks)]。

    格式**唔可以自創** —— 下游 `inject_fact_anchors` 同引擎逐行 regex 食佢。
    對照 `claw_racenet_scraper.py` 147–252 行。
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    mm_dd = date_str[5:]
    idx = [f"# AU Wong Choi Formguide Index\n", f"Meeting: {venue} {date_str}\n"]
    for race_no, p, blocks in races:
        meta = p["meta"]
        cond = meta.get("track_condition", "Unknown")
        dist = meta.get("distance", "?")
        # ⚠️ 標題**一定要**係 `RACE N -- XXXm | class`（行首大寫 RACE）。
        # `inject_fact_anchors` 用 `^RACE\s+\d+\s*[—–-]\s*(\d{3,5})m` 抽路程，
        # 個 regex 只食**單個**破折號，所以 `RACE 4 -- 1410m`（兩個 hyphen）一樣唔得。
        hdr = f"RACE {race_no} — {dist}m"
        if meta.get("race_class"):
            hdr += f" | {meta['race_class']}"
        by_name = {b["name"].lower(): b for b in blocks}
        rc_path = out / f"{mm_dd} Race {race_no} Racecard.md"
        fg_path = out / f"{mm_dd} Race {race_no} Formguide.md"
        with open(rc_path, "w", encoding="utf-8") as f_rc, \
                open(fg_path, "w", encoding="utf-8") as f_fg:
            for f in (f_rc, f_fg):
                f.write(f"{hdr}\n")
                f.write(f"Track: {cond} | Weather: {meta.get('weather','Unknown')} "
                        f"| Rail: {meta.get('rail','')}\n{'='*60}\n")
            for num in sorted(p["overview"]):
                ov = p["overview"][num]
                name = ov.get("name", "?")
                blk = by_name.get(name.lower(), {})
                st = blk.get("stats", {})
                bar = blk.get("barrier", "?")
                if ov.get("scratched"):
                    f_rc.write(f"{num}. {name} - status:Scratched\n")
                    f_fg.write(f"{num}. {name} - status:Scratched\n\n")
                    continue
                f_rc.write(f"{num}. {name} ({bar})\n")
                f_rc.write(f"Trainer: {ov.get('trainer','')} | Jockey: {ov.get('jockey','')} "
                           f"| Weight: {st.get('Weight','?')} | Age: {ov.get('age_sex','')} "
                           f"| Rating: {ov.get('rating','')}\n")
                f_rc.write(f"Career: {ov.get('career','')} | Win: {ov.get('win_pct','')} "
                           f"| Place: {ov.get('place_pct','')}\n" + "-" * 40 + "\n")
                f_fg.write(f"[{num}] {name} ({bar})\n")
                f_fg.write(f"{ov.get('age_sex','')} | Sire: | Dam: \n")
                f_fg.write(f"Flucs:$- ${ov.get('fixed_win','-')}\n")
                f_fg.write(f"T: {ov.get('trainer','')} (LY: {st.get('_trainer_ly','-')}) "
                           f"| J: {ov.get('jockey','')} (LY: {st.get('_jockey_ly','-')})\n\n")
                f_fg.write(f"{'Career:':<10} {st.get('Career','-'):<15} "
                           f"{'Last 10:':<10} {ov.get('last6','-'):<15} "
                           f"{'Prize:':<10} {st.get('Prizemoney','-'):<15}\n")
                f_fg.write(f"{'Win %:':<10} {ov.get('win_pct','-'):<15} "
                           f"{'Place %:':<10} {ov.get('place_pct','-'):<15} "
                           f"{'ROI:':<10} {'-':<15}\n\n")
                f_fg.write(f"{'Track:':<10} {st.get('Track','-'):<15} "
                           f"{'Distance:':<10} {st.get('Distance','-'):<15} "
                           f"{'Trk/Dist:':<10} {st.get('Trk/Dist','-'):<15}\n")
                f_fg.write(f"{'Firm:':<10} {st.get('Firm','-'):<15} "
                           f"{'Good:':<10} {st.get('Good','-'):<15} "
                           f"{'Soft:':<10} {st.get('Soft','-'):<15}\n")
                f_fg.write(f"{'Heavy:':<10} {st.get('Heavy','-'):<15} "
                           f"{'Synth:':<10} {st.get('Synthetic','-'):<15} "
                           f"{'Class:':<10} {'-':<15}\n\n")
                f_fg.write(f"{'1st Up:':<10} {st.get('1st Up','-'):<15} "
                           f"{'2nd Up:':<10} {st.get('2nd Up','-'):<15} "
                           f"{'3rd Up:':<10} {st.get('3rd Up','-'):<15}\n")
                f_fg.write(f"{'Season:':<10} {'-':<15} "
                           f"{'12 Month:':<10} {st.get('12 months','-'):<15} "
                           f"{'Fav:':<10} {'-':<15}\n")
                # Sportsbet 獨有／之前冇寫出嚟嘅欄位。純新增行，唔會撞到既有 regex。
                # `Days` = 距上仗日數（久休訊號）；`Ave $` = 平均獎金（班次代理）；
                # `J/H` = 人馬配搭往績（`jockey_horse_fit_score` 缺咗嘅嘢）。
                f_fg.write(f"{'Days:':<10} {ov.get('days','-') or '-':<15} "
                           f"{'Ave $:':<10} {ov.get('ave_prize','-'):<15} "
                           f"{'J/H:':<10} {st.get('Jockey','-'):<15}\n")
                f_fg.write(f"{'WinRange:':<10} {st.get('Win Range','-'):<15} "
                           f"{'Turf:':<10} {st.get('Turf','-'):<15} "
                           f"{'12moRec:':<10} {st.get('12 months','-'):<15}\n\n")
                for run in blk.get("runs", []):
                    a, b = run_line(run)
                    f_fg.write(a + "\n" + b + "\n")
                    f_fg.write("Video: \nNote: \nStewards: \n\n")
                f_fg.write("=" * 60 + "\n\n")
        idx.append(f"- Race {race_no}: {dist}m — {rc_path.name} / {fg_path.name}\n")
        if verbose:
            print(f"   ✅ R{race_no}: {len(p['overview'])} 匹 → {fg_path.name}")
    (out / f"{mm_dd} Formguide_Index.md").write_text("".join(idx), encoding="utf-8")
    (out / "Meeting_Summary.md").write_text(
        f"# {venue} {date_str}\n\n{len(races)} races extracted from Sportsbet.\n",
        encoding="utf-8")


def discover_meetings(fetcher, country="Australia"):
    """由 sportsbet.com.au 賽馬 API 攞今日賽事。

    ⚠️ 唔可以行 sportsbetform 首頁 —— 佢對 curl_cffi 403（CloudFront 只擋 root）。
    """
    url = ("https://www.sportsbet.com.au/apigw/sportsbook-racing/Sportsbook/Racing/"
           "NextEvents?racingFilters=HR_DOMESTIC&groupByFilters=true")
    try:
        r = fetcher.session.get(url, timeout=30)
        data = r.json() if r.status_code == 200 else None
    except Exception:  # noqa: BLE001
        return []
    if not data:
        return []
    found = []

    def walk(o):
        if isinstance(o, dict):
            if o.get("id") and o.get("competitionName") and o.get("raceNumber"):
                found.append(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(data)
    return [e for e in found if not country or e.get("country") == country]


def main():
    ap = argparse.ArgumentParser(description="Sportsbet AU 賽馬表格抓取")
    ap.add_argument("--race-url", help="完整賽事頁 URL")
    ap.add_argument("--meeting", help="meetingId")
    ap.add_argument("--race", help="raceId")
    ap.add_argument("--probe", action="store_true", help="只做覆蓋率量度，唔寫檔")
    ap.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--dump-text", help="把純文字寫去呢個路徑（debug 用）")
    ap.add_argument("--meeting-url", help="馬場首頁 URL（/{meetingId}/{raceId}/ 任何一場都得）")
    ap.add_argument("--races", help="逗號分隔嘅 raceId 清單")
    ap.add_argument("--out-dir", help="寫 Racecard/Formguide 落邊")
    ap.add_argument("--date", help="YYYY-MM-DD")
    ap.add_argument("--venue", help="馬場名")
    args = ap.parse_args()

    # 成個馬場模式
    if args.meeting_url and args.races and args.out_dir:
        f = SportsbetFormFetcher(delay=args.delay, use_cache=not args.no_cache)
        mid = re.search(r"/(\d+)/", args.meeting_url)
        mid = mid.group(1) if mid else args.meeting
        out = []
        for i, rid in enumerate(args.races.split(","), 1):
            html = f.get(f"{BASE}/{mid}/{rid.strip()}/")
            if not html:
                print(f"   ⚠️ R{i} 攞唔到，跳過")
                continue
            pr = parse_race(html)
            out.append((pr["meta"].get("race_number", i), pr, parse_runner_blocks(html)))
        if not out:
            print("❌ 一場都攞唔到")
            return 1
        write_meeting(out, args.out_dir, args.date or "2026-01-01",
                      args.venue or (out[0][1]["meta"].get("venue") or "Unknown"))
        return 0

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
