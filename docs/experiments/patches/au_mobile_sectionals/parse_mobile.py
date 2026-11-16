"""sportsbetform 手機版 `/mobile/{eventId}/{n}/` 嘅 Speed 分頁（`mobile-sectional-times`）parser。

呢個分頁係**成場**（每匹馬一段），唔係淨係 URL 嗰匹：server 已經 render 咗
`FormGuide.getSectionalsCacheable(sportsbetEventId)`，預設篩選「Last 10 Runs / All Tracks」。

每匹馬：號碼、名、檔位、四個摘要（EARLY／MID／LATE／AVG km/h —— 係 Sportsbet
喺「而家」嗰 10 仗度計嘅平均，**唔好用**，point-in-time 唔安全，要自己由逐仗重算）。
每一仗：名次、馬數、場地、場地狀況、日期、路程、**本駒**完成時間，同 6 格
（1000m／800m／600m／400m／200m／Fnsh）每格「200m 分段秒數 + km/h」。
格名係「嗰 200m 段開始嘅位置」：`600m` = 離終點 800→600？唔係 —— 見 NOTES：
實測 `Fnsh` = 最後 200m，`200m` = 400→200，`400m` = 600→400，`600m` = 800→600，
`800m` = 1000→800，`1000m` = 1200→1000。冇數據 = `-`。
"""
from __future__ import annotations

import html
import re
import sys
from datetime import date

COLS = ["1000m", "800m", "600m", "400m", "200m", "Fnsh"]
# 每格嘅段：離終點 (start, end) 米
SEG = {"1000m": (1200, 1000), "800m": (1000, 800), "600m": (800, 600),
       "400m": (600, 400), "200m": (400, 200), "Fnsh": (200, 0)}


def _f(x: str):
    x = x.strip()
    if not x or x == "-":
        return None
    try:
        return float(x)
    except ValueError:
        return None


def parse(page: str) -> list[dict]:
    t = re.sub(r"\s+", " ", page)
    i = t.find('data-component="mobile-sectional-times"')
    if i < 0:
        return []
    j = t.find('<script id="template-mobile-sectional-times"', i)
    t = t[i:j if j > 0 else len(t)]
    runners = []
    for block in re.split(r'<a class="sectionals__runner"', t)[1:]:
        num = re.search(r'runner-number">([^<]*)<', block)
        info = re.search(r'runner-info">([^<]*)<', block)
        if not info or "{{" in info.group(1):
            continue
        m = re.match(r"\s*(.*?)\s*\((\d+)\)\s*$", html.unescape(info.group(1)))
        name, barrier = (m.group(1), int(m.group(2))) if m else (info.group(1).strip(), None)
        ov = dict((lab.replace("&nbsp;", " "), _f(v)) for v, lab in re.findall(
            r'overview-val">([^<]*)</div> <div class="sectionals__overview-label">([^<]*)<', block))
        runs = []
        for row in re.split(r'class="sectionals__event-row"', block)[1:]:
            fid = re.search(r'data-competitor-form-summary-id="(\d+)"', row)
            fin = re.search(r'finishing-num">([^<]*)<.*?finishing-starters">\s*of\s*([^<]*)<', row)
            hdr = re.search(r'event-name">([^<]*)<.*?track-conditions"[^>]*>([^<]*)<.*?'
                            r'event-info-row">\s*(\d\d)/(\d\d)/(\d{4}),\s*(\d+)m,\s*([\d.]+)s', row)
            if not hdr:
                runs.append({"unparsed": True})
                continue
            cols = re.findall(r'speed-label">([^<]+)</div> <div class="sectionals__speed-data">'
                              r'([^<]*)</div> <div class="sectionals__speed-data">([^<]*)<', row)
            seg = {c: (_f(a), _f(b)) for c, a, b in cols if c in COLS}
            d, mo, y = int(hdr.group(3)), int(hdr.group(4)), int(hdr.group(5))
            runs.append({
                "form_summary_id": fid.group(1) if fid else None,
                "pos": fin.group(1).strip() if fin else None,
                "starters": _f(fin.group(2)) if fin else None,
                "track": html.unescape(hdr.group(1)).strip(),
                "condition": hdr.group(2).strip(),
                "date": date(y, mo, d).isoformat(),
                "distance": int(hdr.group(6)),
                "time": float(hdr.group(7)),
                "split": {c: seg.get(c, (None, None))[0] for c in COLS},
                "kmh": {c: seg.get(c, (None, None))[1] for c in COLS},
            })
        runners.append({"number": int(num.group(1)) if num and num.group(1).isdigit() else None,
                        "name": name, "barrier": barrier, "overview": ov, "runs": runs})
    return runners


def derived(run: dict) -> dict:
    """由一仗推：L800/L600/L400 秒數（要齊格先計）、前段速度 = (路程-已知段)/(時間-已知段時間)。"""
    sp = run["split"]
    out = {}
    for name, cols in (("l400", ["200m", "Fnsh"]), ("l600", ["400m", "200m", "Fnsh"]),
                       ("l800", ["600m", "400m", "200m", "Fnsh"]),
                       ("l1000", ["800m", "600m", "400m", "200m", "Fnsh"])):
        v = [sp[c] for c in cols]
        out[name] = sum(v) if all(x is not None for x in v) else None
    # 前段：用最長嘅連續已知末段
    for name, metres in (("l1000", 1000), ("l800", 800), ("l600", 600), ("l400", 400)):
        if out[name] is not None and run["distance"] > metres + 100:
            pre_t = run["time"] - out[name]
            if pre_t > 0:
                out["early_kmh"] = (run["distance"] - metres) / pre_t * 3.6
                out["early_basis"] = metres
            break
    return out


if __name__ == "__main__":
    import json
    for p in sys.argv[1:]:
        print(json.dumps(parse(open(p, encoding="utf-8", errors="replace").read()), ensure_ascii=False)[:2000])
