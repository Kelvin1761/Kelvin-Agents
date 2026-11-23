"""晨操一定要喺排位表之後抽（2026-11-23，11-25 跑馬地 R2 天下寵兒冇晨操標籤）。

extract_trackwork 用本地排位表做馬匹名單；先抽晨操 = 用 HKJC localtrackwork 頁嘅舊名單，後備馬補上嘅馬冇晨操。
"""
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "scripts" / "batch_extract.py"


def test_trackwork_extracted_after_racecards():
    src = SRC.read_text(encoding="utf-8")
    main = src[src.index("def main("):]
    racecards = main.index("executor.submit(extract_single_race")
    trackwork = main.index("extract_trackwork_meeting(args.base_url")
    assert racecards < trackwork, "晨操要喺排位表之後抽，唔係用 HKJC 晨操頁嘅舊名單"
