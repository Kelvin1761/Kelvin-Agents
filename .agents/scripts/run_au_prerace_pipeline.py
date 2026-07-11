#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AU Racing 一鍵賽前管線 (Pre-Race Data Pipeline)
================================================
Usage:
    python3 run_au_prerace_pipeline.py <meeting_dir>
    python3 run_au_prerace_pipeline.py 2026-04-18_Randwick/

Steps:
    1. 檢查 Racecard / Formguide
    2. inject_fact_anchors.py 生成 Facts.md
    3. build_au_logic.py 生成 deterministic Race_X_Logic.json
    4. au_auto_orchestrator.py 生成 Auto Analysis / Auto Scoring
    5. Output pipeline_summary.json

Note: 依家 AU mainline 已切去 full Python。
      Monte Carlo 唔再屬於主流程，只保留作 side research。
"""

import os
import sys
import json
import glob
import subprocess
from datetime import datetime
from pathlib import Path

# Force UTF-8
os.environ["PYTHONUTF8"] = "1"

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
AU_SCRIPTS = Path(__file__).resolve().parent.parent / "skills" / "au_racing" / "au_wong_choi" / "scripts"
AU_AUTO_SCRIPTS = Path(__file__).resolve().parent.parent / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts"


def log(msg: str, level: str = "INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{level}] {msg}")


def find_python():
    """Cross-platform Python finder."""
    import shutil
    for cmd in ["python3", "python"]:
        if shutil.which(cmd):
            return cmd
    log("Python not found!", "ERROR")
    sys.exit(1)


def run_step(python: str, cmd: list, step_name: str, timeout: int = 120) -> bool:
    """Execute a pipeline step and return success status."""
    log(f"▶ {step_name}")
    try:
        result = subprocess.run(
            [python] + cmd,
            capture_output=True, text=True, timeout=timeout,
            env={**os.environ, "PYTHONUTF8": "1"}
        )
        if result.returncode == 0:
            log(f"  ✅ {step_name} 完成")
            return True
        else:
            log(f"  ❌ {step_name} 失敗: {result.stderr[:200]}", "ERROR")
            return False
    except subprocess.TimeoutExpired:
        log(f"  ⏰ {step_name} 超時 ({timeout}s)", "ERROR")
        return False
    except FileNotFoundError:
        log(f"  ❌ 腳本不存在", "ERROR")
        return False


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 run_au_prerace_pipeline.py <meeting_dir>")
        print("Example: python3 run_au_prerace_pipeline.py 2026-04-18_Randwick/")
        sys.exit(1)

    meeting_dir = Path(sys.argv[1]).resolve()
    if not meeting_dir.exists():
        log(f"目錄不存在: {meeting_dir}", "ERROR")
        sys.exit(1)

    python = find_python()
    summary = {
        "meeting_dir": str(meeting_dir),
        "timestamp": datetime.now().isoformat(),
        "steps": {},
        "status": "PENDING"
    }

    log(f"🏇 AU 賽前管線啟動: {meeting_dir.name}")
    log("ℹ️ AU mainline: full Python deterministic pipeline")

    # Step 1: Check for existing Formguide/Racecard files
    racecard_files = sorted(glob.glob(str(meeting_dir / "*Racecard*")))
    formguide_files = sorted(glob.glob(str(meeting_dir / "*Formguide*")))

    if not racecard_files or not formguide_files:
        log("⚠️ Racecard/Formguide 未找到 — 需要先執行 au_orchestrator.py 提取數據")
        summary["steps"]["data_check"] = {"status": "SKIP", "reason": "No racecard/formguide found"}
    else:
        log(f"📋 找到 {len(racecard_files)} 個 Racecard, {len(formguide_files)} 個 Formguide")
        summary["steps"]["data_check"] = {"status": "PASS", "racecards": len(racecard_files), "formguides": len(formguide_files)}

    # Step 2: Inject Facts.md for each race
    inject_script = SCRIPTS_DIR / "inject_fact_anchors.py"
    if inject_script.exists() and racecard_files:
        facts_count = 0
        for i, (rc, fg) in enumerate(zip(racecard_files, formguide_files), 1):
            facts_file = meeting_dir / f"Race_{i}_Facts.md"
            if facts_file.exists():
                log(f"  ⏭️ Race {i} Facts.md 已存在，跳過")
                facts_count += 1
                continue
            venue = meeting_dir.name.split("_")[-1] if "_" in meeting_dir.name else "Unknown"
            ok = run_step(python, [str(inject_script), rc, fg, "--max-display", "5", "--venue", venue], f"Facts.md 注入 Race {i}")
            if ok:
                facts_count += 1
        summary["steps"]["facts_injection"] = {"status": "PASS" if facts_count > 0 else "FAIL", "count": facts_count}
    else:
        log("⏭️ inject_fact_anchors.py 不存在或無數據，跳過 Facts 注入")
        summary["steps"]["facts_injection"] = {"status": "SKIP"}

    # Step 3: Build deterministic Logic.json files
    logic_builder = AU_AUTO_SCRIPTS / "build_au_logic.py"
    logic_count = 0
    facts_files = sorted(meeting_dir.glob("*Facts.md"))
    if logic_builder.exists() and facts_files:
        for facts_file in facts_files:
            race_num_match = __import__("re").search(r"Race[ _](\d+)", facts_file.name)
            if not race_num_match:
                continue
            race_num = int(race_num_match.group(1))
            logic_file = meeting_dir / f"Race_{race_num}_Logic.json"
            if logic_file.exists():
                log(f"  ⏭️ Race {race_num} Logic.json 已存在，跳過")
                logic_count += 1
                continue
            ok = run_step(python, [str(logic_builder), str(facts_file), "--output", str(logic_file)], f"Logic.json 生成 Race {race_num}")
            if ok:
                logic_count += 1
        summary["steps"]["logic_build"] = {"status": "PASS" if logic_count > 0 else "FAIL", "count": logic_count}
    else:
        log("⏭️ build_au_logic.py 不存在或無 Facts，跳過 Logic 生成")
        summary["steps"]["logic_build"] = {"status": "SKIP"}

    # Step 3.5: racenet sectionals timing enrichment (2026-07-11)
    # timing_600m_* 原始 writer 已失傳、上游 06-19 起斷供；呢步由每場 /sectionals
    # 頁重建（真 L600 時間，最近5場語義）。網絡步驟：被封/失敗只會 skip，
    # 引擎對 missing timing 有中性處理，唔會影響後面 orchestrator。
    timing_script = AU_AUTO_SCRIPTS / "au_sectionals_timing_enrich.py"
    if timing_script.exists() and logic_count > 0:
        ok = run_step(python, [str(timing_script), str(meeting_dir)],
                      "Sectionals timing 補完", timeout=600)
        summary["steps"]["timing_enrich"] = {"status": "PASS" if ok else "WARN"}
    else:
        summary["steps"]["timing_enrich"] = {"status": "SKIP"}

    # Step 3.6: free official trial / jump-out readiness evidence.  The
    # collector routes from each trial's venue (NSW/QLD/VIC/SA/WA/TAS), not
    # from today's meeting.  It is deliberately shadow-only and non-fatal.
    official_trial_script = AU_AUTO_SCRIPTS / "au_official_free_data.py"
    if official_trial_script.exists() and logic_count > 0:
        ok = run_step(
            python,
            [str(official_trial_script), "--meeting-dir", str(meeting_dir), "--limit", "120", "--delay", "0.8"],
            "官方試閘／跳閘資料核對（按州／馬場路由）",
            timeout=180,
        )
        summary["steps"]["official_trial_shadow"] = {"status": "PASS" if ok else "WARN"}
    else:
        summary["steps"]["official_trial_shadow"] = {"status": "SKIP"}

    # Step 3.7: persist the verified heat-level time and exact trial-jockey
    # fields onto Logic for research.  The engine intentionally ignores these
    # shadow fields until their walk-forward test is positive.
    official_trial_feature_script = AU_AUTO_SCRIPTS / "au_official_trial_feature_enrich.py"
    if official_trial_feature_script.exists() and logic_count > 0:
        ok = run_step(
            python,
            [str(official_trial_feature_script), "--meeting-dir", str(meeting_dir)],
            "官方試閘 shadow feature 寫入 Logic",
            timeout=60,
        )
        summary["steps"]["official_trial_feature_shadow"] = {"status": "PASS" if ok else "WARN"}
    else:
        summary["steps"]["official_trial_feature_shadow"] = {"status": "SKIP"}

    # Step 4: Run deterministic auto orchestrator
    auto_script = AU_AUTO_SCRIPTS / "au_auto_orchestrator.py"
    if auto_script.exists():
        ok = run_step(python, [str(auto_script), str(meeting_dir)], "AU Auto 分析輸出")
        summary["steps"]["auto_pipeline"] = {"status": "PASS" if ok else "FAIL"}
    else:
        log("⏭️ au_auto_orchestrator.py 不存在，跳過 Auto 分析")
        summary["steps"]["auto_pipeline"] = {"status": "SKIP"}

    # Output summary
    # WARN = 非致命網絡步驟（timing enrichment）失敗，唔應拖冧成條 pipeline
    all_pass = all(s.get("status") in ("PASS", "SKIP", "WARN") for s in summary["steps"].values())
    summary["status"] = "PASS" if all_pass else "PARTIAL"

    summary_path = meeting_dir / "pipeline_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    log(f"📄 管線摘要已寫入: {summary_path}")
    log(f"{'✅' if all_pass else '⚠️'} 管線狀態: {summary['status']}")
    log("💡 下一步: 可直接執行 au_orchestrator.py，或者使用目前已生成嘅 Auto outputs")


if __name__ == "__main__":
    main()
