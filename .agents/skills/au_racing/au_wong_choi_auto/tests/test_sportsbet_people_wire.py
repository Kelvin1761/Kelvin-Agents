"""騎練往績（LY token）由個人頁去到賽事檔嘅成條線。

`write_meeting` 一直寫 `st.get('_trainer_ly','-')`，但**成個 repo 冇一個地方
set 過 `_trainer_ly` / `_jockey_ly`** —— 所以每匹馬都出 `(LY: -)`。引擎嘅
`(LY: N:w-p-s)` 就係騎練往績嘅入口，冇咗佢 `jockey_score` 得 63%（現有源
99%）、`trainer_score` 51%。抓一千幾個個人頁但唔接呢條線，等於抓完擺喺度。

配對唔可以要求全等：總覽表出全名，連結文字**截短**咗而且帶後綴
（`Ben, Will & Jd ...`、`Emily Pozman  (a-3)`）。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "au_racing"))

from claw_sportsbet_form import _match_person, parse_people  # noqa: E402

HTML = ('<a href="/Trainer/15645/" class="x">Ben, Will &amp; Jd ...</a>'
        '<a href="/Jockey/55471/">Emily Pozman  (a-3)</a>'
        '<a href="/Trainer/724/">Ciaron Maher</a>'
        '<a href="/Jockey/2488/">Daniel Stackhou...</a>')


class PeopleMatchTest(unittest.TestCase):
    def setUp(self):
        self.people = parse_people(HTML)

    def test_exact_name_matches(self):
        self.assertEqual(_match_person(self.people, "Trainer", "Ciaron Maher"), "724")

    def test_truncated_link_text_still_matches_the_full_name(self):
        # 連結寫 `Daniel Stackhou...`，總覽表寫 `Daniel Stackhouse`
        self.assertEqual(
            _match_person(self.people, "Jockey", "Daniel Stackhouse"), "2488")

    def test_a_suffix_on_the_link_is_ignored(self):
        # `Emily Pozman  (a-3)` —— 見習磅後綴唔可以令配對失敗
        self.assertEqual(_match_person(self.people, "Jockey", "Emily Pozman"), "55471")

    def test_kind_is_not_crossed(self):
        """騎師唔可以配到練馬師個 ID —— 配錯人比冇數據更差。"""
        self.assertIsNone(_match_person(self.people, "Jockey", "Ciaron Maher"))

    def test_unknown_person_returns_none_rather_than_a_guess(self):
        self.assertIsNone(_match_person(self.people, "Jockey", "Nobody At All"))

    def test_a_short_name_does_not_match_by_accident(self):
        # 短過 min_len 嘅候選唔可以做前綴配對，否則 "A" 會配中任何人
        self.assertIsNone(_match_person(self.people, "Trainer", "C"))


if __name__ == "__main__":
    unittest.main()
