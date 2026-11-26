"""HKJC 賽前馬匹 AI 摘要單元測試（全部用 fake runner，唔會叫 Hydrogen／subprocess）。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
SCRIPTS = HERE.parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import ai_horse_summary as S  # noqa: E402


SAMPLE_ANALYSIS = """# 第 1 場分析
| 1 | 8 | 竣誠駒 | 79.9 | A- |
| 2 | 3 | 金鑽貴人 | 75.4 | B+ |

**【No.8】 竣誠駒** | 檔位:9
第1／2｜79.9 A-
- ✅ 檔位同跑法配合極佳，同程往績硬淨，近三仗加速段穩定。
- ❌ 今仗負磅略重，末段或稍受考驗。
- ➖ 場地適應性一般，屬中性因素。

**【No.3】 金鑽貴人** | 檔位:2
第2／2｜75.4 B+
- ✅ 騎師近態銳利，早段前速有優勢。
- ➖ 轉場適應暫作中性評估，未見明顯負面訊號。
"""

SAMPLE_CSV = """horse_number,horse_name,rank,official_ranking_score
8,竣誠駒,1,79.9
3,金鑽貴人,2,75.4
"""


def _write_race(meeting: Path, race_no: int, analysis: str = SAMPLE_ANALYSIS, csv_text: str | None = SAMPLE_CSV) -> None:
    (meeting / f"Race_{race_no}_Auto_Analysis.md").write_text(analysis, encoding="utf-8")
    if csv_text is not None:
        (meeting / f"Race_{race_no}_Auto_Scoring.csv").write_text(csv_text, encoding="utf-8")


def _valid_reply_json() -> str:
    return json.dumps(
        [
            {
                "no": 8,
                "name": "竣誠駒",
                "rank": 1,
                "score": 79.9,
                "summary": "排第 1 名（79.9 分），檔位同跑法配合極佳兼同程硬淨；隱憂係今仗負磅略重。",
                "evidence": [
                    "檔位同跑法配合極佳，同程往績硬淨",
                    "今仗負磅略重，末段或稍受考驗",
                ],
            },
            {
                "no": 3,
                "name": "金鑽貴人",
                "rank": 2,
                "score": 75.4,
                "summary": "排第 2 名（75.4 分），騎師近態銳利兼早段有前速；報告暫無明顯負面訊號。",
                "evidence": [
                    "騎師近態銳利，早段前速有優勢",
                    "轉場適應暫作中性評估，未見明顯負面訊號",
                ],
            },
        ],
        ensure_ascii=False,
    )


class TestParseAndLoad(unittest.TestCase):
    def test_parse_reply_with_surrounding_noise(self):
        noisy = f"好嘅，以下係結果：\n```json\n{_valid_reply_json()}\n```\n完。"
        parsed = S.parse_reply(noisy)
        self.assertIsInstance(parsed, list)
        self.assertEqual([r["no"] for r in parsed], [8, 3])

    def test_parse_reply_rejects_non_list_or_missing_brackets(self):
        with self.assertRaises(ValueError):
            S.parse_reply('{"no": 8}')
        with self.assertRaises(ValueError):
            S.parse_reply("純文字冇括號")

    def test_load_truth_hkjc(self):
        with tempfile.TemporaryDirectory() as td:
            csv_path = Path(td) / "Race_1_Auto_Scoring.csv"
            csv_path.write_text(SAMPLE_CSV, encoding="utf-8")
            truth = S.load_truth_hkjc(csv_path)
            self.assertEqual(truth[8], {"name": "竣誠駒", "rank": 1, "score": 79.9})
            self.assertEqual(truth[3], {"name": "金鑽貴人", "rank": 2, "score": 75.4})


class TestVerify(unittest.TestCase):
    def setUp(self):
        self.truth = {
            8: {"name": "竣誠駒", "rank": 1, "score": 79.9},
            3: {"name": "金鑽貴人", "rank": 2, "score": 75.4},
        }

    def _base_row(self, **overrides):
        row = {
            "no": 8,
            "name": "竣誠駒",
            "rank": 1,
            "score": 79.9,
            "summary": "排第 1 名（79.9 分），檔位同跑法配合極佳；隱憂係今仗負磅略重。",
            "evidence": [
                "檔位同跑法配合極佳，同程往績硬淨",
                "今仗負磅略重，末段或稍受考驗",
            ],
        }
        row.update(overrides)
        return row

    def test_verify_pass_and_markdown_norm(self):
        row = self._base_row(
            score=79.96,  # 剛剛好差 0.06 應過關
            evidence=[
                "*檔位同跑法配合極佳*， 同程往績硬淨",
                "`今仗負磅略重`，末段或稍受考驗",
            ],
        )
        accepted, rejected = S.verify([row], SAMPLE_ANALYSIS, self.truth)
        self.assertIn(8, accepted)
        self.assertEqual(rejected, [])

    def test_evidence_from_other_horse_rejected(self):
        row = self._base_row(evidence=["騎師近態銳利，早段前速有優勢", "今仗負磅略重，末段或稍受考驗"])
        accepted, rejected = S.verify([row], SAMPLE_ANALYSIS, self.truth)
        self.assertEqual(accepted, {})
        self.assertIn("呢匹馬", rejected[0]["reason"])

    def test_summary_wrong_rank_score_or_other_horse_rejected(self):
        for text, why in (("排第 2 名，檔位配合極佳。", "排名"),
                          ("今場 75.4 分，檔位配合極佳。", "數字"),
                          ("檔位配合極佳，同金鑽貴人一樣有前速。", "其他馬")):
            accepted, rejected = S.verify([self._base_row(summary=text)], SAMPLE_ANALYSIS, self.truth)
            self.assertEqual(accepted, {}, text)
            self.assertIn(why, rejected[0]["reason"], text)

    def test_subscore_or_substring_does_not_rescue_wrong_total(self):
        analysis = SAMPLE_ANALYSIS.replace("- ➖ 場地適應性一般", "- 狀態 65.0 分\n- ➖ 場地適應性一般")
        accepted, rejected = S.verify([self._base_row(summary="今場 65.0 分，檔位配合極佳。")], analysis, self.truth)
        self.assertEqual(accepted, {})
        accepted, _ = S.verify([self._base_row(summary="排第 1 名，狀態 65.0 分算穩陣。")], analysis, self.truth)
        self.assertIn(8, accepted)  # 緊貼維度名嘅分項 OK
        accepted, _ = S.verify([self._base_row(summary="綜合狀態 65.0 分，檔位配合極佳。")], analysis, self.truth)
        self.assertEqual(accepted, {})  # 「綜合」= 總分，要等於 79.9
        accepted, _ = S.verify([self._base_row(summary="狀態一般。今場 65.0 分，檔位配合極佳。")], analysis, self.truth)
        self.assertEqual(accepted, {})  # 維度詞喺上一句唔算
        truth = {8: dict(self.truth[8], score=79.86), 3: self.truth[3]}
        analysis2 = analysis.replace("79.9 A-", "79.9 A-\n- 段落 79.8 數")
        accepted, _ = S.verify([self._base_row(score=79.9, summary="今場 79.8 分，檔位配合極佳。")], analysis2, truth)
        self.assertEqual(accepted, {})  # 79.86 只可以寫 79.9
        self.assertFalse(S._has_number("65.0", "5"))
        self.assertFalse(S._has_number("165.0", "65.0"))
        self.assertTrue(S._has_number("得 65.0 分", "65.0"))

    def test_last_horse_section_stops_at_next_part(self):
        text = SAMPLE_ANALYSIS + "\n---\n#### [第三部分] 最終預測\n- 首選穩陣，末段必定追到上。\n"
        ctx = S.horse_context(text, 3, "金鑽貴人")
        self.assertNotIn("末段必定追到上", ctx)

    def test_verify_wrong_name(self):
        accepted, rejected = S.verify([self._base_row(name="假馬名")], SAMPLE_ANALYSIS, self.truth)
        self.assertEqual(accepted, {})
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0]["no"], 8)

    def test_verify_wrong_rank(self):
        accepted, rejected = S.verify([self._base_row(rank=2)], SAMPLE_ANALYSIS, self.truth)
        self.assertEqual(accepted, {})
        self.assertEqual(rejected[0]["no"], 8)

    def test_verify_score_diff_over_tolerance(self):
        accepted, rejected = S.verify([self._base_row(score=79.97)], SAMPLE_ANALYSIS, self.truth)
        self.assertEqual(accepted, {})
        self.assertEqual(rejected[0]["no"], 8)

    def test_verify_evidence_not_in_analysis(self):
        accepted, rejected = S.verify(
            [self._base_row(evidence=["呢句完全唔係報告原文寫嘅內容", "今仗負磅略重，末段或稍受考驗"])],
            SAMPLE_ANALYSIS,
            self.truth,
        )
        self.assertEqual(accepted, {})
        self.assertEqual(rejected[0]["no"], 8)

    def test_verify_evidence_count_limits(self):
        accepted, rejected = S.verify(
            [self._base_row(evidence=["檔位同跑法配合極佳，同程往績硬淨"])],
            SAMPLE_ANALYSIS,
            self.truth,
        )
        self.assertEqual(accepted, {})
        self.assertEqual(rejected[0]["no"], 8)

    def test_verify_summary_invented_number(self):
        accepted, rejected = S.verify(
            [self._base_row(summary="排第 1 名（79.9 分），贏過 88.5 米紀錄。")],
            SAMPLE_ANALYSIS,
            self.truth,
        )
        self.assertEqual(accepted, {})
        self.assertEqual(rejected[0]["no"], 8)

    def test_verify_summary_too_long_or_empty(self):
        accepted1, rejected1 = S.verify([self._base_row(summary="   ")], SAMPLE_ANALYSIS, self.truth)
        accepted2, rejected2 = S.verify([self._base_row(summary="好" * 121)], SAMPLE_ANALYSIS, self.truth)
        self.assertEqual(accepted1, {})
        self.assertEqual(accepted2, {})
        self.assertEqual(len(rejected1), 1)
        self.assertEqual(len(rejected2), 1)

    def test_verify_duplicate_no_rejects_both(self):
        r1 = self._base_row()
        r2 = self._base_row(summary="排第 1 名，同程硬淨。")
        accepted, rejected = S.verify([r1, r2], SAMPLE_ANALYSIS, self.truth)
        self.assertEqual(accepted, {})
        self.assertEqual(len(rejected), 2)
        self.assertTrue(all(item["no"] == 8 for item in rejected))


class TestSummariseRaceAndMeeting(unittest.TestCase):
    def test_summarise_race_writes_sidecar_and_uses_cache(self):
        with tempfile.TemporaryDirectory() as td:
            meeting = Path(td) / "2026-11-26_HappyValley"
            meeting.mkdir()
            _write_race(meeting, 1)

            calls = []

            def fake_runner(path: Path) -> str:
                calls.append(path)
                return _valid_reply_json()

            res1 = S.summarise_race(meeting, 1, runner=fake_runner)
            self.assertEqual(res1, {"status": "ok", "accepted": 2, "rejected": 0})
            self.assertEqual(len(calls), 1)

            sidecar = meeting / "Race_1_AI_Summary.json"
            self.assertTrue(sidecar.exists())
            data = json.loads(sidecar.read_text(encoding="utf-8"))
            self.assertEqual(data["schema"], 1)
            self.assertEqual(data["platform"], "hkjc")
            self.assertEqual(data["race"], 1)
            self.assertEqual(data["source"], "Race_1_Auto_Analysis.md")
            self.assertEqual(data["label"], "AI 摘要（未入分）")
            self.assertEqual(set(data["horses"].keys()), {"3", "8"})

            # Cache hit: runner must NOT be called again
            res2 = S.summarise_race(meeting, 1, runner=fake_runner)
            self.assertEqual(res2, {"status": "cached"})
            self.assertEqual(len(calls), 1)

            # Source changed -> recomputes
            _write_race(meeting, 1, analysis=SAMPLE_ANALYSIS + "\n補充一句。\n")
            res3 = S.summarise_race(meeting, 1, runner=fake_runner)
            self.assertEqual(res3["status"], "ok")
            self.assertEqual(len(calls), 2)

            # force=True -> recomputes even when cached
            res4 = S.summarise_race(meeting, 1, runner=fake_runner, force=True)
            self.assertEqual(res4["status"], "ok")
            self.assertEqual(len(calls), 3)

    def test_summarise_race_runner_error_returns_failed_without_sidecar(self):
        with tempfile.TemporaryDirectory() as td:
            meeting = Path(td) / "2026-11-26_HappyValley"
            meeting.mkdir()
            _write_race(meeting, 2)

            def broken_runner(_path: Path) -> str:
                raise RuntimeError("boom")

            res = S.summarise_race(meeting, 2, runner=broken_runner)
            self.assertEqual(res["status"], "failed")
            self.assertIn("boom", res["reason"])
            self.assertFalse((meeting / "Race_2_AI_Summary.json").exists())

    def test_summarise_race_missing_csv_returns_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            meeting = Path(td) / "2026-11-26_HappyValley"
            meeting.mkdir()
            _write_race(meeting, 3, csv_text=None)

            res = S.summarise_race(meeting, 3, runner=lambda p: _valid_reply_json())
            self.assertEqual(res["status"], "skipped")
            self.assertFalse((meeting / "Race_3_AI_Summary.json").exists())

    def test_summarise_meeting_numeric_order_and_platform_check(self):
        with tempfile.TemporaryDirectory() as td:
            meeting = Path(td) / "2026-11-26_ShaTin"
            meeting.mkdir()
            for r in (10, 2, 1):
                _write_race(meeting, r)

            out = S.summarise_meeting(meeting, platform="hkjc", workers=2, runner=lambda p: _valid_reply_json())
            self.assertEqual(list(out.keys()), [1, 2, 10])
            self.assertTrue(all(v["status"] == "ok" for v in out.values()))

            with self.assertRaises(ValueError) as ctx:
                S.summarise_meeting(meeting, platform="au")
            self.assertIn("暫時只支援 hkjc", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
