"""AI 覆盤解讀（L2）：抽 JSON、Python 核事實、假設語法、入帳狀態、輸出。唔會真叫 Gemini／Claude。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))

import review_ai as R  # noqa: E402

REVIEW = {"summary": {"races": 9, "slots": 27, "model_top3_hits": 12, "market_top3_hits": 13, "model_top1_wins": 1,
                      "fav_wins": 2, "winner_in_model_top5": 4, "model_logloss_top3": 0.5478},
          "meetings": [{"races": [{"under": [{"name": "合夥飛馳", "rank": 10, "pos": 1}]}], "over_total": 15,
                        "over_with_incident": 5}],
          "cohorts": [{"cohort": "tag:騎師此程弱", "today_hits": 9, "today_n": 19, "today_resid_pp": 27.8,
                       "trail_model_resid_pp": -2.1},
                      {"cohort": "days:休 ≥90 日", "today_hits": 1, "today_n": 6},
                      {"cohort": "model:模型獨家睇好（模型頭三、SP 第 6+；用賽後 SP 分組，只做評估）", "today_hits": 1,
                       "today_n": 5}]}


def test_json_from_handles_fences_and_noise():
    assert R._json_from('```json\n{"a": 1}\n```') == {"a": 1}
    assert R._json_from('好嘅：{"a": 2} 完') == {"a": 2}
    assert R._json_from("冇 JSON") is None


def test_fact_check_drops_invented_numbers_and_names():
    text = ("今晚模型頭三入前三 12/27，市場 13/27。「合夥飛馳」由第 10 跑出贏。"
            "「騎師此程弱」組別今晚偏差 +27.8pp。「虛構馬」其實好勁。模型 log-loss 0.9999 好差。")
    kept, dropped = R.fact_check(text, REVIEW)
    assert "12/27" in kept and "合夥飛馳" in kept and "+27.8pp" in kept
    assert len(dropped) == 2 and any("虛構馬" in d for d in dropped) and any("0.9999" in d for d in dropped)


def test_hypothesis_grammar():
    hyps = [{"title": "a", "cohort": ["tag:騎師此程弱"], "direction": "model_under"},
            {"title": "b", "cohort": ["tag:唔存在"], "direction": "model_under"},
            {"title": "c", "cohort": ["model:模型獨家睇好（模型頭三、SP 第 6+；用賽後 SP 分組，只做評估）"], "direction": "model_over"},
            {"title": "d", "cohort": ["tag:騎師此程弱", "days:休 ≥90 日", "tag:x"], "direction": "model_over"}]
    ok, bad = R.check_hypotheses(hyps, REVIEW)
    assert [h["title"] for h in ok] == ["a"]
    assert {h["title"]: h["rejected"] for h in bad} == {"b": "條件唔喺當日組別清單", "c": "用賽後 SP 分組（洩漏）"}
    ok, bad = R.check_hypotheses([{"title": "e", "cohort": ["tag:騎師此程弱"], "direction": "sideways"}], REVIEW)
    assert not ok and bad[0]["rejected"] == "方向唔合法"


def test_register_states_and_dedupe(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "ledger_path", lambda: tmp_path / "learning" / "hypotheses.jsonl")
    hyps = [{"title": "new", "cohort": ["tag:騎師此程弱"], "direction": "model_under",
             "review": {"leak": False, "worth": True, "done_before": None}},
            {"title": "old", "cohort": ["days:休 ≥90 日"], "direction": "model_over",
             "review": {"leak": False, "worth": True, "done_before": "EXP-20261126-02"}},
            {"title": "leaky", "cohort": ["tag:x"], "direction": "model_over", "review": {"leak": True, "worth": True}},
            {"title": "meh", "cohort": ["tag:y"], "direction": "model_over", "review": {"leak": False, "worth": False}}]
    assert R.register("hkjc", "2026-11-25", hyps) == 2
    rows = [json.loads(x) for x in (tmp_path / "learning" / "hypotheses.jsonl").read_text().splitlines()]
    assert {r["title"]: r["state"] for r in rows} == {"new": "watching", "old": "covered"}
    assert R.register("hkjc", "2026-11-26", hyps) == 0          # 同條件唔重複入帳


def test_render_and_telegram():
    r = {"domain": "hkjc", "date": "2026-11-25", "narrative": "今晚一般。", "dropped_sentences": ["x"], "registered": 1,
         "hypotheses": [{"title": "騎師此程弱被低估", "cohort": ["tag:騎師此程弱"], "direction": "model_under",
                         "review": {"leak": False, "worth": True, "done_before": None, "note": "值得"}}]}
    md = R.render_md(r)
    assert "🤖 AI 解讀" in md and "核實刪咗 1 句" in md and "✅ 值得驗證" in md and "模型低估" in md
    tg = R.telegram_text(r)
    assert "香港賽馬 AI 覆盤解讀" in tg and "值得之後驗證：騎師此程弱被低估" in tg


def test_daily_gemini_failure_does_not_raise(tmp_path, monkeypatch):
    (tmp_path / "2026-11-25.json").write_text(json.dumps(REVIEW, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(R, "run_gemini", lambda d, p, timeout=600: (None, "429"))
    r = R.daily("hkjc", "2026-11-25", out_dir=tmp_path)
    assert r["status"] == "gemini_failed" and (tmp_path / "2026-11-25.ai.json").exists()


def test_spawn_is_off_under_pytest(monkeypatch):
    called = []
    monkeypatch.setattr(R.subprocess, "Popen", lambda *a, **k: called.append(a))
    R.spawn_daily("au", "2026-11-25")
    assert called == []


def test_weekly_job_registered():
    root = HERE.parents[4]
    fresh = (root / ".agents/scripts/job_freshness.py").read_text(encoding="utf-8")
    assert '"central-wong-choi.review-weekly"' in fresh
    assert (root / ".agents/skills/central_wong_choi/launchd/com.antigravity.central-wong-choi.review-weekly.plist.template").exists()


# Sol 覆核 2026-11-26 追加

def test_fact_check_sign_and_urls():
    review = dict(REVIEW, cohorts=REVIEW["cohorts"] + [{"cohort": "tag:x", "today_hits": 1, "today_n": 2, "trail_model_resid_pp": -5.9}])
    kept, dropped = R.fact_check("跨日 -5.9pp。跌咗 5.9pp。跨日 +5.9pp。詳情 https://evil.example。", review)
    assert "-5.9pp" in kept and "跌咗 5.9pp" in kept
    assert any("+5.9pp" in d for d in dropped) and any("https" in d for d in dropped)


def test_cohort_must_be_list():
    ok, bad = R.check_hypotheses([{"title": "s", "cohort": "tag:騎師此程弱", "direction": "model_under"},
                                  {"title": "m", "cohort": ["tag:騎師此程弱", 3], "direction": "model_under"}], REVIEW)
    assert not ok and {b["rejected"] for b in bad} == {"條件格式唔啱（要字串清單）"}


def test_register_needs_explicit_verdict_and_born_is_registration_day(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "ledger_path", lambda: tmp_path / "hypotheses.jsonl")
    hyps = [{"title": "no-leak-field", "cohort": ["tag:a"], "direction": "model_under", "review": {"worth": True}},
            {"title": "ok", "cohort": ["tag:b"], "direction": "model_under", "review": {"leak": False, "worth": True}}]
    assert R.register("au", "2026-11-01", hyps, today="2026-11-26") == 1
    row = json.loads((tmp_path / "hypotheses.jsonl").read_text())
    assert row["born"] == "2026-11-26" and row["source_day"] == "2026-11-01" and row["id"] == "H-au-2026-11-01-1"


def test_daily_lock_and_done_skip(tmp_path, monkeypatch):
    (tmp_path / "2026-11-25.json").write_text(json.dumps(REVIEW, ensure_ascii=False), encoding="utf-8")
    (tmp_path / ".2026-11-25.ai.lock").write_text("")
    assert R.daily("hkjc", "2026-11-25", out_dir=tmp_path)["status"] == "busy"
    (tmp_path / ".2026-11-25.ai.lock").unlink()
    (tmp_path / "2026-11-25.ai.json").write_text(json.dumps({"status": "ok"}))
    monkeypatch.setattr(R, "run_gemini", lambda *a, **k: (_ for _ in ()).throw(AssertionError("唔應該再跑")))
    assert "skipped" in R.daily("hkjc", "2026-11-25", out_dir=tmp_path)


def test_weekly_failure_is_not_fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(R.PR, "output_dir", lambda d: tmp_path / "reviews" / d)
    monkeypatch.setattr(R, "_claude", lambda *a, **k: ("", "quota"))
    R.weekly(today="2026-11-30")
    assert not list((tmp_path / "reviews" / "weekly").glob("*.json"))
    assert (tmp_path / "reviews" / "weekly" / "2026-11-30.failed.log").exists()


def test_claude_is_locked_down(monkeypatch):
    seen = {}

    class P:
        returncode, stdout, stderr = 0, json.dumps({"result": "{}"}), ""
    monkeypatch.setattr(R.shutil, "which", lambda *a, **k: "/bin/claude")
    monkeypatch.setattr(R.subprocess, "run", lambda cmd, **k: seen.update(cmd=cmd, cwd=k.get("cwd")) or P())
    R._claude("hi", "sonnet", read_dirs=(Path("/repo/docs/experiments"),))
    cmd = seen["cmd"]
    assert "--strict-mcp-config" in cmd and cmd[cmd.index("--tools") + 1:cmd.index("--tools") + 4] == ["Read", "Grep", "Glob"]
    assert "--add-dir" in cmd and "Bash" in cmd[cmd.index("--disallowedTools"):]
    assert "review_ai_claude_" in seen["cwd"]                     # 唔喺 repo 入面跑


def test_spawn_launches_when_scheduled(monkeypatch, tmp_path):
    called = []
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("WC_DISABLE_REVIEW_AI", raising=False)
    monkeypatch.setattr(R.PR, "output_dir", lambda d: tmp_path / d)
    monkeypatch.setattr(R.subprocess, "Popen", lambda cmd, **k: called.append((cmd, k.get("start_new_session"))))
    R.spawn_daily("nba", "2026-11-25")
    (cmd, detached), = called
    assert cmd[-6:] == ["daily", "--domain", "nba", "--date", "2026-11-25", "--telegram"] and detached
