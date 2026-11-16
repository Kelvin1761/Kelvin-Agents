"""HKJC 報名表快照（Kelvin 2026-11-17「如果佢報咗一個禮拜內嘅比賽，今仗會唔會係熱身？」；EXP-20261117-04）。

研究（用事後出賽，只係近似）：下仗 ≤7 日後再出嘅馬，今仗入位率低過模型 dev −2.8pp [−5.4,−0.4]、holdout −2.5pp（7 季 6 季負）。
但「下仗幾時出」好多時係今仗之後先決定（倒果為因）。乾淨版本 = 今仗開跑**之前**已經報咗下一場 —— 只有即時報名表先知，
HKJC 冇歷史報名表，所以由而家開始儲快照，forward 判。

報名表頁（一頁 = 下一個賽日，例如 11-17 已經有 11-22 沙田）：每個練馬師一行、每場一欄，馬名連結帶 horseid。
快照：<資料根>/HKJC_Entries/<賽日>_<抓取 UTC>.json。用法：
  fetch_and_store(root)          —— 一個請求（禮貌），同一個賽日當日已抓過就唔再抓
  entered_soon(root, race_date)  —— {horseid: {"date", "venue", "race", "class", "distance", "days"}}，
                                    只用今仗賽日 03:00 UTC（香港 11:00）之前抓嘅快照，賽日喺今仗之後 1–7 日
"""
from __future__ import annotations

import html as _html
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

URL = "https://racing.hkjc.com/zh-hk/local/information/entries"
DIRNAME = "HKJC_Entries"
PRE_RACE_UTC = "T030000Z"
WINDOW_DAYS = 7


def parse(page: str) -> dict:
    """報名表 HTML → {"date": ISO, "venue": "沙田"/"跑馬地", "races": [{"no", "class", "distance"}], "entries": {horseid: [race_no…]}}。"""
    m = re.search(r"賽事日期:\s*(\d{2})/(\d{2})/(\d{4})\s*([^\s-]+)", page)
    if not m:
        raise ValueError("報名表搵唔到賽事日期")
    meeting = date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
    venue = m.group(4)
    text = re.sub(r"<[^>]+>", "\n", page)
    lines = [_html.unescape(x).strip() for x in text.split("\n") if x.strip()]
    i = lines.index(next(x for x in lines if x.startswith("賽事日期")))

    def block(title, stop):
        a = lines.index(title, i) + 1
        b = lines.index(stop, a)
        return lines[a:b]
    classes = block("賽事班次", "評分幅度")
    dists = [int(x.rstrip("米")) for x in block("途程", "組別") if x.endswith("米")]
    races = [{"no": n + 1, "class": c, "distance": dists[n] if n < len(dists) else None} for n, c in enumerate(classes)]
    entries: dict[str, list[int]] = {}
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", page, flags=re.S):
        if "trainerprofile" not in row:
            continue
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.S)[1:]   # 第一格 = 練馬師
        for col, cell in enumerate(cells):
            for hid in re.findall(r"horseid=(HK_\d{4}_[A-Z]\d{3})", cell, flags=re.I):
                entries.setdefault(hid.upper(), []).append(col + 1)
    if not entries:
        raise ValueError("報名表冇馬（版面可能改咗）")
    return {"date": meeting, "venue": venue, "races": races, "entries": entries}


def fetch_and_store(root: Path, *, now: datetime | None = None, getter=None) -> Path | None:
    """抓一次報名表、存快照；同一賽日今日已有快照就唔抓。失敗返 None（純顯示／研究，唔可以令評分失敗）。"""
    now = now or datetime.now(timezone.utc)
    folder = Path(root) / DIRNAME
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    today = stamp[:8]
    if folder.exists() and any(p.name.split("_", 1)[1].startswith(today) for p in folder.glob("*_*.json")):
        return None
    try:
        if getter is None:
            import urllib.request
            req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                page = resp.read().decode("utf-8", errors="replace")
        else:
            page = getter(URL)
        snap = parse(page)
    except Exception:
        return None
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / f"{snap['date']}_{stamp}.json"
    out.write_text(json.dumps(dict(snap, captured_utc=stamp), ensure_ascii=False), encoding="utf-8")
    return out


def entered_soon(root: Path, race_date: str) -> dict:
    """今仗賽日開跑前已見到嘅報名（賽日喺今仗之後 1–7 日）；同一賽日取最新一份賽前快照。"""
    folder = Path(root) / DIRNAME
    if not folder.exists():
        return {}
    d0 = date.fromisoformat(str(race_date)[:10])
    cutoff = d0.strftime("%Y%m%d") + PRE_RACE_UTC
    best: dict[str, Path] = {}
    for p in sorted(folder.glob("*_*.json")):
        meeting, stamp = p.stem.split("_", 1)
        try:
            gap = (date.fromisoformat(meeting) - d0).days
        except ValueError:
            continue
        if 1 <= gap <= WINDOW_DAYS and stamp < cutoff:
            best[meeting] = p          # sorted → 最後嗰份 = 最新賽前快照
    out = {}
    for meeting, p in sorted(best.items()):
        snap = json.loads(p.read_text(encoding="utf-8"))
        races = {r["no"]: r for r in snap.get("races") or []}
        for hid, nos in (snap.get("entries") or {}).items():
            if hid in out:
                continue
            r = races.get(nos[0], {})
            out[hid] = {"date": meeting, "venue": snap.get("venue"), "race": nos[0], "class": r.get("class"),
                        "distance": r.get("distance"), "days": (date.fromisoformat(meeting) - d0).days}
    return out
