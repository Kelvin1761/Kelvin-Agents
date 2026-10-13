"""Sportsbet Expert Tips 存檔（2026-10-14）。

守住四樣：照真實結構抽到評述同 Selections；冇區塊回 None（唔好砌）；
JSONL 只加唔改而且同內容唔重複寫；賽後頁（賽果已出／開跑後先攞）唔寫。
"""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import sb_expert_tips as T  # noqa: E402

TIPS = """
<div id="expert-tips" class="sprite-expert">
  <div class="expert-wrapper"><div class="right-expert"><span class="box-padding">
    <h3>Expert Tips</h3>
    <p class="expert-comment-container">KING TUT is 2 for 2... <a href="javascript: void(0);" class="read-moreexpert">Show more</a></p>
    <div class="full-comment">KING TUT is 2 for 2 1st up. Rosa &amp; co appeal.</div>
  </span></div>
  <div class="selection">
    <strong class="selection-label">Selections:</strong>
    <span class="selection-runner"><span><img src="//silk/a.svg" alt="Runners Colours"> <span class="runner-number active">10</span></span></span>
    <span class="selection-runner"><span><img src="//silk/b.svg" alt="Runners Colours" /> <span class="runner-number">7</span></span></span>
  </div></div>
</div>
<div id="full-form"></div>
"""


def page(form_line="", jump="1791960300"):
    return (
        '<html><head><title>Caulfield Race 8</title>'
        '<link rel="canonical" href="https://www.sportsbetform.com.au/452921/3447928/">'
        '</head><body><span class="race">Race 8 <abbr data-utime="' + jump + '" '
        'class="timestamp time24" title="Wednesday, 14 October 2026 at 5:45pm"> - 17:45</abbr>'
        '</span>' + TIPS + form_line + '</body></html>')


BEFORE = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)   # 開跑 = 10-14 06:45Z
AFTER = datetime(2026, 10, 14, 8, 0, tzinfo=timezone.utc)
POST_LINE = ('<span class="b">Caulfield</span> (<span class="good">Good</span>) '
             '14/10/2026 Race 8 1100m BM78 <span class="b">Finished</span> 1/13')


class TestExtract(unittest.TestCase):
    def test_real_structure(self):
        got = T.extract(page(), names={10: "King Tut", 7: "Swift Force"})
        self.assertEqual(got["tips_text"], "KING TUT is 2 for 2 1st up. Rosa & co appeal.")
        self.assertFalse(got["tips_text_truncated"])
        self.assertEqual([(s["number"], s["name"]) for s in got["selections"]],
                         [(10, "King Tut"), (7, "Swift Force")])
        self.assertEqual(got["selections"][0]["silk"], "//silk/a.svg")

    def test_names_never_invented(self):
        got = T.extract(page())
        self.assertEqual([s["name"] for s in got["selections"]], [None, None])

    def test_absent_block_is_none(self):
        self.assertIsNone(T.extract("<html><title>Caulfield Race 8</title></html>"))
        self.assertIsNone(T.extract(None))

    def test_meta(self):
        m = T.page_meta(page())
        self.assertEqual((m["venue"], m["race_number"], m["race_date"], m["race_id"]),
                         ("Caulfield", 8, "2026-10-14", "3447928"))


class TestAppend(unittest.TestCase):
    def setUp(self):
        T._SEEN.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "tips.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def rows(self):
        if not self.path.exists():
            return []
        return [json.loads(x) for x in self.path.read_text().splitlines()]

    def test_pre_race_written_once(self):
        rec = T.build_record(page(), fetched_at=BEFORE)
        self.assertTrue(rec["pre_race"])
        self.assertTrue(T.append_capture(rec, self.path))
        self.assertFalse(T.append_capture(dict(rec), self.path))   # 同 run 重複
        T._SEEN.clear()                                              # 新 run
        self.assertFalse(T.append_capture(dict(rec), self.path))   # 內容冇變
        rows = self.rows()
        self.assertEqual(len(rows), 1)
        for k in ("captured_at", "race_date", "venue", "race_number", "source_url", "pre_race"):
            self.assertIn(k, rows[0])

    def test_changed_tips_appended_not_overwritten(self):
        T.append_capture(T.build_record(page(), fetched_at=BEFORE), self.path)
        changed = page().replace("Rosa &amp; co appeal.", "Scratching changes things.")
        T.append_capture(T.build_record(changed, fetched_at=BEFORE), self.path)
        rows = self.rows()
        self.assertEqual(len(rows), 2)
        self.assertIn("Rosa & co", rows[0]["tips_text"])     # 舊一行冇被改

    def test_results_present_not_written(self):
        rec = T.build_record(page(POST_LINE), fetched_at=BEFORE)
        self.assertTrue(rec["results_present"])
        self.assertFalse(rec["pre_race"])
        self.assertFalse(T.append_capture(rec, self.path))
        self.assertEqual(self.rows(), [])

    def test_fetched_after_jump_not_written(self):
        rec = T.build_record(page(), fetched_at=AFTER)
        self.assertFalse(rec["pre_race"])
        self.assertFalse(T.append_capture(rec, self.path))

    def test_unknown_jump_not_written(self):
        html = page().replace('<span class="race">', '<span class="x">')
        rec = T.build_record(html, fetched_at=BEFORE)
        self.assertIsNone(rec["pre_race"])
        self.assertFalse(T.append_capture(rec, self.path))


if __name__ == "__main__":
    unittest.main()
