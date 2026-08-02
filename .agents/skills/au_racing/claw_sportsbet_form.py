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


# ⚠️ 檔位同負磅**兩樣都可以冇**。試閘寫成
#     `Finished 2/8 (of 0), Jockey Thomas Stockdale, Weight kg`
# —— 完全冇 `Barrier N,`，而 `Weight kg` 中間冇數字。舊 regex 兩樣都要求，
# 所以呢類**一段都 match 唔到**：Flemington R5 頁面有 160 段 `Finished x/y`，
# 只 parse 到 109 段，**漏咗 51 段（32%）**，而且全部係試閘。
# 呢個就係 `trial_score` 追唔到現有數據源嘅主因。
# 冇檔位／負磅嘅時候留 None —— 現有源都係寫 `(None) Nonekg`，格式對得上。
RE_RUN = re.compile(
    r"Finished\s+(?P<pos>\d+)\s*/\s*(?P<field>\d+)"
    r"(?:\s+(?P<margin>[\d.]+)L)?"
    r".*?Jockey\s+(?P<jockey>[^,]+?)"
    r"(?:,\s*Barrier\s+(?P<barrier>\d+))?"
    # ⚠️ SP 後面唔可以跟字母。負磅冇數字嘅時候，下一個 token 係 `1st Kyle …`，
    # 而 `[\d.]+` 會食咗個 "1" 當 SP —— 試閘變咗 `Flucs:$- $1`。
    r",\s*Weight\s*(?P<weight>[\d.]+)?kg(?:\s+(?P<sp>\d+(?:\.\d+)?)(?![\w.]))?", re.S)
# ⚠️ 試閘寫 `(of 0)` —— **冇 `$` 號**。舊 regex 要求 `$`，所以試閘 match 唔到，
# 跟住喺較闊嘅視窗度撈到隔籬**正式賽**嘅獎金：試閘顯示 $175,000，班次判斷即刻錯。
RE_PRIZE = re.compile(r"\(of\s*\$?([\d,]+)\)")
# ⚠️ Sportsbet 出兩種寫法，`Settled` 嗰截係**可有可無**：
#     In running Settled 11th, 800m 11th, 400m 11th   ← 33.8%
#     In running 800m 5th, 400m 3rd                   ← 22.6%
# 舊 regex 硬食 `In running 800m`，所以第一種**一條都 match 唔到** ——
# 走位覆蓋率由應有嘅 56.4% 跌到 22.6%，而且 `Settled` 成個掉咗。
# 掉咗 Settled 嘅代價唔止走位：`inject_fact_anchors` 嘅 PI = Settled − Finish，
# 冇 Settled 就冇 PI，`_sectional_breakdown().has_pi` 永遠 False，
# 段速分全場中性 60（實測 evidence 0% vs 現有數據源 45%）。
RE_INRUN = re.compile(r"In running\s+(?:Settled\s+(?P<settled>\w+),\s*)?"
                      r"800m\s+(?P<p800>\w+),\s*400m\s+(?P<p400>\w+)")
RE_SECT = re.compile(r"Sectionals\s+600m\s+(?P<l600>[\d.]+)s")
# ⚠️ 場地係寫成 "Flemington ( Soft ) 20/06/2026"（括號入面有空格），
# 唔容許空格就成條 header 都 match 唔到（實測覆蓋率會由 92% 跌到 0%）。
# ⚠️ 場地可以係**空**：試閘寫成 `Southside Cranbourne ( ) 13/04/2026 Race 2 800m
# Jump Out - H8 Barrier Trial` —— 括號入面乜都冇。舊 regex 要求最少一個字母，
# 所以**成類試閘都 match 唔到 header**，跟住喺 `run_line` 靜靜咁被丟。
# 實測：Flemington R5 109 段往績有 26 段（24%）冇 header，`trial_score` 只得 7%
# 有證據，而現有數據源有 54%。呢個係同 `Settled`、`L600 Delta` 一模一樣嘅
# 失敗模式 —— **regex 收得太緊，靜靜咁掉走一整類數據**，第三次。
RE_HDR = re.compile(
    r"(?P<track>[A-Z][A-Za-z' \-]+?)\s*\(\s*(?P<going>[A-Za-z]*(?:\s*\d+)?)\s*\)\s*"
    r"(?P<date>\d{2}/\d{2}/\d{4})\s*Race\s*(?P<race>\d+)\s*(?P<dist>\d{3,4})m\s*(?P<cls>[^|]{0,40})")
# 下游用 `**(TRIAL)**` 認試閘（`inject_fact_anchors.TRIAL_MARKER`），
# 認到就唔會計入 PI／近績趨勢，但仍然入到試閘分。
TRIAL_MARKER = "**(TRIAL)**"
RE_TRIAL = re.compile(r"Barrier\s*Trial|Jump\s*Out", re.I)
# ⚠️ 試閘唔публ負磅，寫 `1st Rivkin (Mollie Fitzgerald n/a)`。舊 regex 硬要
# `NN.Nkg`，所以**試閘嘅頭三名全部攞唔到** —— 而嗰個正正係試閘最有價值嘅嘢。
RE_OPP = re.compile(r"(?P<ord>1st|2nd|3rd)\s+(?P<name>[A-Z][A-Za-z'\- ]+?)\s*"
                    r"\((?P<jockey>[^)]*?)\s(?:(?P<wt>[\d.]+)kg|n/a)\)"
                    r"(?:\s*(?P<mgn>[\d.]+)L)?")
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


RE_PERSON = re.compile(r'href="/(Jockey|Trainer)/(\d+)/"[^>]*>([^<]{2,60})<')


def parse_people(html):
    """賽事頁 → {(kind, 正規化名): person_id}。

    連結文字係**截短**咗嘅（`Ben, Will & Jd ...`、`Daniel Stackhou...`），
    仲會帶埋後綴（`Emily Pozman  (a-3)`）。所以配對要用**前綴**，唔可以要求
    全等 —— 總覽表出全名，連結出短名。
    """
    out = {}
    for kind, pid, raw in RE_PERSON.findall(html):
        name = re.sub(r"\s*\([^)]*\)\s*$", "", raw).strip().rstrip(".").strip()
        if name:
            out.setdefault((kind, _people_key(name)), pid)
    return out


def _people_key(name):
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _match_person(people, kind, name, min_len=6):
    """總覽表嘅全名 → person_id。連結文字截短過，所以做前綴比對。"""
    key = _people_key(name)
    if not key:
        return None
    hit = people.get((kind, key))
    if hit:
        return hit
    # ⚠️ 前綴比對**兩邊**都要夠長。只限制候選長度嘅話，一個 "C" 之類嘅殘缺名
    # 會前綴配中 "ciaronmaher" —— 配錯人比冇數據更差，因為佢會靜靜咁畀
    # 另一個練馬師嘅往績當咗自己嘅。
    if len(key) < min_len:
        return None
    matches = {pid for (k, cand), pid in people.items()
               if k == kind and len(cand) >= min_len
               and (key.startswith(cand) or cand.startswith(key))}
    # 撞正多過一個就唔猜 —— 寧可冇數據
    return matches.pop() if len(matches) == 1 else None


def parse_race(html):
    """由賽事頁 HTML 抽出 meta + 逐匹馬 + 逐場往績。"""
    txt = to_text(html)
    flat = re.sub(r"\s+", " ", txt)
    meta = {}
    m = re.search(r"Track:\s*([A-Za-z]+\s*\d*)", flat)
    if m:
        meta["track_condition"] = m.group(1).strip()
    # ⚠️ 場地同場次一定要由頁面攞 —— **唔可以**靠呼叫者嘅 raceId 次序推。
    # raceId 唔跟場次遞增（實測 2026-08-01 Flemington：3393737=R7、3393739=R9、
    # 3394294=R6、3394295=R8），所以「照 raceId 排序當場次」會將 R6–R9 錯配。
    # 之前呢度個 regex 要求 `Race 7 - 14:30` 嘅開跑時間，但賽後頁面得
    # `Flemington Race 7`，所以成個 meta（venue / race_number）長期係 None，
    # 靜靜跌返落 enumerate 次序。開跑時間變成可有可無。
    m = re.search(r"<title>\s*([A-Z][A-Za-z' \-]+?)\s+Race\s+(\d+)\s*</title>", html) \
        or re.search(r"^\s*([A-Z][A-Za-z' \-]+?)\s+Race\s+(\d+)\s*$", txt, re.M)
    if m:
        meta.update(venue=m.group(1).strip(), race_number=int(m.group(2)))
    m = re.search(r"Race\s+\d+\s*-\s*(\d{2}:\d{2})", txt)
    if m:
        meta["start"] = m.group(1)
    m = re.search(r"(\d{3,4})m\s", flat)
    if m:
        meta["distance"] = int(m.group(1))

    overview = parse_overview(html)
    # 名 → ID 對應，寫 meeting 檔嗰陣攞騎練統計用
    meta["people_by_name"] = parse_people(html)
    # 騎練 profile ID 直接喺賽事頁 —— 冇 slug 要猜（Racenet 就係死喺呢度兩次）。
    people = [(k, pid) for k, pid in
              re.findall(r'href="/(Jockey|Trainer)/(\d+)/"', html)]
    seen_p, meta["people"] = set(), []
    for k, pid in people:
        if (k, pid) in seen_p:
            continue
        seen_p.add((k, pid))
        meta["people"].append((k, pid))

    # 逐場往績：由 "Finished x/y" 錨定，向後掃同一段落
    runs = []
    starts = [m.start() for m in RE_RUN.finditer(flat)]
    for i, m in enumerate(RE_RUN.finditer(flat)):
        # ⚠️ 每段一定要**截到下一仗開始為止**。之前寫死 +900 字元，於是隔籬仗嘅
        # 獎金／走位／段速／對手會漏過嚟：試閘（獎金應該係 `(of 0)`）攞咗隔籬
        # 正式賽嘅 $175,000，而 `Barrier Trial` 四個字漏過嚟仲會令一場 14 匹嘅
        # 正式賽被標成試閘。呢個同 `Settled`、`L600 Delta`、試閘 header 係
        # 同一個病：**掃描範圍冇界，就會靜靜咁撈錯數據**。
        nxt = starts[i + 1] if i + 1 < len(starts) else len(flat)
        seg = flat[m.start(): min(nxt, m.start() + 900)]
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
        # 獎金一定喺 `Finished x/y … (of $N), Jockey …` 之間，即係 RE_RUN
        # 個 match 範圍以內。掃闊過呢個範圍就會撈到下一仗嘅獎金。
        pz = RE_PRIZE.search(flat[m.start():m.end()])
        # 試閘**只**睇 header 個 class 欄（例如 `OPEN-BT Barrier Trial`）。
        # ⚠️ 唔好掃成段文字 —— 試過掃 seg[:320]，結果隔籬段嘅 "Barrier Trial"
        # 漏過嚟，把一場 14 匹、負 15.85L 嘅正式 Caulfield 賽事標成試閘。
        # 試閘獎金寫成 `(of 0)`，係第二個獨立訊號。
        cls_txt = (hdr or {}).get("cls") or ""
        is_trial = bool(RE_TRIAL.search(cls_txt)) or (pz and pz.group(1) == "0")
        runs.append({**m.groupdict(),
                     "header": hdr,
                     "is_trial": is_trial,
                     "prize": pz.group(1) if pz else None,
                     "p800": ir.group("p800") if ir else None,
                     "p400": ir.group("p400") if ir else None,
                     "settled": ir.group("settled") if ir else None,
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


def run_date(run):
    """往績行嘅日期，正規化做 YYYY-MM-DD（攞唔到就回 ""）。

    Sportsbet 出 DD/MM/YYYY，下游 regex 要 YYYY-MM-DD。
    """
    d = ((run.get("header") or {}).get("date") or "").strip()
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", d)
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else d


def run_line(run):
    """砌一條 Racenet 格式嘅往績行。"""
    h = run.get("header") or {}
    # `Barrier Trial Apiam Bendigo` —— header regex 個 track group 會連前面
    # 嗰句 "Barrier Trial" 一齊食咗，落到賽事名度就變咗個唔存在嘅馬場。
    track = RE_TRIAL.sub("", (h.get("track") or "")).strip()
    dist = h.get("dist")
    cond = (h.get("going") or "").strip()
    # ⚠️ 下游 `inject_fact_anchors.race_simple` 要
    #     `^場地 R\d+ YYYY-MM-DD \d+m cond:\S+ \$[0-9,]+`
    # Sportsbet 出 DD/MM/YYYY，而且賽事獎金唔喺同一行。兩者任何一樣唔啱，
    # 成條往績行會被靜靜丟棄（Facts 會報「數據不足」而唔會報錯）。
    d = run_date(run)
    prize = re.sub(r"[^\d]", "", run.get("prize") or "") or "0"
    # 現有數據源寫 `Southside Cranbourne **(TRIAL)** R8 ...`，下游照住認。
    label = f"{track} {TRIAL_MARKER}" if run.get("is_trial") else track
    parts = [f"{label} R{h.get('race','?')} {d} {dist or '?'}m cond:{cond or 'None'} ${prize}"]
    parts.append(f"{(run.get('jockey') or '').strip()} ({run.get('barrier','?')})"
                 f" {run.get('weight','?')}kg")
    if run.get("sp"):
        parts.append(f"Flucs:$- ${run['sp']}")
    pos = []
    if run.get("p800"):
        pos.append(f"{run['p800']}@800m")
    if run.get("p400"):
        pos.append(f"{run['p400']}@400m")
    # `Nth@Settled` 一定要寫喺最後、同其他走位同一行 —— `inject_fact_anchors`
    # 用 `(\d+)\w+@Settled` 喺成個 race_block 度搵，而 PI = Settled − Finish。
    if run.get("settled"):
        pos.append(f"{run['settled']}@Settled")
    tail = " ".join(pos) + "."
    if run.get("margin"):
        tail += f" margin:{run['margin']}L"
    if run.get("field"):
        tail += f" starters:{run['field']}"
    delta = _l600_delta(run.get("l600"), track, dist)
    if delta is not None:
        # ⚠️ 個 key **一定要**係 `L600 Delta:`，唔係 `Last600:`。
        # `_pace_figure_score` 讀 `pf_aggregates['l600_delta_avg']`，而佢淨係由
        # `L600 Delta:` 嚟（engine_core `_parse_pf_token`）。`Last600:` 會去咗
        # `l600_time`，冇任何 leaf 讀 —— 所以寫錯 key 唔會報錯，只會令段速實速
        # 全場中性 60。實測：2026-08-01 Flemington 九場，PF 寫咗 96% 嘅往績行，
        # 但 pace_figure_score 嘅 evidence 係 **0%**、SD 0.00。
        # 而且 `Last600:` 喺 live Formguide 係 PuntingForm 評分（29–93），
        # 唔係秒差 —— 借佢個名擺個 delta 落去係兩把唔同嘅尺。
        tail += f" PF[L600 Delta: {delta}]"
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


def write_meeting(races, out_dir, date_str, venue, verbose=True,
                  speedmaps=None, odds=None):
    """寫 Racenet 格式嘅 meeting 檔。`races` = [(race_no, parsed, blocks)]。

    格式**唔可以自創** —— 下游 `inject_fact_anchors` 同引擎逐行 regex 食佢。
    對照 `claw_racenet_scraper.py` 147–252 行。
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    mm_dd = date_str[5:]
    idx = [f"# AU Wong Choi Formguide Index\n", f"Meeting: {venue} {date_str}\n"]
    speedmaps = speedmaps or {}
    odds = odds or {}
    kept = dropped = ly_hit = ly_miss = 0
    # ⚠️ `_trainer_ly` / `_jockey_ly` 一直**有人讀、冇人寫** —— write_meeting 用
    # `st.get('_trainer_ly','-')`，但成個 repo 冇一個地方 set 佢，所以每匹馬都出
    # `(LY: -)`。引擎個 `(LY: N:w-p-s)` token 就係騎練往績嘅入口，冇咗佢
    # `jockey_score` 得 63%（現有源 99%）、`trainer_score` 51%。
    # 抓一千幾個個人頁但唔接呢條線，等於抓完擺喺度。
    try:
        import sb_people_stats
        _people_cache = sb_people_stats.load_cache()
    except Exception:  # noqa: BLE001 — 攞唔到統計唔應該炸咗寫檔
        sb_people_stats, _people_cache = None, {}
    for race_no, p, blocks in races:
        meta = p["meta"]
        sm = speedmaps.get(race_no) or {}
        od = odds.get(race_no) or {}
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
                def _ly(kind, person_name):
                    nonlocal ly_hit, ly_miss
                    pid = _match_person(meta.get("people_by_name") or {}, kind,
                                        person_name)
                    entry = _people_cache.get(f"{kind.lower()}|{pid}") if pid else None
                    tok = (entry or {}).get("ly") or "-"
                    if tok != "-":
                        ly_hit += 1
                    else:
                        ly_miss += 1
                    return tok
                f_fg.write(f"T: {ov.get('trainer','')} (LY: {_ly('Trainer', ov.get('trainer',''))}) "
                           f"| J: {ov.get('jockey','')} (LY: {_ly('Jockey', ov.get('jockey',''))})\n\n")
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
                           f"{'12moRec:':<10} {st.get('12 months','-'):<15}\n")
                # Sportsbet 獨有：官方預測定位序（Speedmap）同 win/place 賠率。
                # 兩樣都係新增行，唔會撞到既有 regex；暫時冇 leaf 讀，留住備用。
                w, pl = od.get(num, (None, None))
                f_fg.write(f"{'SpeedPos:':<10} {str(sm.get(num,'-')):<15} "
                           f"{'WinOdds:':<10} {str(w or '-'):<15} "
                           f"{'PlcOdds:':<10} {str(pl or '-'):<15}\n\n")
                for run in blk.get("runs", []):
                    # ⚠️ 時點正確性 —— 呢個 filter 唔可以拆。Sportsbet 嘅表格頁係
                    # **賽後**先抓到，所以每匹馬嘅往績第一行就係我哋要預測嗰場，
                    # 連名次、負距、頭馬名同 600m 段速都齊。留住佢等於將答案餵返
                    # 落 form_score / 段速實速 / 賽績線 / 定位，backtest 會靚到假。
                    # 實測：2026-08-01 Flemington 520 條往績有 89 條（17.1%）
                    # 係當日或之後，而且係**最近一行**，即係近績加權最重嗰行。
                    if run_date(run) >= date_str:
                        dropped += 1
                        continue
                    a, b = run_line(run)
                    f_fg.write(a + "\n" + b + "\n")
                    f_fg.write("Video: \nNote: \nStewards: \n\n")
                    kept += 1
                f_fg.write("=" * 60 + "\n\n")
        idx.append(f"- Race {race_no}: {dist}m — {rc_path.name} / {fg_path.name}\n")
        if verbose:
            print(f"   ✅ R{race_no}: {len(p['overview'])} 匹 → {fg_path.name}")
    (out / f"{mm_dd} Formguide_Index.md").write_text("".join(idx), encoding="utf-8")
    (out / "Meeting_Summary.md").write_text(
        f"# {venue} {date_str}\n\n{len(races)} races extracted from Sportsbet.\n"
        f"Form runs kept: {kept}; dropped as on/after {date_str}: {dropped}\n"
        f"Jockey/trainer LY tokens filled: {ly_hit}; missing: {ly_miss}\n",
        encoding="utf-8")
    if verbose:
        print(f"   往績行：保留 {kept}，因為喺 {date_str} 當日或之後而丟棄 {dropped}")
    return {"kept": kept, "dropped": dropped, "ly_hit": ly_hit, "ly_miss": ly_miss}


RE_SPEED = re.compile(r"^\s*(\d{1,2})\s*$")


def parse_speedmap(html):
    """`?view=Speedmap` → {馬號: 預測定位序}（1 = 最前）。

    ⚠️ 佢**唔係圖** —— 零 SVG/canvas，純 DOM 文字。版面係
        Barriers ... Finish post
        11    10. Salizou      ← 左邊係檔位，右邊 `馬號. 馬名`
    我哋要嘅係**由後到前嘅列表次序**（表頭寫明 "Predicted settling positions
    after start"），所以由上到下 enumerate 就係定位序。
    """
    txt = to_text(html)
    order, seen = [], set()
    started = False
    for line in txt.splitlines():
        l = line.strip()
        if "Predicted settling" in l or "Speed Map" in l:
            started = True
            continue
        if not started:
            continue
        m = re.match(r"^(\d{1,2})\.\s+(.+)$", l)
        if m and m.group(1) not in seen:
            seen.add(m.group(1))
            order.append(int(m.group(1)))
        if "Replay speed map" in l or "Weather" in l:
            break
    return {n: i + 1 for i, n in enumerate(order)}


def fetch_odds(fetcher, event_id):
    """Sportsbet Markets API → {馬號: (winPrice, placePrice)}。

    ⚠️ 賠率**唔喺** sportsbetform 嘅 static HTML（嗰格係投注掣，價錢由 JS 填），
    所以一定要行呢個 API。
    """
    url = ("https://www.sportsbet.com.au/apigw/sportsbook-racing/Sportsbook/"
           f"Racing/Events/{event_id}/Markets")
    try:
        r = fetcher.session.get(url, timeout=30)
        data = r.json() if r.status_code == 200 else None
    except Exception:  # noqa: BLE001
        return {}
    out = {}

    def walk(o):
        if isinstance(o, dict):
            num = o.get("runnerNumber") or o.get("competitorNumber")
            if num and (o.get("winPrice") or o.get("placePrice")):
                out[int(num)] = (o.get("winPrice"), o.get("placePrice"))
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(data or {})
    return out


def parse_date_index(html):
    """`/{YYYY-MM-DD}/` 嗰版 → {slug: {"meetingId", "races": [...]}}。

    **呢個就係歷史 meetingId 嘅索引**，之前以為冇。首頁「Previous Form Guides」
    嘅日曆 widget 就係行呢條路（`document.location = '/'+date+'/'`）。widget 本身
    設咗 `setStartDate(-14)`，但**個限制淨係喺 widget 度** —— 直接開 URL
    實測返到一年前（2025-08-02，23 個馬場、185 場）。

    每個馬場嘅 meetingId 由 puntcdn 檔名嚟：
        //puntcdn.com/form-guides-sportsbet/20260725_caulfield_445618.pdf
                                            ^日期      ^slug      ^meetingId
    同版仲有齊 `/{meetingId}/{raceId}/` 嘅賽事連結，所以 raceId 都唔使猜。

    ⚠️ **呢版 curl_cffi 攞唔到（403）**，同首頁一樣 —— CloudFront 淨係擋
    index/root，唔擋 `/{meetingId}/{raceId}/`。所以發現要行瀏覽器（每個日期
    一版），抽取先行 curl_cffi。呢個函數只做 parse，唔負責攞頁。
    已抽好嘅結果放喺 `data/sb_archive_meeting_ids.json`（94 個場次 / 836 場）。
    """
    out = {}
    for m in re.finditer(
            r"form-guides-sportsbet/(\d{8})_([a-z0-9_]+?)_(\d+)(?:_[A-Za-z]+)?\.pdf", html):
        out.setdefault(m.group(2), {"date": m.group(1), "meetingId": m.group(3),
                                    "races": []})
    by_mid = {v["meetingId"]: v for v in out.values()}
    for m in re.finditer(r'href="/(\d{5,7})/(\d{5,9})/"', html):
        entry = by_mid.get(m.group(1))
        if entry is not None and m.group(2) not in entry["races"]:
            entry["races"].append(m.group(2))
    for v in out.values():
        v["races"].sort()
    return out


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
        # 馬匹往績索引：抽取嘅副產品，賽績線靠佢查對手後續走勢。
        # 每個 runner block 已經帶埋成個往績清單，所以呢度**唔會多打一個請求**。
        try:
            import sb_horse_index
            stats = sb_horse_index.update([b for _, _, bl in out for b in bl])
            print(f"   📇 馬匹索引 +{stats['runs_added']} 條往績"
                  f"（共 {stats['index_size']:,} 匹）")
        except Exception as exc:  # noqa: BLE001 — 索引失敗唔應該炸咗抽取
            print(f"   ⚠️ 馬匹索引略過（{type(exc).__name__}: {exc}）")
        # 逐場攞新鮮騎練統計。ID 由賽事頁直接嚟，所以唔會撞錯人；
        # `sb_people_stats` 有 TTL cache，跑熟之後每場只補幾個。失敗非致命。
        try:
            import sb_people_stats
            ppl = [(k, pid, "") for _, pr, _ in out
                   for k, pid in (pr["meta"].get("people") or [])]
            if ppl:
                sb_people_stats.refresh(ppl, fetcher=f)
        except Exception as exc:  # noqa: BLE001 — 統計攞唔到唔應該炸咗抽取
            print(f"   ⚠️ 騎練統計略過（{type(exc).__name__}: {exc}）")
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
