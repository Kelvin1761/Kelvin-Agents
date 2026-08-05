#!/usr/bin/env python3
"""Sportsbet 騎師／練馬師統計 —— 取代 `au_profile_stats.py`。

點解換得過：Racenet 版靠**人名推導 slug**，而嗰個推導錯得好厲害
（`ciaron-maher` vs 真 slug `ciaron-maher-david-eustace`），加上每次抽取
上限 25 個，結果 1,033 個騎練得 150 個有數據。

Sportsbet 冇呢兩個問題：
  * **賽事頁直接畀數字 ID** —— `/Jockey/987/`、`/Trainer/1300/`。冇 slug 要猜。
  * `/top-jockeys/` `/top-trainers/` 一個請求攞前 50，仲有 12 Months /
    Last Season / This Season 三個窗。

個人頁比 Racenet 闊好多：Win% / Place% / ROI 分生涯、12 個月、近 10、近 100，
再拆場地（Good/Soft/Heavy/Firm）、跑道類型、路程段、**檔位段、負磅段、
獎金段、馬群大細段**。Racenet 淨係得四個數字。

⚠️ 引擎要嘅格式係 `(LY: 288:53-39-35)` = starts:1st-2nd-3rd，
    啱啱好對應個人頁「12 Months」嗰行。`ly_token()` 就係做呢個轉換。
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from claw_sportsbet_form import BASE, SportsbetFormFetcher, to_text  # noqa: E402

CACHE_NAME = "AU_Sportsbet_People_Cache.json"
# ⚠️ TTL 可以由 env 覆寫。2026-08-05：晚更（22:00，有十二個鐘）設 0 令每個場次都
# 重抽騎練統計；早更（10:00，最早一場約 11:44）維持 21 日 cache。
# 點解要 refresh：呢個係「去年官方」滾動 12 個月紀錄，賽季中段會變。21 日 TTL
# 之下一個 8 月大爆發嘅騎師，我哋仲用 7 月中嘅數字，最多滯後 3 個星期。
# 成本：一個場次約 90–100 個人物 × 節奏（20 秒）≈ 30–35 分鐘，晚更做得到。
TTL_DAYS = int(os.environ.get("WC_SB_PEOPLE_TTL_DAYS", "21"))
# 個人頁嘅統計表逐行係：標籤 Starts 1st 2nd 3rd Win% Place% AvgOdds ROI
RE_ROW = re.compile(
    r"^(?P<label>[A-Za-z0-9$,+\- ]+?)\s+(?P<starts>\d+)\s+(?P<w>[\d\-]+)\s+"
    r"(?P<p>[\d\-]+)\s+(?P<s>[\d\-]+)\s+(?P<win>[\d.]+)%\s+(?P<place>[\d.]+)%", re.M)
WANT = {"Career", "12 Months", "Last 10", "Last 100",
        "Good", "Soft", "Heavy", "Firm", "Turf", "Synthetic"}


def cache_path():
    # ⚠️ 自己頂返 repo root 落 sys.path。呢個 module 會俾 cwd=au_racing 嘅
    # process import（`claw_sportsbet_form.py` 就係），嗰陣 repo root 唔喺
    # sys.path，`import wongchoi_paths` 會 ModuleNotFoundError。而 caller
    # (`write_meeting`) 係用 `except Exception` 包住，於是靜靜咁當「冇統計」，
    # 1,064 個 `(LY:)` token 全部寫成 `-`（2026-08-05 實測）。
    import sys
    root = str(Path(__file__).resolve().parents[3])
    if root not in sys.path:
        sys.path.insert(0, root)
    from wongchoi_paths import AU_RACING

    return Path(AU_RACING) / CACHE_NAME


def load_cache(path=None):
    path = Path(path) if path else cache_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _fresh(entry, ttl_days=TTL_DAYS):
    try:
        t = datetime.fromisoformat(entry.get("fetched_at", ""))
    except ValueError:
        return False
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - t).days < ttl_days


def parse_person(html):
    """個人頁 → {section: {starts, 1st, 2nd, 3rd, win_pct, place_pct}}。

    同一個標籤（例 `Good`）喺「Career」同「Last 12 Months」兩張表都出現，
    所以只收**第一次**（生涯），唔好畀後面嗰張覆蓋。
    """
    txt = to_text(html)
    # tab 分隔嘅表格喺 to_text 之後變成空白分隔，統一成單空格先 match
    flat = "\n".join(re.sub(r"\s+", " ", l).strip() for l in txt.splitlines())
    out = {}
    for m in RE_ROW.finditer(flat):
        label = m.group("label").strip()
        if label not in WANT or label in out:
            continue
        num = lambda k: (0 if m.group(k) == "-" else int(m.group(k)))  # noqa: E731
        out[label] = {"starts": int(m.group("starts")), "1st": num("w"),
                      "2nd": num("p"), "3rd": num("s"),
                      "win_pct": float(m.group("win")),
                      "place_pct": float(m.group("place"))}
    return out


def ly_token(stats):
    """→ 引擎要嘅 `288:53-39-35`（starts:1st-2nd-3rd）。冇 12 個月數據就回 `-`。"""
    s = (stats or {}).get("12 Months")
    if not s or not s.get("starts"):
        return "-"
    return f"{s['starts']}:{s['1st']}-{s['2nd']}-{s['3rd']}"


def refresh(people, fetcher=None, ttl_days=TTL_DAYS, max_people=40, path=None,
            verbose=True, cache_only=False):
    """`people` = [(kind, person_id, name)]，kind 係 'Jockey' / 'Trainer'。

    ID 由賽事頁直接嚟，所以**唔會撞錯人**。失敗一律非致命。

    `cache_only=True`：只讀已經落 cache 嘅個人頁，一個網絡請求都唔出。
    ⚠️ 點解需要呢個模式：curl_cffi 會俾 sportsbetform 403，所以 live 抽取
    嗰陣呢個 refresh 其實成功唔到 —— 靜靜咁失敗，然後 `(LY:)` 全部係 `-`。
    實測 2026-08-04 Warwick（鄉郊場）：cache 由大城市場次砌，只填到 107/214。
    正路係**抽取階段行瀏覽器把個人頁落 cache，呢度 cache-only 讀返** ——
    同賽事頁一樣嘅分工。冇咗呢個 flag，唯一選擇係出網然後失敗。
    """
    path = Path(path) if path else cache_path()
    cache = load_cache(path)
    f = fetcher or SportsbetFormFetcher(delay=8, verbose=verbose)
    todo, seen = [], set()
    for kind, pid, name in people:
        key = f"{kind.lower()}|{pid}"
        if not pid or key in seen:
            continue
        seen.add(key)
        if key in cache and _fresh(cache[key], ttl_days):
            continue
        todo.append((kind, pid, name, key))
    if verbose:
        print(f"   騎練統計：{len(seen)} 個人物，需要補 {len(todo)}，"
              f"今次抓 {min(len(todo), max_people)}")
    ok = 0
    for kind, pid, name, key in todo[:max_people]:
        url = f"{BASE}/{kind}/{pid}/"
        if cache_only and not f._cache_path(url).exists():
            continue
        html = f.get(url)
        if not html:
            continue
        stats = parse_person(html)
        if not stats:
            continue
        cache[key] = {"name": name, "id": str(pid), "kind": kind.lower(),
                      "stats": stats, "ly": ly_token(stats),
                      "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        ok += 1
    if verbose:
        print(f"   騎練統計：成功 {ok}，cache 共 {len(cache)}")
    return cache


def lookup(cache, kind, person_id):
    return (cache.get(f"{kind.lower()}|{person_id}") or {}).get("stats")


def main():
    import argparse

    ap = argparse.ArgumentParser(description="Sportsbet 騎練統計")
    ap.add_argument("--person", nargs=2, metavar=("KIND", "ID"),
                    help="例：--person Jockey 987")
    ap.add_argument("--delay", type=float, default=8.0)
    args = ap.parse_args()
    if not args.person:
        ap.error("要 --person KIND ID")
    kind, pid = args.person
    f = SportsbetFormFetcher(delay=args.delay)
    html = f.get(f"{BASE}/{kind}/{pid}/")
    if not html:
        print("❌ 攞唔到（可能撞 rate limit）")
        return 1
    st = parse_person(html)
    print(f"{kind}/{pid}  抽到 {len(st)} 個切面")
    for k, v in st.items():
        print(f"   {k:12} {v['starts']:>5} 戰  {v['1st']}-{v['2nd']}-{v['3rd']}  "
              f"勝 {v['win_pct']:>5.1f}%  上名 {v['place_pct']:>5.1f}%")
    print(f"\n引擎 LY token → {ly_token(st)}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    sys.exit(main())
