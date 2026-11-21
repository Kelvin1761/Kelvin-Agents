"""路程分（參考分）同首本路程標籤只有一個來源：生涯同程紀錄（EXP-20261121-33，Kelvin 2026-11-21）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from au_racing_engine import track_going as T  # noqa: E402


def test_same_distance_reads_career_record():
    rec = T.same_distance("1:0-1-0 | 同程: 4:0-3-0 | 同場同程: 1:0-1-0")
    assert (rec["starts"], rec["wins"], rec["places"], rec["complete"]) == (4, 0, 3, True)


def test_distance_score_from_record():
    fire_star = T.distance_rate_score(T.same_distance("x | 同程: 4:0-3-0 | y"))[0]
    earn_to_burn = T.distance_rate_score(T.same_distance("x | 同程: 7:3-1-0 | y"))[0]
    assert round(fire_star, 1) == 69.0 and round(earn_to_burn, 1) == 66.9   # 上名率 3/4 vs 4/7
    assert T.distance_rate_score(T.same_distance("x | 同程: 0:0-0-0 | y"))[0] == 55.0
    assert T.distance_rate_score(T.same_distance("x | 同程: 7: | y"))[0] == 60.0  # 截斷


def test_engine_and_tags_share_the_helper():
    scripts = Path(__file__).resolve().parents[1] / "scripts" / "au_racing_engine"
    assert "_track.same_distance(" in (scripts / "engine_core.py").read_text(encoding="utf-8")
    assert "_track.same_distance(" in (scripts / "tags.py").read_text(encoding="utf-8")
    assert "距離分佈顯示今場未必係" not in (scripts / "engine_core.py").read_text(encoding="utf-8")
