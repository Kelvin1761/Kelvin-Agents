"""每週健康巡查：原文區塊、Python 核實（剔走 AI 講錯）、輸出。唔會真叫 AI。"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))

import health_sweep as H  # noqa: E402

SAMPLE = {"id": "au|M|R1|3", "platform": "au", "horse": "Irish Master",
          "raw": "【Racecard】\n3. Irish Master (6)\nTrainer: Mark & Levi Kavanagh | Jockey: Joe Bowditch | Weight: 59.5kg",
          "ours": {"barrier": 6, "weight": 58.5, "jockey": "Joe Bowditch", "trainer": "Mark & Levi Kavanagh"}}
HEALTH = {"au": [{"week": "2026-W48", "source": "leaf", "field": "trial_score", "fill_rate": 0.4},
                 {"week": "2026-W45", "source": "leaf", "field": "trial_score", "fill_rate": 0.95}], "hkjc": []}


def test_block_extracts_one_horse():
    text = "1. A (1)\nx\n2. B (2)\ny\n3. C (3)\nz\n10. J (10)\nj\n11. K (11)\nk"
    assert H._block(text, r"^2\. ", r"^\d+\. ") == "2. B (2)\ny\n"
    assert H._block(text, r"^10\. ", r"^\d+\. ") == "10. J (10)\nj\n"        # 兩位數馬號（Sol）
    assert H._block(text, r"^1\. ", r"^\d+\. ") == "1. A (1)\nx\n"
    assert H._block(text, r"^9\. ", r"^\d+\. ") is None


def test_verify_keeps_only_grounded_mismatches():
    res = {"spot_checks": [
        {"id": "au|M|R1|3", "field": "weight", "ours": "58.5", "raw": "Weight: 59.5kg", "verdict": "mismatch"},   # 真
        {"id": "au|M|R1|3", "field": "jockey", "ours": "Joe Bowditch", "raw": "Jockey: Someone Else", "verdict": "mismatch"},  # 原文冇
        {"id": "au|M|R1|3", "field": "barrier", "ours": "7", "raw": "(6)", "verdict": "mismatch"},                   # 我哋唔係 7
        {"id": "au|X|R9|1", "field": "weight", "ours": "1", "raw": "x", "verdict": "mismatch"},                      # 樣本唔存在
        {"id": "au|M|R1|3", "field": "trainer", "verdict": "unclear"}],
        "field_health": [{"platform": "au", "field": "trial_score (leaf)", "issue": "由 0.95 跌到 0.4"},
                         {"platform": "au", "field": "trial_score", "issue": "由 0.95 跌到 0.12"},
                         {"platform": "au", "field": "made_up", "issue": "x"}]}
    v = H.verify(res, [SAMPLE], HEALTH)
    assert [c["field"] for c in v["confirmed_mismatches"]] == ["weight"]
    assert len(v["rejected_claims"]) == 3 and len(v["unclear"]) == 1
    assert [t["issue"] for t in v["trend_flags"]] == ["由 0.95 跌到 0.4"] and len(v["rejected_trends"]) == 2


def test_outputs():
    ok = {"status": "ok", "date": "2026-11-30", "window": ["2026-11-23", "2026-11-30"], "samples": 40, "checked_by": "Hydrogen",
          "confirmed_mismatches": [], "rejected_claims": [], "unclear": [], "trend_flags": []}
    assert "全部對得上" in H.telegram_text(ok)
    bad = dict(ok, confirmed_mismatches=[{"id": "au|M|R1|3", "field": "weight", "ours_actual": 58.5, "raw": "59.5kg"}])
    assert "要 Opus 跟進" in H.telegram_text(bad) and "59.5kg" in H.render_md(bad)
    assert "AI 巡查失敗" in H.telegram_text({"status": "ai_failed", "error": "429"})


def test_empty_quote_is_not_confirmation():
    res = {"spot_checks": [{"id": "au|M|R1|3", "field": "weight", "ours": "58.5", "raw": "", "verdict": "mismatch"}]}
    v = H.verify(res, [SAMPLE], HEALTH)
    assert not v["confirmed_mismatches"] and v["rejected_claims"]


def test_no_samples_not_ok(monkeypatch):
    monkeypatch.setattr(H, "sample_platform", lambda *a, **k: ([], {}))
    monkeypatch.setattr(H, "field_health_table", lambda p: [])
    monkeypatch.setattr(H, "run_ai", lambda *a, **k: (_ for _ in ()).throw(AssertionError("唔應該叫 AI")))
    assert H.build(5, 1, "2026-11-30")["status"] == "no_samples"


def test_telegram_strips_urls():
    bad = {"status": "ok", "samples": 2, "checked_by": "Hydrogen", "trend_flags": [],
           "confirmed_mismatches": [{"id": "x", "field": "weight", "ours_actual": 1, "raw": "see https://evil.example/x"}]}
    assert "https" not in H.telegram_text(bad) and "網址已刪" in H.telegram_text(bad)


def test_luna_fallback_uses_codex_provider(monkeypatch, tmp_path):
    """Gemini 失敗退 Luna 一定要 `--provider codex`（`run quick` 預設係 Hydrogen low）。"""
    calls = []

    class P:
        returncode, stdout, stderr = 1, "", "fail"
    monkeypatch.setattr(H.subprocess, "run", lambda cmd, **k: calls.append(cmd) or P())
    H.run_ai({"spot_checks": [], "field_health": {}})
    assert [c[c.index("run") + 1] for c in calls] == ["third", "quick"]
    assert "--provider" not in calls[0] and calls[1][calls[1].index("--provider") + 1] == "codex"
