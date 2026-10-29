"""HKJC forward-test tracker: one table of every pending forward test.

Before this existed, each forward test lived in its own experiment record and
only two of them were ever reported.  The prospective shadow ledger had two
profiles past their minimum (`pre_race_draw_context_v1_generic` 53/20,
`race_shape_v2_legacy_hv` 27/20) and three that had never been active — and
nobody was told (found 2026-10-27).

What it does (never changes a model setting):

* ``section()``   weekly review: progress of every test, one line each.
* ``remind()``    after each post-race run: one Telegram message the first
                  time a test reaches its minimum (remembered in state).
* auto-judge      tests whose rule is fully pre-registered and needs no human
                  reading (``harness_ab``) are judged once when ready, the
                  verdict is frozen in state and reported; applying it is
                  still Kelvin's call.

Tests already judged by their own weekly section (first-section speed,
official injury) are listed with their frozen verdict only.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

STATE_KEY = "forward_tracker"


@dataclass(frozen=True)
class ForwardTest:
    key: str
    label: str
    experiment: str
    kind: str                     # shadow_profile | harness_ab | awt_races | trackwork_meetings | rail_ledger | state_judge
    minimum: int
    since: str = ""
    profile: str = ""
    arm: str = ""
    state_key: str = ""
    action: str = "夠數之後要人手做 Stage 4 review"
    decided: str = ""             # 人手判完寫低結論；之後只顯示，唔再提醒
    extra: dict = field(default_factory=dict)


FORWARD_TESTS: tuple[ForwardTest, ...] = (
    ForwardTest("gear_removed", "配備「除去」−3 剷走", "EXP-20261010-05", "harness_ab", 60,
                since="2026-10-11", arm="docs/experiments/patches/hkjc_arm_no_gear_removed.py",
                action="自動判：Gold、Good、NDCG@5 Δ 全部 ≥ 0 → 建議剷走 −3；否則維持"),
    # EXP-20261029-30 B：回放 345 場 Gold +1.16pp [+0.29, +2.30] 但 Good −0.58pp，按 v3 REJECT。
    # Kelvin 交我決定；呢個係 harness_ab 嘅加入類（唔係剷走類），所以過咗係「建議上線」。
    ForwardTest("weight_rating_gap", "負磅分改用官方評分差距", "EXP-20261029-30", "harness_ab", 60,
                since="2026-10-30", arm="docs/experiments/patches/hkjc_arm_weight_rating_gap.py",
                action="自動判：forward Gold、Good、NDCG@5 Δ 全部 ≥ 0 → 建議上線；否則維持現行（宣佈負磅）",
                extra={"pass_verdict": "建議上線（等你決定）"}),
    ForwardTest("first_section", "頭段速度（已退回）", "EXP-20261016-53", "state_judge", 150,
                state_key="first_section_forward_final", action="每週自動判，見前速 forward 一段"),
    ForwardTest("official_injury", "官方傷患紀錄 B1", "EXP-20261020-02", "state_judge", 60,
                state_key="official_injury_forward_final", action="每週自動判，見傷患記錄一段"),
    ForwardTest("awt_experience", "冇泥地經驗（AWT）", "EXP-20261027-03", "awt_races", 30,
                since="2026-10-28", action="夠數之後重跑分層加權差（預先登記），正數而且 CI 下界 > 0 先開排名候選"),
    # EXP-20261029-01 喺 36 個賽日再篩六個訊號（試閘、距最後一課、上仗後負荷、同日同場地快操速度、
    # 同平時習慣比、騎師真係有操），Holm 後全部 1.0 → UNRESOLVABLE；夠 60 個賽日用同一個腳本原封重跑。
    ForwardTest("trackwork_rescreen", "晨操細分訊號重新篩選", "EXP-20261029-01", "trackwork_meetings", 60,
                action="夠數之後原封重跑 docs/experiments/patches/hkjc_screen_trackwork_readiness.py"
                       "（六個訊號、Holm）；Holm 後 CI 下界 > 0 先做 arm"),
    ForwardTest("rail_bias", "賽道配置 → 當日內檔偏差", "EXP-20261010-14", "rail_ledger", 60,
                action="兩個場地都夠 60 個賽日：跑預先登記嘅 Kruskal–Wallis（配置 ≥ 5 日先比），p < 0.05 先設計賽前用法；"
                       "`hkjc_rail_bias_ledger.py report`"),
    ForwardTest("weight_refit_t02", "權重 refit t02", "EXP-20260928-10", "shadow_profile", 120,
                profile="weight_refit_t02"),
    # race_shape_v3_hv 已經 experimental live（EXP-20260929-01），由 race_shape_v2_legacy_hv 做 rollback 對照。
    # race_shape_v3_hv_t02（A+B）2026-10-27 撤走：跑馬地 V3 已經 live，weight_refit_t02 喺跑馬地
    # 就等於 A+B，冇額外問題要答。佢亦唔喺 DEFAULT_SHADOW_PROFILES，由來冇記錄。
    ForwardTest("race_shape_v2_legacy_hv", "跑馬地 V3 rollback 對照", "EXP-20260929-01", "shadow_profile", 20,
                profile="race_shape_v2_legacy_hv", action="夠數之後睇 legacy 有冇好過 live V3（rollback 對照）",
                decided="2026-10-27 review：27 場舊版冇一項贏（Good −1、頭五捕捉／NDCG CI 全負）→ 維持 V3"),
    ForwardTest("race_shape_st_draw70", "沙田 draw70", "EXP-20260929-02", "shadow_profile", 80,
                profile="race_shape_st_draw70"),
    ForwardTest("race_shape_legacy_unbounded", "形勢 winsor10 rollback 對照", "EXP-20261008-03", "shadow_profile", 80,
                profile="race_shape_legacy_unbounded", action="ledger 已有 rollback gate；夠數睇 gate 狀態"),
    ForwardTest("trainer_recency_st_early90", "沙田季初練馬師 90 日", "EXP-20261005-01", "shadow_profile", 80,
                profile="trainer_recency_st_early90"),
    # pre_race_draw_context_v2 已經上線（EXP-20261007-01），由 v1_generic 做 rollback 對照。
    ForwardTest("pre_race_draw_context_v1_generic", "賽前檔位 v1 rollback 對照", "EXP-20261007-01", "shadow_profile", 20,
                profile="pre_race_draw_context_v1_generic", action="夠數之後睇 v1 有冇好過 live（rollback 對照）",
                decided="2026-10-27 review：53 場舊版冇一項贏（Good −2、NDCG CI 全負）→ 維持 v2"),
)

STALLED_AFTER_ROWS = 20


def _results_races(meeting_dir: Path) -> dict:
    files = sorted(meeting_dir.glob("*全日賽果.json"))
    if not files:
        return {}
    try:
        payload = json.loads(files[0].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in payload.items() if isinstance(v, dict) and v.get("results")}


def _meetings(root: Path, since: str = "") -> list[Path]:
    out = []
    for path in sorted(root.glob("20[0-9][0-9]-[0-9][0-9]-[0-9][0-9]_*")):
        if path.is_dir() and path.name[:10] >= since and path.name.endswith(("_ShaTin", "_HappyValley")):
            out.append(path)
    return out


def _race_count(root: Path, since: str) -> int:
    return sum(len(_results_races(m)) for m in _meetings(root, since))


def _awt_race_count(root: Path, since: str) -> int:
    count = 0
    for meeting in _meetings(root, since):
        for race_no in _results_races(meeting):
            cards = list(meeting.glob(f"* Race {race_no} 排位表.md"))
            if cards and "場地: 全天候跑道" in cards[0].read_text(encoding="utf-8", errors="replace"):
                count += 1
    return count


def _trackwork_meetings(root: Path) -> int:
    return sum(1 for m in _meetings(root) if _results_races(m) and any(m.glob("*晨操.json")))


RAIL_LEDGER_NAME = "HKJC_Rail_Bias_Ledger.jsonl"  # hkjc_rail_bias_ledger.LEDGER_NAME


def _rail_meetings(root: Path) -> dict[str, int] | None:
    """Meetings per venue in the rail-bias ledger (EXP-20261010-14); None = ledger missing."""
    path = root / RAIL_LEDGER_NAME
    if not path.exists():
        return None
    meetings: dict[str, set] = {"沙田": set(), "跑馬地": set()}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("venue") in meetings:
            meetings[row["venue"]].add(row.get("meeting"))
    return {venue: len(names) for venue, names in meetings.items()}


def _ledger_summary(ledger_path: Path | None) -> dict:
    if not ledger_path or not ledger_path.exists():
        return {}
    try:
        payload = json.loads(ledger_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    summary = payload.get("summary") or {}
    total = len(payload.get("rows") or [])
    for item in summary.values():
        item["_ledger_rows"] = total
    return summary


def progress(test: ForwardTest, *, root: Path, ledger: dict, state: dict) -> dict:
    """{count, minimum, status, note} — status: collecting | ready | stalled | decided | unknown."""
    if test.decided:
        return {"count": None, "minimum": test.minimum, "status": "decided", "note": test.decided}
    tracker = state.get(STATE_KEY) or {}
    judged = (tracker.get("judged") or {}).get(test.key)
    if judged:
        return {"count": judged.get("count"), "minimum": test.minimum, "status": "decided",
                "note": judged.get("line", "")}
    if test.kind == "state_judge":
        frozen = state.get(test.state_key)
        if isinstance(frozen, dict) and frozen.get("line"):
            return {"count": None, "minimum": test.minimum, "status": "decided", "note": frozen["line"]}
        return {"count": None, "minimum": test.minimum, "status": "collecting", "note": test.action}
    if test.kind == "shadow_profile":
        item = ledger.get(test.profile)
        if not item:
            return {"count": None, "minimum": test.minimum, "status": "unknown", "note": "ledger 冇呢個 profile"}
        count = int(item.get("active_races") or 0)
        note = ""
        gate = item.get("rollback_gate") or {}
        if gate.get("status"):
            note = f"rollback gate：{gate['status']}"
        recorded = int(item.get("races") or 0)
        if count == 0 and recorded >= STALLED_AFTER_ROWS:
            return {"count": 0, "minimum": test.minimum, "status": "stalled",
                    "note": f"{recorded} 場有記錄但 0 場 active —— 可能冇接通或者已經同 live 一樣，要人手查"}
        if recorded == 0 and int(item.get("_ledger_rows") or 0) >= STALLED_AFTER_ROWS:
            return {"count": 0, "minimum": test.minimum, "status": "stalled",
                    "note": "ledger 有其他 profile 嘅記錄，呢個一場都冇 —— 唔喺預設 shadow 清單？要決定撤定駁返"}
    elif test.kind == "harness_ab":
        count = _race_count(root, test.since)
        note = ""
    elif test.kind == "awt_races":
        count = _awt_race_count(root, test.since)
        note = ""
    elif test.kind == "trackwork_meetings":
        count = _trackwork_meetings(root)
        note = ""
    elif test.kind == "rail_ledger":
        per_venue = _rail_meetings(root)
        if per_venue is None:
            return {"count": None, "minimum": test.minimum, "status": "unknown",
                    "note": f"搵唔到 {RAIL_LEDGER_NAME}"}
        count = min(per_venue.values())  # 兩個場地都要夠數
        note = "、".join(f"{venue} {n}" for venue, n in per_venue.items())
    else:
        return {"count": None, "minimum": test.minimum, "status": "unknown", "note": f"未知 kind {test.kind}"}
    status = "ready" if count >= test.minimum else "collecting"
    return {"count": count, "minimum": test.minimum, "status": status, "note": note}


ICON = {"collecting": "⏳", "ready": "⏰", "stalled": "⚠️", "decided": "✅", "unknown": "❔"}


def _line(test: ForwardTest, item: dict) -> str:
    count = "—" if item["count"] is None else str(item["count"])
    text = f"{ICON[item['status']]} {test.label}（{test.experiment}）：{count}/{item['minimum']}"
    if item["status"] == "ready":
        text += f" —— 夠數：{test.action}"
    elif item["note"] and item["status"] in {"stalled", "decided", "unknown"}:
        text += f" —— {item['note']}"
    elif item["note"]:
        text += f"｜{item['note']}"
    return text


def section(state: dict, *, root: Path, ledger_path: Path | None) -> str:
    ledger = _ledger_summary(ledger_path)
    lines = ["🧪 Forward 測試進度（夠數會另外 Telegram 提你；永遠唔會自動改模型）"]
    order = {"ready": 0, "stalled": 1, "collecting": 2, "unknown": 3, "decided": 4}
    items = [(t, progress(t, root=root, ledger=ledger, state=state)) for t in FORWARD_TESTS]
    for test, item in sorted(items, key=lambda pair: order[pair[1]["status"]]):
        lines.append(_line(test, item))
    return "\n\n" + "\n".join(lines)


def remind(state: dict, *, root: Path, ledger_path: Path | None,
           notify: Callable[[str], bool]) -> list[str]:
    """Telegram once per test the first time it is ready or stalled."""
    ledger = _ledger_summary(ledger_path)
    tracker = state.setdefault(STATE_KEY, {})
    sent = tracker.setdefault("notified", {})
    messages = []
    for test in FORWARD_TESTS:
        item = progress(test, root=root, ledger=ledger, state=state)
        if item["status"] not in {"ready", "stalled"}:
            continue
        marker = item["status"]
        if sent.get(test.key) == marker:
            continue
        if item["status"] == "ready":
            message = (f"⏰ Forward 測試夠數喇：{test.label}（{test.experiment}）{item['count']}/{item['minimum']}\n"
                       f"要做：{test.action}\n記錄：docs/experiments/{test.experiment}*.md")
        else:
            message = (f"⚠️ Forward 測試冇累積：{test.label}（{test.experiment}）\n{item['note']}")
        if notify(message):
            sent[test.key] = marker
            messages.append(message)
    return messages


def _compare_deltas(report: dict) -> dict:
    detail = (report.get("verdict") or {}).get("detail") or {}
    primary, ranking = detail.get("primary") or {}, detail.get("ranking") or {}
    return {
        "gold": (primary.get("gold") or {}).get("delta"),
        "good": (primary.get("good_positional") or {}).get("delta"),
        "ndcg": (ranking.get("ndcg_at5") or {}).get("delta"),
        "races": report.get("races"),
    }


def judge_ready(state: dict, *, root: Path, run_cmd: Callable, harness: Path, python: str,
                out_dir: Path, stamp: Callable[[], str]) -> list[str]:
    """Run each ready ``harness_ab`` test once (pre-registered commands), freeze the verdict."""
    tracker = state.setdefault(STATE_KEY, {})
    judged = tracker.setdefault("judged", {})
    lines = []
    for test in FORWARD_TESTS:
        if test.kind != "harness_ab" or test.key in judged:
            continue
        count = _race_count(root, test.since)
        if count < test.minimum:
            continue
        folder = out_dir / test.experiment
        folder.mkdir(parents=True, exist_ok=True)
        base, cand, cmp_path = folder / "fwd_base.jsonl", folder / "fwd_candidate.jsonl", folder / "compare.json"
        env = {"PYTHONDONTWRITEBYTECODE": "1"}
        steps = (
            [python, str(harness), "run", "--since", test.since, "--out", str(base)],
            [python, str(harness), "run", "--since", test.since, "--arm", test.arm, "--out", str(cand)],
            [python, str(harness), "compare", str(base), str(cand), "--stage4", "fixed_rule",
             "--leakage-audit-passed", "--out", str(cmp_path)],
        )
        failed = None
        for cmd in steps:
            code, output = run_cmd(cmd, timeout=3600, env_overlay=env)
            if code != 0:
                failed = f"exit={code}｜{output[-200:]}"
                break
        if failed:
            lines.append(f"⚠️ {test.label} 自動判失敗（下星期再試）：{failed}")
            continue
        deltas = _compare_deltas(json.loads(cmp_path.read_text(encoding="utf-8")))
        if None in (deltas["gold"], deltas["good"], deltas["ndcg"]):
            lines.append(f"⚠️ {test.label} 判定輸出缺欄位，要人手睇 {cmp_path}")
            continue
        passed = deltas["gold"] >= 0 and deltas["good"] >= 0 and deltas["ndcg"] >= 0
        verdict = test.extra.get("pass_verdict", "建議剷走（等你決定）") if passed else "維持現狀"
        line = (f"{test.label}（{test.experiment}）forward {deltas['races']} 場：Gold Δ {100 * deltas['gold']:+.2f}pp、"
                f"Good Δ {100 * deltas['good']:+.2f}pp、NDCG Δ {deltas['ndcg']:+.4f} → {verdict}")
        judged[test.key] = {"line": line, "count": count, "decided_at": stamp(), "passed": passed}
        lines.append("🧪 " + line)
    return lines


_SAFE_KEY = re.compile(r"^[a-z0-9_]+$")
assert all(_SAFE_KEY.match(t.key) for t in FORWARD_TESTS)
