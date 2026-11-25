#!/usr/bin/env python3
"""每日自動覆盤（自學循環 L1，Kelvin 2026-11-26；設計 docs/plans/2026-11-26-self-learning-loop.md）。

照 11-18 跑馬地人手覆盤嘅做法，每個賽日自動出一份：
  1. **對市場**：模型頭三入前三 vs 市場（SP 頭三）、首選贏 vs 大熱贏、頭馬喺模型頭五。
  2. **失手分類**：直接讀 `Miss_Autopsy.json`（輸入有問題／擠迫／市場都估唔中／模型判錯）同 Gold／Good 標籤。
  3. **逐場表**：被低估（入前三、模型 ≥4）同被高估（模型頭三、唔入前三）嘅馬，附「邊個維度推高／拉低」——
     直接用 Logic `python_auto.tags`（同 dashboard chip 同一份，`impact` = 對綜合分嘅貢獻），唔另計。
  4. **跨日核實（描述，唔係判決）**：今日嘅組別（tag／備戰階段／相隔日數／模型獨家睇好）喺之前 N 個 live 賽日
     嘅模型殘差（實際 − 賽前校準機率）同市場殘差（實際 − 去水市場機率），按賽日 cluster bootstrap 95% CI。
     **唔會**據此改模型；篩選／判決係 L3／L4 嘅事（每季、Holm、預先登記 forward）。
  5. **核數**：每個場次應有幾多場（有賽果）、用到幾多場、冇用嘅原因；有缺就喺報告頂寫明。

機率：`model_probability.walk_forward`（每個賽日只用之前賽日 fit），同校準板同一條公式；市場 = SP（HKJC 最終獨贏）
`devig.power` 去水，入頭三用 `market_ruler.harville_top3`。賠率只做賽後評估，唔入模型。

輸出：`<WongChoiControl>/reviews/<platform>/<date>.json`＋`.md`。

    python3 post_review.py --platform au --date 2026-11-25 [--trail-days 20] [--telegram]
"""
from __future__ import annotations

import argparse
import json
import math
import re
import os
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import date as Date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SHARED = HERE.parent
REPO = HERE.parents[3]
for _p in (str(HERE), str(SHARED), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import model_probability as M  # noqa: E402

VERSION = "post-review-v1"
TRAIL_DAYS = {"au": 20, "hkjc": 10}
BOOT = 1000
MIN_COHORT_N = 30          # 跨日樣本少過呢個唔報 CI
TODAY_MIN_N = 4            # 今日組別最少幾匹先列


# ---------------------------------------------------------------- 讀數

def _core():
    return M._core()


def _logic_horses(analysis_dir: Path, race_num: int) -> dict[int, dict]:
    p = Path(analysis_dir) / f"Race_{race_num}_Logic.json"
    if not p.exists():
        return {}
    out = {}
    for key, h in (json.loads(p.read_text(encoding="utf-8")).get("horses") or {}).items():
        try:
            n = int(float(h.get("horse_number") or key))
        except (TypeError, ValueError):
            continue
        out[n] = h
    return out


def _tags(pa: dict) -> list[dict]:
    """AU：python_auto.tags；HKJC：python_auto.summary.tags（同 dashboard chip 同一份）。"""
    t = pa.get("tags") or (pa.get("summary") or {}).get("tags") or {}
    rows = []
    for tone in ("good", "bad", "note", "info"):
        for x in t.get(tone) or []:
            if isinstance(x, dict) and x.get("key"):
                rows.append({"key": x["key"], "label": x.get("label") or x["key"], "tone": tone,
                             "impact": x.get("impact"), "scored": bool(x.get("scored"))})
    return rows


def _days_bin(d) -> str | None:
    if d in (None, ""):
        return None
    try:
        d = float(d)
    except (TypeError, ValueError):
        return None
    if d <= 0:
        return None
    return "隔 ≤14 日" if d <= 14 else "隔 15–35 日" if d <= 35 else "隔 36–89 日" if d <= 89 else "休 ≥90 日"


INCIDENT_LABELS = {"B": "受阻", "S": "出閘慢", "W": "走外疊冇遮擋", "M": "醫療事故", "R": "騎法被查詢"}


def hkjc_incidents(results_file: Path) -> dict[int, dict[int, dict]]:
    """HKJC 賽後競賽事件報告 → {場: {馬號: {"text", "flags", "labels"}}}（Kelvin 2026-11-26：覆盤要睇埋賽後報告）。

    拆句用回放嘅 `hkjc_history_replay_build._incident_by_horse`、分類用引擎 `incident_history.flags`
    （同入分嘅「上仗走外疊／醫療」同一份 regex，唔另寫）。賽後資訊：只做覆盤解讀，**唔入組別、唔入模型**。"""
    sys.path.insert(0, str(REPO / ".agents/skills/hkjc_racing/hkjc_reflector/scripts"))
    sys.path.insert(0, str(REPO / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts"))
    import hkjc_history_replay_build as rb
    from hkjc_racing_engine.incident_history import flags

    raw = json.loads(Path(results_file).read_text(encoding="utf-8"))
    out: dict[int, dict[int, dict]] = {}
    for key, race in (raw.items() if isinstance(raw, dict) else []):
        if not isinstance(race, dict):
            continue
        try:
            race_no = int(race.get("race_no") or key)
        except (TypeError, ValueError):
            continue
        by_code = rb._incident_by_horse(race.get("incident_report") or "")
        per = {}
        for row in race.get("results") or []:
            m = re.search(r"\(([A-Z]\d{3})\)", str(row.get("horse_name") or ""))
            try:
                n = int(str(row.get("horse_no") or "").strip())
            except ValueError:
                continue
            if m and m.group(1) in by_code:
                text = by_code[m.group(1)]
                f = flags(text) or ""
                per[n] = {"text": text, "flags": f, "labels": [INCIDENT_LABELS[c] for c in f if c in INCIDENT_LABELS]}
        out[race_no] = per
    return out


def meeting_detail(platform: str, meeting_dir: Path, core) -> tuple[dict, dict]:
    """→ ({(race, 馬號): detail}, 核數)。detail = 名、排名、tags、組別、名次、SP。只讀賽前快照。"""
    from wongchoi_paths import SnapshotArchiveOffline

    recon = {"meeting": meeting_dir.name, "results_races": 0, "detail_races": 0, "reason": None}
    results_file = (sorted(meeting_dir.glob("*全日賽果.json")) or [None])[0] if platform == "hkjc" \
        else core.find_existing_results_file(platform, meeting_dir)
    if not results_file:
        recon["reason"] = "no_results"
        return {}, recon
    results = core.load_structured_results(platform, Path(results_file))
    recon["results_races"] = len(results)
    try:
        snapshot, _created, _cut = core.select_prerace_snapshot(meeting_dir, platform)
    except SnapshotArchiveOffline:
        recon["reason"] = "offline"
        return {}, recon
    if snapshot is None:
        recon["reason"] = "no_snapshot"
        return {}, recon
    preds = core.load_prediction_rows(Path(snapshot), platform)
    incidents = {}
    if platform == "hkjc":
        try:
            incidents = hkjc_incidents(Path(results_file))
        except Exception as exc:  # noqa: BLE001 — 冇事件報告唔阻覆盤，但要寫低
            recon["incident_error"] = f"{type(exc).__name__}: {exc}"
        recon["incident_races"] = sum(1 for v in incidents.values() if v)
    out = {}
    for race_num in sorted(results):
        logic = _logic_horses(Path(snapshot), int(race_num))
        res = {r["horse_no"]: r for r in results[race_num].get("results") or [] if r.get("horse_no")}
        ranks = {p["horse_no"]: p for p in preds.get(race_num, [])}
        if not ranks:
            continue
        recon["detail_races"] += 1
        for n, p in ranks.items():
            horse = logic.get(n, {})
            pa = horse.get("python_auto") or {}
            prep = pa.get("preparation_cycle") or {}
            cohorts = [_cohort_key(t) for t in _tags(pa)]
            if prep.get("label"):
                cohorts.append(f"prep:{prep['label']}")
            b = _days_bin(prep.get("days_since_last_run") if prep else horse.get("days_since_last"))
            if b:
                cohorts.append(f"days:{b}")
            r = res.get(n) or {}
            out[(int(race_num), n)] = {
                "name": p.get("horse_name"),
                "rank": p.get("rank") if (p.get("rank") or 999) < 999 else p.get("derived_rank"),
                "tags": _tags(pa), "cohorts": cohorts,
                "placing": int(r.get("placing") or 0), "sp": M._float(r.get("odds")),
                "incident": (incidents.get(int(race_num)) or {}).get(n),
            }
    return out, recon


# ---------------------------------------------------------------- 機率

def race_probs(race: dict, params: dict, platform: str) -> list[dict]:
    """race = model_probability 嘅場次（rows：n、ability、pos、sp）→ 每匹加 p_top3、p_win、m_top3、m_win。"""
    from calibration_board import _market     # 同校準板同一個去水（power）＋Harville
    ab = [x["ability"] for x in race["rows"]]
    t3 = M.top3_probs(ab, params, platform)
    w = M.win_probs(ab, params["beta_win"])
    mk = _market(race)
    mw, mt3 = (mk if mk else (None, None))
    rows = []
    for i, x in enumerate(race["rows"]):
        rows.append(dict(x, p_top3=float(t3[i]), p_win=float(w[i]),
                         m_top3=float(mt3[i]) if mt3 is not None else None,
                         m_win=float(mw[i]) if mw is not None else None, hit3=int(x["pos"] <= 3)))
    return rows


def _boot_ci(by_day: dict[str, list[float]], rng) -> list[float] | None:
    days = [d for d in by_day if by_day[d]]
    if len(days) < 3:
        return None
    sums = np.array([sum(by_day[d]) for d in days])
    cnts = np.array([len(by_day[d]) for d in days])
    idx = rng.integers(0, len(days), size=(BOOT, len(days)))
    est = sums[idx].sum(1) / cnts[idx].sum(1)
    return [float(np.quantile(est, 0.025)), float(np.quantile(est, 0.975))]


# ---------------------------------------------------------------- 主流程

def _next_day(d: str) -> str:
    return (Date.fromisoformat(d) + timedelta(days=1)).isoformat()


def build(platform: str, day: str, root: Path | None = None, trail_days: int | None = None, seed: int = 7) -> dict:
    root = Path(root) if root else M.default_root(platform)
    trail_days = trail_days or TRAIL_DAYS[platform]
    core = _core()
    races, sources = M.collect(platform, root, until=_next_day(day))
    # 只計有賽前快照嘅場（Sol 2026-11-26）：model_probability 冇快照會退返讀場次目錄（可能係賽後重評）
    no_snapshot = Counter(r["meeting"] for r in races if not r.get("published_at"))
    races = [r for r in races if r.get("published_at")]
    wf = M.walk_forward(races, platform)
    live_days = sorted(d for d in wf if d <= day)
    window = live_days[-(trail_days + 1):]            # 今日 + 之前 N 日
    if day not in wf:
        window = [d for d in window if d < day][-trail_days:]
    meetings = {r["meeting"] for r in races if r["date"] in set(window) | {day}}
    detail, recon = {}, []
    for m in sorted(M.meeting_list(platform, root), key=lambda p: p.name):
        if m.name not in meetings and m.name[:10] != day:
            continue
        got, rc = meeting_detail(platform, m, core)
        if m.name[:10] == day:
            recon.append(rc)
        for (race, n), v in got.items():
            detail[(m.name, race, n)] = v

    rows = []                                           # 每匹：日期、場次、機率、組別
    join_missing = Counter()                            # 機率有、detail（排名／tags）冇 = 配唔到
    for r in races:
        if r["date"] not in set(window) or r["date"] not in wf:
            continue
        for x in race_probs(r, wf[r["date"]], platform):
            d = detail.get((r["meeting"], r["race"], x["n"]))
            if d is None or not d.get("rank"):
                join_missing[r["meeting"]] += 1
                d = d or {}
            rows.append(dict(x, date=r["date"], meeting=r["meeting"], race=r["race"],
                             rank=d.get("rank"), tags=d.get("tags") or [], cohorts=list(d.get("cohorts") or []),
                incident=d.get("incident")))
    # 模型獨家睇好：模型頭三、市場（SP）第 6 或之後 —— 用 SP 分組只係賽後評估
    by_race = defaultdict(list)
    for x in rows:
        by_race[(x["meeting"], x["race"])].append(x)
    for rr in by_race.values():
        sp_rank = {x["n"]: i + 1 for i, x in enumerate(sorted((y for y in rr if y.get("sp")), key=lambda y: y["sp"]))}
        for x in rr:
            x["sp_rank"] = sp_rank.get(x["n"])
            if x.get("rank") and x["rank"] <= 3 and (sp_rank.get(x["n"]) or 0) >= 6:
                x["cohorts"].append("model:模型獨家睇好（模型頭三、SP 第 6+；用賽後 SP 分組，只做評估）")

    today = [x for x in rows if x["date"] == day]
    review = {
        "version": VERSION, "platform": platform, "date": day,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "probability": {"source": "model_probability.walk_forward（只用之前賽日 fit）",
                        "available": day in wf, "params": wf.get(day)},
        "reconciliation": _reconcile(recon, races, day, join_missing, no_snapshot),
        "summary": _summary(today, by_race, day),
        "meetings": _meetings(platform, root, day, by_race, detail),
        "cohorts": _cohorts(rows, day, window, np.random.default_rng(seed)),
        "window": {"days": [d for d in window if d < day], "n_days": len([d for d in window if d < day])},
        "sources": sources,
        "rules": "描述唔係判決：唔會據此改模型；篩選每季做（Holm），判決經預先登記 forward（設計 §2–§4）。",
    }
    return review


def _reconcile(recon: list[dict], races: list[dict], day: str, join_missing: Counter | None = None,
               no_snapshot: Counter | None = None) -> dict:
    used = Counter(r["meeting"] for r in races if r["date"] == day)
    join_missing, no_snapshot = join_missing or Counter(), no_snapshot or Counter()
    rows, missing, unjoined = [], 0, 0
    for rc in recon:
        n_used = used.get(rc["meeting"], 0)
        gap = rc["results_races"] - n_used
        missing += max(gap, 0)
        unjoined += join_missing.get(rc["meeting"], 0)
        rows.append(dict(rc, prob_races=n_used, missing=max(gap, 0),
                         unjoined_horses=join_missing.get(rc["meeting"], 0),
                         reason=rc["reason"] or ("no_snapshot" if no_snapshot.get(rc["meeting"]) else None)))
    return {"meetings": rows, "missing_races": missing, "unjoined_horses": unjoined, "ok": missing == 0 and unjoined == 0,
            "note": "missing = 有賽果但機率／配對用唔到嘅場（冇賽前快照、斷碟、預測唔齊）；"
                    "unjoined = 有機率但搵唔到排名／tags 嘅馬（唔入低估／高估表）。機率只喺完賽馬入面計（同校準板）。"}


def _summary(today: list[dict], by_race: dict, day: str) -> dict:
    races = [rr for (m, _r), rr in by_race.items() if rr and rr[0]["date"] == day]
    out = {"races": len(races), "model_top3_hits": 0, "market_top3_hits": 0, "slots": 0,
           "model_top1_wins": 0, "fav_wins": 0, "winner_in_model_top5": 0,
           "model_logloss_top3": None, "market_logloss_top3": None}
    ll_m, ll_k = [], []
    for rr in races:
        top3 = {x["n"] for x in rr if x["pos"] <= 3}
        mod = [x for x in rr if x.get("rank") and x["rank"] <= 3]
        mkt = [x for x in rr if x.get("sp_rank") and x["sp_rank"] <= 3]
        out["slots"] += min(3, len(rr))
        out["model_top3_hits"] += sum(x["n"] in top3 for x in mod)
        out["market_top3_hits"] += sum(x["n"] in top3 for x in mkt)
        out["model_top1_wins"] += any(x.get("rank") == 1 and x["pos"] == 1 for x in rr)
        out["fav_wins"] += any(x.get("sp_rank") == 1 and x["pos"] == 1 for x in rr)
        out["winner_in_model_top5"] += any(x["pos"] == 1 and x.get("rank") and x["rank"] <= 5 for x in rr)
        for x in rr:
            if x.get("m_top3") is not None:
                ll_m.append(_ll(x["p_top3"], x["hit3"]))
                ll_k.append(_ll(x["m_top3"], x["hit3"]))
    if ll_m:
        out["model_logloss_top3"], out["market_logloss_top3"] = float(np.mean(ll_m)), float(np.mean(ll_k))
    return out


def _ll(p, y):
    p = min(max(p, 1e-9), 1 - 1e-9)
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))


def _autopsy(meeting_dir: Path) -> dict[int, dict]:
    p = meeting_dir / "Miss_Autopsy.json"
    try:
        return {int(r["race"]): r for r in json.loads(p.read_text(encoding="utf-8")).get("races") or []}
    except (OSError, ValueError, TypeError, KeyError):
        return {}


def _label(picks: list[dict], actual: list[dict]) -> str:
    """Gold／Good／Pass／1 Hit／Miss —— 經 reflector 共用函數（eval_metrics.exclusive_label），唔另計。"""
    return _core().performance_label_from_rows(picks, actual)


def _generic(label: str) -> str:
    """組別名去走個別數字／人名：「久休 179 日復出」→「久休 N 日復出」、「騎練實績弱（X）」→「騎練實績弱」。"""
    label = re.sub(r"[（(][^）)]*[）)]", "", label)
    return re.sub(r"\d+(?:\.\d+)?", "N", label).strip()


def _cohort_key(t: dict) -> str:
    return "tag:" + _generic(t["label"]) if t.get("label") else f"tag:{t['key']}"


def _explain(x: dict, over: bool) -> list[str]:
    tags = [t for t in x.get("tags") or [] if isinstance(t.get("impact"), (int, float))]
    pick = sorted((t for t in tags if (t["impact"] > 0) == over), key=lambda t: -abs(t["impact"]))[:2]
    return [f"{t['label']}（{t['impact']:+.1f}）" for t in pick]


def _meetings(platform: str, root: Path, day: str, by_race: dict, detail: dict) -> list[dict]:
    dirs = {m.name: m for m in M.meeting_list(platform, root) if m.name[:10] == day}
    out = []
    for name in sorted(dirs):
        autopsy = _autopsy(dirs[name])
        races = []
        for (m, race), rr in sorted(by_race.items()):
            if m != name:
                continue
            a = autopsy.get(race) or {}
            picks = [{"horse_no": x["n"]} for x in sorted((y for y in rr if y.get("rank")), key=lambda y: y["rank"])]
            actual = [{"horse_no": x["n"]} for x in rr if x["pos"] <= 3]
            label = a.get("label") or _label(picks, actual)
            under = [x for x in rr if x.get("rank") and x["pos"] <= 3 and x["rank"] >= 4]
            over = [x for x in rr if x.get("rank") and x["rank"] <= 3 and x["pos"] > 3]
            fmt = lambda x, ov: {"n": x["n"], "name": x.get("name"), "rank": x.get("rank"), "pos": x["pos"],  # noqa: E731
                                 "sp": x.get("sp"), "p_top3": round(x["p_top3"], 3),
                                 "m_top3": None if x.get("m_top3") is None else round(x["m_top3"], 3),
                                 "why": _explain(x, ov), "incident": x.get("incident")}
            report = [{"n": x["n"], "name": x.get("name"), "rank": x["rank"], "pos": x["pos"],
                       "labels": x["incident"]["labels"], "text": x["incident"]["text"]}
                      for x in sorted((y for y in rr if y.get("rank") and y["rank"] <= 3 and y.get("incident")),
                                      key=lambda y: y["rank"])]
            races.append({"race": race, "label": label, "bucket": a.get("bucket"), "model_top3_report": report,
                          "triggers": a.get("triggers") or [],
                          "under": [fmt(x, False) for x in sorted(under, key=lambda y: y["pos"])],
                          "over": [fmt(x, True) for x in sorted(over, key=lambda y: y.get("rank") or 99)]})
        labels = Counter(r["label"] for r in races if r["label"])
        buckets = Counter(r["bucket"] for r in races if r["bucket"])
        over = [x for r in races for x in r["over"]]
        excused = [x for x in over if (x.get("incident") or {}).get("labels")]
        out.append({"meeting": name, "races": races, "labels": dict(labels), "buckets": dict(buckets),
                    "incident_reports": any(r["model_top3_report"] for r in races) or any(x.get("incident") for x in over),
                    "over_total": len(over), "over_with_incident": len(excused)})
    return out


def _cohorts(rows: list[dict], day: str, window: list[str], rng) -> list[dict]:
    """今日出現過嘅組別：今日數字＋之前窗口（唔包今日）嘅殘差 CI。只描述。"""
    labels = {}
    for x in rows:
        for t in x.get("tags") or []:
            labels.setdefault(_cohort_key(t), _generic(t["label"]))
    today_c = defaultdict(list)
    trail_c = defaultdict(lambda: {"model": defaultdict(list), "market": defaultdict(list), "n": 0})
    for x in rows:
        for c in set(x["cohorts"]):
            if x["date"] == day:
                today_c[c].append(x)
            elif x.get("m_top3") is not None:
                t = trail_c[c]
                t["model"][x["date"]].append(x["hit3"] - x["p_top3"])
                t["market"][x["date"]].append(x["hit3"] - x["m_top3"])
                t["n"] += 1
    out = []
    for c, xs in today_c.items():
        if len(xs) < TODAY_MIN_N:
            continue
        hit = sum(x["hit3"] for x in xs)
        exp = sum(x["p_top3"] for x in xs)
        t = trail_c.get(c)
        entry = {"cohort": c, "label": labels.get(c, c.split(":", 1)[-1]), "today_n": len(xs), "today_hits": hit,
                 "today_model_expected": round(exp, 2), "today_resid_pp": round(100 * (hit - exp) / len(xs), 1),
                 "trail_n": t["n"] if t else 0}
        if t and t["n"] >= MIN_COHORT_N:
            mm = [v for d in t["model"].values() for v in d]
            km = [v for d in t["market"].values() for v in d]
            entry.update(trail_model_resid_pp=round(100 * float(np.mean(mm)), 1),
                         trail_model_ci_pp=[round(100 * v, 1) for v in (_boot_ci(t["model"], rng) or [])] or None,
                         trail_market_resid_pp=round(100 * float(np.mean(km)), 1),
                         trail_market_ci_pp=[round(100 * v, 1) for v in (_boot_ci(t["market"], rng) or [])] or None)
            entry["reading"] = _reading(entry)
        else:
            entry["reading"] = "跨日樣本唔夠，唔講"
        out.append(entry)
    out.sort(key=lambda e: -abs(e["today_resid_pp"]) * math.sqrt(e["today_n"]))
    return out


def _reading(e: dict) -> str:
    ci = e.get("trail_model_ci_pp")
    if not ci:
        return "跨日樣本唔夠，唔講"
    today_up = e["today_resid_pp"] > 0
    if ci[0] > 0 or ci[1] < 0:
        same = (ci[0] > 0) == today_up
        mk = e.get("trail_market_ci_pp")
        mkt = "；市場都偏差" if mk and (mk[0] > 0 or mk[1] < 0) else "；市場冇顯著偏差（市場啱、模型錯）"
        return ("跨日同方向" if same else "跨日方向相反（今晚係反常）") + mkt + "（描述，唔係判決）"
    return "今晚現象：跨日 CI 包 0"


# ---------------------------------------------------------------- 輸出

def render_md(rv: dict) -> str:
    s = rv["summary"]
    plat = {"au": "AU", "hkjc": "HKJC"}[rv["platform"]]
    L = [f"# {plat} 自動覆盤 {rv['date']}", ""]
    rc = rv["reconciliation"]
    if rc.get("unjoined_horses"):
        L += [f"> ⚠️ 核數：{rc['unjoined_horses']} 匹馬有機率但配唔到排名／tags（唔入低估／高估表）", ""]
    if rc["missing_races"]:
        L += [f"> ⚠️ 核數：有 {rc['missing_races']} 場有賽果但用唔到（" +
              "、".join(f"{m['meeting']} 缺 {m['missing']}（{m['reason'] or '預測唔齊'}）" for m in rc["meetings"] if m["missing"]) + "）", ""]
    if s["races"]:
        L += ["| | 模型 | 市場（SP） |", "|---|---|---|",
              f"| 頭三入前三 | {s['model_top3_hits']}/{s['slots']} | {s['market_top3_hits']}/{s['slots']} |",
              f"| 首選／大熱贏 | {s['model_top1_wins']}/{s['races']} | {s['fav_wins']}/{s['races']} |",
              f"| 頭馬喺模型頭五 | {s['winner_in_model_top5']}/{s['races']} | — |"]
        if s["model_logloss_top3"] is not None:
            L.append(f"| 入頭三 log-loss（越細越準） | {s['model_logloss_top3']:.4f} | {s['market_logloss_top3']:.4f} |")
        L.append("")
    for m in rv["meetings"]:
        lab = "、".join(f"{k} {v}" for k, v in sorted(m["labels"].items()))
        L += [f"## {m['meeting']}", f"標籤：{lab or '—'}；失手分類：" +
              ("、".join(f"{k} {v}" for k, v in sorted(m["buckets"].items())) or "—"), ""]
        has_inc = m.get("incident_reports")
        if has_inc and m.get("over_total"):
            L += [f"賽後報告：被高估嘅 {m['over_total']} 匹入面，{m['over_with_incident']} 匹有賽中事件（受阻／出閘慢／走外疊／醫療／騎法）"
                  "—— 屬賽前預測唔到，唔係模型盲點嘅證據。", ""]
        head = "| 場 | 標籤 | 分類 | 被低估（入前三、模型 ≥4） | 被高估（模型頭三、唔入前三） |" + (" 賽後報告（模型頭三） |" if has_inc else "")
        L += [head, "|---|---|---|---|---|" + ("---|" if has_inc else "")]

        def cell(x):
            inc = x.get("incident") or {}
            tag = f"〔{'、'.join(inc['labels'])}〕" if inc.get("labels") else ""
            return f"{x['name']}（模型{x['rank']}→第{x['pos']}，${x['sp']}）{tag}{'／'.join(x['why'])}"
        for r in m["races"]:
            u = "；".join(cell(x) for x in r["under"]) or "—"
            o = "；".join(cell(x) for x in r["over"]) or "—"
            line = f"| R{r['race']} | {r['label'] or '—'} | {r['bucket'] or '—'} | {u} | {o} |"
            if has_inc:
                rep_ = "；".join(f"{x['name']}（模型{x['rank']}→第{x['pos']}）{_short(x['text'])}" for x in r["model_top3_report"]) or "—"
                line += f" {rep_} |"
            L.append(line)
        L.append("")
    if rv["cohorts"]:
        L += [f"## 今晚嘅組別，同之前 {rv['window']['n_days']} 個 live 賽日比（描述，唔係判決）", "",
              "| 組別 | 今晚 | 今晚殘差 | 跨日模型殘差 [95% CI] | 跨日市場殘差 | 讀法 |", "|---|---|---|---|---|---|"]
        for c in rv["cohorts"][:12]:
            ci = c.get("trail_model_ci_pp")
            tm = f"{c['trail_model_resid_pp']:+.1f}pp [{ci[0]:+.1f}, {ci[1]:+.1f}]（n={c['trail_n']}）" if ci else f"—（n={c['trail_n']}）"
            km = f"{c['trail_market_resid_pp']:+.1f}pp" if c.get("trail_market_resid_pp") is not None else "—"
            L.append(f"| {c['label']} | {c['today_hits']}/{c['today_n']} 入位（模型預 {c['today_model_expected']}） | "
                     f"{c['today_resid_pp']:+.1f}pp | {tm} | {km} | {c['reading']} |")
        L += ["", "殘差 = 實際入頭三 − 賽前校準機率；正 = 被低估。CI 按賽日抽樣。" + rv["rules"]]
    return "\n".join(L) + "\n"


def _short(text: str, n: int = 70) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip().replace("|", "／")
    return text if len(text) <= n else text[: n - 1] + "…"


def telegram_text(rv: dict) -> str:
    s = rv["summary"]
    plat = {"au": "AU", "hkjc": "HKJC"}[rv["platform"]]
    labels = Counter()
    for m in rv["meetings"]:
        labels.update(m["labels"])
    lines = [f"📋 {plat} 自動覆盤 {rv['date']}（{s['races']} 場）",
             f"頭三入前三：模型 {s['model_top3_hits']}/{s['slots']}・市場 {s['market_top3_hits']}/{s['slots']}",
             f"首選贏 {s['model_top1_wins']}・大熱贏 {s['fav_wins']}・頭馬喺頭五 {s['winner_in_model_top5']}/{s['races']}",
             "標籤：" + ("、".join(f"{k} {v}" for k, v in sorted(labels.items())) or "—")]
    over = sum(m.get("over_total", 0) for m in rv["meetings"] if m.get("incident_reports"))
    excused = sum(m.get("over_with_incident", 0) for m in rv["meetings"] if m.get("incident_reports"))
    if over:
        lines.append(f"賽後報告：被高估 {over} 匹入面 {excused} 匹有賽中事件（預測唔到）")
    notable = [c for c in rv["cohorts"] if c.get("trail_model_ci_pp") and "跨日同方向" in c.get("reading", "")][:3]
    if notable:
        lines.append("跨日都見到（描述，未判）：")
        lines += [f"・{c['label']}：今晚 {c['today_resid_pp']:+.0f}pp，跨日 {c['trail_model_resid_pp']:+.1f}pp" for c in notable]
    return "\n".join(lines)


def output_dir(platform: str) -> Path:
    root = os.environ.get("WONGCHOI_CONTROL_STATE_ROOT") or str(Path.home() / "WongChoiData" / "WongChoiControl")
    return Path(root) / "reviews" / platform


def _atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)


def health(today: str | None = None) -> tuple[bool, list[str]]:
    """健康.sh 用：最近一個已完賽賽日（尋日或之前）有冇覆盤；最新覆盤核數有冇缺。未開始過 = 提示唔當錯。"""
    today = today or Date.today().isoformat()
    cutoff = (Date.fromisoformat(today) - timedelta(days=1)).isoformat()
    ok, lines = True, []
    for plat in ("au", "hkjc"):
        files = sorted(output_dir(plat).glob("????-??-??.json"))
        last = files[-1].stem if files else None
        try:
            days = sorted({m.name[:10] for m in M.meeting_list(plat, M.default_root(plat)) if m.name[:10] <= cutoff})
        except Exception as exc:  # noqa: BLE001
            ok = False
            lines.append(f"{plat}：讀唔到賽日（{type(exc).__name__}）")
            continue
        want = days[-1] if days else None
        if last is None:
            lines.append(f"{plat}：未有覆盤（自動覆盤 2026-11-26 先開始）")
            continue
        if want and last < want:
            ok = False
            lines.append(f"{plat}：最近完賽 {want} 未有覆盤（最新 {last}）")
            continue
        rc = json.loads(files[-1].read_text(encoding="utf-8")).get("reconciliation") or {}
        if rc.get("ok") is False:
            ok = False
            lines.append(f"{plat}：{last} 覆盤核數有 {rc.get('missing_races')} 場用唔到")
        else:
            lines.append(f"{plat}：最新覆盤 {last}，核數 OK")
    return ok, lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--platform", choices=["au", "hkjc"])
    ap.add_argument("--date")
    ap.add_argument("--health", action="store_true", help="健康.sh：覆盤有冇出、核數")
    ap.add_argument("--trail-days", type=int)
    ap.add_argument("--data-root")
    ap.add_argument("--output-dir")
    ap.add_argument("--telegram", action="store_true", help="發 content 摘要（Kelvin＋Heison）")
    a = ap.parse_args(argv)
    if a.health:
        good, lines = health()
        print("\n".join(lines))
        return 0 if good else 1
    if not (a.platform and a.date):
        ap.error("要 --platform 同 --date")
    rv = build(a.platform, a.date, Path(a.data_root) if a.data_root else None, a.trail_days)
    out = Path(a.output_dir) if a.output_dir else output_dir(a.platform)
    _atomic(out / f"{a.date}.json", json.dumps(rv, ensure_ascii=False, indent=1, default=str))
    _atomic(out / f"{a.date}.md", render_md(rv))
    print(f"{out / (a.date + '.md')}：{rv['summary']['races']} 場；核數 {'OK' if rv['reconciliation']['ok'] else '有缺'}")
    marker = out / f".{a.date}.telegram-sent"
    if a.telegram and rv["summary"]["races"] and not marker.exists():   # 同一日只發一次（重跑唔重發）
        sys.path.insert(0, str(SHARED / "scripts"))
        import racing_telegram as T
        res = T.send_message(telegram_text(rv), audience="content")
        if isinstance(res, dict) and res.get("ok"):
            _atomic(marker, datetime.now(timezone.utc).isoformat())
    return 0


if __name__ == "__main__":
    sys.exit(main())
