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
    ready_from_status: bool = False   # True = 跟狀態檔自己嘅 boolean `ready`（只限要同時夠賽日＋場數嘅測試）


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
    ForwardTest("heavy_h2", "大爛地近績質素分用返舊公式（H2；live 照用 C2，只做反事實）",
                "EXP-20261105-06", "status_file", 200, "場",
                "scheduler 夠數會自動判一次（v3 fixed_rule：live C2 vs H2，只計大爛地）並凍結；睇 au-heavy-h2-forward-status.json，"
                "adopt_h2=true 就由你決定係咪上線 H2",
                status_file="au-heavy-h2-forward-status.json"),
    ForwardTest("debut_neutral", "初出馬冇證據穩定性分 52.4 → 60（D1，用戶接受嘅實驗性上線）",
                "EXP-20261105-09", "status_file", 700, "場",
                "scheduler 夠數會自動判一次（v3 fixed_rule：上線版 vs 舊 52.4）並凍結；睇 au-debut-neutral-forward-status.json，"
                "keep=false 就建議 WC_AU_DEBUT_NEUTRAL=0 回退",
                status_file="au-debut-neutral-forward-status.json"),
    ForwardTest("betfair_market_log", "Betfair 市場走勢記錄（API 自己記，T−60／T−15／T−5 最佳買賣價＋BSP）",
                "EXP-20261106-02", "status_file", 2000, "場",
                "夠數就跑修訂協議嘅 Q1（走勢喺 BSP 以外有冇資訊）同 Q2（四條 BSP 規則，Holm）；只係研究，唔會自動落注",
                status_file="au-betfair-log-status.json"),
    # lpos_backfill（EXP-20261120-87）已停：AllRacing 只回溯約 11 日，見 EXP-20261124-21。
    ForwardTest("lpos_forward", "末段扣位置 Lpos（手機逐駒分段，β 0.10 固定，只追蹤唔郁排名）",
                "EXP-20261116-20", "status_file", 2500, "場",
                "scheduler 夠數會自動判一次（v3 fixed_rule：live vs live＋0.10×Lpos）並凍結；睇 au-lpos-forward-status.json，"
                "win=true 先由你決定係咪上線（要另一個改動）",
                status_file="au-lpos-forward-status.json"),
    ForwardTest("sb_over_betfair", "頭兩選 Sportsbet 位賠明顯高過 Betfair（≥1.10 倍）紙上位注（盲測，只計數量）",
                "EXP-20261121-31", "status_file", 1000, "注",
                "scheduler 夠數會自動判一次（高價組 ROI CI 下限 >0 同高過其餘）並凍結；睇 au-sb-betfair-forward-status.json，"
                "PASS 先由你決定點用（唔會自動落注）",
                status_file="au-sb-betfair-forward-status.json"),
    ForwardTest("age_upnil", "老馬（−3.46）＋練馬師剩餘表現（β 40）＋騎練總獎金實驗性上線退回監察；休後第二仗 0 上名（−1.93）shadow",
                "EXP-20261121-37", "status_file", 1000, "場",
                "scheduler 夠數會用 log-loss 尺判一次並凍結；睇 au-age-upnil-forward-status.json："
                "OLD／TRES／PRIZE rollback_recommended=true 就建議 WC_AU_OLD_HORSE_LIVE=0／WC_AU_TRAINER_RESIDUAL_LIVE=0／WC_AU_PEOPLE_PRIZE_LIVE=0；SUNIL PASS 先由你決定上唔上",
                status_file="au-age-upnil-forward-status.json"),
    ForwardTest("pr1_shadow", "表現評分 PR1（輸距＋負磅）疊 live shadow（唔郁排名）",
                "EXP-20261122-05", "status_file", 1000, "場",
                "scheduler 夠數會判一次並凍結：Good 同頭二選有中 CI 下界都 > 0 = PASS（Kelvin：咁先考慮犧牲 Gold）；"
                "睇 au-pr1-shadow-forward-status.json，上唔上線由你決定",
                status_file="au-pr1-shadow-forward-status.json"),
    ForwardTest("fq_floor", "近績質素分場內 SD 下限 0.3065（F1）上線退回監察：上線版 vs 冇下限",
                "EXP-20261124-20", "status_file", 1000, "場",
                "scheduler 夠數會用 log-loss 尺 v2 判一次並凍結；睇 au-fq-floor-forward-status.json："
                "F1 rollback_recommended=true 就建議 WC_AU_FQ_SD_FLOOR_LIVE=0（要你決定）",
                status_file="au-fq-floor-forward-status.json"),
    ForwardTest("speed_live", "WinningTime 速度分（0.5 × 場內 z）上線退回監察：上線版 vs 冇速度分",
                "EXP-20261124-42", "status_file", 1000, "場",
                "scheduler 夠數會用 log-loss 尺 v2 判一次並凍結；睇 au-speed-forward-status.json："
                "SPEED rollback_recommended=true（機率變差、AUC 護欄唔過、或者 Gold／Good 都跌）就建議 WC_AU_SPEED_LIVE=0（要你決定）",
                status_file="au-speed-forward-status.json"),
    ForwardTest("s2_live", "S2（pace_figure 混 Sportsbet 全程速度＋pace_perf 權重 ×1.64）上線退回監察：上線版 vs 冇 S2",
                "EXP-20261127-03", "status_file", 1000, "場",
                "scheduler 夠數會用 log-loss 尺 v2 判一次並凍結；睇 au-s2-forward-status.json："
                "S2 rollback_recommended=true 就建議 WC_AU_S2_LIVE=0（要你決定）",
                status_file="au-s2-forward-status.json"),
    ForwardTest("trainer_residual_autorollback", "練馬師剩餘表現表版本 shadow＋自動回退（只比改寫咗舊歷史嘅重建）",
                "EXP-20261125-08", "status_file", 7, "賽日",
                "長開監察：每個改寫版本 3 個 7 賽日窗口；CI 下界 >0 或連續 3 個點估計 >0 = 自動回退指針並鎖定（另推 Telegram）；"
                "睇 au-trainer-residual-shadow-status.json，鎖咗要你查成因後 `au_residual_versions.py unpin`",
                status_file="au-trainer-residual-shadow-status.json"),
    ForwardTest("h1_trial_prep", "H1 試閘＋備戰分加重（w 凍結 0.79／1.35 分每 SD，shadow 唔郁排名）",
                "EXP-20261125-11", "status_file", 1000, "場",
                "要同時夠 30 個賽日同 1,000 場；scheduler 夠數會自動判一次（m3 追市場軌：log-loss 尺 v2 PASS＋"
                "市場尺 gap_change ≤ 0）並凍結；睇 au-h1-forward-status.json，PASS 先由你決定上唔上線（要另一個改動）",
                status_file="au-h1-forward-status.json", ready_from_status=True),
    # 通用假設 forward（au_hypothesis_forward.ARMS）：每個 arm 一行，status 檔 = au-hyp-forward-<id>.json。
    # test_au_hypothesis_forward 會核對 ARMS 同呢度一一對應。
    ForwardTest("h2_jockey_trainer", "H2 騎師＋練馬師分加重（w 凍結 0.99／0.85 分每 SD，shadow 唔郁排名）",
                "EXP-20261126-01", "status_file", 2000, "場",
                "要同時夠 60 個賽日同 2,000 場；夠數自動判一次（m3 追市場軌）並凍結；PASS 先由你決定上唔上線",
                status_file="au-hyp-forward-EXP-20261126-01.json", ready_from_status=True),
    ForwardTest("h3_spell_backup", "H3 休後狀態曲線（休 ≥90 日 −1.72、隔 ≤14 日 +1.15 分，shadow 唔郁排名）",
                "EXP-20261126-02", "status_file", 2000, "場",
                "要同時夠 60 個賽日同 2,000 場；夠數自動判一次（m3 追市場軌）並凍結；PASS 先由你決定上唔上線",
                status_file="au-hyp-forward-EXP-20261126-02.json", ready_from_status=True),
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
        enough = out["count"] >= out["minimum"]
        if test.ready_from_status:
            # 只限明確標咗嘅測試（EXP-20261125-11：要同時夠賽日同場數），而且一定要係真 boolean
            flag = status.get("ready")
            if not isinstance(flag, bool):
                out["error"] = f"{path.name}: ready 唔係 boolean（{flag!r}）"
                out["ready"] = False
                return out
            enough = flag
        out["ready"] = out["done"] or enough
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
    try:   # 共用總板（系統升級第 5 項）；壞咗都唔阻判決同推送
        fb = _forward_board()
        fb.publish("au", [fb.row(t.key, t.label, t.experiment, count=report[t.key]["count"],
                                 minimum=report[t.key]["minimum"], unit=t.unit,
                                 status=("error" if report[t.key]["error"] else "decided" if report[t.key]["done"]
                                         else "ready" if report[t.key]["ready"] else "collecting"),
                                 note=report[t.key]["error"] or (t.action if report[t.key]["ready"] else ""))
                          for t in tests])
    except Exception as exc:  # noqa: BLE001
        print(f"forward 總板寫唔到：{type(exc).__name__}: {exc}", file=sys.stderr)
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


def _forward_board():
    """共用 forward 總板（shared_wong_choi/forward_board.py）；用檔案路徑載入，唔拉成個 package。"""
    import importlib.util
    path = Path(__file__).resolve().parents[2] / "shared_wong_choi" / "forward_board.py"
    spec = importlib.util.spec_from_file_location("wc_forward_board", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
