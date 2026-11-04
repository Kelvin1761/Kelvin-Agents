#!/usr/bin/env python3
"""HKJC 自購馬「來港前賽績記錄」（fsc PDF）—— starter PDF 唔喺度時嘅海外往績後備來源。

點解要有呢個檔
--------------
海外往績（`pdf_overseas_races`）只有一個來源：全日出賽馬匹資料 PDF
（`{YYYYMMDD}_starter_all_chi.pdf`）入面「Overseas Form of …」嗰幾版。以前呢份
PDF 係發佈閘嘅**硬條件**，佢一日攞唔到，成個場次就卡死（2026-09-06 沙田 22 次
run 有 20 次卡喺 PDF）。而 PDF 喺評分入面嘅唯一用途就係海外往績。

每匹自購馬另外有一份靜態嘅「來港前賽績記錄」：

    https://racing.hkjc.com/general/-/media/Sites/JCRW/pp_formsheet/ch/fsc_{烙號}.pdf

（烙號要補零：`L031` 得，`L31` 404；只有中文版，`/en/` 404。）入面有完整來港前
賽績，starter PDF 只係抽最近 10 仗。所以 starter PDF 冇嘅時候，逐匹馬由 fsc 砌返
**同一個 shape** 嘅 rows（`inject_hkjc_fact_anchors.parse_pdf_overseas_races` 嘅輸出），
下游 Facts → Logic → 引擎完全唔使改。

starter PDF 仍然係**主來源**：佢喺度就一律用佢，排名唔會郁。

同 starter PDF 對齊嘅規則（全部由實數據量出嚟，見
`docs/audits/hkjc-starter-pdf-soft-gate-20261103.md`）
--------------------------------------------------------------------------------
1. **邊啲馬有海外往績表**：starter PDF 個標題寫明「24/25, 25/26 及 26/27 年度自購馬匹」
   —— 即係最近三季入口嘅馬。烙號字母就係入口季度（J=23/24、K=24/25、L=25/26、
   M=26/27；2026-09 換季嗰日 J 字頭由 PDF 全部消失）。舊季入口嘅馬有 fsc 都唔可以用，
   否則佢哋會無端端多咗海外往績，排名就郁。
2. **最近 10 仗、舊→新排**：starter PDF 寫明 Last 10 starts，而且由舊排到新。
   `features/form.py` 係按 list 次序俾權重嘅，所以次序一定要一樣。計「10 仗」
   要連冇名次嗰啲行（例如 PU）一齊計，同 PDF 一樣。
3. **一級／二級／三級 → G1／G2／G3，表列 → L**：引擎嘅海外加分只認 `G1`／`1級`
   呢類字（`speed.py`、`jockey.py`、`trainer.py`），中文「一級」唔會中 —— 唔轉就會
   靜靜冇咗海外加分。
4. 場地、方向、地區、勝負距離同樣轉做 starter PDF 用嘅英文碼。馬場名、配備、
   賽事類別未逐個翻譯嘅會保留中文：呢幾欄只係顯示用，評分唔讀。
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

FSC_URL = "https://racing.hkjc.com/general/-/media/Sites/JCRW/pp_formsheet/ch/fsc_{brand}.pdf"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
# fsc 係入口前嘅靜態文件，入咗口就唔會再改。成功下載嘅檔永久 cache；
# 「冇呢份檔」（404）只 cache 一段時間，因為新入口馬嘅檔可能遲啲先上。
MISSING_RETRY_SECONDS = 7 * 24 * 3600
CACHE_DIRNAME = "_overseas_formsheet_cache"

# 入口季度 → 烙號字母。由 starter PDF 實測：2026-05～07 個標題係「23/24, 24/25 &
# 25/26」，海外表入面只有 J/K/L；2026-09 起變「24/25, 25/26 & 26/27」，J 全部消失、
# 10-19 開始出現 M。之後嘅季度假設逐個字母順延 —— 如果 HKJC 跳字母，呢度會令
# 新季嘅馬被當成舊季（即係冇 fallback rows），唔會錯加 rows。
_SEASON_LETTER_ANCHOR = (2023, "J")
SEASONS_LISTED = 3

REGION_CODES = {
    "澳洲": "AUS", "紐西蘭": "NZ", "英國": "GB", "愛爾蘭": "IRE", "南非": "SAF",
    "法國": "FR", "美國": "USA", "德國": "GER", "日本": "JPN", "意大利": "ITY",
    "阿根廷": "ARG", "巴西": "BRZ", "智利": "CHI", "新加坡": "SIN", "加拿大": "CAN",
    "烏拉圭": "URU", "阿聯酋": "UAE", "杜拜": "UAE", "澳門": "MAC", "秘魯": "PER",
    "瑞典": "SWE", "西班牙": "SPA", "挪威": "NOR", "丹麥": "DEN", "沙地阿拉伯": "KSA",
    "卡塔爾": "QA", "巴林": "BHR", "韓國": "KOR", "馬來西亞": "MAL", "比利時": "BEL",
    "荷蘭": "HOL", "捷克": "CZE", "奧地利": "AUT", "瑞士": "SWI", "土耳其": "TUR",
    "毛里裘斯": "MAU", "津巴布韋": "ZIM",
}
DIRECTION_CODES = {"右": "RH", "左": "LH", "直": "St"}
GRADE_CODES = {"一級": "G1", "二級": "G2", "三級": "G3", "表列": "L"}
# 場地（草地）。全天候跑道喺 fsc 寫成「膠沙地 (Polytrack)-標準」，個括號就係
# starter PDF 用嘅字，另外處理。
TURF_GOING_CODES = {
    "快地": "F", "好地至快地": "GF", "好地": "G", "好地至軟地": "GS", "好地至黏地": "GY",
    "黏地": "Y", "黏地至軟地": "YS", "軟地": "S", "軟地至大爛地": "SH", "爛地": "SH",
    "大爛地": "H", "沙地": "Sand",
}
# 同一個中文字，各地 starter PDF 用嘅英文碼唔同（法國「爛地」寫 VS）。只影響顯示。
TURF_GOING_BY_REGION = {("FR", "爛地"): "VS"}
# 冇括號嘅「膠沙地」：starter PDF 多數寫 Synthetic（紐西蘭劍橋等），英國有啲寫
# Polytrack／Tapeta。Surface 一樣係 SYNTHETIC，所以只係顯示字唔同。
BARE_ALL_WEATHER = "Synthetic"
# 2026-09～11 語料實際對到嘅英／愛全天候跑道（只收對得上嘅，唔估）。
BARE_ALL_WEATHER_BY_COURSE = {
    ("IRE", "鄧多克"): "Polytrack", ("GB", "金頓"): "Polytrack",
    ("GB", "嶺飛"): "Polytrack", ("GB", "湛士福城"): "Polytrack", ("GB", "紐卡素"): "Tapeta",
}
MARGIN_WORDS = {
    "馬頭": "Hd", "短馬頭": "SH", "馬頸": "Nk", "馬鼻": "Nose", "長馬頭": "LHd",
    "長馬頸": "LNk", "平頭": "DH", "Head": "Head",
    "頭位": "Hd", "短頭位": "SH", "頸位": "Nk", "鼻位": "Ns", "短馬頭位": "SH",
    "平頭馬": "DH", "多個馬位": "Dist",
}
AGE_RE = re.compile(r"(\d)歲(及以上)?")

ROW_START_RE = re.compile(r"^\s*(\d{1,2})\.(\d{1,2})\.(\d{4})\s")
ROW_RE = re.compile(
    r"^\s*(?P<date>\d{1,2}\.\d{1,2}\.\d{4})\s+(?P<course>.+?)(?:\s+(?P<dir>右|左|直))?\s+"
    r"(?P<dist>\d{3,4})\s+(?P<mid>.+?)\s+(?P<grade>一級|二級|三級|表列|-)\s+"
    r"(?P<place>\d+)\s*/\s*(?P<field>\d+)(?:\s*\(平頭\))?\s+(?P<barrier>\S+)\s+(?P<wt>\d+)(?:\([+-]?\d+\))?\s+"
    r"(?P<odds>\S+)\s+(?P<rest>.+)$"
)
# 「1.3.02R」呢類手民之誤都見過（J215）：分鐘後面嗰格補返兩位。
TIME_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{2})R?$")
ALL_WEATHER_RE = re.compile(r"^(?P<word>\S*地)\s*\((?P<code>[A-Za-z][A-Za-z ]*)\)(?:-\S+)?\s*")


# ───────────────────────────── 資格：邊啲馬有表 ─────────────────────────────

def normalise_brand(value: object) -> str:
    """`K475`／`HK_2024_K475`／`L31` → `K475`／`L031`；認唔到就回 ''。"""
    text = str(value or "").strip().upper().rsplit("_", 1)[-1]
    match = re.fullmatch(r"([A-Z])0*(\d{1,3})", text)
    if not match:
        return ""
    return f"{match.group(1)}{int(match.group(2)):03d}"


def season_start_year(race_date: str) -> int:
    """HKJC 馬季九月開。`2026-11-04` → 2026；`2026-07-15` → 2025。"""
    dt = datetime.strptime(race_date, "%Y-%m-%d")
    return dt.year if dt.month >= 9 else dt.year - 1


def season_letter(start_year: int) -> str:
    anchor_year, anchor_letter = _SEASON_LETTER_ANCHOR
    return chr(ord(anchor_letter) + (start_year - anchor_year))


def listed_in_starter_pdf(brand: str, race_date: str) -> bool:
    """starter PDF 個海外往績表只列最近三季入口嘅自購馬。"""
    brand = normalise_brand(brand)
    if not brand:
        return False
    oldest = season_letter(season_start_year(race_date) - (SEASONS_LISTED - 1))
    return brand[0] >= oldest


# ───────────────────────────── 解析 fsc 文字 ─────────────────────────────

def _details_lines(text: str) -> list[str]:
    text = (text or "").replace("﻿", "").replace("\r\n", "\n").replace("\r", "\n")
    idx = text.find("往績詳情")
    body = text[idx:] if idx >= 0 else text
    return [line.strip() for line in body.split("\n")]


def split_run_blocks(text: str) -> list[tuple[datetime, str, str]]:
    """每仗兩行：第一行以日期開頭，第二行係（星期）＋ 續行。

    回傳 `(日期, 第一行, 續行)`；所有以日期開頭嘅行都計 —— 包括冇名次嗰啲 —— 因為
    starter PDF 個「最近 10 仗」都係咁數。
    """
    blocks: list[list] = []
    for line in _details_lines(text):
        if not line:
            continue
        match = ROW_START_RE.match(line + " ")
        if match:
            try:
                dt = datetime(int(match.group(3)), int(match.group(2)), int(match.group(1)))
            except ValueError:
                continue
            blocks.append([dt, line, ""])
        elif blocks and line.startswith("("):
            # 「(六) (1.36.15) (HKD 40,700) 季: …」—— 續行一定以（星期）開頭；
            # 只收第一條續行，之後嘅係頁尾／下一個表。
            if not blocks[-1][2]:
                blocks[-1][2] = line
    return [(dt, first, cont) for dt, first, cont in blocks]


def _going_and_class(mid: str, cont: str = "") -> tuple[str, str]:
    """`mid` = 「場地 賽事名稱/類別」。回傳 (starter PDF 場地碼, 類別文字)。

    場地字有時會斷開兩行（「好地至」＋續行「快地」、「好地至黏」＋「地」），
    所以認唔到就試埋續行第一個字。
    """
    mid = mid.strip()
    aw = ALL_WEATHER_RE.match(mid)
    if aw:
        code = aw.group("code").strip()
        return code, mid[aw.end():].strip()
    head, _, tail = mid.partition(" ")
    if head == "膠沙地":
        return BARE_ALL_WEATHER, tail.strip()
    if head in TURF_GOING_CODES:
        return TURF_GOING_CODES[head], tail.strip()
    cont_tokens = re.sub(r"^\([^)]*\)\s*", "", cont or "").split()
    if cont_tokens:
        for key, code in TURF_GOING_CODES.items():
            if key.startswith(head) and cont_tokens[0].startswith(key[len(head):]):
                return code, tail.strip()
    if head.startswith("泥地"):
        return "Dirt", tail.strip()
    return head, tail.strip()


def _surface(going: str) -> str:
    # 同 `parse_pdf_overseas_races` 完全一樣嘅規則。
    upper = going.upper()
    if upper == "DIRT":
        return "DIRT"
    if upper in {"SYNTHETIC", "POLYTRACK", "TAPETA", "AWT"}:
        return "SYNTHETIC"
    return "TURF"


def _margin(token: str) -> str:
    token = token.strip()
    match = re.fullmatch(r"([+-]?)(.*?)馬位", token)
    if match:
        return f"{match.group(1)}{match.group(2)}L"
    sign = token[:1] if token[:1] in "+-" else ""
    word = token[len(sign):]
    if word in MARGIN_WORDS:
        return f"{sign}{MARGIN_WORDS[word]}"
    return token


def _finish_time(token: str) -> str:
    match = TIME_RE.match(token)
    return f"{match.group(1)}.{int(match.group(2)):02d}.{match.group(3)}" if match else token


def _is_margin(token: str) -> bool:
    body = token.lstrip("+-")
    return body.endswith("馬位") or body in MARGIN_WORDS


def _age_code(*texts: str) -> str:
    for text in texts:
        match = AGE_RE.search(text or "")
        if match:
            return f"{match.group(1)}yo" + ("+" if match.group(2) else "")
    return "-"


def parse_run(dt: datetime, first: str, cont: str = "") -> Optional[dict]:
    """一仗 → `parse_pdf_overseas_races` 同一個 dict shape；解析唔到回 None。"""
    match = ROW_RE.match(first)
    if not match:
        return None
    direction = match.group("dir")
    if not direction:
        # 方向偶然斷咗落續行：「(三) 右 ( - ) …」
        wrapped = re.match(r"^\([^)]*\)\s+(右|左|直)\b", cont or "")
        direction = wrapped.group(1) if wrapped else ""
    course_tokens = match.group("course").split()
    region = REGION_CODES.get(course_tokens[0], course_tokens[0]) if course_tokens else ""
    racecourse = " ".join(course_tokens[1:]) if len(course_tokens) > 1 else ""
    going, class_text = _going_and_class(match.group("mid"), cont)
    going_word = match.group("mid").split()[0] if match.group("mid").split() else ""
    going = TURF_GOING_BY_REGION.get((region, going_word), going)
    if going == BARE_ALL_WEATHER:
        going = BARE_ALL_WEATHER_BY_COURSE.get((region, racecourse), going)
    rest = match.group("rest").split()
    time_idx = next((i for i, tok in enumerate(rest) if TIME_RE.match(tok)), None)
    margin_idx = next((i for i, tok in enumerate(rest) if _is_margin(tok)), None)
    if time_idx is None or margin_idx is None or margin_idx > time_idx:
        return None
    gear_tokens = [tok for tok in rest[:margin_idx] if tok != "-"]
    cont_gear = re.match(r"^\([^)]*\)\s+(/\S+)", cont or "")
    if cont_gear and gear_tokens:
        gear_tokens[-1] += cont_gear.group(1)
    grade = GRADE_CODES.get(match.group("grade"), "")
    age = _age_code(match.group("mid"), cont)
    # 賽事名（多數係英文，例如「GOLDEN GATE S. - 3歲 二班讓磅賽」）唔入 Race_Type：
    # starter PDF 都冇，而且引擎用子字串搵 G1/G2/G3，賽事名入面有呢啲字就會誤中。
    class_text = AGE_RE.sub("", class_text.rsplit(" - ", 1)[-1]).replace("及", "").strip()
    if re.search(r"[A-Za-z]", class_text):
        class_text = ""
    race_type = " ".join(part for part in (age, grade or class_text or "-") if part)
    return {
        "Date": f"{dt.day}/{dt.month}/{dt.year}",
        "Region": region,
        "Racecourse": racecourse,
        "Direction": DIRECTION_CODES.get(direction, ""),
        "Distance": int(match.group("dist")),
        "Going": going,
        "Surface": _surface(going),
        "Placing": int(match.group("place")),
        "Field_Size": int(match.group("field")),
        "Race_Type": race_type,
        "Weight": int(match.group("wt")),
        "Finish_Time_Raw": _finish_time(rest[time_idx]),
        "Margin": _margin(rest[margin_idx]),
        "Gear": " ".join(gear_tokens),
        "Is_PDF_Overseas": True,
        "Source": "fsc_formsheet",
        "Raw_Line": first,
    }


def rows_from_text(text: str, race_date: str, limit: int = 10) -> list[dict]:
    """fsc 全文 → starter PDF 等價 rows：賽日之前、最近 `limit` 仗、舊→新。"""
    cutoff = datetime.strptime(race_date, "%Y-%m-%d")
    blocks = sorted(
        (block for block in split_run_blocks(text) if block[0] < cutoff),
        key=lambda block: block[0],
    )[-limit:]
    rows = []
    for dt, first, cont in blocks:
        row = parse_run(dt, first, cont)
        if row is not None:
            rows.append(row)
    return rows


# ───────────────────────────── 下載 + cache ─────────────────────────────

def default_cache_dir() -> Path:
    env = os.environ.get("WC_HKJC_FSC_CACHE_DIR", "").strip()
    if env:
        return Path(env).expanduser()
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from wongchoi_paths import HK_RACING  # noqa: E402

    return Path(HK_RACING) / CACHE_DIRNAME


def _http_get(url: str, timeout: float = 30.0) -> tuple[int, bytes]:
    import requests

    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    return response.status_code, response.content


def _pdf_text(pdf_path: Path) -> str:
    import pdfplumber

    with pdfplumber.open(str(pdf_path)) as pdf:
        return "\n".join((page.extract_text() or "") for page in pdf.pages)


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def fetch_formsheet_text(
    brand: str,
    cache_dir: Optional[Path] = None,
    http_get: Callable[[str], tuple[int, bytes]] = _http_get,
    now: Optional[float] = None,
) -> tuple[Optional[str], str]:
    """回傳 `(全文 or None, 狀態)`；狀態係 cached／downloaded／not_found／error:…。

    全文 cache 做 `fsc_{烙號}.txt`（同 PDF 並排），之後唔使再開 PDF。
    """
    import time

    brand = normalise_brand(brand)
    if not brand:
        return None, "error:bad_brand"
    cache_dir = Path(cache_dir) if cache_dir else default_cache_dir()
    pdf_path = cache_dir / f"fsc_{brand}.pdf"
    txt_path = cache_dir / f"fsc_{brand}.txt"
    miss_path = cache_dir / f"fsc_{brand}.missing"
    now = time.time() if now is None else now
    if txt_path.is_file():
        return txt_path.read_text(encoding="utf-8"), "cached"
    if pdf_path.is_file():
        text = _pdf_text(pdf_path)
        _atomic_write_bytes(txt_path, text.encode("utf-8"))
        return text, "cached"
    if miss_path.is_file() and now - miss_path.stat().st_mtime < MISSING_RETRY_SECONDS:
        return None, "not_found"
    try:
        status, content = http_get(FSC_URL.format(brand=brand))
    except Exception as exc:  # 網絡失敗唔可以拖冧 Facts；交返 caller 報 warning。
        return None, f"error:{type(exc).__name__}"
    if status == 404 or (status == 200 and not content.startswith(b"%PDF")):
        cache_dir.mkdir(parents=True, exist_ok=True)
        miss_path.write_text(str(status), encoding="utf-8")
        return None, "not_found"
    if status != 200:
        return None, f"error:http_{status}"
    _atomic_write_bytes(pdf_path, content)
    text = _pdf_text(pdf_path)
    _atomic_write_bytes(txt_path, text.encode("utf-8"))
    if miss_path.exists():
        miss_path.unlink()
    return text, "downloaded"


def fallback_overseas_rows(
    brand: str,
    race_date: str,
    cache_dir: Optional[Path] = None,
    http_get: Callable[[str], tuple[int, bytes]] = _http_get,
) -> tuple[list[dict], str]:
    """starter PDF 冇嘅時候，一匹馬嘅海外往績。回傳 `(rows, 狀態)`。

    狀態：`ok`／`not_listed`（唔係最近三季入口，PDF 本身都唔會有表）／
    `no_brand`（多數係訪港馬，冇 HK 烙號 → 冇 fsc）／`not_found`／`error:…`。
    """
    norm = normalise_brand(brand)
    if not norm:
        return [], "no_brand"
    if not listed_in_starter_pdf(norm, race_date):
        return [], "not_listed"
    text, status = fetch_formsheet_text(norm, cache_dir=cache_dir, http_get=http_get)
    if text is None:
        return [], status
    return rows_from_text(text, race_date), "ok"


if __name__ == "__main__":  # 手動檢查：python3 hkjc_overseas_formsheet.py L193 2026-10-14
    if len(sys.argv) != 3:
        print("Usage: hkjc_overseas_formsheet.py <烙號> <YYYY-MM-DD>", file=sys.stderr)
        sys.exit(2)
    found, state = fallback_overseas_rows(sys.argv[1], sys.argv[2])
    print(json.dumps({"status": state, "rows": found}, ensure_ascii=False, indent=1))
