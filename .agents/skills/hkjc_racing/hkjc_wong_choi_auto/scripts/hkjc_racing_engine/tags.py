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
    ("騎練組合", -1): ("騎練唔合拍", "bad", 2.0),   # Kelvin 2026-11-17：負面要突出
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
        "race_class": ra.get("race_class"),
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


def load_gear(meeting_dir: Path | None, race_no) -> dict:
    """horse_no(str) -> 排位表配備代碼 list（HKJC：1 = 首次、- = 除去、2 = 再戴）。"""
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
            g = re.search(r"^配備:\s*(.*)$", block, re.M)
            if no and g:
                out[no.group(1)] = [x.strip() for x in g.group(1).split("/") if x.strip()]
        break
    return out


def _trainer_pattern_tags(horse: dict, meta: dict, gear: list[str]) -> list[dict]:
    """個別練馬師出擊 pattern（EXP-20261115-20）：純顯示，唔入分。"""
    from .trainer_patterns import NAMES, matches
    out = []
    for c in matches(horse, meta.get("race_class"), meta.get("distance"), gear):
        good = c["resid_pp"] > 0
        out.append(_tag(f"trainer_pattern:{c['pattern']}", f"{c['trainer']}{NAMES[c['pattern']]}（歷史 {c['resid_pp']:+.0f}pp）",
                        "good" if good else "bad",
                        why=f"{c['trainer']}嘅馬喺「{NAMES[c['pattern']]}」時，入位率歷史上{'高' if good else '低'}過模型預測 "
                            f"{abs(c['resid_pp']):.0f}pp（{c['n']} 匹，95% {c['ci'][0]:+.0f}～{c['ci'][1]:+.0f}；前段 {c['early_pp']:+.0f}、後段 {c['late_pp']:+.0f}）。"
                            "歷史統計、未入分（EXP-20261115-20）。"))
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
    data = horse.get("_data") if isinstance(horse.get("_data"), dict) else {}
    prev = (runs[0]["jockey"] if runs else "") or str(data.get("prev_jockey") or "").strip()
    scored = next((a for a in (auto.get("trainer_signal_detail") or {}).get("adjustments") or []
                   if a.get("factor") == "換騎" and a.get("delta")), None)
    if scored:
        label = f"換騎（{prev}→{today}）" if prev and prev != today else f"換騎（今仗 {today}）"
        first = "首次合作" in str(data.get("jockey_change_note") or "")
        why = str(scored.get("evidence") or "") + ("；今仗騎師首次策騎此駒" if first else "")
        return [_tag("jockey_change", label, "bad", why=why, scored=True)]
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
    out += _surface_tags(runs, meta, complete)
    if complete:
        if meta.get("awt") and not any(r["awt"] for r in runs):
            out.append(_tag("first_awt", "初跑泥地", "note", why=f"香港 {len(runs)} 仗從未跑過全天候跑道；未入分。"))
        venue = meta.get("venue")
        if venue and not any(r["venue"] == venue for r in runs):
            name = "沙田" if venue == "ST" else "跑馬地"
            out.append(_tag("first_venue", f"初跑{name}", "note", why=f"香港 {len(runs)} 仗從未喺{name}跑過；未入分。"))
    return out


AWT_TURF_GAP = 0.25               # 泥地／草地上名率相差 ≥ 25 個百分點先出標籤


def _placed(r) -> bool:
    return isinstance(r["placing"], int) and 1 <= r["placing"] <= 3


def _surface_tags(runs: list[dict], meta: dict, complete: bool) -> list[dict]:
    """泥地相對草地、直路 1000 往績（Kelvin 2026-11-16「真訊號但加分唔過 → 做顯示標籤」；EXP-20261114-11：
    兩樣都係模型之上嘅真訊號（holdout 確認），但做成加分喺細樣本過唔到閘，所以**未入分**）。"""
    out = []
    if meta.get("awt"):
        awt = [r for r in runs if r["awt"]]
        turf = [r for r in runs if not r["awt"]]
        if len(awt) >= 2 and len(turf) >= 3:
            ra = sum(map(_placed, awt)) / len(awt)
            rt = sum(map(_placed, turf)) / len(turf)
            detail = f"泥地 {len(awt)} 仗 {sum(map(_placed, awt))} 上名、草地 {len(turf)} 仗 {sum(map(_placed, turf))} 上名"
            why = (f"香港往績：{detail}。歷史回放：泥地相對草地表現係模型之上嘅真訊號（holdout 確認），"
                   "但做成加分過唔到閘；未入分。")
            if ra - rt >= AWT_TURF_GAP:
                out.append(_tag("awt_better", "泥地表現好過草地", "good", why=why))
            elif rt - ra >= AWT_TURF_GAP:
                out.append(_tag("awt_worse", "泥地表現差過草地", "bad", why=why))
    if meta.get("venue") == "ST" and meta.get("distance") == 1000 and not meta.get("awt"):
        straight = [r for r in runs if r["venue"] == "ST" and not r["awt"] and r["distance"] == 1000]
        placed = sum(map(_placed, straight))
        why_tail = "歷史回放：以往直路 1000 表現係模型之上嘅真訊號（holdout 確認），但做成加分過唔到閘；未入分。"
        if placed:
            out.append(_tag("straight_placed", f"直路有上名往績（{len(straight)}戰{placed}上名）", "good",
                            why=f"沙田直路 1000米 {len(straight)} 仗 {placed} 次上名。" + why_tail))
        elif len(straight) >= 2:
            out.append(_tag("straight_unplaced", f"直路{len(straight)}戰未上過名", "bad",
                            why=f"沙田直路 1000米 {len(straight)} 仗未上過名。" + why_tail))
        elif not straight and complete and runs:
            out.append(_tag("first_straight", "初跑直路", "note", why=f"香港 {len(runs)} 仗從未跑過沙田直路 1000米；未入分。"))
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
        # Kelvin 2026-11-16：唔寫「強」—— 分數係按對手後續數據計，唔係標籤寫「強」（EXP-20261114-12）。
        return "賽績線佔優" if good else "賽績線蝕底"
    if key == "class_advantage":
        return "評分與經驗佔優" if good else "評分與經驗蝕底"
    if key == "horse_health":
        return "健康新鮮" if good else "休賽／健康扣分"
    if key == "distance_fit":
        return "同程有上名" if good else "同程未上過名"
    return ""


FOREIGN_CODE_MIN = 800            # HKJC 畀訪港（外隊）馬嘅烙號數字（例如 J816）


def is_foreign(horse: dict) -> bool:
    code = str(horse.get("horse_code") or horse.get("hkjc_horse_id") or "")   # 後備：HK_2025_J816
    m = re.search(r"[A-Z](\d{3})$", code)
    return bool(m and int(m.group(1)) >= FOREIGN_CODE_MIN)


def _foreign_tag(horse: dict) -> list[dict]:
    """外隊馬（Kelvin 2026-11-14 決定 4）：冇本地往績嘅維度用中性 60 —— 標明，唔當差。純顯示，唔郁分。"""
    if not is_foreign(horse):
        return []
    return [_tag("foreign_horse", "外隊馬｜本地資料不足", "note",
                 why="訪港外隊馬冇香港往績：狀態、同程、賽績線、段速等維度用中性 60，唔代表匹馬差。"
                     "回放顯示外隊馬喺同一模型排名入位率高過本地馬（EXP-20261114-07）；未入分。")]


def _debut_trainer_tag(horse: dict, meta: dict) -> list[dict]:
    """初出馬：練馬師初出紀錄（Kelvin 2026-11-14 決定 3；EXP-20261114-06）—— 未入分，forward shadow 觀察緊。"""
    if not (horse.get("is_debut") or horse.get("debut_runner")) or not meta.get("date"):
        return []
    from .debut_trainer import rate
    info = rate(str(horse.get("trainer") or "").strip(), meta["date"])
    if not info or info["starts"] < 5:
        return []
    tone = "good" if info["z"] >= 1 else ("bad" if info["z"] <= -1 else "note")
    return [_tag("debut_trainer", f"練馬師初出馬上名率 {info['rate'] * 100:.0f}%（{info['places']}/{info['starts']}）", tone,
                 why="練馬師之前帶初出馬入頭三嘅比率（收縮向 25%）。回放證實喺模型之上有剩餘（EXP-20261114-06）；"
                     "未入分，forward 觀察緊。")]


def _form_pattern_tags(horse: dict, meta: dict) -> list[dict]:
    """老馬贏後／降班＋評分跌返贏馬分（EXP-20261115-15）：純顯示，forward shadow 觀察緊。"""
    from .form_patterns import flags
    f = flags(horse, meta.get("race_class"), meta.get("date"))
    out = []
    if f["old_won_last"]:
        out.append(_tag("old_won_last", f"老馬贏後（在港 {f['starts']} 仗）", "bad",
                        why="在港 ≥35 仗嘅馬上仗贏咗，下仗入位率歷史上低過模型預測約 10pp（回放 dev −11.2pp、holdout −9.7pp）；"
                            "高班（評分 ≥95／一二班）唔計。未入分，forward 觀察中。"))
    if f["classdrop_rating_back"]:
        out.append(_tag("classdrop_rating_back", f"降班＋評分跌返贏馬分（{f['rating']:.0f} ≤ 上次贏馬 {f['win_rating']:.0f}）", "good",
                        why="今仗降班，而且評分跌返最近一次贏馬時嘅分數或以下；歷史上入位率高過模型預測約 5pp"
                            "（回放 dev、holdout 都 +5.2pp）。未入分，forward 觀察中。"))
    return out


# 檔位 chip（Kelvin 2026-11-17）：以前「檔位走位有利（1檔）」「近仗早段偏前抽內檔」「1檔額外著數」三個 chip 講同一樣嘢。
# 而家：檔位分（race_shape 維度）＋逐檔修正＋跑法×檔位 合成一個「內檔／中檔／外檔 優勢／劣勢」；
# 跑法本身明顯唔夾呢段檔位（同組同檔位段其他跑法平均差 ≥ 1pp）→ 另出扣分位「跑法唔夾檔位」。
_STYLE_WORD_SHORT = {"F": "放頭", "M": "守中", "B": "後上"}
_BAND_WORD = {"I": "內檔", "C": "中檔", "O": "外檔"}
_GROUP_WORD = {"HVS": "跑馬地短途", "HVL": "跑馬地中長途", "STS": "沙田短途", "STL": "沙田中長途",
               "AWTS": "泥地短途", "AWTL": "泥地中長途", "STRS": "沙田直路"}
STYLE_NAME_MIN = 0.01   # 跑法格同同組同檔位段（按樣本加權）平均差 ≥ 1pp 先叫「跑法有關」


def _band(d: int) -> str:
    return "I" if d <= 4 else ("C" if d <= 9 else "O")


def _style_vs_band(det: dict) -> float:
    """跑法格值 − 同組同檔位段 F／M／B 加權平均（比例）；冇資料 = 0。"""
    from .draw_style import frozen
    fz = frozen()
    g, st, band = det.get("group"), det.get("style"), _band(int(det.get("draw") or 0))
    if st not in _STYLE_WORD_SHORT:
        return 0.0
    cells, ns = fz.get("style_cells") or {}, fz.get("style_n") or {}
    keys = [f"{g}|{x}|{band}" for x in "FMB"]
    tot = sum(ns.get(k, 0) for k in keys)
    mean = sum(cells.get(k, 0.0) * ns.get(k, 0) for k in keys) / tot if tot else 0.0
    return cells.get(f"{g}|{st}|{band}", 0.0) - mean


def _draw_tags(horse: dict, auto: dict) -> list[dict]:
    det = auto.get("draw_style_detail") or {}
    try:
        d = int(horse.get("barrier") or horse.get("draw") or det.get("draw") or 0)
    except (TypeError, ValueError):
        d = 0
    if d <= 0:
        return []
    band = _band(d)
    dim = _impact(auto, "race_shape") or 0.0
    style_part, curve_part = float(det.get("style_part") or 0.0), float(det.get("curve_part") or 0.0)
    diff = _style_vs_band(det) if det else 0.0
    style_named = abs(diff) >= STYLE_NAME_MIN and (diff > 0) == (style_part > 0) and abs(style_part) >= DRIVER_FLOOR
    rest = dim + curve_part
    misfit = style_named and style_part < 0 and rest > 0          # 檔位本身有利，但跑法唔夾 → 分開兩個 chip
    total = rest + (0.0 if misfit else style_part)
    rs = auto.get("run_style") or {}
    place = _GROUP_WORD.get(det.get("group"), "呢個場地路程")
    style = _STYLE_WORD_SHORT.get(det.get("style"), "")
    basis = (f"慣性跑法{rs.get('label')}（近 {len(rs.get('runs') or [])} 仗第一個沿途位平均第 {100 * float(rs['habit']):.0f}%、"
             f"{rs.get('same')} 仗同類，{rs.get('consistency')}）。") if rs.get("habit") is not None else ""
    dim_why = _short_reason((auto.get("matrix_reasoning") or {}).get("race_shape"))
    out = []
    if abs(total) >= DRIVER_FLOOR:
        good = total > 0
        named_here = style_named and not misfit and (style_part > 0) == good
        label = f"{_BAND_WORD[band]}{style if named_here else ''}{'優勢' if good else '劣勢'}（{d}檔）"
        why = (f"{dim_why + '。' if dim_why else ''}組成（原始分）：檔位分 {dim:+.1f}、{place} {d} 檔歷史修正 {curve_part:+.1f}"
               + ("" if misfit else f"、跑法×檔位 {style_part:+.1f}") + f"。{basis}"
               + ("呢段檔位對呢個跑法特別有利／不利，所以寫埋跑法名。" if named_here else ""))
        out.append(_tag("draw", label, "good" if good else "bad", why=why, scored=True, impact=round(total, 2)))
    if misfit:
        out.append(_tag("draw_style_misfit", f"跑法唔夾檔位（{style}馬抽{_BAND_WORD[band]}）", "bad", scored=True,
                        impact=round(style_part, 2),
                        why=f"{basis}{place}{style}馬抽{_BAND_WORD[band]}，歷史入位率低過同檔位段其他跑法約 {abs(diff) * 100:.1f}pp"
                            f"（6,000 場回放，檔位×跑法組件）。檔位本身有利，但呢個跑法用唔到。"))
    return out


def _gear_tags(codes: list[str], trainer_pattern_keys: set) -> list[dict]:
    """配備（Kelvin 2026-11-17「有訊號但入唔到分嘅要突出」）。除去配備：歷史入位率高過模型預測約 1pp
    （EXP-20261115-09 +1.10 [+0.40,+1.78]；EXP-20261115-10 對 live +0.8），單項入分 A/B 唔過 → 未入分。
    首次配備：兩次量度 −1.3 同 −0.3，唔穩定 → 只係「留意」。練馬師專屬配備 pattern 已經有 chip 就唔重複。"""
    from . import gear
    out = []
    rem, fst = gear.removed(codes), gear.first(codes)
    if rem and "gear_removed" not in trainer_pattern_keys:
        out.append(_tag("gear_removed", f"除去{'、'.join(gear.name(c) for c in rem)}", "good",
                        why="今仗除去配備。歷史上除去配備嘅馬入位率高過模型預測約 1pp（兩個時段都正），"
                            "但單項入分 A/B 過唔到閘；未入分。"))
    if fst and "gear_first" not in trainer_pattern_keys:
        out.append(_tag("gear_first", f"首次戴{'、'.join(gear.name(c) for c in fst)}", "note",
                        why="今仗首次戴配備。歷史量度方向偏負但唔穩定（−1.3／−0.3pp）；未入分。"))
    return out


def _incident_tag(auto: dict) -> list[dict]:
    """上仗事件報告（EXP-20261116-06，入分）：上仗走外疊冇遮擋（藉口）／上仗醫療事故。"""
    fl = str(auto.get("incident_history_flags") or "")
    delta = float(auto.get("incident_history_delta") or 0.0)
    out = []
    if "W" in fl:
        out.append(_tag("incident_wide", "上仗走外疊冇遮擋", "good", scored=True, impact=round(delta, 2),
                        why="上仗競賽事件報告記錄走外疊、冇遮擋：往績名次差唔代表能力差。歷史上下仗入位率高過模型預測約 2–3pp"
                            "（6,000 場回放 dev／holdout 都改善）。"))
    if "M" in fl:
        out.append(_tag("incident_medical", "上仗醫療事故", "bad", scored=True, impact=round(delta, 2),
                        why="上仗競賽事件報告有喘鳴／流鼻血／心律不正／跛等醫療紀錄。歷史上下仗入位率低過模型預測約 3–4pp。"))
    if "R" in fl:
        out.append(_tag("incident_ride", "上仗騎法被查詢", "good",
                        why="上仗競賽事件報告：競賽小組查詢騎法、騎師交代策騎指示，或者被告誡／未有力策。"
                            "歷史上下仗入位率高過模型預測約 3pp（dev／holdout 都正），但入分過唔到閘；未入分。"))
    if auto.get("incident_wide_two_back"):
        out.append(_tag("incident_wide_two_back", "上上仗走外疊冇遮擋", "good",
                        why="上仗之前嗰場競賽事件報告記錄走外疊、冇遮擋（上仗冇）。歷史上入位率仍然高過模型預測約 2pp"
                            "（dev／holdout 都正、7 季全正），但入分過唔到閘（EXP-20261116-18）；未入分。"))
    return out


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
    covered.add("race_shape")   # 檔位：_draw_tags 一個 chip 講晒（Kelvin 2026-11-17）
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
        gear = load_gear(meeting_dir, meta.get("race_no"))
        extra: dict[str, list] = {}
        for source in (_purton_tags(horses, runs_by_no), _fastest_finisher(horses)):
            for no, items in source.items():
                extra.setdefault(no, []).extend(items)
        for no, h in horses.items():
            extra.setdefault(no, []).extend(_debut_trainer_tag(h, meta) + _foreign_tag(h) + _form_pattern_tags(h, meta)
                                            + _draw_tags(h, h["python_auto"]) + _incident_tag(h["python_auto"])
                                            + _trainer_pattern_tags(h, meta, gear.get(no, [])))
            tp = {t["key"].split(":", 1)[1] for t in extra[no] if t["key"].startswith("trainer_pattern:")}
            extra[no].extend(_gear_tags(gear.get(no, []), tp))
        return {no: horse_tags(no, h, h["python_auto"], runs=runs_by_no.get(no) or [], meta=meta,
                               priority=priorities.get(no, ""), extra=extra.get(no))
                for no, h in horses.items()}
    except Exception as exc:  # 純顯示：出錯就冇標籤，唔可以令評分失敗
        return {"_error": f"{type(exc).__name__}: {exc}"}
