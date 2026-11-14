"""HKJC 歷史引擎回放：喺生成好嘅賽日資料夾上**離線**行真流程（inject → skeleton）。

做法：同一個 process 入面 import 真 `inject_hkjc_fact_anchors` 同 `create_hkjc_logic_skeleton`，只攔截網絡：
  - 馬匹頁（horse?horseid=…）→ 外置碟 raw/horse_all（有就用）或 raw/horse 嘅原始 HTML，交返真解析器
    之後按賽日只留「賽日當季 + 前兩季」嘅往績 —— 同 live 預設「近三季」頁一樣
  - 賽果頁（localresults?...RaceDate=…&RaceNo=…）→ 賽果庫 + 分段頁（名次、馬號、馬名、馬匹 ID、頭馬距離）
  - 任何其他網址 → 直接報錯（保證回放期間冇上網）
  - inject 每匹馬 `time.sleep(0.5)` 嘅限速喺離線冇意義，喺呢個 process 停用
引擎、inject、skeleton 一行唔改。

用法：python3 hkjc_history_replay_run.py <meeting_dir> [<meeting_dir> ...]
"""
from __future__ import annotations

import datetime as dt
import gzip
import io
import json
import os
import re
import sys
import time
import traceback
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[5]
SCRIPTS = REPO / ".agents/scripts"
SKEL_DIR = REPO / ".agents/skills/hkjc_racing/hkjc_wong_choi/scripts"
for p in (str(REPO), str(SCRIPTS), str(SKEL_DIR), str(_HERE.parent)):
    if p not in sys.path:
        sys.path.insert(0, p)

BASE = Path("/Volumes/Kelvin Hardisk 1/WongChoi-Archive/hkjc-history")
RAW = BASE / "raw"
CACHE_CWD = BASE / "replay_cwd" / str(os.getpid())   # 每個 process 自己一份 .hkjc_cache（並行時唔會互相寫爛），唔污染 repo
_RACE_DATE = {"iso": None}
_INDEX = {}


class _Resp:
    def __init__(self, text: str, status: int = 200):
        self.text, self.status_code = text, status
        self.content = text.encode("utf-8")
        self.encoding = "utf-8"
        self.ok = status == 200


def _offline_get(url, *a, **k):
    m = re.search(r"horseid=(HK_\d{4}_[A-Z]\d{3})", str(url))
    if m and "information/horse" in str(url):
        hid = m.group(1)
        for p in (RAW / "horse_all" / f"{hid}.html.gz", RAW / "horse" / f"{hid}.html.gz"):
            if p.exists():
                return _Resp(gzip.open(p, "rt", encoding="utf-8", errors="ignore").read())
        return _Resp("", 404)
    raise RuntimeError(f"回放離線：唔准上網 {url}")


def _season_start(iso: str) -> dt.date:
    d = dt.date.fromisoformat(iso)
    return dt.date(d.year if d.month >= 9 else d.year - 1, 9, 1)


def _entry_iso(e: dict) -> str | None:
    m = re.match(r"(\d{2})/(\d{2})/(\d{2,4})$", str(e.get("date") or ""))
    if not m:
        return None
    y = m.group(3) if len(m.group(3)) == 4 else "20" + m.group(3)
    return f"{y}-{m.group(2)}-{m.group(1)}"


def _three_seasons(profile: dict) -> dict:
    """同 live「近三季」頁一樣：只留賽日當季 + 前兩季（賽日之後嘅由 inject 自己 as-of 剔走）。"""
    iso = _RACE_DATE["iso"]
    if not iso or not profile or profile.get("error"):
        return profile
    s = _season_start(iso)
    cutoff = dt.date(s.year - 2, 9, 1).isoformat()
    ents = [e for e in profile.get("entries", []) if (_entry_iso(e) or "9999") >= cutoff]
    return dict(profile, entries=ents)


def _offline_race_result(result_url: str, timeout: int = 15) -> list[dict]:
    import hkjc_profile_scraper as hps
    u = str(result_url)
    dm = re.search(r"[Rr]ace[Dd]ate=(\d{4})/(\d{2})/(\d{2})", u)
    nm = re.search(r"[Rr]ace[Nn]o=(\d+)", u)
    if not dm or not nm:
        return []
    key = (f"{dm.group(1)}-{dm.group(2)}-{dm.group(3)}", int(nm.group(1)))
    res, sec = _INDEX["results"].get(key), _INDEX["sect"].get(key)
    if not res:
        return []
    no2id = {str(h.get("horse_no")): h.get("horse_id") for h in (sec or {}).get("horses", [])}
    out = []
    for row in res.get("results", []):
        pos = str(row.get("pos") or "")
        m = re.match(r"\d+", pos)
        if not m:
            continue
        hn = str(row.get("horse_no") or "")
        margin = str(row.get("lbw") or "-")
        out.append({"placing": int(m.group()), "horse_no": int(hn) if hn.isdigit() else 0,
                    "horse_name": re.sub(r"\s*\([A-Z]\d+\)", "", row.get("horse_name") or "").strip(),
                    "horse_id": no2id.get(hn, ""), "margin_raw": margin,
                    "margin_numeric": hps.parse_margin_cn(margin)})
    return out


def install() -> None:
    CACHE_CWD.mkdir(parents=True, exist_ok=True)
    os.chdir(CACHE_CWD)
    import hkjc_history_replay_build as hb
    _INDEX.update(hb.load_index())
    import requests
    requests.get = _offline_get
    import scrape_hkjc_horse_profile as shp
    shp.requests.get = _offline_get
    shp._profile_cache = {}
    orig = shp.scrape_horse_profile

    def scrape(hid, timeout=15):
        shp._profile_cache = {}            # 唔用 48 小時 cache：每場要按賽日重新切三季
        return _three_seasons(orig(hid, timeout))
    shp.scrape_horse_profile = scrape
    import hkjc_profile_scraper as hps
    hps.requests.get = _offline_get
    hps.scrape_race_result = _offline_race_result
    hps._result_cache = {}
    hps.scrape_horse_profile = scrape
    time.sleep = lambda *_a, **_k: None


def run_meeting(md: Path) -> dict:
    import inject_hkjc_fact_anchors as inj
    import create_hkjc_logic_skeleton as sk
    inj.scrape_horse_profile = sys.modules["scrape_hkjc_horse_profile"].scrape_horse_profile
    day = re.match(r"(\d{4}-\d{2}-\d{2})", md.name).group(1)
    _RACE_DATE["iso"] = day
    stats = {"meeting": md.name, "races": 0, "facts_fail": [], "logic_fail": []}
    for fg in sorted(md.glob("* Race * 賽績.md"), key=lambda p: int(re.search(r"Race (\d+)", p.name).group(1))):
        n = int(re.search(r"Race (\d+)", fg.name).group(1))
        facts = md / fg.name.replace("賽績", "Facts")
        buf = io.StringIO()
        try:
            sys.argv = ["inject_hkjc_fact_anchors.py", str(fg), "--output", str(facts), "--race-date", day, "--race-num", str(n)]
            with redirect_stdout(buf), redirect_stderr(buf):
                inj.main()
        except SystemExit as e:
            if e.code not in (0, None):
                stats["facts_fail"].append((n, f"exit {e.code}", buf.getvalue()[-400:]))
                continue
        except Exception:
            stats["facts_fail"].append((n, traceback.format_exc()[-400:], ""))
            continue
        logic = md / f"Race_{n}_Logic.json"
        buf = io.StringIO()
        try:
            sys.argv = ["create_hkjc_logic_skeleton.py", str(facts), str(n), "--all-horses", "--output", str(logic)]
            with redirect_stdout(buf), redirect_stderr(buf):
                sk.main()
        except SystemExit as e:
            if e.code not in (0, None):
                stats["logic_fail"].append((n, f"exit {e.code}", buf.getvalue()[-400:]))
                continue
        except Exception:
            stats["logic_fail"].append((n, traceback.format_exc()[-400:], ""))
            continue
        stats["races"] += 1
    return stats


def main() -> None:
    dirs = [Path(a).resolve() for a in sys.argv[1:]]
    install()
    for md in dirs:
        print(json.dumps(run_meeting(md), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
