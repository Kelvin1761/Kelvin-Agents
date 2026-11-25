#!/usr/bin/env python3
"""練馬師剩餘表現表：新版 vs 上一版 shadow 比較＋自動回退（EXP-20261125-08）。排程每晚重建表之後跑。

比咩（預先登記，改呢度 = 改規則，要開新實驗號）：
  * 只比**改寫咗舊歷史**嘅版本（`au_residual_versions.commit` 標 `shadow: pending`）。純追加新一日嘅重建
    唔比 —— 呢個表本身就係要每晚加新賽果，「多一日資料有冇用」唔係呢度要答嘅問題，而且晚晚比會變成
    晚晚做一次假設檢定（一個月 30 次，2.5% 單邊 → 好大機會亂咁回退）。
  * 新表**截到上一版 `as_of`** 先比：兩邊用同一個資訊截止日，差異 = 純粹「重建改寫咗舊紀錄」。
  * 窗口 = 啟用日（悉尼日期）**之後**嘅有賽果賽日，每 K = 7 個一個窗口、唔重疊，每個改寫版本最多 3 個窗口（頭 21 個賽日）。
    兩版都喺嗰啲賽日之前建好，查表又只攞賽日之前嘅紀錄，所以冇未來資料。每個窗口夠 7 日判一次就凍結
    （冇 optional stopping）。之後再有改寫版本或者回退 = 舊版本嘅窗口停（superseded），唔再判。
    點解要 3 個窗口：之後嘅重建通常係純追加，唔會再比，所以一個壞改寫只有自己嘅窗口可以捉到佢。
  * 只計兩版令最少一匹馬 overlay 唔同嘅場次；Δ = 每匹 Δlog-loss（新 − 舊），賽日 bootstrap 2,000（seed 0）。

近似（為咗平，唔重跑引擎）：
  1. 其他 leaf 全部凍結喺儲存值：分數 = 儲存 `ability_score` − 儲存 `trainer_residual_feature` + 該版 overlay。
  2. 校準 (a, α, γ) 兩邊共用 = `au_logloss_ruler.calibrations(…, "v2")` 喺儲存 live 分數上 walk-forward fit
     （只用之前賽日），唔係每邊各自 refit。overlay 差異相對成個分數細，共用校準嘅偏差細；而且偏差對兩邊一樣方向。
  3. 場內平均用有賽果嘅出賽馬（退出馬唔計），引擎 live 用成個 field —— 兩邊同一個近似。

判法：
  * 回退 if Δ 95% CI 下界 > 0（新版明顯差），或者
  * 連續 3 個已判窗口（有差異場次嘅，可以跨版本）點估計都 > 0。
  回退 = 指針指返（第一個）失敗版本嘅上一版＋鎖定；之後重建照存版本但唔啟用，直到 Kelvin `unpin`。

    python3 au_residual_shadow.py --data-root DIR --output STATUS.json [--apply]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR.parents[2] / "shared_racing"))
sys.path.insert(0, str(SCRIPT_DIR.parents[2] / "shared_racing" / "scripts"))

import au_residual_versions as versions  # noqa: E402
from au_racing_engine import people_overlays as people  # noqa: E402

K_DAYS = 7
WINDOWS = 3          # 每個改寫版本最多判 3 個唔重疊窗口（頭 21 個賽日）
CONSECUTIVE = 3
BOOTSTRAP = 2000
EXPERIMENT = versions.EXPERIMENT


def overlay(trainer: str, field: list[str], date: str, table: dict) -> float:
    """同 `people_overlays.trainer_feature` 一樣（唔睇 live 開關，開關由 caller 檢查）。"""
    field = [t for t in field if t] or [trainer]
    mean = sum(people.trainer_raw(t, date, table) for t in field) / len(field)
    return round(people.TRAINER_BETA * (people.trainer_raw(trainer, date, table) - mean), 4)


def window_days(races: list[dict], activated_on: str, k: int = K_DAYS) -> list[str]:
    """啟用日之後（嚴格大過）頭 k 個有賽果嘅賽日。"""
    return sorted({r["date"] for r in races if str(r["date"]) > str(activated_on)})[:k]


def evaluate_window(races: list[dict], cal: dict, new_table: dict, prev_table: dict, *, seed: int = 0) -> dict:
    """races：窗口場次，rows 要有 live、tres、trainer、pos。→ {races_differ, runners, dlogloss: [pt, lo, hi]}。"""
    from au_logloss_ruler import _nll

    deltas, by_day = [], defaultdict(list)
    for race in races:
        if race["date"] not in cal:
            continue
        field = [x["trainer"] for x in race["rows"]]
        base = np.array([x["live"] - x["tres"] for x in race["rows"]], float)
        old = np.array([overlay(x["trainer"], field, race["date"], prev_table) for x in race["rows"]])
        new = np.array([overlay(x["trainer"], field, race["date"], new_table) for x in race["rows"]])
        if not (old != new).any():
            continue
        lo, n = _nll(race, cal[race["date"]], base + old, "v2")
        ln, _ = _nll(race, cal[race["date"]], base + new, "v2")
        by_day[race["date"]].append(len(deltas))
        deltas.append((ln - lo, n))
    if not deltas:
        return {"races_differ": 0, "runners": 0, "days": 0, "dlogloss": None}
    d = np.array([x[0] for x in deltas])
    n = np.array([x[1] for x in deltas], float)
    days = sorted(by_day)
    rng = np.random.default_rng(seed)
    boot = []
    for _ in range(BOOTSTRAP):
        ii = np.concatenate([by_day[days[j]] for j in rng.integers(0, len(days), len(days))])
        boot.append(d[ii].sum() / n[ii].sum())
    return {"races_differ": len(deltas), "runners": int(n.sum()), "days": len(days),
            "dlogloss": [float(d.sum() / n.sum()), float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))]}


def decide(evaluated: list[dict]) -> dict | None:
    """evaluated：已判窗口（按啟用次序），每個 {version, previous, result}。→ 回退指示 或 None。

    冇差異場次（dlogloss None）嘅窗口唔計入、亦唔打斷連續；已經觸發過回退（acted）嘅唔再計。"""
    scored = [e for e in evaluated if (e.get("result") or {}).get("dlogloss") and not e.get("acted")]
    if not scored:
        return None
    last = scored[-1]
    if last["result"]["dlogloss"][1] > 0:
        return {"rule": "ci_lower_above_0", "failed": [last["version"]], "to": (last.get("previous") or {}).get("version")}
    tail = scored[-CONSECUTIVE:]
    if len(tail) == CONSECUTIVE and all(e["result"]["dlogloss"][0] > 0 for e in tail):
        return {"rule": "three_consecutive_worse", "failed": list(dict.fromkeys(e["version"] for e in tail)),
                "to": (tail[0].get("previous") or {}).get("version")}
    return None


def run(live: Path, races: list[dict] | None, *, apply: bool, collect=None, now=None) -> dict:
    """更新 pending 窗口、判、（apply 先）回退。races None 就有需要先 collect。→ 狀態。"""
    ptr = versions.load_pointer(live)
    status = {"experiment": EXPERIMENT, "target_races": K_DAYS, "unit": "賽日", "outcomes_visible": False,
              "races_collected": 0, "active_version": (ptr or {}).get("version"), "pinned": bool((ptr or {}).get("pinned")),
              "pending": 0, "evaluations": [], "rollback_now": None, "state": "no_pointer"}
    if not ptr:
        return status
    if not people.trainer_residual_live():
        status["state"] = "overlay_off"
        return status
    history = ptr.get("history") or []
    pending = [e for e in history if e.get("shadow") == "pending"]
    status["pending"] = len(pending)
    if pending and races is None:
        races = collect()
    changed = False
    if pending:
        from au_logloss_ruler import calibrations, eligible
        races = eligible(races)
        cal = calibrations([{**r, "rows": [{**x, "ability": x["live"]} for x in r["rows"]]} for r in races], "v2")
        for entry in pending:
            later = history[history.index(entry) + 1:]
            superseded = any(e.get("history_rewritten") or e.get("event") == "rollback" for e in later)
            done = entry.setdefault("windows", [])
            days = window_days(races, entry["activated_on"], K_DAYS * WINDOWS)
            status["races_collected"] = max(status["races_collected"], len(days) - K_DAYS * len(done))
            prev = entry.get("previous") or {}
            new_t = versions.read_table(live, entry["file"])
            prev_t = versions.read_table(live, prev.get("file") or "")
            if new_t is None or prev_t is None:
                entry["shadow"] = "version_missing"
                changed = True
                continue
            cutoff = prev.get("as_of")
            while len(done) < WINDOWS and len(days) >= K_DAYS * (len(done) + 1) and not superseded:
                w = days[K_DAYS * len(done):K_DAYS * (len(done) + 1)]
                win = [r for r in races if r["date"] in set(w)]
                done.append({"window": w, "cutoff": cutoff,
                             **evaluate_window(win, cal, versions.truncate(new_t, cutoff), versions.truncate(prev_t, cutoff))})
                changed = True
            if len(done) >= WINDOWS or superseded:
                entry["shadow"] = "done"
                entry["superseded"] = superseded and len(done) < WINDOWS
                changed = True
    windows = [{"version": e["version"], "previous": e.get("previous"), "result": w, "entry": e, "index": i}
               for e in history for i, w in enumerate(e.get("windows") or [])]
    status["evaluations"] = [{"version": w["version"], "previous": (w["previous"] or {}).get("version"),
                              "window_no": w["index"] + 1, **w["result"]} for w in windows[-10:]]
    status["pending"] = sum(e.get("shadow") == "pending" for e in history)
    if windows and not status["pending"]:
        status["races_collected"] = K_DAYS
    decision = None if ptr.get("pinned") else decide([{**w, "acted": w["result"].get("acted")} for w in windows])
    if decision and decision.get("to"):
        if apply:
            for w in windows:
                w["result"]["acted"] = True   # unpin 之後唔會用返同一批窗口即刻再回退
            versions._write_pointer(live, ptr)
            try:
                versions.rollback(live, to_version=decision["to"], reason=decision["rule"],
                                  evidence={k: decision[k] for k in ("rule", "failed", "to")}, now=now)
            except (OSError, ValueError) as exc:
                decision = {**decision, "error": f"{type(exc).__name__}: {exc}"}
            changed = False
        status["rollback_now"] = {**decision, "applied": apply and "error" not in decision}
    if changed and apply:
        versions._write_pointer(live, ptr)
    status["state"] = ("rolled_back" if status["rollback_now"] else "pinned" if ptr.get("pinned")
                       else "pending" if any(e.get("shadow") == "pending" for e in history) else "ok")
    return status


def telegram_text(status: dict) -> str:
    rb = status["rollback_now"]
    last = (status["evaluations"] or [{}])[-1]
    d = last.get("dlogloss") or [0, 0, 0]
    return (f"⏪ 練馬師剩餘表現表自動回退（{EXPERIMENT}）\n"
            f"規則：{rb['rule']}；失敗版本 {', '.join(rb['failed'])} → 指返 {rb['to']} 並鎖定\n"
            f"最近窗口 Δlog-loss/匹 {d[0]:+.5f}（95% CI {d[1]:+.5f} ~ {d[2]:+.5f}），差異場次 {last.get('races_differ')}\n"
            "新重建照存但唔啟用；查清點解重建改寫咗舊紀錄之後先 "
            "`au_residual_versions.py unpin --actor kelvin`")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--output", required=True)
    ap.add_argument("--table", default=None)
    ap.add_argument("--apply", action="store_true", help="判到要回退就真係郁指針（排程用）")
    args = ap.parse_args(argv)
    from au_trainer_residual_table import collect

    live = Path(args.table) if args.table else people.live_table_path()

    def _collect():
        from au_archive_calibrator import ARCHIVE_ROOT
        return collect(Path(args.data_root) if args.data_root else ARCHIVE_ROOT)

    status = run(live, None, apply=args.apply, collect=_collect)
    if status["rollback_now"]:
        status["telegram"] = telegram_text(status)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: status[k] for k in ("state", "races_collected", "pending", "rollback_now")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
