"""自學循環 → dashboard（Portfolio 頁「🧠 自學」面板，Kelvin 2026-11-26）。

AGENTS.md：Kelvin 睇得到嘅改動一定要有 dashboard 顯示。呢度只係抄 `<WongChoiControl>` 入面已經寫好嘅檔，唔重計：
  * `reviews/<au|hkjc|nba|tennis>/<日>.json`（Python 每日覆盤）＋`<日>.ai.json`（AI 解讀：Gemini 寫、Python 核、Sonnet 審）
  * `learning/hypotheses.jsonl`（假設帳）
  * `health_sweep/<日>.json`（每週健康巡查）
  * `reviews/weekly/<日>.json`（每週 Opus 總結）
  * `learning/gap_report.json`（改善空間清單：填唔滿嘅輸入欄、可以重評嘅舊 REJECT；Kelvin：唔准假設已經做晒）
每個 domain 只帶最近 7 日、精簡欄位（避免 snapshot 太大）。冇檔 = 照列「未有」，唔扮有。
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1
DOMAINS = (("hkjc", "香港賽馬"), ("au", "AU 賽馬"), ("nba", "NBA"), ("tennis", "網球"))
DAYS = 7
MAX_COHORTS = 5
MAX_MISSES = 8


def control_root() -> Path:
    return Path(os.environ.get("WONGCHOI_CONTROL_STATE_ROOT") or (Path.home() / "WongChoiData" / "WongChoiControl"))


def _read(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _cohorts(rv: dict) -> list[dict]:
    keep = ("label", "today_n", "today_hits", "today_resid_pp", "trail_model_resid_pp", "trail_model_ci_pp",
            "trail_market_resid_pp", "reading")
    rows = [c for c in rv.get("cohorts") or [] if c.get("trail_model_ci_pp")]
    rows.sort(key=lambda c: ("跨日同方向" not in str(c.get("reading")), -abs(c.get("today_resid_pp") or 0)))
    return [{k: c.get(k) for k in keep} for c in rows[:MAX_COHORTS]]


def _racing_misses(rv: dict) -> list[dict]:
    out = []
    for m in rv.get("meetings") or []:
        for r in m.get("races") or []:
            if r.get("label") not in ("Miss", "1 Hit"):
                continue
            over = (r.get("over") or [])[:1]
            under = (r.get("under") or [])[:1]
            out.append({"meeting": m.get("meeting"), "race": r.get("race"), "label": r.get("label"),
                        "bucket": r.get("bucket"),
                        "over": [{"name": x.get("name"), "rank": x.get("rank"), "pos": x.get("pos"),
                                  "why": x.get("why"), "incident": (x.get("incident") or {}).get("labels")} for x in over],
                        "under": [{"name": x.get("name"), "rank": x.get("rank"), "pos": x.get("pos"),
                                   "why": x.get("why")} for x in under]})
    return out[:MAX_MISSES]


def _fav_second(rv: dict) -> dict | None:
    """深入覆盤 L1.5 個案 a（大熱贏、模型排第二）：計數＋每場拆分（只抄 post_review 寫好嘅 pair_autopsy）。"""
    pa = rv.get("pair_autopsy")
    if not isinstance(pa, dict):
        return None
    if pa.get("error"):
        return {"error": str(pa["error"])[:200]}

    def part(p: dict) -> dict:
        return {"key": p.get("key"), "label": p.get("label") or p.get("key"), "kind": p.get("kind"),
                "contribution": round(float(p.get("contribution") or 0), 2),
                "top_value": p.get("top_value"), "win_value": p.get("win_value"),
                "top_weak": bool((p.get("top_evidence") or {}).get("weak")) if isinstance(p.get("top_evidence"), dict) else False,
                "win_weak": bool((p.get("win_evidence") or {}).get("weak")) if isinstance(p.get("win_evidence"), dict) else False}

    cases = []
    for c in (pa.get("cases") or [])[:MAX_MISSES]:
        sw = c.get("swap") or {}
        cases.append({"meeting": c.get("meeting"), "race": c.get("race"), "field_size": c.get("field_size"),
                      "top_pick": {k: (c.get("top_pick") or {}).get(k) for k in ("name", "sp", "pos")},
                      "winner": {k: (c.get("winner") or {}).get(k) for k in ("name", "sp")},
                      "gap": round(float(c.get("total_gap") or 0), 2), "swap_reason": sw.get("reason"),
                      "leaf_level_valid": c.get("leaf_level_valid"), "unexplained": c.get("unexplained"),
                      "top_reasons": [part(p) for p in c.get("top_reasons") or []],
                      "against": [part(p) for p in c.get("against") or []],
                      "weak": [part(p) for p in c.get("weak_evidence_reasons") or []]})
    keys = ("races_with_results", "fav_won", "fav_won_rank1", "fav_won_rank2", "fav_won_rank3plus", "sp_missing")
    return {"counters": {k: (pa.get("counters") or {}).get(k) for k in keys}, "cases": cases}


def _sgm(rv: dict) -> dict | None:
    """NBA SGM 組合覆盤（Kelvin 2026-11-27「same level of details and harshness」）：只抄 post_review_sports 寫好嘅 `sgm`。"""
    s = rv.get("sgm")
    if not isinstance(s, dict):
        return None
    keys = ("combos", "won", "lost", "void", "hit_rate", "mean_model_p", "mean_implied_p", "pnl_units", "roi",
            "one_leg_away", "one_leg_away_share", "bust_legs_total", "bust_by_market", "bust_by_miss_class",
            "bust_p80_plus", "mean_ev", "mean_correlation_discount")
    pick = lambda d: {k: (d or {}).get(k) for k in keys}  # noqa: E731
    trail = s.get("trailing_summary") or {}
    combos = []
    for c in (s.get("combos") or [])[:12]:
        dg = c.get("diagnosis") or {}
        combos.append({"event": c.get("event"), "kind": c.get("kind_label"), "state": c.get("state"),
                       "odds": c.get("odds"), "model_p": c.get("model_p"), "ev": c.get("ev"),
                       "correlation_discount": c.get("correlation_discount"),
                       "one_leg_away": dg.get("one_leg_away"), "bust_was_weakest_link": dg.get("bust_was_weakest_link"),
                       "morning_update_changed": dg.get("morning_update_changed"),
                       "would_21h_version_have_won": dg.get("would_21h_version_have_won"),
                       "legs": [{k: l.get(k) for k in ("selection", "state", "actual", "line", "model_p", "exp_minutes",
                                                       "act_minutes", "miss")} for l in c.get("legs") or []]})
    return {"day": pick(s.get("day_summary")), "trail": pick(trail), "trail_formal": pick(trail.get("formal")),
            "trail_research": pick(trail.get("research")), "trail_days": s.get("trail_days"), "combos": combos}


def _day(domain: str, rv: dict, ai: dict | None) -> dict:
    out = {"date": rv.get("date"), "summary": rv.get("summary") or {}, "cohorts": _cohorts(rv),
           "reconciliation_ok": (rv.get("reconciliation") or {}).get("ok")}
    if domain in ("au", "hkjc"):
        out["misses"] = _racing_misses(rv)
        labels: dict = {}
        for m in rv.get("meetings") or []:
            for k, v in (m.get("labels") or {}).items():
                labels[k] = labels.get(k, 0) + v
        out["labels"] = labels
        out["fav_second"] = _fav_second(rv)
    else:
        out["featured_summary"] = rv.get("featured_summary")
        out["confident_miss_classes"] = rv.get("confident_miss_classes")
        out["confident_total"] = rv.get("confident_total")
        if domain == "nba":
            out["sgm"] = _sgm(rv)
    if ai and ai.get("status") in ("ok", "partial"):
        out["ai"] = {"reviewer": ai.get("reviewer") if "reviewer" in ai else "sonnet", "narrative": str(ai.get("narrative") or "")[:2000], "dropped": len(ai.get("dropped_sentences") or []),
                     "hypotheses": [{"title": h.get("title"), "cohort": h.get("cohort"), "direction": h.get("direction"),
                                     "verdict": _verdict(h.get("review"))} for h in (ai.get("hypotheses") or [])[:5]
                                    if isinstance(h, dict)]}
    return out


def _verdict(rv: dict | None) -> str:
    if not rv:
        return "未審"
    if rv.get("leak"):
        return "洩漏"
    if rv.get("done_before"):
        return f"做過 {rv.get('done_before')}"
    return "值得驗證" if rv.get("worth") else "唔值得"


def export_learning_board(root: Path | None = None) -> dict:
    root = Path(root or control_root())
    domains = {}
    for key, label in DOMAINS:
        d = root / "reviews" / key
        files = sorted(p for p in d.glob("????-??-??.json")) if d.is_dir() else []
        days = []
        for p in files[-DAYS:][::-1]:
            rv = _read(p)
            if isinstance(rv, dict):
                try:      # 壞檔唔好拖死成個匯出（Sol）
                    days.append(_day(key, rv, _read(p.with_suffix(".ai.json"))))
                except Exception:  # noqa: BLE001
                    days.append({"date": rv.get("date"), "summary": {}, "error": "覆盤檔格式唔啱"})
        domains[key] = {"label": label, "days": days}
    hyps = []
    ledger = root / "learning" / "hypotheses.jsonl"
    if ledger.exists():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            try:
                h = json.loads(line)
            except ValueError:
                continue
            hyps.append({k: h.get(k) for k in ("id", "domain", "born", "title", "cohort", "direction", "state",
                                               "done_before", "progress", "result", "judged_at")})
    sweeps = sorted((root / "health_sweep").glob("????-??-??.json")) if (root / "health_sweep").is_dir() else []
    sweep = _read(sweeps[-1]) if sweeps else None
    if isinstance(sweep, dict):
        sweep = {k: sweep.get(k) for k in ("date", "checked_by", "samples", "confirmed_mismatches", "trend_flags")}
    weeklies = sorted((root / "reviews" / "weekly").glob("????-??-??.json")) if (root / "reviews" / "weekly").is_dir() else []
    weekly = _read(weeklies[-1]) if weeklies else None
    if isinstance(weekly, dict):
        weekly = {k: weekly.get(k) for k in ("since", "until", "text")}
    gap = _read(root / "learning" / "gap_report.json")
    if isinstance(gap, dict):
        gap = {"date": gap.get("date"), "domains": {
            k: {"gaps": (v or {}).get("gaps", [])[:8], "gaps_total": (v or {}).get("gaps_total"),
                "known_retired_total": (v or {}).get("known_retired_total"), "error": (v or {}).get("error"),
                "old_rejects": (v or {}).get("old_rejects", [])[:3]} for k, v in (gap.get("domains") or {}).items()}}
    return {"schema_version": SCHEMA_VERSION, "status": "valid",
            "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "domains": domains, "hypotheses": hyps[-40:][::-1], "health_sweep": sweep, "weekly": weekly, "gap_report": gap}
