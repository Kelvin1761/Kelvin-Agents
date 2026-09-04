#!/usr/bin/env python3
"""End-to-end pressure test of the AU automation, on copied meetings.

AU has stages HKJC does not: archiving into `Archive/` (which doubles as the
backtest corpus), results ingestion into the canonical CSV, `--drop-meeting`
removal from the published snapshot, and scratching-driven field rebuilds.
Everything writes into a temporary tree; the live corpus, the results CSV and
Cloudflare are never touched.

Each stage asserts something observable, and the adversarial section breaks
each guard on purpose -- a guard that never fires is not a guard.
"""
from __future__ import annotations

import csv
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RESULTS: list[tuple[str, bool, str]] = []


def stage(name: str, ok: bool, detail: str) -> None:
    RESULTS.append((name, ok, detail))
    print(f"  {'✅' if ok else '❌'} {name}: {detail}")


def run(cmd, cwd=REPO, **kw):
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=True,
                          cwd=cwd, **kw)


def main() -> int:
    live = Path(os.environ["WC_PRESSURE_AU_MEETING"])
    work = Path(tempfile.mkdtemp(prefix="wc-au-pressure-"))
    print(f"隔離工作區：{work}\n")

    print("── 1. 場次結構 / 評分產物 ──")
    copied = work / live.name
    shutil.copytree(live, copied)
    # Production always re-scores before gating (`_auto_command` then
    # `_run_data_health_gate`), so a stored meeting from an older engine is not
    # what the gate ever sees. Re-score here or the health stage measures a
    # Logic that predates whatever leaf was added most recently.
    rescore = run([sys.executable,
                   ".agents/skills/au_racing/au_wong_choi_auto/scripts/au_auto_orchestrator.py",
                   copied])
    stage("重新評分成功", rescore.returncode == 0,
          f"rc={rescore.returncode} " + (rescore.stderr or "").strip().splitlines()[-1][:60]
          if rescore.returncode else "rc=0")
    logics = sorted(copied.glob("Race_*_Logic.json"))
    analyses = sorted(copied.glob("Race_*_Auto_Analysis.md"))
    stage("Logic 同分析數目一致", len(logics) == len(analyses) and logics,
          f"{len(logics)} Logic / {len(analyses)} 分析")
    scoring_csv = copied / "Meeting_Auto_Scoring.csv"
    stage("全場評分 CSV 存在且有行", scoring_csv.is_file()
          and len(scoring_csv.read_text(encoding="utf-8").splitlines()) > 1,
          f"{len(scoring_csv.read_text(encoding='utf-8').splitlines()) - 1 if scoring_csv.is_file() else 0} 行")

    print("\n── 2. 合規 / 健康 ──")
    qa = run([sys.executable, ".agents/skills/race_compliance_qa/scripts/race_compliance_scan.py",
              "--root", copied, "--platform", "au"])
    stage("Race QA 通過", qa.returncode == 0,
          (qa.stdout or qa.stderr).strip().splitlines()[-1][:80])
    health = run([sys.executable, ".agents/skills/shared_racing/scripts/racing_data_health.py",
                  "--platform", "au", "--meeting-dir", copied])
    stage("健康掃描通過", health.returncode == 0,
          (health.stdout or "").strip().splitlines()[-1][:80] if health.stdout else f"rc={health.returncode}")
    contract = run([sys.executable, ".agents/skills/shared_racing/scripts/data_contract.py",
                    "--platform", "au", "--meeting", copied, "--gate"])
    dead = [ln for ln in (contract.stdout or "").splitlines() if "dead-field" in ln]
    stage("欄位級合約放行（冇死欄位）", contract.returncode == 0 and not dead,
          f"rc={contract.returncode}, dead={len(dead)}")

    print("\n── 3. Dashboard 合併 / 移除 ──")
    base = work / "base.json"
    key = f"{live.name[:10]}|{live.name[11:].split(' Race')[0]}"
    base.write_text(json.dumps({
        "meetings": [], "races": {}, "consensus": {}, "roi": {}}), encoding="utf-8")
    merged = work / "merged.json"
    add = run([sys.executable, "generate_static.py", "--base-snapshot", base,
               "--meeting-dir", copied, "--output-json", merged,
               "--output-html", work / "m.html"], cwd=REPO / "Horse_Racing_Dashboard")
    data = json.loads(merged.read_text(encoding="utf-8")) if merged.exists() else {}
    stage("AU 場次合併入 snapshot", len(data.get("meetings", [])) == 1,
          f"{[m['date'] + '|' + m['venue'] for m in data.get('meetings', [])]}, rc={add.returncode}")
    merged_key = next(iter(data.get("races", {})), None)
    dropped = work / "dropped.json"
    rm = run([sys.executable, "generate_static.py", "--base-snapshot", merged,
              "--drop-meeting", merged_key or key, "--output-json", dropped,
              "--output-html", work / "d.html"], cwd=REPO / "Horse_Racing_Dashboard")
    after = json.loads(dropped.read_text(encoding="utf-8")) if dropped.exists() else {}
    stage("--drop-meeting 真係移除到", after.get("meetings") == [],
          f"剩 {len(after.get('meetings', []))} 個, rc={rm.returncode}")

    print("\n── 4. 歸檔 ──")
    archive = work / "Archive"
    archive.mkdir()
    shutil.move(str(copied), str(archive / live.name))
    sys.path.insert(0, str(REPO / ".agents/skills/shared_racing/scripts"))
    from corpus_paths import meeting_dirs
    found = [p.name for p in meeting_dirs(work)]
    stage("歸檔之後語料仍然搵得返", live.name in found,
          f"corpus_paths 見到 {len(found)} 個場次")
    stage("rglob 以外嘅淺掃會漏", live.name not in [p.name for p in work.iterdir() if p.is_dir()],
          "已歸檔場次唔喺頂層（所以一定要用 corpus_paths）")

    adversarial(work, archive / live.name)

    print("\n" + "=" * 60)
    failed = [n for n, ok, _ in RESULTS if not ok]
    print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} 通過"
          + (f"；失敗：{failed}" if failed else "；全部通過 ✅"))
    print(f"工作區保留喺 {work}")
    return 1 if failed else 0


def adversarial(work: Path, meeting: Path) -> None:
    print("\n── 5. 故障注入 ──")

    drift = work / "drift"
    shutil.copytree(meeting, drift)
    analysis = drift / "Race_1_Auto_Analysis.md"
    text = analysis.read_text(encoding="utf-8")
    # ⚠️ AU renders 「🥇 **第一選**」 with Chinese numerals; HKJC renders
    # 「**第1選**」 with digits. The same scan handles both via two regexes, so
    # an injection written for one platform silently matches nothing on the
    # other and "proves" the guard is broken.
    pat = r"(🥇\s*\*\*第一選\*\*.*?[\[#]?)(\d+)"
    picks = re.findall(r"[🥇🥈]\s*\*\*第[一二]選\*\*.*?馬號[^\d]*(\d+)", text, re.S)
    if len(picks) >= 2:
        a, b = picks[0], picks[1]
        swapped = re.sub(r"(🥇\s*\*\*第一選\*\*.*?馬號[^\d]*)\d+",
                         rf"\g<1>{b}", text, count=1, flags=re.S)
        swapped = re.sub(r"(🥈\s*\*\*第二選\*\*.*?馬號[^\d]*)\d+",
                         rf"\g<1>{a}", swapped, count=1, flags=re.S)
        assert swapped != text, "injection did not modify the picks block"
        analysis.write_text(swapped, encoding="utf-8")
        qa = run([sys.executable,
                  ".agents/skills/race_compliance_qa/scripts/race_compliance_scan.py",
                  "--root", drift, "--platform", "au"])
        stage("AU Analysis/Logic 漂移會被捉到", qa.returncode != 0, f"rc={qa.returncode}")
    else:
        stage("AU Analysis/Logic 漂移會被捉到", False,
              "⚠️ 呢個場次冇 **第N選** 區塊，注入唔到（測試限制，唔係缺陷）")

    missing = work / "missing"
    shutil.copytree(meeting, missing)
    victim = sorted(missing.glob("Race_*_Auto_Analysis.md"))[2]
    victim.unlink()
    health = run([sys.executable, ".agents/skills/shared_racing/scripts/racing_data_health.py",
                  "--platform", "au", "--meeting-dir", missing])
    stage("少一場分析會被捉到", health.returncode != 0,
          f"rc={health.returncode}, "
          + ("MISSING_ANALYSIS" if "MISSING_ANALYSIS" in (health.stdout or "") else "冇報"))

    dead = work / "deadfield"
    shutil.copytree(meeting, dead)
    for logic_path in dead.glob("Race_*_Logic.json"):
        payload = json.loads(logic_path.read_text(encoding="utf-8"))
        # ⚠️ AU nests them: `horses[n].python_auto.feature_scores`. Writing to
        # `horses[n].feature_scores` creates a key nothing reads, and the
        # injection then "shows" the contract missing a dead field.
        for horse in (payload.get("horses") or {}).values():
            auto = horse.get("python_auto") if isinstance(horse, dict) else None
            if isinstance(auto, dict) and isinstance(auto.get("feature_scores"), dict):
                auto["feature_scores"]["pace_figure_score"] = 60.0
        logic_path.write_text(json.dumps(payload), encoding="utf-8")
    contract = run([sys.executable, ".agents/skills/shared_racing/scripts/data_contract.py",
                    "--platform", "au", "--meeting", dead, "--gate"])
    lines = [ln for ln in (contract.stdout or "").splitlines() if "dead-field" in ln]
    stage("死欄位會被合約攔住", contract.returncode != 0 or bool(lines),
          f"rc={contract.returncode}, dead 行 {len(lines)}")


if __name__ == "__main__":
    raise SystemExit(main())
