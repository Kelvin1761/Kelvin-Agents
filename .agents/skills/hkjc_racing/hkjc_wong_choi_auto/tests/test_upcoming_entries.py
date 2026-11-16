"""報名表快照（EXP-20261117-04）：解析、只用賽前快照、1–7 日窗口、一日只抓一次。"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from hkjc_racing_engine import upcoming_entries as ue  # noqa: E402

PAGE = """<div>賽事日期: 22/11/2026 沙田 - 草地 "B+2" 賽道</div>
<div>練馬師</div><div>賽事班次</div><div>G2</div><div>4</div><div>評分幅度</div><div>(60-40)</div>
<div>途程</div><div>1600米</div><div>1200米</div><div>組別</div><div>1</div>
<table><tr><td><a href="/x/trainerprofile?trainerid=AAA">甲</a></td><td></td>
<td><a href="/zh-hk/local/information/horse?horseid=HK_2024_K264">廚神</a></td></tr>
<tr><td><a href="/x/trainerprofile?trainerid=BBB">乙</a></td>
<td><a href="/zh-hk/local/information/horse?horseid=HK_2023_J075">嘉應傳承</a></td><td></td></tr></table>"""


def test_parse_maps_horse_to_race_column():
    s = ue.parse(PAGE)
    assert s["date"] == "2026-11-22" and s["venue"] == "沙田"
    assert s["entries"] == {"HK_2024_K264": [2], "HK_2023_J075": [1]}
    assert s["races"][1] == {"no": 2, "class": "4", "distance": 1200}


def test_only_pre_race_snapshots_within_seven_days(tmp_path):
    folder = tmp_path / ue.DIRNAME
    folder.mkdir()
    snap = dict(ue.parse(PAGE))
    (folder / "2026-11-22_20261117T010000Z.json").write_text(json.dumps(snap), encoding="utf-8")
    soon = ue.entered_soon(tmp_path, "2026-11-18")
    assert soon["HK_2024_K264"]["days"] == 4 and soon["HK_2024_K264"]["race"] == 2
    assert ue.entered_soon(tmp_path, "2026-11-14") == {}          # 8 日後唔計
    (folder / "2026-11-22_20261117T010000Z.json").rename(folder / "2026-11-22_20261118T050000Z.json")
    assert ue.entered_soon(tmp_path, "2026-11-18") == {}          # 賽日 11:00 HKT 之後先抓 = 唔係賽前


def test_fetch_once_per_day_and_never_raises(tmp_path):
    now = datetime(2026, 11, 17, 1, 0, tzinfo=timezone.utc)
    calls = []
    getter = lambda url: calls.append(url) or PAGE
    assert ue.fetch_and_store(tmp_path, now=now, getter=getter) is not None
    assert ue.fetch_and_store(tmp_path, now=now, getter=getter) is None and len(calls) == 1
    bad = tmp_path / "b"
    assert ue.fetch_and_store(bad, now=now, getter=lambda u: "<html>改咗版</html>") is None
