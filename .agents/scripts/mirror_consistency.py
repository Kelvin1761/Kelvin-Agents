#!/usr/bin/env python3
"""Drive 鏡像同本機正本一唔一致 —— 睇實物，唔係睇上次 run 嘅 log。

點解要有：`step_mirror_reports` 只鏡像「今次動過嘅場次」。一個舊場次**事後**
被重新評分（例如 2026-07-17 嗰次全語料重評，見 memory `au-archive-rescored-post-race`）
就永遠唔會再推上 Drive。2026-09-05 實測 AU：16,202 個有對應正本嘅鏡像檔，
**2,299 個（14.2%）落後過正本**，中位數 0.5 日、最耐 **98 日**。

而原本個健康檢查只問「上次 mirror run 有冇 failed」—— 嗰個永遠答「冇」，
因為每次 run 都成功鏡像咗佢自己嗰批。呢個係
[[health-alerts-must-check-artifacts-not-logs]] 同一個形狀。

用法：
    mirror_consistency.py --check              # 掃描 + 報告（健康.sh 用）
    mirror_consistency.py --backfill           # 真係補返
    mirror_consistency.py --check --platform au
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

# 落後幾耐先算「鏡像根本冇返去攞」而唔係「啱啱寫完未輪到佢」。
# 排程一日跑兩次（AU 10:00/22:00），所以正常漂移唔會超過一日。
STALE_DAYS = float(os.environ.get("WC_MIRROR_STALE_DAYS", "2"))

PLATFORMS = {
    "au": ("AU", ".wongchoi_au_mirror_root",
           "/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/AU_Racing"),
    "hkjc": ("HKJC", ".wongchoi_hk_mirror_root",
             "/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/HK_Racing"),
}


def _mirror_root(marker: str) -> Path | None:
    path = REPO / marker
    try:
        if path.is_file():
            return Path(path.read_text(encoding="utf-8").strip())
    except OSError:
        pass
    return None


def _primary_for(primary_root: Path, rel: Path) -> Path | None:
    """正本可能喺 root，亦可能喺 `Archive/`（完成嘅場次會搬入去）。"""
    for cand in (primary_root / rel, primary_root / "Archive" / rel):
        try:
            if cand.exists():
                return cand
        except OSError:
            continue
    return None


def scan(mirror_root: Path, primary_root: Path) -> dict:
    now = time.time()
    total = paired = matched = behind = stale = 0
    worst = 0.0
    worst_path = ""
    drift: list[tuple[Path, Path]] = []
    for dirpath, _dirs, files in os.walk(mirror_root):
        for name in files:
            if name.startswith("."):
                continue          # `.wongchoi-tmp-*` 之類
            mirror = Path(dirpath) / name
            total += 1
            try:
                rel = mirror.relative_to(mirror_root)
            except ValueError:
                continue
            primary = _primary_for(primary_root, rel)
            if primary is None:
                continue          # 鏡像獨有（舊嘢）—— 唔係我哋要答嘅問題
            paired += 1
            try:
                ms, ps = mirror.stat(), primary.stat()
            except OSError:
                continue
            if ms.st_size == ps.st_size:
                matched += 1
                continue
            behind += 1
            lag_days = (ps.st_mtime - ms.st_mtime) / 86400.0
            drift.append((primary, mirror))
            if lag_days > STALE_DAYS:
                stale += 1
            if lag_days > worst:
                worst, worst_path = lag_days, str(rel)
    return {"total": total, "paired": paired, "matched": matched,
            "behind": behind, "stale": stale, "worst_days": worst,
            "worst_path": worst_path, "drift": drift, "now": now}


def backfill(drift, mirror_root: Path) -> dict:
    sys.path.insert(0, str(REPO / ".agents/skills/au_racing/au_daily_auto"))
    import au_daily_schedule as sched
    done = failed = verify_failed = 0
    problems = []
    for primary, mirror in drift:
        try:
            out = sched.atomic_copy2(primary, mirror)
        except Exception as exc:            # noqa: BLE001
            failed += 1
            problems.append((type(exc).__name__, mirror.relative_to(mirror_root)))
            continue
        # 驗實物：寫完要真係同正本一樣大細，唔係 `atomic_copy2` 回咗就算。
        try:
            if out.stat().st_size != primary.stat().st_size:
                verify_failed += 1
                problems.append(("大細對唔上", mirror.relative_to(mirror_root)))
                continue
        except OSError:
            verify_failed += 1
            continue
        done += 1
    return {"done": done, "failed": failed, "verify_failed": verify_failed,
            "problems": problems}


def main() -> int:
    ap = argparse.ArgumentParser(description="Drive 鏡像一致性")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--platform", choices=sorted(PLATFORMS), action="append")
    args = ap.parse_args()
    if not (args.check or args.backfill):
        ap.error("要 --check 或者 --backfill")

    worst_status = 0
    for key in (args.platform or sorted(PLATFORMS)):
        label, marker, primary_default = PLATFORMS[key]
        mirror_root = _mirror_root(marker)
        if mirror_root is None or not mirror_root.is_dir():
            print(f"SKIP\t{label}\t搵唔到鏡像根（{marker}）")
            continue
        primary_root = Path(primary_default)
        if not primary_root.is_dir():
            print(f"SKIP\t{label}\t搵唔到本機正本根")
            continue

        result = scan(mirror_root, primary_root)
        if args.backfill and result["drift"]:
            out = backfill(result["drift"], mirror_root)
            print(f"BACKFILL\t{label}\t補咗 {out['done']}"
                  f"\t失敗 {out['failed']}\t核實唔過 {out['verify_failed']}")
            for why, rel in out["problems"][:5]:
                print(f"  留低：{why}\t{rel}")
            result = scan(mirror_root, primary_root)

        pct = 100.0 * result["matched"] / max(1, result["paired"])
        line = (f"{label}\t對得上 {result['matched']}/{result['paired']}"
                f"（{pct:.1f}%）\t落後 {result['behind']}"
                f"\t其中過期 {result['stale']}")
        if result["stale"]:
            print(f"STALE\t{line}\t最耐 {result['worst_days']:.0f} 日"
                  f"：{result['worst_path'][:60]}")
            worst_status = 1
        elif result["behind"]:
            print(f"DRIFT\t{line}\t（全部喺 {STALE_DAYS:.0f} 日內，"
                  f"應該係啱啱寫完未輪到鏡像）")
        else:
            print(f"OK\t{line}")
    return worst_status


if __name__ == "__main__":
    raise SystemExit(main())
