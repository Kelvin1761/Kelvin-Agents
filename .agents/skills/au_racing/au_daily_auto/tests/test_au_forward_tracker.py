"""AU forward 追蹤表：每個測試第一次夠數推一次 Telegram，之後唔重覆；讀唔到唔當夠數。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import au_forward_tracker as tracker  # noqa: E402

FILE_TEST = tracker.ForwardTest("t_file", "檔案測試", "EXP-X", "status_file", 10, "場", "做嘢",
                                status_file="x.json")
S2_TEST = tracker.ForwardTest("t_s2", "S2", "EXP-Y", "s2_status", 41, "賽日", "evaluate")


def _write(work: Path, races: int, **extra) -> None:
    work.mkdir(parents=True, exist_ok=True)
    (work / "x.json").write_text(json.dumps({"races_collected": races, "config": {"target_races": 10}, **extra}))


def test_pushes_once_when_ready(tmp_path: Path) -> None:
    pushed = []
    _write(tmp_path, 9)
    tracker.check(work_dir=tmp_path, push=pushed.append, tests=(FILE_TEST,))
    assert pushed == []
    _write(tmp_path, 10)
    tracker.check(work_dir=tmp_path, push=pushed.append, tests=(FILE_TEST,))
    tracker.check(work_dir=tmp_path, push=pushed.append, tests=(FILE_TEST,))
    assert len(pushed) == 1 and "10/10 場" in pushed[0] and "EXP-X" in pushed[0]


def test_missing_status_is_an_error_not_ready(tmp_path: Path) -> None:
    pushed = []
    report = tracker.check(work_dir=tmp_path, push=pushed.append, tests=(FILE_TEST,))
    assert pushed == [] and report["t_file"]["error"]


def test_s2_status_output_is_parsed(tmp_path: Path) -> None:
    pushed = []
    def run(_cmd):
        return 0, "forward days with snapshot + results: 41 / 41 needed\nalready evaluated: False\n"
    report = tracker.check(work_dir=tmp_path, push=pushed.append, run=run, tests=(S2_TEST,))
    assert report["t_s2"]["ready"] and len(pushed) == 1 and "41/41 賽日" in pushed[0]


def test_s2_not_ready_below_minimum(tmp_path: Path) -> None:
    pushed = []
    def run(_cmd):
        return 0, "forward days with snapshot + results: 15 / 41 needed\nalready evaluated: False\n"
    tracker.check(work_dir=tmp_path, push=pushed.append, run=run, tests=(S2_TEST,))
    assert pushed == []


def test_registry_covers_known_forward_tests() -> None:
    experiments = " ".join(t.experiment for t in tracker.FORWARD_TESTS)
    for exp in ("EXP-20260927-02", "EXP-20261009-05", "EXP-20261016-03", "EXP-20261101-30", "EXP-20261102-08"):
        assert exp in experiments
