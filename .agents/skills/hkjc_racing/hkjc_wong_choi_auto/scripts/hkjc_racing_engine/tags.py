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
from .distance_move import BIG_MOVE  # 大幅增減程門檻（400 米）只有一份：引擎組件
# 首本路程（EXP-20261118-05，Kelvin 2026-11-18）：同程 ≥2 仗而且上名率 > 2/3。舊門檻（≥3 仗、上名率 ≥40% 或勝率 ≥25%）
# 冇量過；回放只有上名率 >2/3 嗰組實際入頭三多過模型（dev／holdout 都 +3.5pp），34–66%、有贏過都 ≈0。
SPECIALIST_MIN_STARTS = 2
SPECIALIST_PLACE_RATE = 2 / 3
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
        "race_context": ra,
    }


def _segment_figure_tag(horse, meta):
    from . import performance_figure as pf, surface_move
    from .market_history import horse_code
    surface = surface_move.today_surface(meta.get("race_context") or {})
    segment = "awt" if surface == "泥地" else ("straight" if surface == "田草" and meta.get("distance") == 1000 else None)
    if not segment or not meta.get("date"):
        return []
    code = horse_code(horse)
    result = pf.segment_gap(pf.figures_as_of(meta["date"]).get(code), pf.segment_figures(meta["date"])[segment].get(code),
                            pf._weight(horse))
    delta = (horse.get("python_auto") or {}).get("straight_figure_delta") if segment == "straight" else None
    scored = delta is not None
    # 入分係場內置中：gap 細但影響大（或者 gap 正但全場更高、影響負）都要顯示，顏色跟影響方向（Sol 覆核 2026-11-24）。
    if not result or (abs(result["gap"]) < 0.10 and not (scored and abs(float(delta)) >= 0.3)):
        return []
    gap = result["gap"]
    name = "泥地" if segment == "awt" else "直路"
    status = "實驗性入分" if scored else "未入分"
    evidence = ("六季泥地場機率準咗但頭二變差；未入分" if segment == "awt"
                else "六季直路 206 場 Gold +1.94、Good +2.91、頭二 +5，但 CI 跨零；Kelvin 2026-11-24 決定實驗性上線，forward 退回監察")
    return [_tag("segment_figure:" + segment, f"{name}表現{'好' if gap > 0 else '差'}過平時 {abs(gap):.2f} 秒／公里（{status}）",
                 ("good" if float(delta) > 0 else "bad") if scored else ("good" if gap > 0 else "bad"),
                 scored=scored, impact=None if delta is None else round(float(delta), 2),
                 why=f"最近 {result['n']} 仗{name}表現數字（最多 6 仗）減最近 6 仗整體，都換算今仗負磅。EXP-20261123-18：{evidence}。")]


def _head_to_head_tags(horse, horses, meta):
    from datetime import date, timedelta
    import math
    from . import performance_figure as pf
    from .market_history import horse_code
    try:
        today = date.fromisoformat(meta["date"])
        weight = float(horse["weight"])
        km = float(meta["distance"]) / 1000
        if not math.isfinite(weight) or not math.isfinite(km) or km <= 0:
            return []
    except (KeyError, TypeError, ValueError):
        return []
    code = horse_code(horse)
    if not code:
        return []
    rows = pf.load_results()
    if rows is None or rows.empty:
        return []
    past = rows[(rows.date < today.isoformat()) & (rows.date >= (today - timedelta(days=365)).isoformat())]
    mine = past[past.code == code]
    def rank(item):
        no, h = item
        auto = h.get("python_auto") or {}
        return (-float(auto.get("ability_score") or 0), -float(auto.get("ability_score_raw") or 0), int(no) if str(no).isdigit() else 9999)
    out = []
    for no, opponent in sorted(horses.items(), key=rank):
        other_code = horse_code(opponent)
        if not other_code or other_code == code:
            continue
        try:
            other_weight = float(opponent["weight"])
            if not math.isfinite(other_weight):
                continue
        except (KeyError, TypeError, ValueError):
            continue
        common = mine.merge(past[past.code == other_code], on="race", suffixes=("_self", "_other"))
        if common.empty:
            continue
        common = common.sort_values(["date_self", "race"], ascending=False)
        for row in common.itertuples(index=False):
            try:
                t1, t2, w1, w2, old_km = map(float, (row.time_self, row.time_other, row.w_self, row.w_other, row.km_self))
                if not all(map(math.isfinite, (t1, t2, w1, w2, old_km))):
                    continue
            except (TypeError, ValueError):
                continue
            raw = t2 - t1
            adjusted = max(-1.0, min(1.0, raw + pf.BETA_LB * old_km * (w1 - w2) - pf.BETA_LB * km * (weight - other_weight)))
            def wording(v):
                if abs(v) < 0.005:
                    return "平手"
                if abs(v) >= 1.0:   # 換算值截 ±1 秒；原始差距同樣咁寫，唔會出現「輸 3.44、換算輸 1.00」
                    return f"{'贏' if v > 0 else '輸'}超過 1 秒"
                return f"{'贏' if v > 0 else '輸'} {abs(v):.2f} 秒"
            name = opponent.get("horse_name") or str(no) + "號"
            out.append(_tag("head_to_head:" + str(no), f"上次對 {name}：{wording(raw)}；換算今仗負磅 {wording(adjusted)}（未入分）", "note",
                            why="最近一次同場完成時間，按當時及今仗路程與負磅換算，結果截於 ±1 秒。EXP-20261123-08：級際賽交手訊號 β 大好多，全部場頭二 −14；未入分。"))
            break
        if len(out) >= 2:
            break
    return out


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
    today = "泥地" if meta.get("awt") else ("谷草" if meta.get("venue") == "HV" else ("田草" if meta.get("venue") == "ST" else None))
    for c in matches(horse, meta.get("race_class"), meta.get("distance"), gear, today):
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


def _distance_move_tags(auto: dict) -> list[dict]:
    """大幅增減程（≥400 米，EXP-20261117-03）：只讀引擎 distance_move 結果 —— 入咗分就一定有 chip
    （以前放喺 _distance_venue_tags 入面，馬匹頁往績冇載入就提早 return，11-18 有 10 匹扣咗分冇 chip）。"""
    out = []
    mv = auto.get("distance_move") or {}
    prev, dist = mv.get("prev"), mv.get("today")
    if prev and dist and mv.get("up"):
        delta = float(auto.get("distance_move_delta") or 0.0)
        out.append(_tag("distance_up", f"大幅增程（{prev}→{dist}米）", "bad", scored=True, impact=round(delta, 2),
                        why=f"上仗 {prev}米，今仗 {dist}米（增 ≥400 米）。歷史上大幅增程嘅馬入位率低過模型預測約 2pp，"
                            "短途（≤1200）轉一哩以上更明顯（約 −4～−6pp）；6,000 場回放 dev／holdout 都改善（EXP-20261117-03）。"))
    elif prev and dist and mv.get("home"):
        delta = float(auto.get("distance_move_delta") or 0.0)
        out.append(_tag("distance_up_home", f"大幅增程但返首本（{prev}→{dist}米，唔扣）", "note", scored=True, impact=round(delta, 2),
                        why=f"上仗 {prev}米，今仗 {dist}米（增 ≥400 米），但以前喺今仗路程 ±100 米上過名、或者上上仗／再前一仗跑過呢個路程，"
                            "所以唔當大幅增程扣分（只剩全場置中嘅細微影響）。回放 1,121 匹次：唔扣唔會變差（頭二入頭三 +2／+1，EXP-20261124-08）。"))
    elif prev and dist and prev - dist >= BIG_MOVE:
        out.append(_tag("distance_down", f"大幅減程（{prev}→{dist}米）", "note",
                        why=f"上仗 {prev}米，今仗 {dist}米（減 ≥400 米）。歷史上冇穩定加減（dev +1.5、holdout −0.2pp）；未入分。"))
    return out


_CN_CLASS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5}


def _class_no(text) -> int | None:
    """班次 → 數字（同回放 features.num 一樣：取第一個數字；中文「第四班」→ 4）。"""
    t = str(text or "")
    m = re.search(r"第([一二三四五])班", t)
    if m:
        return _CN_CLASS[m.group(1)]
    m = re.search(r"\d+", t)
    return int(m.group()) if m else None


def _hist(horse: dict) -> list[dict]:
    data = horse.get("_data") if isinstance(horse.get("_data"), dict) else {}
    return [h for h in (data.get("hk_history") or []) if isinstance(h, dict)]


def _surface_move_tags(horse: dict, auto: dict) -> list[dict]:
    """轉場（EXP-20261117-06）：入分嘅四種寫埋影響；其他方向按回放殘差顯示（未入分）。"""
    from .surface_move import BETA, LABEL, SURFACE_NAME
    out = []
    mv = auto.get("surface_move") or {}
    parts = [LABEL[k] for k in BETA if mv.get(k)]
    if parts:
        delta = float(auto.get("surface_move_delta") or 0.0)
        out.append(_tag("surface_move", "、".join(parts), "good" if delta > 0 else "bad", scored=True, impact=round(delta, 2),
                        why="轉場（6,000 場回放）：跑馬地轉沙田草地入位率低過模型約 5pp（7 季全負）、沙田草地轉跑馬地高約 3pp、"
                            "初次沙田草地約 −5～−7pp、初次泥地約 −3pp；dev／holdout 都改善（EXP-20261117-06）。"))
    hist = _hist(horse)
    today = mv.get("today")
    if not hist or not today:
        return out
    prev = hist[0].get("surface")
    unscored = {("谷草", "泥地"): ("bad", "dev −1.4、holdout −3.5pp"), ("泥地", "田草"): ("bad", "dev −3.0、holdout −2.0pp"),
                ("泥地", "谷草"): ("good", "dev +3.1、holdout +0.7pp"), ("田草", "泥地"): ("note", "dev +1.6、holdout +0.1pp，冇訊號")}
    if (prev, today) in unscored and not parts:
        tone, nums = unscored[(prev, today)]
        out.append(_tag("surface_move_info", f"{SURFACE_NAME[prev]}轉{SURFACE_NAME[today]}", tone,
                        why=f"上仗{SURFACE_NAME[prev]}、今仗{SURFACE_NAME[today]}。回放殘差 {nums}；入分 A/B 冇包呢個方向，未入分。"))
    if today == "谷草" and not any(h.get("surface") == "谷草" for h in hist):
        out.append(_tag("first_hv", "初次跑馬地", "note", why="香港往績從未跑過跑馬地；回放殘差 dev +0.9、holdout +0.4pp，冇訊號。未入分。"))
    return out


def _same_distance_venue_tags(auto: dict) -> list[dict]:
    """同程上名要同場地（EXP-20261119-01）：同程上名全部喺另一場地 → 一個 chip 講晒（連 distance_fit 嗰 +0.43）。"""
    from .venue_distance import label
    info = auto.get("same_distance_venue") or {}
    if not info.get("on"):
        return []
    delta = float(auto.get("same_distance_venue_delta") or 0.0)
    return [_tag("same_distance_venue", label(info, info.get("distance")), "bad", scored=True, impact=round(delta, 2),
                 why=f"今仗路程上過 {info.get('n')} 次名，但冇一次喺今仗場地。「同程有上名」+0.43 照計，"
                     "另外再扣：沙田直路 1000 同谷草彎路 1000（或者兩邊 1200）唔係同一件事。6,000 場回放，"
                     "呢類馬入頭三少過模型估計 dev 2.7pp、holdout 4.6pp；修正後兩個窗都改善（EXP-20261119-01）。")]


def _horse_age_tag(auto: dict) -> list[dict]:
    """馬齡（EXP-20261119-01）：7 歲或以上先出 chip（6 歲或以下全部一樣 = 中性）。"""
    info = auto.get("horse_age") or {}
    if not info.get("years_over"):
        return []
    delta = float(auto.get("horse_age_delta") or 0.0)
    return [_tag("horse_age", f"{info['age']} 歲", "bad" if delta < 0 else "note", scored=True, impact=round(delta, 2),
                 why=f"6 歲之後每大一歲扣 0.37 原始分（{info['age']} 歲 = 扣 {0.37 * info['years_over']:.2f}，再同全場平均比）。"
                     "回放：8 歲以上入頭三少過模型估計約 1.5–2pp；入分後機率準咗（dev／holdout log-loss 都改善），"
                     "但排名指標冇升（EXP-20261119-01）。")]


def _excuse_streak_tag(auto: dict) -> list[dict]:
    """連續兩仗有藉口（EXP-20261119-06 X1，實驗性上線）：一個 chip，組成（邊兩仗、咩藉口、名次）寫喺 tooltip。"""
    info = auto.get("excuse_streak") or {}
    if not info:
        return []
    name = {"B": "受阻", "W": "走外疊", "R": "騎法被質疑"}
    parts = [f"{d[5:]} 第{p}名（{'、'.join(name[c] for c in 'BWR' if c in (f or ''))}）"
             for d, f, p in zip(info.get("dates", []), info.get("flags", []), info.get("placings", []))]
    delta = float(auto.get("excuse_streak_delta") or 0.0)
    return [_tag("excuse_streak", "連續兩仗有藉口", "good" if delta > 0 else "note", scored=True, impact=round(delta, 2),
                 why=f"上兩仗：{'；'.join(parts)}。兩仗都有事件報告藉口而且都跑唔入位，近績扣得太盡。"
                     "回放：呢類馬入頭三多過模型估計 dev 3.8pp、holdout 4.2pp（7 季全正）。"
                     "⚠️ 實驗性上線、未證實改善（改善嘅係機率準度、唔係排名；EXP-20261119-06）。")]


def _thin_evidence_tag(auto: dict) -> list[dict]:
    """薄證據收窄（EXP-20261119-05，實驗性上線）：一個 chip 講晒仗數、休幾耐、郁咗幾多。"""
    info = auto.get("thin_evidence") or {}
    if not info:
        return []
    delta = float(auto.get("thin_evidence_delta") or 0.0)
    return [_tag("thin_evidence", f"證據薄：香港 {info['starts']} 仗、休 {info['gap']} 日", "bad" if delta < 0 else "note",
                 scored=True, impact=round(delta, 2),
                 why="香港得 1–2 仗又休咗半年以上，綜合分向全場平均收窄一半（高分跌、低分升，唔係扣分）。"
                     "歷史同類馬（本地 116 匹）模型排頭 2 嘅入位 29%、模型估 55%；排 3–5 就準（33%／28%）。"
                     "⚠️ 實驗性上線、未證實改善（回放樣本太少，把尺量唔到；EXP-20261119-05）。")]


def _performance_figure_tag(auto: dict) -> list[dict]:
    """表現數字取代段速（EXP-20261123-10）：一個 chip，數字同組成（扣走段速幾多、加表現數字幾多）寫喺 tooltip。"""
    info = auto.get("performance_figure") or {}
    if not info:
        return []
    delta = float(auto.get("performance_figure_delta") or 0.0)
    fig, mu = info.get("figure"), info.get("field_mean")
    if fig is None or mu is None:
        label, tone = "表現數字：往績不足", "note"
        detail = "近 6 仗少過 2 仗有完成時間，用全場平均（再按回放扣少少）。"
    else:
        gap = fig - mu
        label = f"表現數字：{'快' if gap >= 0 else '慢'}過全場平均 {abs(gap):.2f} 秒／公里"
        tone = "good" if gap >= 0.05 else "bad" if gap <= -0.05 else "note"
        detail = f"表現數字 {fig:+.3f}（全場平均 {mu:+.3f}）。"
    return [_tag("performance_figure", label, tone, scored=True, impact=round(delta, 2),
                 why=detail + "表現數字 = 近 6 仗每公里時間，扣走嗰場賽事本身快慢，再按今仗負磅換算（每磅 0.0094 秒／公里），"
                     "越近嗰仗越重。佢取代咗段速分（輸頭馬差距、能量、L400 走勢、前段對標準一級級跳嘅標籤）："
                     f"扣走段速 {float(info.get('sectional_removed') or 0):+.2f}、加表現數字 {float(info.get('figure_added') or 0):+.2f}。"
                     "6,047 場回放：dev／holdout log-loss 都改善，頭二入頭三 +19／+3（EXP-20261123-10）。")]


def _class_move_tags(horse: dict, meta: dict) -> list[dict]:
    """Kelvin 2026-11-17（EXP-20261117-06）：初落班＋同程上過名、升班輕磅（上仗未贏）。都未入分。"""
    hist = _hist(horse)
    today = _class_no(meta.get("race_class"))
    if not hist or today is None:
        return []
    last = _class_no(hist[0].get("class"))
    dist = meta.get("distance")
    out = []
    if last is not None and today > last and not any(_class_no(h.get("class")) == today for h in hist):
        placed = [h for h in hist if h.get("distance") == dist and isinstance(h.get("placing"), int) and 1 <= h["placing"] <= 3]
        if placed:
            out.append(_tag("first_drop_placed", f"初落第{today}班＋{dist}米上過名（{len(placed)}次）", "good",
                            why="第一次落到呢個班次，而且喺今仗路程上過名。回放殘差 dev +7.8、holdout +6.2pp（7 季 6 季正），"
                                "但罕有，入分 A/B CI 上界啱啱到 0 → 未入分（EXP-20261117-06）。"))
    try:
        w = int(str(horse.get("weight") or "0").split(".")[0])
    except ValueError:
        w = 0
    if last is not None and today < last and hist[0].get("placing") != 1 and 0 < w <= 118:
        out.append(_tag("class_up_light", f"升班輕磅（{w}磅、上仗未贏）", "good",
                        why="升班但唔係因為上仗贏咗即升，今仗負磅 ≤118。回放殘差 dev +3.3、holdout +1.2pp（同方向、holdout 唔顯著）；未入分。"))
    return out


def _age_weight_tag(horse: dict) -> list[dict]:
    data = horse.get("_data") if isinstance(horse.get("_data"), dict) else {}
    try:
        age, w = int(data.get("age") or 0), int(str(horse.get("weight") or "0").split(".")[0])
    except ValueError:
        return []
    if age == 3 and w >= 133:
        return [_tag("young_top_weight", f"3 歲負 {w} 磅", "note",
                     why="3 歲馬負頂磅。回放（只有現役馬有馬齡）dev +2.1、holdout −1.8pp，樣本細、冇訊號；未入分。")]
    return []


def jockey_work(horse: dict) -> dict:
    """今仗騎師近 21 日親自快操／試閘課數 —— 讀抽取層 `extract_trackwork.race_jockey_work` 寫入晨操摘要嘅結果（唯一定義）。
    舊晨操檔冇呢兩欄 = 0（唔扮有）。"""
    tw = horse.get("trackwork") if isinstance(horse.get("trackwork"), dict) else {}
    sm = tw.get("summary") if isinstance(tw.get("summary"), dict) else {}
    def n(key):
        try:
            return max(0, int(sm.get(key) or 0))
        except (TypeError, ValueError):
            return 0
    return {"gallops": n("race_jockey_gallops_21d"), "trials": n("race_jockey_trials_21d")}


def trainer_work(horse: dict) -> dict:
    """練馬師近 21 日親自快操／試閘課數 —— 讀抽取層 `extract_trackwork.trainer_work` 寫入晨操摘要嘅結果（唯一定義）。
    舊晨操檔冇呢兩欄 = 0（唔扮有）。"""
    tw = horse.get("trackwork") if isinstance(horse.get("trackwork"), dict) else {}
    sm = tw.get("summary") if isinstance(tw.get("summary"), dict) else {}
    def n(key):
        try:
            return max(0, int(sm.get(key) or 0))
        except (TypeError, ValueError):
            return 0
    return {"gallops": n("trainer_gallops_21d"), "trials": n("trainer_trials_21d")}


def _trainer_work_tag(horse: dict) -> list[dict]:
    """練馬師近 21 日親自快操／試閘（Kelvin 2026-11-21；未入分）。

    量度（EXP-20261121-41，重抓 1,232 匹馬晨操頁，2026-05 → 11-18 共 4,175 次出賽）：練馬師親自操只有 51 次（1.2%），
    差唔多全部係韋達同廖康銘嘅馬。按賠率調整後上名率 +2.7pp [−8.3, +14.9]、按模型排名 +2.1pp [−10.3, +15.3]；
    「上仗至今」窗口 −1.4pp。CI 闊、冇訊號 → 放「留意」，唔放加分位。"""
    work = trainer_work(horse)
    if not (work["gallops"] or work["trials"]):
        return []
    trainer = str(horse.get("trainer") or "").strip() or "練馬師"
    parts = ([f"快操 {work['gallops']} 課"] if work["gallops"] else []) + ([f"試閘 {work['trials']} 次"] if work["trials"] else [])
    return [_tag("trainer_work", f"練馬師{trainer}親自{'＋'.join(parts)}", "note",
                 why=f"近 21 日晨操紀錄：練馬師{trainer}親自策騎{'、'.join(parts)}（唔計比賽）。"
                     "量過 51 次（主要係韋達、廖康銘嘅馬）：按賠率調整後上名率 +2.7pp，但 95% CI −8.3 至 +14.9，"
                     "即係冇訊號；未入分。")]


def _race_people_tags(horses: dict, meta: dict) -> dict:
    """同場騎師揀馬／同馬房正選次選／下游騎師入位後轉潘頓／今仗騎師親自快操試閘（EXP-20261117-06、Kelvin 2026-11-19；全部未入分）。"""
    from .live_priors import get_jt_ratings
    out: dict[str, list] = {}
    jock = {str(h.get("jockey") or "").strip(): no for no, h in horses.items() if str(h.get("jockey") or "").strip()}
    try:
        jt = get_jt_ratings(meta.get("date"))
    except Exception:
        jt = None

    def wr(name):
        row = jt.lookup("jockey", name) if jt is not None else None
        return float(row.get("win_rate") or 0) if row else None
    for no, h in horses.items():
        hist = _hist(h)
        today_j = str(h.get("jockey") or "").strip()
        last3 = [x.get("jockey") for x in hist[:3]]
        if len(last3) == 3 and len(set(last3)) == 1 and last3[0] and last3[0] != today_j and last3[0] in jock \
                and last3[0] != "潘頓":
            other = jock[last3[0]]
            out.setdefault(no, []).append(_tag("regular_jockey_left", f"常騎騎師{last3[0]}今場騎 {other} 號", "bad",
                                               why=f"近三仗都係{last3[0]}騎，今場佢同場揀咗 {other} 號。回放殘差 dev −3.5、holdout −0.7pp"
                                                   "（同方向、holdout 唔顯著）；未入分。"))
            out.setdefault(other, []).append(_tag("regular_jockey_chose", f"{last3[0]}棄 {no} 號揀呢匹", "note",
                                                  why=f"{last3[0]}近三仗都騎 {no} 號，今場轉騎呢匹。留意；未入分。"))
        work = jockey_work(h)
        downtier = None
        place = hist[0].get("placing") if hist else None
        if isinstance(place, int) and 1 <= place <= 3 and today_j == PURTON:
            lj = hist[0].get("jockey") or ""
            rate = wr(lj)
            if lj and lj != PURTON and rate is not None and rate < 8.0:
                downtier = (lj, rate, place)
        if downtier and work["gallops"] and work["trials"]:
            # 一樣嘢一個 chip（Kelvin 2026-11-16）：接手＋親自操＋試閘合成一個，組成寫喺 tooltip
            lj, rate, place = downtier
            out.setdefault(no, []).append(_tag(
                "purton_takeover_full_prep", f"潘頓接手{lj}匹馬＋親自快操＋試閘", "good",
                why=f"上仗{lj}（勝率 {rate:.1f}%）騎跑第 {place}；今仗潘頓接手，而且近 21 日親自快操 {work['gallops']} 課、"
                    f"試閘 {work['trials']} 次。Kelvin：潘頓搶下游騎師跑得好嘅馬兼親自做齊操練，通常係大訊號。"
                    "未量度、未入分（純顯示）。"))
        elif downtier:
            lj, rate, place = downtier
            out.setdefault(no, []).append(_tag("downtier_win_purton", f"上仗{lj}{'贏' if place == 1 else f'跑第{place}'}、今仗轉潘頓",
                                               "note",
                                               why=f"上仗由{lj}（勝率 {rate:.1f}%）策騎跑第 {place}，今仗潘頓接手。"
                                                   "只計上仗贏嘅版本回放樣本太少（n 27／15）量唔到；入位版未量度；未入分。"))
        # 快操 1 課係例行（11-18 跑馬地 108 匹有 41 匹）→ 要快操 ≥2 課或者有試閘先出
        if (work["gallops"] >= 2 or work["trials"]) and not (downtier and work["gallops"] and work["trials"]):
            parts = ([f"快操 {work['gallops']} 課"] if work["gallops"] else []) + ([f"試閘 {work['trials']} 次"] if work["trials"] else [])
            out.setdefault(no, []).append(_tag(
                "race_jockey_work", f"{today_j}親自{'＋'.join(parts)}", "good",   # Kelvin 2026-11-19：放加分位（虛線 = 未入分）
                why=f"近 21 日晨操紀錄：今仗騎師{today_j}親自策騎{'、'.join(parts)}（唔計比賽）。"
                    "騎師親自操＋試閘通常代表有部署；未量度、未入分（純顯示）。"))
    stables: dict[str, list] = {}
    for no, h in horses.items():
        t = str(h.get("trainer") or "").strip()
        if t:
            stables.setdefault(t, []).append(no)
    for t, nos in stables.items():
        if len(nos) < 2:
            continue
        ranked = sorted(nos, key=lambda n: -(wr(str(horses[n].get("jockey") or "").strip()) or 0))
        for i, no in enumerate(ranked):
            rate = wr(str(horses[no].get("jockey") or "").strip())
            out.setdefault(no, []).append(_tag("stable_choice", f"同馬房 {len(nos)} 匹：{'正選' if i == 0 else '次選'}", "note",
                                               why=f"{t}今場出 {len(nos)} 匹（{'、'.join(f'{n} 號' for n in ranked)}）；正選 = 騎師勝率最高"
                                                   f"（呢匹騎師勝率 {rate if rate is not None else 0:.1f}%）。回放：正選 dev +2.1、holdout −0.3pp，冇訊號；未入分。"))
    return out


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
        if len(same) >= SPECIALIST_MIN_STARTS and places / len(same) > SPECIALIST_PLACE_RATE:
            impact = _impact(auto, "distance_fit")
            out.append(_tag("specialist", f"首本路程（{dist}米 {len(same)}戰{wins}勝{places}上名）", "good",
                            why=f"香港 {dist}米 {len(same)} 仗 {wins} 勝、{places} 次上名（上名率 > 2/3）。"
                                "「同程有上名」已入分（同 1 次上名一樣）；上名率咁高嘅馬，回放實際入頭三仲多過模型預測約 3.5pp"
                                "（dev／holdout 都過零），但加大入分 A/B 令 Good 跌 → 額外部分未入分（EXP-20261118-05）。",
                            scored=bool(impact and impact > 0), impact=impact))
        elif not same and complete:
            out.append(_tag("first_distance", f"初跑{dist}米", "note",
                            why=f"香港 {len(runs)} 仗從未跑過 {dist}米；未入分。"))
    out += _surface_tags(runs, meta, complete)
    # 初次泥地／沙田草地／跑馬地 由 _surface_move_tags 出（同轉場組件同一份往績；EXP-20261117-06）
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
        # 呢個維度睇近 6 仗（名次＋輸距），所以標籤印 6 仗；以前只印近 3 仗，會出「近績好（近3仗 4-5-9）」咁矛盾（Kelvin 2026-11-26，天下寵兒）。
        form = [x.strip() for x in re.split(r"[-/]", str(horse.get("last_6_finishes") or "")) if x.strip().isdigit()][:6]
        label = "狀態穩定" if good else "狀態欠穩定"
        if len(form) == 6:
            recent, older = (sum(int(x) for x in form[:3]) / 3, sum(int(x) for x in form[3:]) / 3)
            if good and recent - older >= 2:
                label += "但近三仗回落"
            elif not good and older - recent >= 2:
                label += "但近三仗回升"
        return label + (f"（近{len(form)}仗 {'-'.join(form)}）" if form else "")
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


def _trial_time_tag(horse, meta):
    from . import debut_trainer
    if not debut_trainer.is_debut(horse):
        return []
    auto = horse.get("python_auto") or {}
    scored = "trial_time_delta" in auto
    if not scored and "trial_time_shadow_delta" not in auto:
        return []
    info = auto.get("trial_time")
    if not info:
        return [_tag("trial_time", "未有試閘紀錄", "note")]
    tf = info.get("tf")
    if tf is None:
        return [_tag("trial_time", "試閘：未有標準時間", "note")]
    delta = auto.get("trial_time_delta") if scored else auto.get("trial_time_shadow_delta")
    tone = "good" if delta is not None and delta > 0 else "bad" if delta is not None and delta < 0 else "note"
    direction = "快過" if tf >= 0 else "慢過"
    label = f"試閘時間：{direction}標準 {abs(tf):.2f} 秒／公里（{info['date'][5:]} {info['track']} {info['dist']}米）"
    if not scored:
        label += " · 未入分"
    why = (f"實驗性入分；調整 {delta:+.2f}" if scored else
           f"未入分（forward 紙上測試 EXP-20261124-17）；如果入分會調整 {delta:+.2f}")
    return [_tag("trial_time", label, tone, scored=scored,
                 impact=round(delta, 2) if scored and delta is not None else None, why=why)]


def _debut_trainer_tag(horse: dict, meta: dict) -> list[dict]:
    """初出馬：練馬師初出紀錄（EXP-20261123-13 入分；Kelvin 2026-11-23 上線）。一個 chip，影響寫喺 impact。"""
    if not (horse.get("is_debut") or horse.get("debut_runner")) or not meta.get("date"):
        return []
    auto = horse.get("python_auto") or {}
    delta = auto.get("debut_trainer_delta")
    from .debut_trainer import rate
    info = rate(str(horse.get("trainer") or "").strip(), meta["date"])
    if not info:
        return []
    if info["starts"] < 5 and (delta is None or abs(float(delta)) < 0.3):
        return []
    tone = "good" if info["z"] >= 1 else ("bad" if info["z"] <= -1 else "note")
    return [_tag("debut_trainer", f"練馬師初出馬上名率 {info['rate'] * 100:.0f}%（{info['places']}/{info['starts']}）", tone,
                 scored=delta is not None, impact=None if delta is None else round(float(delta), 2),
                 why="練馬師之前帶初出馬入頭三嘅比率（收縮向 25%：初出馬少嘅練馬師會靠近 25%）。已入分：每高 1 個標準差（7pp）"
                     "加 1.88 原始分，再同全場比。6,047 場回放：dev／holdout log-loss 都改善，六季有初出馬嘅場 AUC +0.0021"
                     "（EXP-20261123-13）。")]


def _form_pattern_tags(horse: dict, meta: dict) -> list[dict]:
    """老馬贏後／降班＋評分跌返贏馬分（EXP-20261115-15）：純顯示，forward shadow 觀察緊。"""
    from .form_patterns import flags
    f = flags(horse, meta.get("race_class"), meta.get("date"))
    out = []
    if f["old_won_last"]:
        out.append(_tag("old_won_last", f"老馬贏後（在港 {f['starts']} 仗）", "bad",
                        why="在港 ≥35 仗嘅馬上仗贏咗，下仗入位率歷史上低過模型預測約 10pp（回放 dev −11.2pp、holdout −9.7pp）；"
                            "高班（評分 ≥95／一二班）唔計。未入分，forward 觀察中。"))
    if f.get("rating_near_win"):
        r, w = f["rating"], f["win_rating"]
        label = f"評分跌返贏馬分（{r:.0f} ≤ 上次贏馬 {w:.0f}）" if r <= w else f"評分接近贏馬分（{r:.0f}，上次贏馬 {w:.0f}）"
        out.append(_tag("rating_near_win", label, "note",
                        why="今仗評分跌返或者接近（高 ≤2 分）最近一次贏馬時嘅評分。歷史：2020–23 入位率高過模型約 2pp，"
                            "但 2024 起冇咗（holdout −0.3pp）；上仗入位＋跌返 dev +4.3／holdout +1.8pp 未確認；"
                            "同降班一齊先穩定（另一個標籤）。未入分（EXP-20261117-02）。"))
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


def _draw_tags(horse: dict, auto: dict, field_dim_mean: float = 0.0) -> list[dict]:
    """field_dim_mean：全場檔位分影響（原始尺）平均。排名只睇同場比較，所以檔位分要對全場平均先講優／劣勢——
    以前對固定中心 63 計，令「檔位中性」嘅中檔馬都出「劣勢」（Kelvin 2026-11-22）。逐檔修正、跑法×檔位本身已場內置中。"""
    det = auto.get("draw_style_detail") or {}
    try:
        d = int(horse.get("barrier") or horse.get("draw") or det.get("draw") or 0)
    except (TypeError, ValueError):
        d = 0
    if d <= 0:
        return []
    band = _band(d)
    dim = (_impact(auto, "race_shape") or 0.0) - field_dim_mean
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
        why = (f"{dim_why + '。' if dim_why else ''}組成（原始分，對全場平均）：檔位分 {dim:+.1f}、{place} {d} 檔歷史修正 {curve_part:+.1f}"
               + ("" if misfit else f"、跑法×檔位 {style_part:+.1f}") + f"。{basis}"
               + ("呢段檔位對呢個跑法特別有利／不利，所以寫埋跑法名。" if named_here else ""))
        out.append(_tag("draw", label, "good" if good else "bad", why=why, scored=True, impact=round(total, 2)))
    if misfit:
        out.append(_tag("draw_style_misfit", f"跑法唔夾檔位（{style}馬抽{_BAND_WORD[band]}）", "bad", scored=True,
                        impact=round(style_part, 2),
                        why=f"{basis}{place}{style}馬抽{_BAND_WORD[band]}，歷史入位率低過同檔位段其他跑法約 {abs(diff) * 100:.1f}pp"
                            f"（6,000 場回放，檔位×跑法組件）。檔位本身有利，但呢個跑法用唔到。"))
    return out


def _next_entry_tag(horse: dict) -> list[dict]:
    """Kelvin 2026-11-17「報咗一個禮拜內嘅比賽，今仗會唔會係熱身？」（EXP-20261117-04）：純顯示＋forward。"""
    data = horse.get("_data") if isinstance(horse.get("_data"), dict) else {}
    e = data.get("next_entry")
    if not isinstance(e, dict) or not e.get("date"):
        return []
    md = str(e["date"])[5:].replace("-", "/")
    detail = "、".join(str(x) for x in (e.get("class") and f"{e['class']}班" if str(e.get("class")).isdigit() else e.get("class"),
                                         e.get("distance") and f"{e['distance']}米") if x)
    return [_tag("next_entry", f"已報 {md} {e.get('venue') or ''}（{e.get('days')} 日後）", "note",
                 why=f"今仗開跑前已經報咗 {e['date']} {e.get('venue') or ''} 第 {e.get('race')} 場（{detail}）。"
                     "歷史上一星期內再出嘅馬，今仗入位率低過模型約 2.5–2.8pp（似熱身）；但嗰個係用事後出賽量，"
                     "「賽前已報」版本 forward 測試緊。未入分。")]


QUICK_BACKUP_DAYS = 10


def _backup_tag(auto: dict) -> list[dict]:
    """Kelvin 2026-11-17「七日匆匆再出／密集出賽要唔要扣分」：回放（EXP-20261117-02）≤7 日 +0.9／+0.3pp、8–10 日 +2.2／+1.2pp、
    近 60 日 ≥3 仗 +1.2／−0.1pp —— 冇一致方向，模型已經處理；只係留意。"""
    days = auto.get("days_since_last")
    if not isinstance(days, (int, float)) or days <= 0 or days > QUICK_BACKUP_DAYS:
        return []
    return [_tag("quick_backup", f"相隔 {int(days)} 日再出", "note",
                 why="上仗之後好快再出。歷史上匆匆再出／密集出賽冇穩定加或扣（回放 dev／holdout 方向唔一致），模型已經處理；未入分。")]


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
               priority: str = "", extra: list | None = None, horses: dict | None = None) -> dict:
    special = _trainer_tags(auto) + _jockey_change_tag(horse, auto, runs) + _distance_venue_tags(horse, auto, runs, meta) + _distance_move_tags(auto)
    special += _surface_move_tags(horse, auto) + _class_move_tags(horse, meta) + _age_weight_tag(horse)
    venue = _same_distance_venue_tags(auto)
    if venue:   # 同一件事（同程）只出一個 chip：場地 chip 已講晒 distance_fit
        special = [t for t in special if t["key"] != "specialist"]
    special += venue + _horse_age_tag(auto) + _excuse_streak_tag(auto) + _thin_evidence_tag(auto) + _trainer_work_tag(horse) + _performance_figure_tag(auto)
    special += extra or []
    special += _segment_figure_tag(horse, meta) + _head_to_head_tags(horse, horses or {}, meta)
    if "+" in str(priority or ""):
        special.append(_tag("trainer_ace", "練馬師王牌", "note",
                            why="排位表「優先參賽次序」標 +（練馬師用王牌確保出賽）。"
                                "量過：市場已經計晒，模型排名後只多約 2pp；未入分。"))
    covered = set()
    if any(t["key"].startswith("trainer:") or t["key"] == "jockey_change" for t in special):
        covered.add("trainer_signal")   # 騎練訊號已由具體加減項講晒
    if any(t["key"] in ("specialist", "first_distance", "same_distance_venue") for t in special):
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
        for source in (_purton_tags(horses, runs_by_no), _fastest_finisher(horses), _race_people_tags(horses, meta)):
            for no, items in source.items():
                extra.setdefault(no, []).extend(items)
        dims = [_impact(h["python_auto"], "race_shape") for h in horses.values()]
        dims = [x for x in dims if x is not None]
        field_dim_mean = sum(dims) / len(dims) if len(dims) >= 2 else 0.0   # 得一匹（測試）= 冇對手可比
        for no, h in horses.items():
            extra.setdefault(no, []).extend(_debut_trainer_tag(h, meta) + _trial_time_tag(h, meta) + _foreign_tag(h) + _form_pattern_tags(h, meta)
                                            + _draw_tags(h, h["python_auto"], field_dim_mean) + _incident_tag(h["python_auto"])
                                            + _trainer_pattern_tags(h, meta, gear.get(no, [])))
            tp = {t["key"].split(":", 1)[1] for t in extra[no] if t["key"].startswith("trainer_pattern:")}
            extra[no].extend(_gear_tags(gear.get(no, []), tp) + _backup_tag(h["python_auto"]) + _next_entry_tag(h))
        return {no: horse_tags(no, h, h["python_auto"], runs=runs_by_no.get(no) or [], meta=meta,
                               priority=priorities.get(no, ""), extra=extra.get(no), horses=horses)
                for no, h in horses.items()}
    except Exception as exc:  # 純顯示：出錯就冇標籤，唔可以令評分失敗
        return {"_error": f"{type(exc).__name__}: {exc}"}
