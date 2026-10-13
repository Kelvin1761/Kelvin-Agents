"""騎練個人資料庫嘅名字擷取。

呢個資料庫 2,255 個人、每人八張情境表，但 `name` 全部係空 —— caller 硬寫
`""`，而個人頁本身**冇名字**（純統計表片段）。唯一來源係賽事頁連結嘅
`title` 屬性。守住三樣：用 title 唔用 anchor（anchor 會截短）、HTML entity
要 unescape（合夥練馬師名含 `&`）、名字缺失唔可以砌一個。
"""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import os
os.environ.setdefault("WC_SB_CACHE_ONLY", "1")

from warm_people_backfill import PERSON_LINK_RE  # noqa: E402


def names(html: str):
    import html as _h
    return {(m.group("kind"), m.group("pid")): _h.unescape(m.group("name")).strip()
            for m in PERSON_LINK_RE.finditer(html)}


TRAINER = ('<a class="detail-links ctrainer" rel="facebox" href="/Trainer/15645/" '
           'title="Ben, Will &amp; Jd Hayes - Career Statistics">Ben, Will &amp; Jd ...</a>')
JOCKEY = ('<a class="detail-links cjockey" rel="facebox" href="/Jockey/617411/" '
          'title="Logan Bates A - Career Statistics">Logan Bates A (a-1.5)</a>')


class TestPersonNameCapture(unittest.TestCase):
    def test_title_beats_truncated_anchor(self):
        """anchor 係 `Ben, Will &amp; Jd ...` —— 截短嘅。要拎 title 個全名。"""
        got = names(TRAINER)
        self.assertEqual(got[("Trainer", "15645")], "Ben, Will & Jd Hayes")

    def test_html_entity_is_unescaped(self):
        """`&amp;` 唔 unescape 就會變 `amp`，合夥練馬師名 0% 對得上。"""
        self.assertIn("&", names(TRAINER)[("Trainer", "15645")])
        self.assertNotIn("amp;", names(TRAINER)[("Trainer", "15645")])

    def test_jockey_apprentice_suffix_is_kept(self):
        """`Logan Bates A` 個 A 係見習標記，係名字一部分，唔好剝。"""
        self.assertEqual(names(JOCKEY)[("Jockey", "617411")], "Logan Bates A")

    def test_both_kinds_in_one_page(self):
        got = names(TRAINER + " " + JOCKEY)
        self.assertEqual(len(got), 2)
        self.assertEqual({k[0] for k in got}, {"Trainer", "Jockey"})

    def test_link_without_title_yields_nothing(self):
        """冇 title 就唔好砌一個名 —— 一個錯名比冇名更難查。"""
        self.assertEqual(names('<a href="/Jockey/999/">Someone</a>'), {})

    def test_other_titles_are_not_matched(self):
        self.assertEqual(names('<a href="/Jockey/999/" title="Blah - Something Else">X</a>'), {})

    def test_horse_links_are_ignored(self):
        self.assertEqual(names('<a href="/Horse/123/" title="Winx - Career Statistics">W</a>'), {})


if __name__ == "__main__":
    unittest.main()


class TestRefreshKeepsExistingName(unittest.TestCase):
    """claw 每晚傳 `""` 做名，晚更 TTL=0 令每個人都重寫 —— 修正前 2,568 人有 2,049 個被洗走名
    （2026-10-13 量；修正 c28db618）。鎖住：空名唔可以覆蓋已知嘅名，快照亦要帶返個名。"""

    def test_empty_name_does_not_erase_cached_name(self):
        import json
        import tempfile
        from unittest import mock

        import sb_people_stats as sps

        class FakeFetcher:
            def _cache_path(self, url):
                return Path("/nonexistent")

            def get(self, url):
                return "<html>stats</html>"

        tables = {"Overall Stats": {"default": {"12 Months": {"starts": 4, "1st": 1, "2nd": 0, "3rd": 1}}}}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "people.json"
            path.write_text(json.dumps({"jockey|617411": {
                "name": "Logan Bates A", "id": "617411", "kind": "jockey",
                "stats": {}, "fetched_at": "2026-09-01T00:00:00+00:00"}}))
            with mock.patch.object(sps, "parse_person_tables", return_value=tables):
                sps.refresh([("Jockey", "617411", "")], fetcher=FakeFetcher(), ttl_days=0,
                            path=path, verbose=False)
            cache = json.loads(path.read_text())
            self.assertEqual(cache["jockey|617411"]["name"], "Logan Bates A")
            snap = sps.snapshot_path(path).read_text().strip().splitlines()[-1]
            self.assertEqual(json.loads(snap)["name"], "Logan Bates A")
