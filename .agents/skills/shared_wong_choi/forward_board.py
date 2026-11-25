"""Forward 測試總板（系統升級第 5 項，2026-11-25）：四個 domain 一個格式、一個地方睇晒。

點解：AU／HKJC／NBA／Tennis 各自有一套 forward 追蹤（`au_forward_tracker`、`hkjc_forward_tracker`、
`nba_forward_tracker`、`tennis_wc.publish.telegram` 嘅 milestone），判法同推送都啱，但係：
  * 要知「而家有幾多個測試、邊個就夠數、邊個停咗」要開四個地方；
  * 一個 tracker 自己停咗（例如 step 冇再跑）冇人會知 —— 佢唔會推「我停咗」。
所以每個 tracker 跑完就 `publish(domain, rows)` 一份統一快照；`健康.sh` 同每週摘要用 `board()`／`render()`。
**唔改任何判決或者推送** —— 各 domain 照舊自己判、自己推 Telegram，呢度只係記錄同總覽。

快照：`<WongChoiControl>/forward_tests/<domain>.json`
  {"domain", "updated_at", "tests": [{"key", "label", "experiment", "count", "minimum", "unit",
                                       "status": collecting|ready|decided|stalled|error, "note"}]}
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

DOMAINS = ("au", "hkjc", "nba", "tennis")
STATUSES = ("stop", "ready", "stalled", "error", "collecting", "decided")
# stop：去到預先登記判決點而判決係 REJECT／STOP（第二輪第 6 項）。未到判決點唔會出 stop —— 提早停 = optional stopping。
STOP_VERDICTS = {"REJECT", "STOP"}
STALE_HOURS = {"au": 36, "hkjc": 24 * 8, "nba": 36, "tennis": 36}   # HKJC 賽後先跑，休季可以隔成個星期
ICON = {"stop": "⛔", "ready": "⏰", "stalled": "⚠️", "error": "❌", "collecting": "⏳", "decided": "✅"}


def board_dir(root: Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    if os.environ.get("WC_FORWARD_BOARD_ROOT"):
        return Path(os.environ["WC_FORWARD_BOARD_ROOT"])
    if "PYTEST_CURRENT_TEST" in os.environ:
        # tracker 嘅舊測試會行 check()／remind()：唔可以將假進度寫入真總板（就算環境有真 control root）
        import tempfile
        return Path(tempfile.gettempdir()) / f"wc-forward-board-pytest-{os.getpid()}"
    base = os.environ.get("WONGCHOI_CONTROL_STATE_ROOT") or (Path.home() / "WongChoiData" / "WongChoiControl")
    return Path(base) / "forward_tests"


def row(key: str, label: str, experiment: str, *, count=None, minimum=None, unit: str = "",
        status: str = "collecting", note: str = "", roi=None, ci=None, verdict=None) -> dict:
    """roi／ci（紙上 ROI＋95% CI）同 verdict（預先登記判決）係選填；有 verdict 屬 STOP_VERDICTS → status 自動 stop。"""
    if verdict in STOP_VERDICTS:
        status = "stop"
    if status not in STATUSES:
        raise ValueError(f"unknown forward status {status!r}")
    out = {"key": key, "label": label, "experiment": experiment,
           "count": None if count is None else int(count), "minimum": None if minimum is None else int(minimum),
           "unit": unit, "status": status, "note": note}
    if roi is not None:
        out["roi"] = float(roi)
    if ci is not None:
        out["ci"] = [float(ci[0]), float(ci[1])]
    if verdict is not None:
        out["verdict"] = str(verdict)
    return out


def publish(domain: str, rows: list[dict], *, root: Path | None = None, now: datetime | None = None) -> Path:
    """寫 domain 快照（原子寫入）。tracker 用 try/except 包住呼叫 —— 總板壞咗唔可以阻住判決同推送。"""
    if domain not in DOMAINS:
        raise ValueError(f"unknown domain {domain!r}")
    for r in rows:
        if r.get("status") not in STATUSES:
            raise ValueError(f"{domain}/{r.get('key')}: bad status {r.get('status')!r}")
    folder = board_dir(root)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{domain}.json"
    payload = {"domain": domain, "updated_at": (now or datetime.now(timezone.utc)).isoformat(), "tests": rows}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)
    return path


def board(*, root: Path | None = None, now: datetime | None = None) -> dict:
    """→ {domain: {"updated_at", "age_hours", "stale", "missing", "tests"}}。"""
    now = now or datetime.now(timezone.utc)
    out = {}
    for d in DOMAINS:
        path = board_dir(root) / f"{d}.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            out[d] = {"missing": True, "stale": True, "tests": [], "updated_at": None, "age_hours": None}
            continue
        age = (now - datetime.fromisoformat(payload["updated_at"])).total_seconds() / 3600
        out[d] = {"missing": False, "updated_at": payload["updated_at"], "age_hours": round(age, 1),
                  "stale": age > STALE_HOURS[d], "tests": payload.get("tests") or []}
    return out


def render(b: dict, *, show_decided: bool = False) -> list[str]:
    """人睇嘅行（健康.sh／週報）。夠數同停咗排先。"""
    lines = []
    order = {s: i for i, s in enumerate(STATUSES)}
    for d in DOMAINS:
        item = b[d]
        if item["missing"]:
            lines.append(f"❔ {d.upper()}：未有總板快照（tracker 未跑過新版）")
            continue
        head = f"{d.upper()}（{item['age_hours']} 鐘前更新）"
        if item["stale"]:
            head = f"⚠️ {head} —— tracker 好耐冇更新，可能停咗"
        lines.append(head)
        for t in sorted(item["tests"], key=lambda t: order.get(t["status"], 9)):
            if t["status"] == "decided" and not show_decided:
                continue
            n = "—" if t["count"] is None else t["count"]
            m = "?" if t["minimum"] is None else t["minimum"]
            note = f" —— {t['note']}" if t["note"] and t["status"] != "collecting" else ""
            perf = ""
            if t.get("roi") is not None:
                ci = t.get("ci")
                perf = f"｜ROI {t['roi']:+.1%}" + (f" [{ci[0]:+.1%}, {ci[1]:+.1%}]" if ci else "")
                if t["status"] == "collecting":
                    perf += "（未到判決點，唔准提早停）"
            if t["status"] == "stop":
                note = f" —— 預先登記判決 {t.get('verdict')}：建議停（由 Kelvin 決定）"
            lines.append(f"   {ICON[t['status']]} {t['label']}（{t['experiment']}）：{n}/{m} {t['unit']}{perf}{note}")
    return lines


def summary(b: dict) -> dict:
    tests = [t for d in DOMAINS for t in b[d]["tests"]]
    return {s: sum(t["status"] == s for t in tests) for s in STATUSES} | {
        "stale_domains": [d for d in DOMAINS if b[d]["stale"]]}
