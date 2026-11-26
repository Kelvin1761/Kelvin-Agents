#!/usr/bin/env python3
"""排程 job 輸出新鮮度（系統升級第 4 項，2026-11-25）：健康檢查睇「應該有嘅輸出出咗未」，唔係淨係睇退出碼。

點解：launchd 只記最後一次退出碼。舊嘅 75（EX_TEMPFAIL）／1 喺之後自癒咗都照嗌，人就學識咗唔睇警號；
相反一個 job 靜靜冇再寫輸出（退出碼 0、或者根本冇再跑）就冇人知。

規則（`健康.sh`「自動化排程」用）：
  * 有登記嘅 job：輸出新鮮 → ✅（退出碼非 0 就註明「已自癒」）；輸出過期 → ❌（唔理退出碼）。
  * 冇登記（冇可靠每次都寫嘅檔，例如 hkjc live、開機 job）→ 照舊睇退出碼。
  * 從未寫過輸出、而 plist 裝咗未夠最大年齡 → ✅「新裝、未到第一次排程」（2026-11-26：astra-audit
    11-25 裝、每週一先跑，被報 ❌）。一有輸出、或者 plist 舊過最大年齡，就照舊判。
  * 最新 manifest 係 blocked、而 run 自己報 skipped_locked → ⚠️「撞鎖跳過」（下一轉會做返）；
    其他 failed／partial／blocked 照舊 ❌。
對照表由逐個 plist 追到 Python 入口查出嚟（2026-11-25），每項嘅最大年齡 = 排程最長間隔＋run 時間＋餘量。

    python3 job_freshness.py            # 印表
    python3 job_freshness.py --json
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import time
from pathlib import Path

HOME = Path.home()
PLIST_DIR = HOME / "Library" / "LaunchAgents"
CP = HOME / "WongChoiData" / "WongChoiControl" / "runs"
SCHED = Path(os.environ.get("WC_SCHEDULER_ROOT", "/Users/imac/wongchoi-scheduler"))
AUD = SCHED / ".agents/skills/au_racing/au_daily_auto"
HKD = SCHED / ".agents/skills/hkjc_racing/hkjc_daily_auto"
NBD = SCHED / ".agents/skills/nba/nba_daily_auto"
CWS = SCHED / ".agents/skills/central_wong_choi/scripts"
TLOG = Path("/Users/imac/Antigravity-repo/tennis-wong-choi/data/logs")

# label（去咗 com.antigravity.）→ (glob 列表（任何一個新就算）, 最大年齡（鐘）)
REGISTRY: dict[str, tuple[list[str], float]] = {
    "au-wong-choi.morning": ([f"{CP}/au/*/morning/10%3A00/attempt-*.json"], 28),
    "au-wong-choi.midday": ([f"{CP}/au/*/morning/12%3A00/attempt-*.json"], 28),
    "au-wong-choi.evening": ([f"{CP}/au/*/evening/22%3A00/attempt-*.json"], 30),
    "au-wong-choi.healthcheck": ([f"{AUD}/logs/healthcheck.out"], 18),
    "au-wong-choi.mobile-sectionals": ([f"{AUD}/work/au-mobile-sectionals-fetch.json"], 28),
    "au-wong-choi.betfair-snapshot": ([f"{AUD}/logs/betfair-snapshot.out"], 0.5),
    "au-wong-choi.betfair-settle": ([f"{AUD}/work/au-betfair-log-status.json"], 28),
    "au-wong-choi.bot": ([f"{AUD}/logs/bot.out"], 0.5),
    "hkjc-wong-choi.watch": ([f"{CP}/hkjc/*/watch/*/attempt-*.json"], 15),
    "hkjc-wong-choi.prerace": ([f"{CP}/hkjc/*/prerace/*/attempt-*.json"], 13),
    "hkjc-wong-choi.lineup": ([f"{CP}/hkjc/*/lineup/*/attempt-*.json"], 15),
    "hkjc-wong-choi.recovery": ([f"{CP}/hkjc/*/recovery/*/attempt-*.json"], 1.5),
    "hkjc-wong-choi.postrace": ([f"{CP}/hkjc/*/postrace/08%3A30/attempt-*.json"], 28),
    "hkjc-wong-choi.intraday": ([f"{HKD}/logs/launchd-intraday.log", f"{HKD}/logs/hkjc_daily_schedule.log"], 1),
    "hkjc-wong-choi.weekly": ([f"{HKD}/logs/launchd-weekly.log"], 172),
    "nba-wong-choi.final-refresh": ([f"{CP}/nba/*/pregame/06%3A30/attempt-*.json",
                                     f"{CP}/nba/*/pregame/13%3A00/attempt-*.json"], 20),
    "nba-wong-choi.warmup": ([f"{CP}/nba/*/pregame/19%3A00/attempt-*.json"], 28),
    "nba-wong-choi.production": ([f"{CP}/nba/*/pregame/21%3A00/attempt-*.json", f"{NBD}/logs/launchd-production.log"], 28),
    "nba-wong-choi.health": ([f"{CP}/nba/*/health/10%3A30/attempt-*.json"], 28),
    "nba-wong-choi.postgame": ([f"{CP}/nba/*/postgame/*/attempt-*.json"], 1),
    "tennis-wong-choi.betfair": ([f"{TLOG}/tennis_betfair_tick.log"], 1),
    "tennis-wong-choi.settle": ([f"{TLOG}/tennis_settle_tick.log"], 2),
    "tennis-wong-choi.preclose": ([f"{TLOG}/tennis_preclose_refresh.log"], 1.5),
    # 所有 slot：復原 run 寫喺其他 slot，最新一個 attempt 先反映到復原咗未（取代舊 Tennis 復原特例）
    "tennis-wong-choi.card": ([f"{CP}/tennis/*/card/*/attempt-*.json"], 28),
    "tennis-wong-choi.daily": ([f"{CP}/tennis/*/daily/*/attempt-*.json"], 28),
    "tennis-wong-choi.night": ([f"{TLOG}/tennis_daily_schedule.log"], 26),
    "tennis-wong-choi.recovery": ([f"{TLOG}/tennis_card_recovery_state.json"], 26),
    "central-wong-choi.durability": ([f"{CWS}/logs/central-durability.out"], 28),
    "central-wong-choi.research-review": ([f"{CP}/central/*/research-review/*.json"], 28),
    "central-wong-choi.roi-summary": ([f"{CWS}/logs/roi-summary.out"], 28),
    "wongchoi.health": ([f"{AUD}/logs/health.out"], 172),
    # 每週一次；latest.json 每次都寫（succeeded／no_changes／skipped_quota／failed）
    # 每日一次；latest.json 每次探測都寫（全部正常都寫）
    "central-wong-choi.model-probe": ([f"{HOME}/WongChoiData/WongChoiControl/model_probe/latest.json"], 28),
    "central-wong-choi.astra-audit": ([f"{HOME}/WongChoiData/WongChoiControl/astra_audit/latest.json"], 172),
    # 每週 AI 覆盤總結（2026-11-26）：review_ai.py weekly 寫 reviews/weekly/<日>.json
    "central-wong-choi.review-weekly": ([f"{HOME}/WongChoiData/WongChoiControl/reviews/weekly/*.json"], 172),
    # 每週健康巡查（2026-11-26）：health_sweep.py 寫 health_sweep/<日>.json（AI 失敗唔寫 .json）
    "central-wong-choi.health-sweep": ([f"{HOME}/WongChoiData/WongChoiControl/health_sweep/*.json"], 172),
    # 每 30 分鐘；live 寫 latest.json、dry-run 寫 latest-dryrun.json（任何一個新就算）。未安裝前唔會喺 LaunchAgents。
    "central-wong-choi.self-repair": ([f"{HOME}/WongChoiData/WongChoiControl/self_repair/latest.json",
                                       f"{HOME}/WongChoiData/WongChoiControl/self_repair/latest-dryrun.json"], 1.5),
    "central-wong-choi.offsite-backup": ([f"{HOME}/WongChoiData/WongChoiControl/offsite_backup_state.json"], 30),
}
# 冇可靠每次都寫嘅檔：只喺賽馬夜有輸出／淨係開機跑 → 照舊睇退出碼
UNREGISTERED_REASON = {
    "hkjc-wong-choi.live": "淨係 HK 賽馬夜先有輸出",
    "hkjc-wong-choi.startup": "淨係開機跑",
    "nba-wong-choi.startup": "淨係開機跑",
}
# 結束碼 1 = 搵到問題嘅數目（設計如此），唔係 job 壞
EXIT_1_BY_DESIGN = {"au-wong-choi.healthcheck", "wongchoi.health"}


FAILED_STATES = {"failed", "partial", "blocked", "error"}
HEALTHY_STATES = {"succeeded", "dormant", "complete", "completed", "ok", "running"}


def newest(patterns: list[str]) -> tuple[float, str] | None:
    best = None
    for pat in patterns:
        for path in glob.iglob(pat):
            try:
                m = os.path.getmtime(path)
            except OSError:
                continue
            if best is None or m > best[0]:
                best = (m, path)
    return best


def run_state(path: str) -> str | None:
    """control-plane manifest／run log 嘅 state 或 status；唔係 JSON 就 None。"""
    if not path.endswith(".json"):
        return None
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    v = d.get("state") or d.get("status") if isinstance(d, dict) else None
    return str(v) if v else None


def skipped_locked(path: str) -> bool:
    """control-plane manifest：有 operation（或佢嘅 source_payload）報 skipped_locked。"""
    if not path.endswith(".json"):
        return False
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    ops = d.get("operations") if isinstance(d, dict) else None
    for op in ops if isinstance(ops, list) else []:
        if not isinstance(op, dict):
            continue
        payload = (op.get("detail") or {}).get("source_payload") if isinstance(op.get("detail"), dict) else None
        if op.get("status") == "skipped_locked" or (isinstance(payload, dict) and payload.get("status") == "skipped_locked"):
            return True
    return False


def plist_age_hours(label: str, now: float, plist_dir: Path | None = None) -> float | None:
    p = Path(plist_dir or PLIST_DIR) / f"com.antigravity.{label}.plist"
    try:
        return (now - p.stat().st_mtime) / 3600
    except OSError:
        return None


def check(label: str, now: float | None = None, plist_dir: Path | None = None) -> dict:
    now = time.time() if now is None else now
    if label not in REGISTRY:
        return {"label": label, "registered": False, "reason": UNREGISTERED_REASON.get(label, "未登記")}
    patterns, max_age = REGISTRY[label]
    hit = newest(patterns)
    age = None if hit is None else (now - hit[0]) / 3600
    pending = False
    if hit is None:
        installed = plist_age_hours(label, now, plist_dir)
        pending = installed is not None and installed <= max_age
    return {"label": label, "registered": True, "max_age_hours": max_age,
            "age_hours": None if age is None else round(age, 2),
            "fresh": age is not None and age <= max_age,
            "pending_first_run": pending,
            "state": run_state(hit[1]) if hit else None,
            "skipped_locked": bool(hit) and skipped_locked(hit[1])}


def classify(label: str, exit_code: int | None, now: float | None = None,
             plist_dir: Path | None = None) -> tuple[str, str]:
    """→ (等級 ok|warn|bad, 訊息)。健康.sh 用。"""
    c = check(label, now, plist_dir)
    if not c["registered"]:
        if exit_code in (None, 0):
            return "ok", label
        return "warn", f"{label} 上次退出碼 {exit_code}（{c['reason']}，冇輸出可以核對）"
    age = "從未寫過" if c["age_hours"] is None else f"{c['age_hours']:.1f} 鐘前"
    if c.get("pending_first_run"):
        return "ok", f"{label}（新裝、未到第一次排程；退出碼 {exit_code}）"
    if not c["fresh"]:
        return "bad", f"{label} 輸出過期：最新 {age}（上限 {c['max_age_hours']:g} 鐘；退出碼 {exit_code}）"
    if (c.get("state") or "").lower() == "blocked" and c.get("skipped_locked"):
        return "warn", f"{label} 最新 run 撞鎖跳過（{age}；另一個 run 揸住鎖，下一轉會做返）"
    if (c.get("state") or "").lower() in FAILED_STATES:
        # 新鮮但最新一次 run 自己寫住失敗 —— 有跑唔等於有做到（例：research-review 11-21 起每日 failed）
        return "bad", f"{label} 最新 run 狀態 {c['state']}（{age}；退出碼 {exit_code}）"
    if exit_code in (None, 0) or (exit_code == 1 and label in EXIT_1_BY_DESIGN):
        return "ok", f"{label}（輸出 {age}）"
    # 退出碼非 0：只有最新 run 自己寫住成功／休眠先算自癒。淨係 log 新鮮唔夠 —— 失敗嗰次都會寫 log（Sol 覆核）。
    if (c.get("state") or "").lower() in HEALTHY_STATES:
        return "ok", f"{label}（退出碼 {exit_code}，但最新 run {c['state']}、{age}，已自癒）"
    return "warn", f"{label} 上次退出碼 {exit_code}（輸出 {age}，但冇 run 狀態可以證明已自癒）"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--classify", nargs=2, metavar=("LABEL", "EXIT"), help="健康.sh 用：印 等級<TAB>訊息")
    a = ap.parse_args(argv)
    if a.classify:
        label, code = a.classify
        level, msg = classify(label, int(code) if code.lstrip("-").isdigit() else None)
        print(f"{level}\t{msg}")
        return 0
    rows = [check(k) for k in sorted(REGISTRY)]
    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
    else:
        for r in rows:
            mark = ("🆕" if r.get("pending_first_run") else
                    "⚠️" if r["fresh"] and (r["state"] or "").lower() == "blocked" and r.get("skipped_locked") else
                    "✅" if r["fresh"] and (r["state"] or "").lower() not in FAILED_STATES else "❌")
            print(f"{mark} {r['label']:38s} {r['age_hours']} / {r['max_age_hours']} 鐘  {r['state'] or ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
