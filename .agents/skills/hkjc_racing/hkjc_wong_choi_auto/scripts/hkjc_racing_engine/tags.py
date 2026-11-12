"""每匹馬嘅「加分位／扣分位／留意」標籤 —— 純顯示，排名之後先做，永遠唔郁分數。

點解要有（Kelvin 2026-11-11）：舊嘅 chip 係「檔位與走位 +2.8」「騎師 艾兆禮」「練馬師 告東尼」
—— 維度名、人名，讀者睇完唔知「點解」。而家每個 chip 都係一句具體事實（「好檔（3檔）」
「人馬合拍」「潘頓棄騎」），而且分清楚：

  * ``scored=True``  ——引擎真係有為呢樣嘢加／扣分（騎練訊號嘅加減項、維度影響）。
  * ``scored=False`` ——賽前事實，**冇入分**，只係俾讀者參考（潘頓棄騎、練馬師王牌、初跑沙田…）。
    儀表板會畫成虛線 chip，tooltip 寫「未入分」，唔會扮成模型理由。

標籤三種語氣：``good``（有利）、``bad``（不利）、``note``（中性事實，要知）。

資料來源（全部賽前已知，同日或之後嘅紀錄一律濾走）：
  * Logic 本身：``python_auto``（騎練加減項、段速明細、維度影響）、``_data``（L400 趨勢）、騎師、檔位。
  * ``<場次資料夾>/.hkjc_cache/profile_cache.json``：HKJC 馬匹頁全部往績（騎師、路程、場地）。
    只用 ``date < 賽日`` 嘅紀錄；往績數目少過 ``hk_starts`` 就當歷史唔齊，唔出「初跑」標籤。
  * ``<場次資料夾>/* Race N 排位表.md``：「優先參賽次序」+ = 練馬師王牌。

任何一步出錯都只係少咗標籤，唔會令評分失敗（``race_tags`` 包住晒）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

PURTON = "潘頓"
BIG_DISTANCE_MOVE = 400          # 米；「大幅升程／縮程」
SPECIALIST_MIN_STARTS = 3        # 首本路程：同程至少 3 仗
SPECIALIST_PLACE_RATE = 0.4      # …而且上名率 ≥ 40% 或者勝出率 ≥ 25%
SPECIALIST_WIN_RATE = 0.25
L400_RUNS = 3                    # 末段：近 3 仗 L400 平均
DRIVER_FLOOR = 0.5               # 維度影響（原始尺）細過呢個唔寫，同 summary.IMPACT_FLOOR 一致

# 騎練訊號加減項（引擎 trainer_signal_detail.adjustments 嘅 factor）→ 標籤。
# 只寫幅度夠大嘅（細項 ±1～±1.5、騎練組合 +2 會令每匹馬都掛住一堆 chip）。
# (factor, 方向) -> (標籤, 語氣, 最少 |delta|)；數值對應 scoring.TRAINER_SIGNAL_CONTEXT_WEIGHTS。
_TRAINER_TAGS = {
    ("人馬歷史", 1): ("人馬合拍", "good", 2.0),          # horse_history_supportive／strong
    ("人馬歷史", -1): ("人馬唔夾", "bad", 2.0),
    ("騎練組合", 1): ("騎練黃金組合", "good", 4.0),      # combo_elite
    ("騎練組合", -1): ("騎練組合弱", "bad", 2.0),
    ("騎師同程", 1): ("騎師擅此程", "good", 3.0),        # jockey_distance_elite
    ("騎師同程", -1): ("騎師此程弱", "bad", 2.0),
    ("練馬師同程", 1): ("馬房擅此程", "good", 2.0),      # trainer_distance_elite
}


def _tag(key, label, tone, *, why="", scored=False, impact=None):
    return {"key": key, "label": label, "tone": tone, "why": why, "scored": scored,
            "impact": None if impact is None else round(float(impact), 2)}


def _num(text):
    m = re.search(r"-?\d+(?:\.\d+)?", str(text or ""))
    return float(m.group()) if m else None


def _distance(text):
    m = re.search(r"(\d{3,4})", str(text or ""))
    return int(m.group(1)) if m else None


def _race_meta(logic_data: dict) -> dict:
    ra = logic_data.get("race_analysis") or {}
    venue = str(ra.get("venue") or "")
    track = str(ra.get("track") or "")
    return {
        "date": str(ra.get("race_date") or "")[:10],
        "race_no": ra.get("race_number"),
        "distance": _distance(ra.get("distance")),
        "venue": "HV" if "跑馬地" in venue or "Happy" in venue else ("ST" if "沙田" in venue or "Sha" in venue else ""),
        "awt": "AWT" in venue.upper() or "AWT" in track.upper() or "全天候" in venue + track,
    }


# ── 往績（HKJC 馬匹頁）─────────────────────────────────────────────────────────

def load_profiles(meeting_dir: Path | None) -> dict:
    if not meeting_dir:
        return {}
    path = Path(meeting_dir) / ".hkjc_cache" / "profile_cache.json"
    try:
        cache = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {key: (value or {}).get("data") or {} for key, value in cache.items()}


def _entry_date(entry: dict) -> str:
    raw = str(entry.get("race_date_full") or entry.get("date") or "")
    m = re.match(r"(\d{4})/(\d{2})/(\d{2})", raw) or re.match(r"(\d{2})/(\d{2})/(\d{4})", raw)
    if not m:
        return ""
    a, b, c = m.groups()
    return f"{a}-{b}-{c}" if len(a) == 4 else f"{c}-{b}-{a}"


def past_runs(profile: dict, race_date: str) -> list[dict]:
    """HK runs strictly before race_date, newest first."""
    runs = []
    for entry in profile.get("entries") or []:
        d = _entry_date(entry)
        vt = str(entry.get("venue_track") or "")
        venue = entry.get("racecourse") or ("HV" if vt.startswith("跑馬地") else "ST" if vt.startswith("沙田") else None)
        if not d or (race_date and d >= race_date) or venue not in ("ST", "HV"):
            continue  # 同日／之後、海外紀錄唔計
        runs.append({"date": d, "venue": venue, "awt": "全天候" in vt, "distance": entry.get("distance"),
                     "jockey": str(entry.get("jockey") or "").strip(), "placing": entry.get("placing")})
    runs.sort(key=lambda r: r["date"], reverse=True)
    return runs


# ── 排位表：練馬師王牌 ───────────────────────────────────────────────────────

def load_priorities(meeting_dir: Path | None, race_no) -> dict:
    """horse_no(str) -> 優先參賽次序 raw text."""
    if not meeting_dir or not race_no:
        return {}
    out = {}
    for card in Path(meeting_dir).glob(f"* Race {race_no} 排位表.md"):
        try:
            text = card.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for block in text.split("\n\n"):
            no = re.search(r"^馬號:\s*(\d+)", block, re.M)
            pr = re.search(r"^優先參賽次序:\s*(.*)$", block, re.M)
            if no and pr:
                out[no.group(1)] = pr.group(1).strip()
        break
    return out


# ── 標籤 ───────────────────────────────────────────────────────────────────

def _trainer_tags(auto: dict) -> list[dict]:
    out = []
    for adj in (auto.get("trainer_signal_detail") or {}).get("adjustments") or []:
        delta = float(adj.get("delta") or 0)
        factor = adj.get("factor")
        if not delta:
            continue
        if factor == "換騎":
            continue  # 由 _jockey_change_tag 用前後騎師名寫
        hit = _TRAINER_TAGS.get((factor, 1 if delta > 0 else -1))
        if not hit or abs(delta) < hit[2]:
            continue
        label, tone, _ = hit
        out.append(_tag(f"trainer:{factor}", label, tone, why=str(adj.get("evidence") or ""), scored=True))
    return out


def _jockey_change_tag(horse: dict, auto: dict, runs: list[dict]) -> list[dict]:
    today = str(horse.get("jockey") or "").strip()
    prev = runs[0]["jockey"] if runs else ""
    scored = next((a for a in (auto.get("trainer_signal_detail") or {}).get("adjustments") or []
                   if a.get("factor") == "換騎" and a.get("delta")), None)
    if scored:
        label = f"換騎（{prev}→{today}）" if prev and prev != today else "換騎"
        return [_tag("jockey_change", label, "bad", why=str(scored.get("evidence") or ""), scored=True)]
    return []


def _purton_tags(horses: dict, runs_by_no: dict) -> dict:
    """潘頓上仗騎、今仗同場揀咗另一匹（EXP-20261111-21；未入分）。"""
    out: dict[str, list] = {}
    chosen = next((no for no, h in horses.items() if str(h.get("jockey") or "").strip() == PURTON), None)
    if not chosen:
        return out
    for no, h in horses.items():
        runs = runs_by_no.get(no) or []
        if no == chosen or not runs or runs[0]["jockey"] != PURTON:
            continue
        ch = horses[chosen]
        out.setdefault(no, []).append(_tag(
            "purton_left", f"潘頓棄騎（揀咗 {chosen} 號）", "bad",
            why=f"上仗潘頓騎，今仗佢同場改騎 [{chosen}] {ch.get('horse_name', '')}。"
                "2024-09→2026-11 579 匹：上名率 23.7%，比賠率預期低約 3pp，未證實；未入分。"))
        out.setdefault(chosen, []).append(_tag(
            "purton_chose", f"潘頓揀咗呢匹（棄 {no} 號）", "note",
            why=f"潘頓上仗騎 [{no}] {h.get('horse_name', '')}，今仗揀咗呢匹；未入分。"))
    return out


def _l400_mean(data: dict):
    text = str((data or {}).get("l400_trend") or "")
    values = [float(v) for v in re.findall(r"\d{2}\.\d{2}", text.split("趨勢")[0])]
    recent = values[-L400_RUNS:]  # 趨勢由舊到新
    return sum(recent) / len(recent) if len(recent) >= 2 else None


def _fastest_finisher(horses: dict) -> dict:
    means = {no: _l400_mean(h.get("_data")) for no, h in horses.items()}
    means = {no: m for no, m in means.items() if m is not None}
    if len(means) < 4:
        return {}
    ordered = sorted(means.items(), key=lambda kv: kv[1])
    if ordered[0][1] == ordered[1][1]:
        return {}
    no, best = ordered[0]
    return {no: [_tag("fastest_l400", f"近{L400_RUNS}仗末段全場最快（{best:.2f}s）", "good",
                      why=f"近{L400_RUNS}仗 L400 平均 {best:.2f}s，全場第一；第二快 {ordered[1][1]:.2f}s。"
                          "冇按路程／場地標準化；未入分（段速維度另有計 L400）。")]}


def _distance_venue_tags(horse: dict, auto: dict, runs: list[dict], meta: dict) -> list[dict]:
    out = []
    data = horse.get("_data") or {}
    try:
        hk_starts = int(data.get("hk_starts") or 0)
    except (TypeError, ValueError):
        hk_starts = 0
    if hk_starts == 0 or not runs:
        return out  # 初出馬：樣樣都係「初跑」，唔逐樣寫
    complete = len(runs) >= hk_starts
    dist = meta.get("distance")
    if dist:
        same = [r for r in runs if r["distance"] == dist]
        places = sum(1 for r in same if isinstance(r["placing"], int) and 1 <= r["placing"] <= 3)
        wins = sum(1 for r in same if r["placing"] == 1)
        if len(same) >= SPECIALIST_MIN_STARTS and (places / len(same) >= SPECIALIST_PLACE_RATE
                                                   or wins / len(same) >= SPECIALIST_WIN_RATE):
            impact = _impact(auto, "distance_fit")
            out.append(_tag("specialist", f"首本路程（{dist}米 {len(same)}戰{wins}勝{places}上名）", "good",
                            why=f"香港 {dist}米 {len(same)} 仗 {wins} 勝、{places} 次上名。",
                            scored=bool(impact and impact > 0), impact=impact))
        elif not same and complete:
            out.append(_tag("first_distance", f"初跑{dist}米", "note",
                            why=f"香港 {len(runs)} 仗從未跑過 {dist}米；未入分。"))
        prev = runs[0]["distance"]
        if prev and abs(dist - prev) >= BIG_DISTANCE_MOVE:
            word = "升程" if dist > prev else "縮程"
            out.append(_tag("distance_move", f"大幅{word}（{prev}→{dist}米）", "note",
                            why=f"上仗 {prev}米，今仗 {dist}米；未入分。"))
    if complete:
        if meta.get("awt") and not any(r["awt"] for r in runs):
            out.append(_tag("first_awt", "初跑泥地", "note", why=f"香港 {len(runs)} 仗從未跑過全天候跑道；未入分。"))
        venue = meta.get("venue")
        if venue and not any(r["venue"] == venue for r in runs):
            name = "沙田" if venue == "ST" else "跑馬地"
            out.append(_tag("first_venue", f"初跑{name}", "note", why=f"香港 {len(runs)} 仗從未喺{name}跑過；未入分。"))
    return out


def _impact(auto: dict, key: str):
    for row in (auto.get("grade_transparency") or {}).get("rows") or []:
        if row.get("key") == key:
            try:
                return float(row.get("impact"))
            except (TypeError, ValueError):
                return None
    return None


def _driver_tags(horse: dict, auto: dict, covered: set) -> list[dict]:
    """把有份影響排名嘅維度寫成一句具體事實（取代「檔位與走位 +2.8」）。"""
    out = []
    reasoning = auto.get("matrix_reasoning") or {}
    for row in (auto.get("grade_transparency") or {}).get("rows") or []:
        key = row.get("key")
        try:
            impact = float(row.get("impact"))
        except (TypeError, ValueError):
            continue
        if abs(impact) < DRIVER_FLOOR or key in covered:
            continue
        good = impact > 0
        why = _short_reason(reasoning.get(key))
        label = _driver_label(key, good, horse, auto) or f"{row.get('label', key)}{'佔優' if good else '蝕底'}"
        out.append(_tag(f"dim:{key}", label, "good" if good else "bad", why=why, scored=True, impact=impact))
    return out


def _short_reason(reasoning) -> str:
    text = str((reasoning or {}).get("text") or "").strip()
    if " → " in text:
        text = text.rsplit(" → ", 1)[0]
    return text.rstrip("。；; ")


def _driver_label(key: str, good: bool, horse: dict, auto: dict) -> str:
    barrier = str(horse.get("barrier") or "").strip()
    if key == "race_shape":
        return f"{'檔位走位有利' if good else '檔位走位唔利'}" + (f"（{barrier}檔）" if barrier else "")
    if key == "stability":
        # last_6_finishes 係由新到舊（同 recent_6_detail 第1仗＝上仗一致）
        form = [x for x in re.split(r"[-/]", str(horse.get("last_6_finishes") or "")) if x.strip().isdigit()][:3]
        return f"{'近績好' if good else '近績差'}" + (f"（近3仗 {'-'.join(form)}）" if form else "")
    if key == "sectional":
        items = [d for d in auto.get("speed_detail") or [] if d.get("delta")]
        items = [d for d in items if (float(d["delta"]) > 0) == good]
        if items:
            top = max(items, key=lambda d: abs(float(d["delta"])))
            why = re.sub(r"（[^）]*）", "", str(top.get("why") or top.get("factor") or "")).strip()
            if not re.search(r"末段|段速|L400|速", why):
                why = "段速" + why
            value = str(top.get("value") or "")
            # L400 值可能帶負磅換算尾巴（「23.64s，上仗 23.27s 按負磅換算 +0.37s」）；標籤只要入分用嗰個數。
            m_l400 = re.match(r"(\d{2}\.\d{2})s(?:$|，)", value) if str(top.get("factor") or "").startswith("L400") else None
            value = f"L400 {m_l400.group(1)}s" if m_l400 else ""
            return why + (f"（{value}）" if value else "")
        return "段速好" if good else "段速弱"
    if key == "trainer_signal":
        jockey = str(horse.get("jockey") or "").strip()
        return f"騎練實績{'強' if good else '弱'}" + (f"（{jockey}）" if jockey else "")
    if key == "form_line":
        return "賽績線強" if good else "賽績線弱"
    if key == "class_advantage":
        return "評分與經驗佔優" if good else "評分與經驗蝕底"
    if key == "horse_health":
        return "健康新鮮" if good else "休賽／健康扣分"
    if key == "distance_fit":
        return "同程有上名" if good else "同程未上過名"
    return ""


def horse_tags(no: str, horse: dict, auto: dict, *, runs: list[dict], meta: dict,
               priority: str = "", extra: list | None = None) -> dict:
    special = _trainer_tags(auto) + _jockey_change_tag(horse, auto, runs) + _distance_venue_tags(horse, auto, runs, meta)
    special += extra or []
    if "+" in str(priority or ""):
        special.append(_tag("trainer_ace", "練馬師王牌", "note",
                            why="排位表「優先參賽次序」標 +（練馬師用王牌確保出賽）。"
                                "量過：市場已經計晒，模型排名後只多約 2pp；未入分。"))
    covered = set()
    if any(t["key"].startswith("trainer:") or t["key"] == "jockey_change" for t in special):
        covered.add("trainer_signal")   # 騎練訊號已由具體加減項講晒
    if any(t["key"] in ("specialist", "first_distance") for t in special):
        covered.add("distance_fit")
    tags = _driver_tags(horse, auto, covered) + special
    order = lambda t: (not t["scored"], -abs(t["impact"] or 0))
    return {tone: sorted([t for t in tags if t["tone"] == tone], key=order) for tone in ("good", "bad", "note")}


def race_tags(logic_data: dict, meeting_dir: Path | None = None) -> dict:
    """horse_no -> {"good": [...], "bad": [...], "note": [...]}.  Never raises."""
    try:
        meta = _race_meta(logic_data)
        horses = {str(no): h for no, h in (logic_data.get("horses") or {}).items()
                  if isinstance(h, dict) and isinstance(h.get("python_auto"), dict)}
        profiles = load_profiles(meeting_dir)
        runs_by_no = {}
        for no, h in horses.items():
            pid = h.get("hkjc_horse_id") or ""
            runs_by_no[no] = past_runs(profiles.get(pid) or {}, meta["date"]) if pid in profiles else []
        priorities = load_priorities(meeting_dir, meta.get("race_no"))
        extra: dict[str, list] = {}
        for source in (_purton_tags(horses, runs_by_no), _fastest_finisher(horses)):
            for no, items in source.items():
                extra.setdefault(no, []).extend(items)
        return {no: horse_tags(no, h, h["python_auto"], runs=runs_by_no.get(no) or [], meta=meta,
                               priority=priorities.get(no, ""), extra=extra.get(no))
                for no, h in horses.items()}
    except Exception as exc:  # 純顯示：出錯就冇標籤，唔可以令評分失敗
        return {"_error": f"{type(exc).__name__}: {exc}"}
