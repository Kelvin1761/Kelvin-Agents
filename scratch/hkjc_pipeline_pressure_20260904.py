#!/usr/bin/env python3
"""End-to-end pressure test of the HKJC automation, on a copied meeting.

Exercises the chain the way the scheduler runs it -- results into the database,
reflection artifacts, dashboard supersede, scoring, and a build-only deploy --
against a COPY of a real meeting under a temporary HK root. Nothing writes to
the live corpus, the live results database or Cloudflare.

Each stage reports PASS/FAIL with the evidence it checked, so a green run means
the stage did something observable, not merely that it exited 0.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RESULTS = []


def stage(name: str, ok: bool, detail: str) -> None:
    RESULTS.append((name, ok, detail))
    print(f"  {'✅' if ok else '❌'} {name}: {detail}")


def run(cmd, **kw):
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=True,
                          cwd=kw.pop("cwd", REPO), **kw)


def main() -> int:
    settled = Path(os.environ["WC_PRESSURE_SETTLED_MEETING"])
    live_meeting = Path(os.environ["WC_PRESSURE_LIVE_MEETING"])
    work = Path(tempfile.mkdtemp(prefix="wc-pressure-"))
    hk_root = work / "HK_Racing"
    hk_root.mkdir(parents=True)
    print(f"隔離工作區：{work}\n")

    print("── 1. 賽果入庫 ──")
    sys.path.insert(0, str(REPO / ".agents/skills/hkjc_racing/hkjc_reflector/scripts"))
    import hkjc_results_db as rdb
    copied_settled = hk_root / settled.name
    shutil.copytree(settled, copied_settled)
    db_root = hk_root / "HKJC_Race_Results_Database"
    rdb.get_results_database_root = lambda: db_root          # isolate the write
    out = rdb.sync_meeting_results(copied_settled)
    season = db_root / out.get("season", "") / out.get("date", "")
    stage("賽果寫入資料庫", out["status"] == "ok" and season.is_dir(),
          f"{out['status']}, {out.get('copied')} 檔 → {out.get('season')}/{out.get('date')}")
    stage("重跑唔會重複寫", rdb.sync_meeting_results(copied_settled)["copied"] == 0,
          "第二次 copied=0")
    corrupted = season / "full_day_results.json"
    stage("兩個檔名都寫齊",
          corrupted.is_file() and any(p.name.endswith("全日賽果.json") for p in season.iterdir()),
          f"{sorted(p.name for p in season.iterdir())}")

    print("\n── 2. 覆盤產物 ──")
    report = copied_settled / "HKJC_Reflection_Report.md"
    stage("覆盤報告存在且非空", report.is_file() and report.stat().st_size > 0,
          f"{report.stat().st_size if report.is_file() else 0} bytes")
    sys.path.insert(0, str(REPO / "Horse_Racing_Dashboard/backend"))
    from services.meeting_detector import _has_hkjc_reflection
    stage("偵測器認得呢個場次已完賽", _has_hkjc_reflection(copied_settled), "reflected=True")

    print("\n── 3. Dashboard 取代 ──")
    base = work / "base-snapshot.json"
    base.write_text(json.dumps({
        "meetings": [{"date": "2026-07-12", "venue": "ShaTin", "region": "hkjc",
                      "analysts": ["Kelvin"]},
                     {"date": "2026-09-04", "venue": "Wyong", "region": "au",
                      "analysts": ["Kelvin"]}],
        "races": {"2026-07-12|ShaTin": {"meeting": {}, "races_by_analyst": {}},
                  "2026-09-04|Wyong": {"meeting": {}, "races_by_analyst": {}}},
        "consensus": {}, "roi": {},
    }), encoding="utf-8")
    merged = work / "merged.json"
    res = run([sys.executable, "generate_static.py",
               "--base-snapshot", base, "--meeting-dir", live_meeting,
               "--output-json", merged, "--output-html", work / "merged.html"],
              cwd=REPO / "Horse_Racing_Dashboard")
    data = json.loads(merged.read_text(encoding="utf-8")) if merged.exists() else {}
    hk_keys = [m for m in data.get("meetings", []) if m.get("region") == "hkjc"]
    au_keys = [m for m in data.get("meetings", []) if m.get("region") == "au"]
    stage("新場次合併入 snapshot", any(m["date"] == live_meeting.name[:10] for m in hk_keys),
          f"hkjc={[m['date'] for m in hk_keys]}")
    stage("舊 HKJC 場次被取代", len(hk_keys) == 1, f"HKJC 剩 {len(hk_keys)} 個")
    stage("AU 場次唔受影響", len(au_keys) == 1, f"AU 剩 {len(au_keys)} 個")
    stage("HTML 建得成", (work / "merged.html").is_file(), f"rc={res.returncode}")

    print("\n── 4. 評分 / 合規 ──")
    scan = run([sys.executable,
                ".agents/skills/race_compliance_qa/scripts/race_compliance_scan.py",
                "--root", live_meeting, "--platform", "hkjc"])
    stage("Race QA 通過", scan.returncode == 0, (scan.stdout or scan.stderr).strip().splitlines()[-1][:90])
    health = run([sys.executable, ".agents/skills/shared_racing/scripts/racing_data_health.py",
                  "--platform", "hkjc", "--meeting-dir", live_meeting])
    stage("資料健康掃描可執行", health.returncode in (0, 1),
          f"rc={health.returncode} {(health.stdout or '').strip().splitlines()[-1][:70] if health.stdout else ''}")

    print("\n── 5. 發佈（只 build，唔推送） ──")
    dist = work / "dist"
    env = {**os.environ, "WC_DASHBOARD_BASE_SNAPSHOT": str(merged)}
    build = run([sys.executable, "generate_static.py", "--from-snapshot", merged,
                 "--output-html", dist / "index.html",
                 "--output-json", dist / "dashboard-data.json",
                 "--output-manifest", dist / "deploy-manifest.json"],
                cwd=REPO / "Horse_Racing_Dashboard", env=env)
    html = dist / "index.html"
    size_mb = html.stat().st_size / 1024 / 1024 if html.is_file() else 0
    stage("Snapshot 可以 render", html.is_file(), f"{size_mb:.2f} MiB")
    stage("細過 Cloudflare 25 MiB 上限", 0 < size_mb < 25, f"{size_mb:.2f} MiB")
    stage("Manifest 生成", (dist / "deploy-manifest.json").is_file(), f"rc={build.returncode}")

    adversarial(work, live_meeting)

    print("\n" + "=" * 60)
    failed = [n for n, ok, _ in RESULTS if not ok]
    print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} 通過"
          + (f"；失敗：{failed}" if failed else "；全部通過 ✅"))
    print(f"工作區保留喺 {work}")
    return 1 if failed else 0




def adversarial(work: Path, live_meeting: Path) -> None:
    """Break each stage on purpose. A guard that never fires is not a guard."""
    print("\n── 6. 故障注入 ──")
    import hkjc_results_db as rdb

    empty = work / "no-results-meeting"
    empty.mkdir()
    stage("冇賽果檔唔會 crash", rdb.sync_meeting_results(empty)["status"] == "no_results",
          "報 no_results")

    bad = work / "2026-13-99_Nowhere"
    bad.mkdir()
    (bad / "2026-13-99_Nowhere_全日賽果.json").write_text("{}", encoding="utf-8")
    stage("日期解析唔到會拒絕", rdb.sync_meeting_results(bad)["status"] == "unparsable_date",
          "報 unparsable_date")

    # A real Analysis/Logic drift must NOT be masked by a snapshot copy.
    drift = work / "drift_meeting"
    shutil.copytree(live_meeting, drift)
    # ⚠️ The scan reads the `**第N選**` picks block, NOT the 全場綜合戰力排名
    # table. Editing the table changes nothing it looks at -- a first attempt at
    # this injection did exactly that and "proved" a guard was broken when the
    # injection had simply missed.
    analysis = drift / "Race_1_Auto_Analysis.md"
    text = analysis.read_text(encoding="utf-8")
    picks = re.findall(r"\*\*第([1-4])選\*\*[^\[]*\[(\d+)\]", text)
    assert len(picks) >= 2, f"injection found no 第N選 block: {picks}"
    a, b = picks[0][1], picks[1][1]
    swapped = re.sub(r"(\*\*第1選\*\*[^\[]*\[)\d+(\])", rf"\g<1>{b}\g<2>", text, count=1)
    swapped = re.sub(r"(\*\*第2選\*\*[^\[]*\[)\d+(\])", rf"\g<1>{a}\g<2>", swapped, count=1)
    assert swapped != text, "injection did not modify the picks block"
    analysis.write_text(swapped, encoding="utf-8")
    scan = run([sys.executable,
                ".agents/skills/race_compliance_qa/scripts/race_compliance_scan.py",
                "--root", drift, "--platform", "hkjc"])
    stage("真嘅 Analysis/Logic 漂移會被捉到", scan.returncode != 0,
          f"rc={scan.returncode}（0 = 漏咗）")

    # Same drift, but with a snapshot copy that happens to match the Logic.
    snap = drift / "Prediction_Snapshots" / "20260101T000000+0800"
    snap.mkdir(parents=True, exist_ok=True)
    shutil.copy2(live_meeting / "Race_1_Auto_Analysis.md", snap / "Race_1_Auto_Analysis.md")
    shutil.copy2(live_meeting / "Race_1_Logic.json", snap / "Race_1_Logic.json")
    scan2 = run([sys.executable,
                 ".agents/skills/race_compliance_qa/scripts/race_compliance_scan.py",
                 "--root", drift, "--platform", "hkjc"])
    stage("快照唔可以掩蓋真漂移", scan2.returncode != 0,
          f"rc={scan2.returncode}（0 = 被快照掩蓋）")

    missing = work / "missing_analysis"
    shutil.copytree(live_meeting, missing)
    (missing / "Race_3_Auto_Analysis.md").unlink()
    # ⚠️ Race-count completeness belongs to the health scan, not the compliance
    # scan -- the latter checks the artifacts it finds, it does not know how many
    # races a meeting should have. Asserting it here "found" a gap that was only
    # the wrong tool.
    health3 = run([sys.executable,
                   ".agents/skills/shared_racing/scripts/racing_data_health.py",
                   "--platform", "hkjc", "--meeting-dir", missing])
    stage("少一場分析會被捉到（健康掃描）", health3.returncode != 0,
          f"rc={health3.returncode}, "
          + ("MISSING_ANALYSIS" if "MISSING_ANALYSIS" in (health3.stdout or "") else "冇報 MISSING_ANALYSIS"))

    sys.path.insert(0, str(REPO / ".agents/skills/hkjc_racing/hkjc_daily_auto"))
    import hkjc_daily_schedule as sched
    original = sched.run_cmd
    sched.run_cmd = lambda cmd, **kw: (1, "network down")
    try:
        stage("攞唔到 live snapshot 會退回", sched.build_dashboard_snapshot(live_meeting) is None,
              "回 None，交返 deploy.sh")
    finally:
        sched.run_cmd = original

    digest_dir = work / "digest"
    digest_dir.mkdir()
    (digest_dir / "Extraction_Readiness.json").write_text(json.dumps({
        "expected_races": 10, "starter_pdf_ready": False,
        "racecards_ready": 10, "formguides_ready": 3, "trackwork_ready": 0,
        "races": [{"race": n, "racecard_ok": True, "formguide_ok": n <= 3}
                  for n in range(1, 11)],
    }), encoding="utf-8")
    digest = sched.readiness_digest(digest_dir)
    stage("未齊時通知講得出邊幾場", "R4賽績" in digest and len(digest) < 200,
          digest.replace("\n", " | ")[:88])


if __name__ == "__main__":
    raise SystemExit(main())
