"""L3 假設驗證：只用 born 之後、預先寫死嘅門檻、判一次就鎖、唔夠數保持盲。"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))

import hypothesis_judge as J  # noqa: E402


def _rows(days, per_day, hit_rate, p=0.3, cohort="tag:A", start="2026-12-01", seed=0):
    rng = np.random.default_rng(seed)
    d0 = date.fromisoformat(start)
    return [{"date": (d0 + timedelta(days=i)).isoformat(), "y": int(rng.random() < hit_rate), "p": p, "cohorts": {cohort}}
            for i in range(days) for _ in range(per_day)]


H = {"id": "H1", "domain": "au", "born": "2026-11-30", "cohort": ["tag:A"], "direction": "model_under", "state": "watching"}


def test_not_enough_stays_blind():
    out = J.judge(H, _rows(20, 20, 0.5))
    assert out["state"] == "watching" and "result" not in out and out["progress"]["days"] == 20


def test_supported_rejected_undecided():
    assert J.judge(H, _rows(40, 70, 0.45))["state"] == "supported"          # +15pp
    assert J.judge(H, _rows(40, 70, 0.30, seed=1))["state"] == "rejected"   # 0pp，n=2800 夠功效
    assert J.judge(H, _rows(40, 70, 0.33, seed=4))["state"] == "undecided"  # +3pp：CI 跨 3pp
    over = dict(H, direction="model_over")
    assert J.judge(over, _rows(40, 70, 0.15, seed=2))["state"] == "supported"  # −15pp，方向啱


def test_power_sample_size_blocks_early_judgement():
    out = J.judge(H, _rows(40, 20, 0.30))           # n=800 < 功效樣本量（p=0.3 → ~1,830）
    assert out["state"] == "watching" and out["progress"]["need_n"] > 1800


def test_cohort_must_match_all_atoms():
    h = dict(H, cohort=["tag:A", "days:休 ≥90 日"])
    assert J.judge(h, _rows(40, 20, 0.6))["progress"]["n"] == 0


def test_run_locks_and_only_uses_after_born(tmp_path, monkeypatch):
    monkeypatch.setenv("WONGCHOI_CONTROL_STATE_ROOT", str(tmp_path))
    led = tmp_path / "learning" / "hypotheses.jsonl"
    led.parent.mkdir(parents=True)
    hs = [H, dict(H, id="H2", state="covered"), dict(H, id="H3", born="2027-01-20")]
    led.write_text("".join(json.dumps(h, ensure_ascii=False) + "\n" for h in hs))
    seen = []

    def fake(domain, since, until):
        seen.append((domain, since, until))
        return [r for r in _rows(40, 70, 0.45) if since < r["date"] <= until]
    r = J.run("2027-01-15", rows_fn=fake)
    assert [h["id"] for h in r["judged"]] == ["H1"] and seen == [("au", "2026-11-30", "2027-01-15")]
    rows = {json.loads(x)["id"]: json.loads(x) for x in led.read_text().splitlines()}
    assert rows["H1"]["state"] == "supported" and rows["H1"]["judged_at"] == "2027-01-15"
    assert rows["H2"]["state"] == "covered" and "progress" not in rows["H3"]      # 未出世夠／唔係 watching 唔郁
    calls = []
    r2 = J.run("2027-01-25", rows_fn=lambda *a: calls.append(a) or [])
    assert r2["judged"] == [] and [c[1] for c in calls] == ["2027-01-20"]        # 只有 H3 會讀；H1 已鎖唔再判
    assert "支持" in J.telegram_text(r["judged"]) and "唔會自動改模型" in J.telegram_text(r["judged"])


def test_concurrent_edit_not_overwritten(tmp_path, monkeypatch):
    monkeypatch.setenv("WONGCHOI_CONTROL_STATE_ROOT", str(tmp_path))
    led = tmp_path / "learning" / "hypotheses.jsonl"
    led.parent.mkdir(parents=True)
    led.write_text(json.dumps(H, ensure_ascii=False) + "\n")

    def fake(domain, since, until):      # 計緊嗰陣有人將 H1 改咗 covered
        led.write_text(json.dumps(dict(H, state="covered"), ensure_ascii=False) + "\n")
        return [r for r in _rows(40, 70, 0.45) if since < r["date"] <= until]
    r = J.run("2027-01-15", rows_fn=fake)
    assert r["judged"] == [] and json.loads(led.read_text())["state"] == "covered"
