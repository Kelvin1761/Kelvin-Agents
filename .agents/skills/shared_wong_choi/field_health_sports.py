#!/usr/bin/env python3
"""NBA／網球欄位健康（Kelvin 2026-11-26：「NBA 同網球完全冇欄位級別監察」）。

同賽馬 `shared_racing/scripts/field_health.py` 同一個目的（捉「欄位仲喺度、數值靜靜變空／變常數」），但資料形狀唔同，
所以係獨立嘅一份（AGENTS.md：AU／HKJC 唔合併；呢度亦唔塞入賽馬工具）。

每日（NBA = target_date，網球 = match_date）將**所有**輸入欄位攤平，逐欄記：n、填充率、唔同值數目、平均、SD。
  NBA：當日 ledger 嘅 `model_obs`（賽前、已發佈快照；每條腿最後一份）＋ `settlement`（分鐘、實際數字）＋ `availability_obs`。
  網球：當日已定價 prop（`prop_tracker`）嘅模型／市場機率、賠率、`pricing_evidence_json`（資料質素、選手 serve／return、fixture、quote）。
寫入 `<WongChoiControl>/field_health/<domain>.jsonl`（同一日重跑會覆蓋嗰日）。

警報（只係捉變化，唔睇絕對值；預先寫死）：同之前 14 日（最少 5 日有數）比較
  * dead：之前填充率中位數 ≥ 0.8，今日 < 0.5
  * constant：（數值欄）之前唔同值中位數 ≥ 5，今日 n ≥ 30 但得 1 個值；日期／時間類欄唔計（一日得一場波就自然得一個值）
  * shrunk：之前 n 中位數 ≥ 50，今日 n < 中位數嘅 30%（成批冇咗）
一直都空／一直都常數嘅欄位唔報（佢哋係「預期空」，例如已中止 shadow 留低嘅欄）。同一個 (domain, 欄位, 類型) 7 日內只推一次 primary。

    python3 field_health_sports.py --domain nba|tennis --date YYYY-MM-DD [--telegram]
    python3 field_health_sports.py --domain nba --backfill 30        # 補歷史做基準（唔發 Telegram）
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sqlite3
import statistics
import sys
import tempfile
from collections import defaultdict
from datetime import date as Date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
NBA_AUTO = REPO / ".agents" / "skills" / "nba" / "nba_daily_auto"
RACING = REPO / ".agents" / "skills" / "shared_racing" / "scripts"

VERSION = "field-health-sports-v1"
BASELINE_DAYS, MIN_BASE_DAYS = 14, 5
ALERT_COOLDOWN_DAYS = 7
SKIP_SUFFIX = ("_at", "_id", "sha256", "snapshot_id", "recorded_at", "captured_at", "tip_off", "start_time_utc",
               "target_date", "match_date", "as_of_date", "data_season", "requested_season")


def control_root() -> Path:
    return Path(os.environ.get("WONGCHOI_CONTROL_STATE_ROOT") or (Path.home() / "WongChoiData" / "WongChoiControl"))


def ledger_file(domain: str) -> Path:
    return control_root() / "field_health" / f"{domain}.jsonl"


def flatten(d: dict, prefix: str = "", depth: int = 0) -> dict:
    """攤平；純數字 key（球員 id 等）按出現次序變 <id1>、<id2>，令每行欄名一致又唔會互相覆蓋（Sol 2026-11-26）。"""
    out = {}
    n_ids = 0
    for k, v in (d or {}).items():
        if re.fullmatch(r"\d{2,}", str(k)):
            n_ids += 1
            k = f"<id{n_ids}>"
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            if depth < 5:
                out.update(flatten(v, key + ".", depth + 1))
        elif not isinstance(v, list):
            out[key] = v
    return out


def profile(rows: list[dict]) -> list[dict]:
    """→ 每欄一行：n（有呢個 key 嘅行）、fill、distinct、mean、sd（數字先有）。"""
    seen, filled, vals, nums = defaultdict(int), defaultdict(int), defaultdict(set), defaultdict(list)
    for r in rows:
        for k, v in r.items():
            if k.endswith(SKIP_SUFFIX):
                continue
            seen[k] += 1
            if v is None or v == "":
                continue
            filled[k] += 1
            vals[k].add(str(v)[:40])
            if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
                nums[k].append(float(v))
    out = []
    for k in sorted(seen):
        x = nums.get(k) or []
        out.append({"field": k, "n": seen[k], "fill_rate": round(filled[k] / seen[k], 4), "distinct": len(vals[k]),
                    "mean": round(statistics.fmean(x), 6) if x else None,
                    "sd": round(statistics.pstdev(x), 6) if len(x) > 1 else None})
    return out


# ---------------------------------------------------------------- 讀數

def nba_rows(day: str) -> list[dict]:
    sys.path.insert(0, str(NBA_AUTO))
    import nba_market_ledger as L
    rows = L.read_rows(Path(L.ledger_root()), day)
    by_leg: dict[tuple, dict] = {}
    for r in rows:
        if r.get("row_type") == "model_obs" and L._pre_tip(r) and r.get("snapshot_role") != "warmup":
            k = L._leg_key(r)
            if k not in by_leg or str(r.get("snapshot_created_at") or "") >= str(by_leg[k].get("snapshot_created_at") or ""):
                by_leg[k] = r
    out = [dict(flatten(r), _kind="model") for r in by_leg.values()]
    out += [dict(flatten({"settle": {k: r.get(k) for k in ("actual", "minutes", "outcome", "y")}}), _kind="settle")
            for r in rows if r.get("row_type") == "settlement"]
    out += [dict(flatten({"availability": {k: r.get(k) for k in ("espn_level", "espn_status", "official_level", "team")}}),
                 _kind="availability") for r in rows if r.get("row_type") == "availability_obs"]
    for x in out:
        x.pop("_kind", None)
    return out


def tennis_db() -> Path:
    ptr = Path.home() / ".wongchoi_tennis_db"
    try:
        p = Path(ptr.read_text(encoding="utf-8").strip())
        if p.exists():
            return p
    except OSError:
        pass
    return REPO / "tennis-wong-choi" / "tennis_wc.db"


def tennis_rows(day: str, db: Path | None = None) -> list[dict]:
    con = sqlite3.connect(f"file:{db or tennis_db()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    out = []
    try:
        for r in con.execute("""SELECT model_prob, model_prob_raw, market_prob_fair, decimal_odds, temper_strength, line,
                                       is_point_in_time, pricing_evidence_json FROM prop_tracker WHERE match_date = ?""", (day,)):
            try:
                ev = json.loads(r["pricing_evidence_json"] or "{}") or {}
            except ValueError:
                ev = {}
            base = {k: r[k] for k in ("model_prob", "model_prob_raw", "market_prob_fair", "decimal_odds",
                                      "temper_strength", "line", "is_point_in_time")}
            out.append({**flatten(base), **flatten(ev, "evidence.")})
    finally:
        con.close()
    return out


# ---------------------------------------------------------------- 帳同警報

def load(domain: str) -> list[dict]:
    p = ledger_file(domain)
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def _lock(domain: str):
    import fcntl
    path = control_root() / "field_health" / f".{domain}.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(path, "w")
    fcntl.flock(fh, fcntl.LOCK_EX)
    return fh


def write_day(domain: str, day: str, prof: list[dict]) -> None:
    rows = [r for r in load(domain) if r.get("date") != day]
    rows += [dict(r, date=day, domain=domain) for r in prof]
    rows.sort(key=lambda r: (r["date"], r["field"]))
    p = ledger_file(domain)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=f".{p.name}.", suffix=".tmp")   # 獨立暫存檔，並行唔會撞
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    os.replace(tmp, p)


def alerts(domain: str, day: str, history: list[dict] | None = None) -> list[dict]:
    rows = history if history is not None else load(domain)
    lo = (Date.fromisoformat(day) - timedelta(days=BASELINE_DAYS)).isoformat()
    today = {r["field"]: r for r in rows if r["date"] == day}
    base = defaultdict(list)
    for r in rows:
        if lo <= r["date"] < day:
            base[r["field"]].append(r)
    out = []
    if not today and len({r["date"] for r in rows if lo <= r["date"] < day}) >= 10:
        out.append({"field": "（全部欄位）", "kind": "empty", "detail": "今日完全冇數據，但之前 14 日有 ≥10 日有"})
        return out
    for field, hist in base.items():
        if len({h["date"] for h in hist}) < MIN_BASE_DAYS:
            continue
        fill = statistics.median(h["fill_rate"] for h in hist)
        dist = statistics.median(h["distinct"] for h in hist)
        n = statistics.median(h["n"] for h in hist)
        t = today.get(field)
        if t is None:
            if n >= 50:
                out.append({"field": field, "kind": "shrunk", "detail": f"今日冇呢欄（之前每日 n 中位數 {n:g}）"})
            continue
        if fill >= 0.8 and t["fill_rate"] < 0.5:
            out.append({"field": field, "kind": "dead", "detail": f"填充率 {fill:.2f} → {t['fill_rate']:.2f}"})
        elif dist >= 5 and t["n"] >= 30 and t["distinct"] == 1 and t.get("mean") is not None:   # 只計數值欄
            out.append({"field": field, "kind": "constant", "detail": f"唔同值 {dist:g} → 1（n={t['n']}）"})
        elif n >= 50 and t["n"] < 0.3 * n:
            out.append({"field": field, "kind": "shrunk", "detail": f"n {n:g} → {t['n']}"})
    return sorted(out, key=lambda a: (a["kind"], a["field"]))


def _state_path(domain: str) -> Path:
    return control_root() / "field_health" / f"alert_state_{domain}.json"     # 每個 domain 一個（Sol：唔好共用）


def _load_state(domain: str) -> dict:
    try:
        return json.loads(_state_path(domain).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def due_alerts(domain: str, day: str, found: list[dict]) -> list[dict]:
    """同一個 (欄位, 類型) 7 日內只推一次。呢度只揀，**發送成功先** `mark_sent`。"""
    state = _load_state(domain)
    due = []
    for a in found:
        last = state.get(f"{a['field']}|{a['kind']}")
        if last and (Date.fromisoformat(day) - Date.fromisoformat(last)).days < ALERT_COOLDOWN_DAYS:
            continue
        due.append(a)
    return due


def mark_sent(domain: str, day: str, sent: list[dict]) -> None:
    state = _load_state(domain)
    state.update({f"{a['field']}|{a['kind']}": day for a in sent})
    p = _state_path(domain)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=f".{p.name}.", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def telegram_text(domain: str, day: str, due: list[dict]) -> str:
    zh = {"dead": "死咗", "constant": "變常數", "shrunk": "成批少咗", "empty": "成日冇數據"}
    lines = [f"🩺 {'NBA' if domain == 'nba' else '網球'} 欄位健康 {day}：{len(due)} 個欄位突然唔妥（同之前 {BASELINE_DAYS} 日比）"]
    lines += [f"・{a['field']}：{zh[a['kind']]}（{a['detail']}）" for a in due[:10]]
    if len(due) > 10:
        lines.append(f"・另外 {len(due) - 10} 個（全文：<WongChoiControl>/field_health/{domain}.jsonl）")
    lines.append("可能係抓取／解析靜靜壞咗；要 Opus 查。")
    return "\n".join(lines)


def weekly_table(domain: str, weeks: int = 8) -> list[dict]:
    """每週健康巡查（health_sweep）用：逐欄逐 ISO 週嘅平均填充率／唔同值／n（同賽馬 *_Field_Health.jsonl 一樣嘅欄位名）。"""
    agg: dict[tuple, list[dict]] = defaultdict(list)
    for r in load(domain):
        y, w, _ = Date.fromisoformat(r["date"]).isocalendar()
        agg[(f"{y}-W{w:02d}", r["field"])].append(r)
    keep = sorted({k[0] for k in agg})[-weeks:]
    out = []
    for (wk, field), xs in sorted(agg.items()):
        if wk in keep:
            out.append({"week": wk, "source": "daily", "field": field, "n": round(statistics.fmean(x["n"] for x in xs)),
                        "fill_rate": round(statistics.fmean(x["fill_rate"] for x in xs), 4),
                        "distinct": round(statistics.fmean(x["distinct"] for x in xs), 1)})
    return out


def run_day(domain: str, day: str, telegram: bool = False) -> dict:
    rows = nba_rows(day) if domain == "nba" else tennis_rows(day)
    prof = profile(rows)
    lock = _lock(domain)
    try:
        if prof:
            write_day(domain, day, prof)
        found = alerts(domain, day)          # 冇數據都要判（「成日冇數據」）
        due = due_alerts(domain, day, found) if telegram else []
        sent = 0
        if telegram and due:
            sys.path.insert(0, str(RACING))
            import racing_telegram as T
            res = T.send_message(telegram_text(domain, day, due), audience="primary")
            if isinstance(res, dict) and res.get("ok"):
                mark_sent(domain, day, due)
                sent = len(due)
    finally:
        lock.close()
    return {"version": VERSION, "domain": domain, "date": day, "rows": len(rows), "fields": len(prof),
            "alerts": found, "sent": sent}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--domain", choices=["nba", "tennis"], required=True)
    ap.add_argument("--date")
    ap.add_argument("--backfill", type=int, help="補過去 N 日（唔發 Telegram）")
    ap.add_argument("--telegram", action="store_true")
    a = ap.parse_args(argv)
    if a.backfill:
        end = Date.fromisoformat(a.date) if a.date else Date.today()
        for i in range(a.backfill, -1, -1):
            d = (end - timedelta(days=i)).isoformat()
            r = run_day(a.domain, d)
            print(f"{d}: rows={r['rows']} fields={r['fields']} alerts={len(r['alerts'])}")
        return 0
    if not a.date:
        ap.error("要 --date 或者 --backfill")
    r = run_day(a.domain, a.date, a.telegram)
    print(json.dumps({k: v for k, v in r.items() if k != "alerts"}, ensure_ascii=False))
    for x in r["alerts"]:
        print(f"  ⚠️ {x['field']}: {x['kind']} {x['detail']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
