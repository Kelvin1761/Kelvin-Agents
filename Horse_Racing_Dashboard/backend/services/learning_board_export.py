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
    else:
        out["featured_summary"] = rv.get("featured_summary")
        out["confident_miss_classes"] = rv.get("confident_miss_classes")
        out["confident_total"] = rv.get("confident_total")
    if ai and ai.get("status") in ("ok", "partial"):
        out["ai"] = {"narrative": str(ai.get("narrative") or "")[:2000], "dropped": len(ai.get("dropped_sentences") or []),
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
