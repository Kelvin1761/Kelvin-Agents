"""練馬師剩餘表現表版本化＋shadow＋自動回退（EXP-20261125-08）。"""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import au_residual_shadow as shadow  # noqa: E402
import au_residual_versions as V  # noqa: E402
from au_racing_engine import people_overlays as P  # noqa: E402


def _payload(table, as_of, built="x"):
    return json.dumps({"experiment": "EXP-20261122-02", "built_at": built, "as_of": as_of, "trainers": table},
                      ensure_ascii=False).encode("utf-8")


T1 = {"jackbruce": [["2026-11-01", 5.0, 50]], "bob": [["2026-11-01", -2.0, 40]]}
T2 = {"jackbruce": [["2026-11-01", 5.0, 50], ["2026-11-02", 6.0, 55]], "bob": [["2026-11-01", -2.0, 40]]}   # 純追加
T2_REWRITE = {"jackbruce": [["2026-11-01", 9.0, 50], ["2026-11-02", 6.0, 55]], "bob": [["2026-11-01", -2.0, 40]]}
NOW1 = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)   # 悉尼 11-01 晚
NOW2 = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.delenv("WC_AU_TRAINER_RESIDUAL_TABLE", raising=False)
    monkeypatch.setattr(P, "_data_root", lambda: tmp_path)
    P._resolve_pointer.cache_clear()
    return tmp_path


def _write_live(root, data):
    live = root / P.TABLE_NAME
    live.write_bytes(data)
    return live


# ── 指針解析 ／ 向後兼容 ──

def test_no_pointer_reads_live_file_exactly_as_before(root):
    live = _write_live(root, _payload(T1, "2026-11-01"))
    assert P.default_table_path() == live
    assert P.load_table() == T1


def test_env_override_ignores_pointer(root, tmp_path, monkeypatch):
    live = _write_live(root, _payload(T1, "2026-11-01"))
    V.commit(live, live.read_bytes(), as_of="2026-11-01", now=NOW1)
    other = tmp_path / "other.json"
    monkeypatch.setenv("WC_AU_TRAINER_RESIDUAL_TABLE", str(other))
    assert P.default_table_path() == other


def test_pointer_resolves_to_version_with_identical_bytes(root):
    data = _payload(T1, "2026-11-01")
    live = _write_live(root, data)
    out = V.commit(live, data, as_of="2026-11-01", now=NOW1)
    assert out["action"] == "activated"
    resolved = P.default_table_path()
    assert resolved != live and resolved.read_bytes() == data == live.read_bytes()
    ptr = json.loads((root / "AU_Trainer_Residual.active.json").read_text())
    assert ptr["sha256"] == hashlib.sha256(data).hexdigest() and ptr["version"].startswith("2026-11-01-")


def test_bad_sha_or_missing_file_falls_back_to_live(root):
    data = _payload(T1, "2026-11-01")
    live = _write_live(root, data)
    V.commit(live, data, as_of="2026-11-01", now=NOW1)
    ptr_path = root / "AU_Trainer_Residual.active.json"
    ptr = json.loads(ptr_path.read_text())
    ptr["sha256"] = "0" * 64
    ptr_path.write_text(json.dumps(ptr))
    P._resolve_pointer.cache_clear()
    assert P.default_table_path() == live
    ptr_path.write_text("{not json")
    P._resolve_pointer.cache_clear()
    assert P.default_table_path() == live


def test_same_bytes_is_noop_and_append_is_not_shadowed(root):
    d1, d2 = _payload(T1, "2026-11-01"), _payload(T2, "2026-11-02")
    live = _write_live(root, d1)
    V.commit(live, d1, as_of="2026-11-01", now=NOW1)
    assert V.commit(live, d1, as_of="2026-11-01", now=NOW1)["action"] == "unchanged"
    out = V.commit(live, d2, as_of="2026-11-02", now=NOW2)
    assert out["history_rewritten"] is False
    ptr = V.load_pointer(live)
    assert ptr["history"][-1]["shadow"] == "not_needed" and ptr["previous"]["as_of"] == "2026-11-01"


def test_rewrite_is_flagged_for_shadow(root):
    d1, d2 = _payload(T1, "2026-11-01"), _payload(T2_REWRITE, "2026-11-02")
    live = _write_live(root, d1)
    V.commit(live, d1, as_of="2026-11-01", now=NOW1)
    assert V.commit(live, d2, as_of="2026-11-02", now=NOW2)["history_rewritten"] is True
    assert V.load_pointer(live)["history"][-1]["shadow"] == "pending"


def test_prune_keeps_n_and_protected(root):
    live = root / P.TABLE_NAME
    for i in range(20):
        t = {"a": [[f"2026-10-{j + 1:02d}", float(j), j] for j in range(i + 1)]}
        V.commit(live, _payload(t, f"2026-10-{i + 1:02d}"), as_of=f"2026-10-{i + 1:02d}", now=NOW1, keep=5)
    files = list((root / "AU_Trainer_Residual.versions").glob("*.json"))
    assert len(files) == 5
    ptr = V.load_pointer(live)
    names = {f.name for f in files}
    assert Path(ptr["file"]).name in names and Path(ptr["previous"]["file"]).name in names


def test_rollback_flips_pointer_pins_and_never_deletes(root):
    d1, d2, d3 = _payload(T1, "2026-11-01"), _payload(T2_REWRITE, "2026-11-02"), _payload(T2_REWRITE, "2026-11-03", "y")
    live = _write_live(root, d1)
    v1 = V.commit(live, d1, as_of="2026-11-01", now=NOW1)["version"]
    V.commit(live, d2, as_of="2026-11-02", now=NOW2)
    before = sorted(p.name for p in (root / "AU_Trainer_Residual.versions").iterdir())
    V.rollback(live, to_version=v1, reason="test")
    P._resolve_pointer.cache_clear()
    assert P.default_table_path().read_bytes() == d1
    assert sorted(p.name for p in (root / "AU_Trainer_Residual.versions").iterdir()) == before
    assert V.commit(live, d3, as_of="2026-11-03", now=NOW2)["action"] == "saved_while_pinned"
    P._resolve_pointer.cache_clear()
    assert P.default_table_path().read_bytes() == d1      # 鎖定：新重建唔啟用
    events = [json.loads(x)["event"] for x in (root / "AU_Trainer_Residual.events.jsonl").read_text().splitlines()]
    assert "rollback" in events and "saved_while_pinned" in events
    assert V.unpin(live, actor="t")["action"] == "unpinned"
    assert V.load_pointer(live)["pinned"] is False


# ── 判法（合成數據） ──

def _w(version, prev, pt, lo):
    return {"version": version, "previous": {"version": prev}, "result": {"dlogloss": [pt, lo, lo + 0.01]}}


def test_decide_ci_lower_above_zero():
    assert shadow.decide([_w("v2", "v1", 0.002, 0.0005)]) == {"rule": "ci_lower_above_0", "failed": ["v2"], "to": "v1"}
    assert shadow.decide([_w("v2", "v1", 0.002, -0.0005)]) is None


def test_decide_three_consecutive_points():
    ws = [_w("v2", "v1", 0.001, -0.001), _w("v2", "v1", 0.001, -0.001), _w("v3", "v2", 0.001, -0.001)]
    assert shadow.decide(ws) == {"rule": "three_consecutive_worse", "failed": ["v2", "v3"], "to": "v1"}
    assert shadow.decide(ws[:2]) is None
    broken = [ws[0], _w("v2", "v1", -0.001, -0.002), ws[1], ws[2]]
    assert shadow.decide(broken) is None     # 中間一個好咗 = 唔連續（最尾三個 −,+,+ 唔算）
    empty = {"version": "v9", "previous": {"version": "v8"}, "result": {"dlogloss": None}}
    assert shadow.decide([ws[0], empty, ws[1], ws[2]])["rule"] == "three_consecutive_worse"   # 冇差異唔打斷
    assert shadow.decide([{**w, "acted": True} for w in ws]) is None   # 已回退過唔再計


def test_window_days_strictly_after_activation():
    races = [{"date": d} for d in ("2026-11-01", "2026-11-02", "2026-11-03", "2026-11-05")]
    assert shadow.window_days(races, "2026-11-02", 7) == ["2026-11-03", "2026-11-05"]


def test_overlay_matches_engine_and_ignores_future_entries():
    table = {"jackbruce": [["2026-11-01", 5.0, 50], ["2026-11-10", 999.0, 51]], "bob": [["2026-11-01", -2.0, 40]]}
    field = ["jackbruce", "bob"]
    assert shadow.overlay("jackbruce", field, "2026-11-10", table) == P.trainer_feature("jackbruce", field, "2026-11-10", table)
    clean = {"jackbruce": [["2026-11-01", 5.0, 50]], "bob": table["bob"]}
    # 賽日（11-10）同日或之後嘅紀錄唔准用：有冇嗰筆未來紀錄，結果一樣
    assert shadow.overlay("jackbruce", field, "2026-11-10", table) == shadow.overlay("jackbruce", field, "2026-11-10", clean)


def _race(date, i, good):
    # 三匹入三甲；good 練馬師嗰兩匹入，bad 嗰兩匹唔入
    rows = []
    for j, (tr, pos) in enumerate((("good", 1), ("good", 2), ("mid", 3), ("bad", 4), ("bad", 5))):
        rows.append({"live": 50.0 - j * 0.5, "tres": 0.0, "trainer": tr, "pos": pos, "ability": 50.0})
    return {"date": date, "meeting": f"m{date}", "race": i, "rows": rows}


def test_evaluate_window_detects_clearly_worse_table():
    races = [_race(f"2026-11-{d:02d}", i, True) for d in range(3, 10) for i in range(1, 9)]
    cal = {r["date"]: (-0.4, 0.3, 1.0) for r in races}
    right = {"good": [["2026-11-01", 20.0, 50]], "bad": [["2026-11-01", -20.0, 50]], "mid": [["2026-11-01", 0.0, 50]]}
    wrong = {"good": [["2026-11-01", -20.0, 50]], "bad": [["2026-11-01", 20.0, 50]], "mid": [["2026-11-01", 0.0, 50]]}
    res = shadow.evaluate_window(races, cal, wrong, right)
    assert res["races_differ"] == len(races) and res["dlogloss"][1] > 0
    assert shadow.decide([{"version": "new", "previous": {"version": "old"}, "result": res}])["to"] == "old"
    same = shadow.evaluate_window(races, cal, right, right)
    assert same["races_differ"] == 0 and same["dlogloss"] is None


def test_run_end_to_end_rolls_back_rewrite_after_window(root, monkeypatch):
    right = {"good": [["2026-08-01", 20.0, 50]], "bad": [["2026-08-01", -20.0, 50]], "mid": [["2026-08-01", 0.0, 50]]}
    wrong = {"good": [["2026-08-01", -20.0, 50]], "bad": [["2026-08-01", 20.0, 50]], "mid": [["2026-08-01", 0.0, 50]]}
    d1, d2 = _payload(right, "2026-08-01"), _payload(wrong, "2026-08-01", "y")
    live = _write_live(root, d1)
    v1 = V.commit(live, d1, as_of="2026-08-01", now=datetime(2026, 9, 20, 12, tzinfo=timezone.utc))["version"]
    V.commit(live, d2, as_of="2026-08-01", now=datetime(2026, 9, 30, 12, tzinfo=timezone.utc))   # 改寫 → pending
    # warm-up／校準賽日＋啟用後賽日；啟用日（09-30 悉尼晚）當日同之前嘅唔入窗口
    days = [f"2026-08-{d:02d}" for d in range(5, 32)] + [f"2026-09-{d:02d}" for d in range(1, 31)] \
        + [f"2026-10-{d:02d}" for d in range(1, 9)]
    races = [_race(d, i, True) for d in days for i in range(1, 9)]
    for r in races:     # 令校準有變化
        r["rows"][3]["live"] += 1.0
    status = shadow.run(live, races, apply=True)
    ev = status["evaluations"][-1]
    assert ev["window"][0] == "2026-10-01" and len(ev["window"]) == 7
    assert status["rollback_now"]["to"] == v1 and status["rollback_now"]["applied"]
    P._resolve_pointer.cache_clear()
    assert P.default_table_path().read_bytes() == d1 and V.load_pointer(live)["pinned"] is True
    again = shadow.run(live, races, apply=True)     # 已鎖定 → 唔再回退
    assert again["rollback_now"] is None and again["state"] == "pinned"


def test_run_without_apply_does_not_touch_pointer(root):
    d1 = _payload(T1, "2026-11-01")
    live = _write_live(root, d1)
    V.commit(live, d1, as_of="2026-11-01", now=NOW1)
    before = (root / "AU_Trainer_Residual.active.json").read_bytes()
    status = shadow.run(live, [], apply=False, collect=lambda: [])
    assert status["state"] == "ok" and (root / "AU_Trainer_Residual.active.json").read_bytes() == before
