"""賽道幾何要對得返場地 —— 唔係印合集檔第一個場地嘅數。

2026-09-02 實測：85 個場地嘅報告印住 `周長 1570m / 直路 280m`，即 Canterbury
嘅尺寸。成因係 `_track_venue_section()` 個 regex 開咗 `re.S`，令標題行嘅 `.*`
跨行由檔案第一個 `##` 一路食落去。同一時間，五個都會場（表擺喺一級標題之下）
反而**乜尺寸都攞唔到**，因為 section 由第一個 `##` 開始，已經行過咗個表。

Facts.md 嗰邊（`inject_fact_anchors.load_track_profile`）更差：佢逐行掃成份
合集檔再覆蓋，所以攞到最後一節（Ascot）嘅尺寸 + 第一節（Canterbury）嘅特性，
砌成一個唔存在嘅賽場。

守住三樣：
  1. 有專屬檔嘅場地要攞到自己嘅真尺寸（唔可以係 0，亦唔可以係人哋嘅數）；
  2. 合集檔入面每一節要攞返自己嗰節；
  3. 資源入面**冇**呢個場地就要報冇資料，唔准 fall back 去人哋嘅數。
"""
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "scripts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from au_racing_engine.engine_core import (  # noqa: E402
    TRACK_PROFILE_CACHE,
    _load_track_profile,
)

GEOMETRY_PATH = Path(__file__).resolve().parents[1] / "resources" / "au_track_geometry.json"
REPO_ROOT = Path(__file__).resolve().parents[5]
INJECT_SCRIPT = REPO_ROOT / ".agents" / "scripts" / "inject_fact_anchors.py"

# 寫死真值（單位 m）係故意嘅：一個「攞到某個場地嘅數」嘅測試，如果自己都係由
# 同一份檔案讀，就永遠捉唔到「攞錯場地」。呢批數 2026-09-02 由兩個獨立來源核對過。
EXPECTED = {
    "Randwick": (2224, 410),
    "Rosehill": (2048, 408),
    "Rosehill Gardens": (2048, 408),
    "Flemington": (2312, 450),
    "Caulfield": (2080, 367),
    "Moonee Valley": (1805, 173),
    "Eagle Farm": (2027, 434),
    "Doomben": (1715, 350),
    "Warwick Farm": (1937, 326),
    "Canterbury": (1567, 308),
    "Morphettville": (2339, 334),
    "Ascot": (2022, 294),
    # 舊版靜靜攞人哋嘅數嗰批 —— 呢啲先係最重要嘅回歸
    "Belmont": (1699, 333),        # 舊版印 Ascot 嘅 1860/350
    "Sandown": (2087, 491),        # 舊版印 Canterbury 嘅「極窄小場 / 直路 280m」，方向完全相反
    "Sandown Lakeside": (1857, 407),
    "Wyong": (1790, 275),
    "Ballarat": (1900, 450),
    "Ballarat Synthetic": (1900, 375),   # 同草地跑道**唔同**條直路，唔准撈亂
    "Pakenham": (2400, 480),
    "Geelong": (2043, 400),
    "Ipswich": (1746, 300),
}

# 兩個來源同人手都查唔到嘅場地。要報冇資料，唔准借人哋嘅數填。
UNKNOWN_VENUES = ("Broome", "Carnarvon", "Katherine", "Mt Isa", "Roma", "Tuncurry")


def _load_inject_module():
    spec = importlib.util.spec_from_file_location("_ifa_for_test", INJECT_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["_ifa_for_test"] = module
    spec.loader.exec_module(module)
    return module


class TestTrackProfileVenueScoping(unittest.TestCase):
    def setUp(self):
        TRACK_PROFILE_CACHE.clear()

    def test_每個場地攞到自己嘅尺寸(self):
        for venue, (circumference, straight) in EXPECTED.items():
            with self.subTest(venue=venue):
                profile = _load_track_profile(venue, 1200)
                self.assertEqual(profile["circumference_m"], circumference)
                self.assertEqual(profile["straight_m"], straight)

    def test_冇資源嘅場地報冇資料而唔係借人哋嘅數(self):
        for venue in UNKNOWN_VENUES:
            with self.subTest(venue=venue):
                profile = _load_track_profile(venue, 1200)
                self.assertEqual(profile["circumference_m"], 0)
                self.assertEqual(profile["straight_m"], 0)
                self.assertEqual(profile["key_traits"], [])
                self.assertEqual(profile["direction"], "")

    def test_幾何檔覆蓋率唔可以靜靜跌(self):
        """幾何檔重抽之後場地數大跌 = 抽取斷咗，唔係「場地少咗」。"""
        payload = json.loads(GEOMETRY_PATH.read_text(encoding="utf-8"))
        venues = payload["venues"]
        with_geometry = [v for v in venues.values() if v["circumference_m"] and v["straight_m"]]
        self.assertGreaterEqual(len(with_geometry), 80, "有幾何嘅場地跌穿 80 —— 查抽取，唔好改呢個門檻")
        for row in venues.values():
            with self.subTest(venue=row["venue"]):
                # 方向只准兩個值。`anti-clockwise` / `Anticlockwise` 混住出現過。
                self.assertIn(row["direction"], ("", "clockwise", "anticlockwise"))
                if row["circumference_m"]:
                    self.assertTrue(row["sources"], "有數就要有來源")
                    self.assertLess(row["circumference_m"], 3000)
                    self.assertGreater(row["circumference_m"], 1000)

    def test_冇幾何就唔出賽道幾何嗰行(self):
        """得一個場地名唔算資料 —— 出咗等於話「有」。"""
        from au_racing_engine.engine_core import RacingEngine

        engine = RacingEngine.__new__(RacingEngine)
        engine.race_context = {"track_profile": _load_track_profile("Broome", 1200)}
        self.assertEqual(engine._track_geometry_brief(), "")

        engine.race_context = {"track_profile": _load_track_profile("Belmont", 1200)}
        self.assertIn("1699m", engine._track_geometry_brief())

    def test_facts_層唔會砌出嵌合體(self):
        """Facts 層仲係讀 markdown（只得九個場地），但唔准再借人哋嘅數。"""
        module = _load_inject_module()
        markdown_venues = {
            "Randwick": (2224, 410), "Flemington": (2312, 450),
            "Moonee Valley": (1805, 173), "Warwick Farm": (1937, 326),
        }
        for venue, (circumference, straight) in markdown_venues.items():
            with self.subTest(venue=venue):
                profile = module.load_track_profile(venue, 1200)
                self.assertEqual(profile["circumference"].split("m")[0], str(circumference))
                self.assertEqual(profile["straight"].split("m")[0], str(straight))
        for venue in UNKNOWN_VENUES:
            with self.subTest(venue=venue):
                profile = module.load_track_profile(venue, 1200)
                self.assertEqual(module.format_track_profile_summary(profile), "")


if __name__ == "__main__":
    unittest.main()
