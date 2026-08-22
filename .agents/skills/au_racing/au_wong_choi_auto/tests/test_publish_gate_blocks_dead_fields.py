"""發佈閘：死欄位要攔，細場次稀疏唔准攔。

2026-08-22 事故：十個場次全部 `pace_figure_score` 中性 60、場內 SD 0.00 ——
排名 **12.2% 權重完全死**。抽取報「成功」、`WinningTime` 齊全、九個 test suite
全綠、日誌零錯、snapshot 結構完全正常。冇任何現有檢查睇得到，最後靠人手發現。

實測影響：拿三個有真 PF 嘅場次（24 場）強制 PF 中性，**71% 場次 top-4 唔同**。

呢個 test 釘死兩邊：
  * 死欄位（幾乎每匹馬中性，而基準話平時有值）→ 一定要攔
  * 細場次稀疏（例如 5 場鄉道卡嘅試閘分 72.7% vs 基準 36.6%）→ 一定唔准攔

第二邊同第一邊一樣重要。一個會攔住正常鄉道日子嘅閘，最後一定會被人關掉，
然後就等於冇閘。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[5]
CONTRACT = ROOT / ".agents" / "skills" / "shared_racing" / "scripts" / "data_contract.py"
BASELINE = (ROOT / ".agents" / "skills" / "shared_racing" / "resources"
            / "au_data_contract.json")


def _fake_meeting(tmp_path: Path, feature_overrides: dict, races=6, runners=10) -> Path:
    """A synthetic meeting whose features are healthy except where overridden."""
    base = json.loads(BASELINE.read_text(encoding="utf-8"))["fields"]
    folder = tmp_path / "2026-08-22 Synthetic Race 1-6"
    folder.mkdir(parents=True, exist_ok=True)
    for race in range(1, races + 1):
        horses = {}
        for n in range(1, runners + 1):
            # spread each field around 60 so nothing looks dead by accident
            scores = {k: 60.0 + ((n % 5) - 2) * 3.0 for k in base}
            scores.update(feature_overrides)
            horses[str(n)] = {"horse_name": f"H{n}", "python_auto": {"feature_scores": scores}}
        (folder / f"Race_{race}_Logic.json").write_text(
            json.dumps({"race_analysis": {}, "horses": horses}), encoding="utf-8")
    return folder


def _gate(folder: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CONTRACT), "--platform", "au",
         "--meeting", str(folder), "--gate"],
        capture_output=True, text=True, timeout=300,
    )


def test_a_dead_field_blocks_publication(tmp_path):
    """Every runner neutral on a normally-populated field → exit 1."""
    folder = _fake_meeting(tmp_path, {"pace_figure_score": 60.0})
    result = _gate(folder)
    assert result.returncode == 1, (
        "PF 全場中性居然過閘 —— 2026-08-22 嗰次就係咁靜靜發佈咗\n"
        + result.stdout[-600:])
    assert "dead-field" in result.stdout
    assert "pace_figure_score" in result.stdout


def test_thin_country_card_does_not_block(tmp_path):
    """A sparse-but-not-dead field warns and publishes.

    `trial_score` at ~70% neutral against a 36.6% baseline is what a real
    5-race country card looks like. Blocking that would block most Tuesdays.
    """
    folder = _fake_meeting(tmp_path, {})
    # make trial_score neutral for 7 of every 10 runners by rewriting in place
    for p in folder.glob("Race_*_Logic.json"):
        d = json.loads(p.read_text(encoding="utf-8"))
        for i, h in enumerate(d["horses"].values()):
            if i % 10 < 7:
                h["python_auto"]["feature_scores"]["trial_score"] = 60.0
        p.write_text(json.dumps(d), encoding="utf-8")
    result = _gate(folder)
    assert result.returncode == 0, (
        "細場次稀疏被攔住 —— 咁樣個閘會被人關掉\n" + result.stdout[-600:])


def test_a_healthy_meeting_passes(tmp_path):
    assert _gate(_fake_meeting(tmp_path, {})).returncode == 0


def test_the_schedule_actually_calls_the_gate():
    """靜態守衛：`step_dashboard` 一定要喺發佈之前叫 `check_data_contract`。

    個閘本身正確但冇人叫，等於冇閘 —— 而呢個係最容易喺重構之中靜靜消失嘅嘢。
    """
    sched = (ROOT / ".agents" / "skills" / "au_racing" / "au_daily_auto"
             / "au_daily_schedule.py").read_text(encoding="utf-8")
    assert "def check_data_contract(" in sched
    body = sched.split("def step_dashboard(", 1)[1].split("\ndef ", 1)[0]
    assert "check_data_contract(" in body, "step_dashboard 冇叫發佈閘"
    gate_at = body.index("check_data_contract(")
    validate_at = body.index("validate_snapshot(")
    assert gate_at < validate_at, "欄位閘要喺 snapshot 驗證之前跑"
