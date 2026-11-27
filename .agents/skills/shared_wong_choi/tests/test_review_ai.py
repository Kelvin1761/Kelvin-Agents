"""AI 覆盤解讀（L2）：抽 JSON、Python 核事實、假設語法、入帳狀態、輸出。唔會真叫 Gemini／Claude。"""
from __future__ import annotations

import json
import sys
import pytest
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))

import review_ai as R  # noqa: E402

@pytest.fixture(autouse=True)
def isolate_control_state(tmp_path, monkeypatch):
    monkeypatch.setenv("WONGCHOI_CONTROL_STATE_ROOT", str(tmp_path / "control"))

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


def test_weekly_runs_judge_then_gap_report(monkeypatch, tmp_path):
    order = []
    import hypothesis_judge as HJ
    import gap_report as GR
    monkeypatch.setattr(R.PR, "output_dir", lambda d: tmp_path / "reviews" / d)
    monkeypatch.setattr(HJ, "run", lambda today, telegram=False: order.append(("judge", today)) or {"judged": []})
    monkeypatch.setattr(GR, "build", lambda today: order.append(("gap", today)) or {})
    monkeypatch.setattr(GR, "write", lambda r: tmp_path / "gap.json")
    monkeypatch.setattr(R, "_claude", lambda prompt, *a, **k: (order.append(("opus", "改善空間" in prompt)) or ("總結", "")))
    R.weekly(today="2026-11-30")
    assert order == [("judge", "2026-11-30"), ("gap", "2026-11-30"), ("opus", True)]


def test_sol_and_fallback_subprocess(monkeypatch):
    h = {"cohort": ["tag:x"], "direction": "model_under"}
    answer = json.dumps({"reviews": [{"i": 0, "leak": False, "worth": True}]})
    calls = []
    class P:
        returncode, stdout, stderr = 0, "", ""
    def run(cmd, **kwargs):
        calls.append(cmd)
        Path(cmd[cmd.index("--out") + 1]).write_text(answer)
        assert "不可信資料" in Path(cmd[cmd.index("--prompt-file") + 1]).read_text()
        return P()
    monkeypatch.setattr(R.subprocess, "run", run)
    reviewed, reviewer, err = R.review_hypotheses("au", "2026-11-26", [h])
    assert reviewer == "sol" and not err and reviewed[0]["review"]["worth"]
    assert calls[0][calls[0].index("--cd") + 1] != str(R.REPO)
    monkeypatch.setattr(R, "sol_review", lambda *a: ([], "quota"))
    monkeypatch.setattr(R, "_claude", lambda *a, **k: (answer, ""))
    reviewed, reviewer, err = R.review_hypotheses("au", "2026-11-26", [h])
    assert reviewer == "sonnet" and not err and reviewed[0]["review"]["worth"]


def test_daily_pending_and_retry_old_file(tmp_path, monkeypatch):
    root = tmp_path / "reviews"
    monkeypatch.setattr(R.PR, "output_dir", lambda domain: root / domain)
    monkeypatch.setattr(R, "ledger_path", lambda: tmp_path / "hypotheses.jsonl")
    out = root / "hkjc"
    out.mkdir(parents=True)
    (out / "2026-11-25.json").write_text(json.dumps(REVIEW))
    hyp = {"title": "x", "cohort": ["tag:騎師此程弱"], "direction": "model_under"}
    monkeypatch.setattr(R, "run_gemini", lambda *a: ({"hypotheses": [hyp]}, ""))
    monkeypatch.setattr(R, "sol_review", lambda *a: ([], "sol failed"))
    monkeypatch.setattr(R, "sonnet_review", lambda *a: ([], "sonnet failed"))
    result = R.daily("hkjc", "2026-11-25", out_dir=out)
    assert result["status"] == "partial" and result["review_pending"] and result["hypotheses"] == [hyp]
    path = out / "2026-11-25.ai.json"
    old = json.loads(path.read_text())
    old.pop("review_pending")
    old["sonnet_error"] = "usage_limit_reached"
    path.write_text(json.dumps(old))
    monkeypatch.setattr(R, "sol_review", lambda d, day, hs: ([dict(h, review={"leak": False, "worth": True}) for h in hs], ""))
    assert R.retry_pending(today="2026-11-27", root=out)["healed"] == 1
    assert R.retry_pending(today="2026-11-27", root=out)["retried"] == 0
    assert json.loads(path.read_text())["reviewer"] == "sol"
    entries = [json.loads(x) for x in (tmp_path / "hypotheses.jsonl").read_text().splitlines()]
    assert len(entries) == 1 and entries[0]["source"] == "gemini+sol"


def test_void_locked_and_judge_skips(tmp_path, monkeypatch):
    import hypothesis_judge as J
    path = tmp_path / "hypotheses.jsonl"
    path.write_text(json.dumps({"id": "H-nba-2026-11-26-1", "state": "watching", "domain": "nba", "born": "2026-11-26"}) + "\n")
    monkeypatch.setattr(R, "ledger_path", lambda: path)
    monkeypatch.setattr(J, "ledger_path", lambda: path)
    assert R.void_hypothesis("H-nba-2026-11-26-1", "收盤價洩漏")
    assert json.loads(path.read_text())["void_reason"] == "收盤價洩漏"
    assert J.run("2026-11-27", rows_fn=lambda *a: (_ for _ in ()).throw(AssertionError()))["watching"] == 0


def test_pending_persisted_before_reviewer_and_force_failure(tmp_path, monkeypatch):
    day = "2026-11-25"
    (tmp_path / f"{day}.json").write_text(json.dumps(REVIEW))
    hyp = {"cohort": ["tag:騎師此程弱"], "direction": "model_under"}
    monkeypatch.setattr(R, "run_gemini", lambda *a: ({"hypotheses": [hyp]}, ""))
    def interrupt(*args):
        assert json.loads((tmp_path / f"{day}.ai.json").read_text())["review_pending"]
        raise RuntimeError("interrupted")
    monkeypatch.setattr(R, "review_hypotheses", interrupt)
    import pytest
    with pytest.raises(RuntimeError):
        R.daily("hkjc", day, out_dir=tmp_path)
    monkeypatch.setattr(R, "retry_pending", lambda **kwargs: {})
    monkeypatch.setattr(R, "run_gemini", lambda *a: (None, "failed"))
    assert R.daily("hkjc", day, out_dir=tmp_path, force=True)["status"] == "partial"


def test_retry_legacy_isolation_and_limits(tmp_path, monkeypatch):
    monkeypatch.setenv("WONGCHOI_CONTROL_STATE_ROOT", str(tmp_path))
    monkeypatch.setattr(R.PR, "output_dir", lambda d: (_ for _ in ()).throw(AssertionError("production path")))
    monkeypatch.setattr(R, "ledger_path", lambda: tmp_path / "ledger.jsonl")
    calls = []
    monkeypatch.setattr(R, "sol_review", lambda d, day, hs: (calls.extend(hs) or [], "failed"))
    monkeypatch.setattr(R, "sonnet_review", lambda *a: ([], "failed"))
    for day, cohort in [("2026-11-20", "fav:old"), ("2026-11-21", "family:x"), ("2026-11-22", "family:y"), ("2026-10-01", "family:z")]:
        (tmp_path / f"{day}.ai.json").write_text(json.dumps({"domain": "tennis", "status": "partial", "hypotheses": [{"cohort": [cohort], "direction": "model_under"}]}))
    counts = R.retry_pending(today="2026-11-27", root=tmp_path, max_files=2)
    assert counts["retried"] == 2 and len(calls) == 1 and counts["too_old"]
    assert json.loads((tmp_path / "2026-11-20.ai.json").read_text())["rejected_hypotheses"][0]["rejected"] == "舊版組別可能用咗賽後價"
    assert R.retry_pending(today="2026-11-27")["retried"] == 0


def test_register_dedupes_cohort_elements(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "ledger_path", lambda: tmp_path / "ledger")
    h = {"cohort": ["tag:a", "tag:a"], "direction": "model_under", "review": {"leak": False, "worth": True}}
    assert R.register("au", "2026-11-25", [h]) == 1
    assert R.register("au", "2026-11-25", [dict(h, cohort=["tag:a"])]) == 0
    assert json.loads((tmp_path / "ledger").read_text())["cohort"] == ["tag:a"]


def test_sol_receives_only_sanitized_fields(monkeypatch):
    class P:
        returncode, stdout, stderr = 0, "", ""
    def run(cmd, **kwargs):
        work = Path(cmd[cmd.index("--cd") + 1])
        assert work != R.REPO and (work / "docs/experiments/INDEX.md").is_file()
        prompt = Path(cmd[cmd.index("--prompt-file") + 1]).read_text()
        assert "SECRET_EXTRA" not in prompt and "X" * 81 not in prompt and "Y" * 301 not in prompt
        Path(cmd[cmd.index("--out") + 1]).write_text(json.dumps({"reviews": [{"i": 0, "leak": False, "worth": True}]}))
        return P()
    monkeypatch.setattr(R.subprocess, "run", run)
    hyp = {"cohort": ["tag:a"], "direction": "model_under", "title": "X" * 100, "why": "Y" * 400, "extra": "SECRET_EXTRA"}
    assert not R.sol_review("au", "2026-11-25", [hyp])[1]


def test_unknown_cohort_cannot_reach_reviewer(monkeypatch):
    monkeypatch.setattr(R, "sol_review", lambda *a: (_ for _ in ()).throw(AssertionError("leak")))
    reviewed, _, error = R.review_hypotheses("tennis", "2026-11-25", [{"cohort": ["close:price"]}])
    assert not error and reviewed[0]["review"]["leak"] is True
