"""AU forward-test tracker：所有進行中嘅 forward／shadow 測試一張表，夠數即刻 Telegram 一次。

點解有呢個：每個 AU forward 測試以前各自喺 scheduler 寫 `runlog.warn`，而 `au_notify.send`
唔推 warning —— 即係夠數都冇人知。S2 forward（EXP-20261016-03）甚至冇 scheduler step。
2026-11-01 Kelvin：「all the forward test when they are ready to be experimented they should
send me a telegram message」。HKJC 同類機制：`hkjc_forward_tracker.py`。

規矩（AGENTS.md「Forward 測試一律登記入追蹤表」）：每個 AU forward／shadow 測試都要加入
`FORWARD_TESTS`。呢度**永遠唔會改模型、唔會自動評估要人手開嘅 family** —— 只係話你知夠數。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

REPO = Path(__file__).resolve().parents[4]
STATE_FILE = "au-forward-tracker-state.json"


@dataclass(frozen=True)
class ForwardTest:
    key: str
    label: str
    experiment: str
    kind: str            # status_file | s2_status
    minimum: int
    unit: str            # 場 | 賽日
    action: str          # 夠數之後要做乜
    status_file: str = ""


FORWARD_TESTS: tuple[ForwardTest, ...] = (
    ForwardTest("winning_time_blind", "WinningTime 速度盲測（global_add＋近期加權兩組，共用 terminal）",
                "EXP-20260927-02 / EXP-20261009-05", "status_file", 2000, "場",
                "scheduler 夠數會自動揭盲同判 Stage 4；睇 AU_Speed_Candidate_Gate.json，上線要 /approve SHA",
                status_file="au-speed-shadow-status.json"),
    ForwardTest("s2_forward", "S2 forward（L600＋全程速度一半一半，refit 權重）",
                "EXP-20261016-03", "s2_status", 41, "賽日",
                "checkout 凍結 commit 之後跑 `python3 scratch/au_s2_forward_shadow_20261016.py evaluate`"
                "（一個 family 只開一次）"),
    ForwardTest("l600_recency", "L600 近期加權（已上線）forward 確認",
                "EXP-20261101-30", "status_file", 600, "場",
                "scheduler 夠數會自動判一次並凍結；Gold／Good 有一項點估計負就交你決定係咪還原",
                status_file="au-l600-recency-forward-status.json"),
    ForwardTest("draw_big_field", "大場次檔位分（≥8 匹，β 1.4274，用戶接受嘅實驗性上線）",
                "EXP-20261102-08", "status_file", 1000, "場",
                "scheduler 夠數會自動判一次（v3 fixed_rule：有檔位 vs 冇檔位）並凍結；睇 au-draw-forward-status.json，"
                "keep=false 就建議 WC_AU_DRAW_LIVE=0 回退",
                status_file="au-draw-forward-status.json"),
    ForwardTest("overseas_rating_proxy", "英愛法往績馬近績質素分由官方讓磅分推算（×0.43，用戶接受嘅實驗性上線）",
                "EXP-20261102-12", "status_file", 100, "場",
                "scheduler 夠數會自動判一次（v3 fixed_rule：有代理 vs 冇代理）並凍結；睇 au-overseas-proxy-forward-status.json，"
                "keep=false 就建議 WC_AU_OVERSEAS_RATING_PROXY=0 回退",
                status_file="au-overseas-proxy-forward-status.json"),
)

_S2_DAYS = re.compile(r"forward days with snapshot \+ results:\s*(\d+)\s*/\s*(\d+)")
_S2_DONE = re.compile(r"already evaluated:\s*(True|False)")


def _default_run(cmd: list[str]) -> tuple[int, str]:
    proc = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=1800)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def progress(test: ForwardTest, *, work_dir: Path, run: Callable = _default_run) -> dict:
    """→ {count, minimum, ready, done, error}。讀唔到就 error，唔當 ready。"""
    out = {"count": None, "minimum": test.minimum, "ready": False, "done": False, "error": ""}
    if test.kind == "status_file":
        path = work_dir / test.status_file
        try:
            status = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            out["error"] = f"{path.name}: {type(exc).__name__}"
            return out
        out["count"] = int(status.get("races_collected") or 0)
        out["minimum"] = int((status.get("config") or {}).get("target_races")
                             or status.get("target_races") or test.minimum)
        out["done"] = bool(status.get("outcomes_visible") or status.get("evaluation"))
        out["ready"] = out["done"] or out["count"] >= out["minimum"]
        return out
    if test.kind == "s2_status":
        rc, text = run([sys.executable, str(REPO / "scratch" / "au_s2_forward_shadow_20261016.py"), "status"])
        days, done = _S2_DAYS.search(text or ""), _S2_DONE.search(text or "")
        if rc != 0 or not days:
            out["error"] = f"s2 status rc={rc}"
            return out
        out["count"], out["minimum"] = int(days.group(1)), int(days.group(2))
        out["done"] = bool(done and done.group(1) == "True")
        out["ready"] = out["done"] or out["count"] >= out["minimum"]
        return out
    out["error"] = f"unknown kind {test.kind}"
    return out


def check(*, work_dir: Path, push: Callable[[str], None], run: Callable = _default_run,
          tests: tuple[ForwardTest, ...] = FORWARD_TESTS) -> dict:
    """更新進度；每個測試第一次 ready 就 push 一次（記喺 state，唔會重覆）。→ {key: progress}。"""
    state_path = work_dir / STATE_FILE
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        state = {}
    notified = state.setdefault("notified", {})
    report = {}
    for test in tests:
        item = progress(test, work_dir=work_dir, run=run)
        report[test.key] = item
        if item["ready"] and test.key not in notified:
            push(f"🧪 Forward 測試夠數：{test.label}（{test.experiment}）\n"
                 f"{item['count']}/{item['minimum']} {test.unit}\n"
                 f"下一步：{test.action}\n"
                 "（live 唔會自動改，上唔上線係你決定）")
            notified[test.key] = {"count": item["count"], "minimum": item["minimum"]}
    state["last"] = report
    work_dir.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    return report


def summary_line(report: dict) -> str:
    parts = []
    for test in FORWARD_TESTS:
        item = report.get(test.key) or {}
        if item.get("error"):
            parts.append(f"{test.experiment.split(' / ')[0]} ⚠️{item['error']}")
        else:
            parts.append(f"{test.experiment.split(' / ')[0]} {item.get('count')}/{item.get('minimum')}"
                         + (" ✅" if item.get("ready") else ""))
    return "；".join(parts)
