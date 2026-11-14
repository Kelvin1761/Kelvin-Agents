"""外隊馬標籤（決定 4）：烙號數字 ≥ 800 先算外隊馬；純顯示、唔入分。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from hkjc_racing_engine import tags  # noqa: E402


def test_foreign_detection_and_tag():
    assert tags.is_foreign({"horse_code": "J816"}) and not tags.is_foreign({"horse_code": "J216"})
    assert not tags.is_foreign({})
    assert tags.is_foreign({"hkjc_horse_id": "HK_2025_J816"})
    out = tags._foreign_tag({"horse_code": "H821"})
    assert len(out) == 1 and out[0]["label"] == "外隊馬｜本地資料不足" and out[0]["scored"] is False
    assert tags._foreign_tag({"horse_code": "K503"}) == []
