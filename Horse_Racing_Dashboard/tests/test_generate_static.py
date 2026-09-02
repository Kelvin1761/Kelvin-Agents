import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


DASHBOARD_DIR = Path(__file__).resolve().parents[1]
if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))

import generate_static  # noqa: E402


class DropAuMeetingTests(unittest.TestCase):
    """Archiving a meeting has to be able to take it off the dashboard.

    Before `drop_au_meetings` existed the incremental path could only add or
    replace, so an archived meeting stayed in the published snapshot forever and
    the scheduler's pre-publish check refused to deploy -- correctly. Cloudflare
    sat on a stale snapshot for two nights while four freshly analysed meetings
    waited behind the gate.
    """

    def _snapshot(self, tmp):
        payload = {
            "meetings": [
                {"date": "2026-08-05", "venue": "Belmont", "region": "AU"},
                {"date": "2026-08-05", "venue": "Cranbourne", "region": "AU"},
                {"date": "2026-07-15", "venue": "HappyValley", "region": "HK"},
            ],
            "races": {
                "2026-08-05|Belmont": {"meeting": {"region": "AU"},
                    "races_by_analyst": {"K": [{"race_number": 1}]}},
                "2026-08-05|Cranbourne": {"meeting": {"region": "AU"},
                    "races_by_analyst": {"K": [{"race_number": 1}]}},
                "2026-07-15|HappyValley": {"meeting": {"region": "HK"},
                    "races_by_analyst": {"K": [{"race_number": 1}]}},
            },
            "consensus": {
                "2026-08-05|Belmont|1": {"x": 1},
                "2026-08-05|Cranbourne|1": {"x": 1},
                "2026-07-15|HappyValley|1": {"x": 1},
            },
            "roi": {},
        }
        path = Path(tmp) / "live.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_drops_meeting_races_and_consensus_together(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = generate_static.drop_au_meetings(
                self._snapshot(tmp), ["2026-08-05|Belmont"])
        self.assertEqual([f"{m['date']}|{m['venue']}" for m in out["meetings"]],
                         ["2026-08-05|Cranbourne", "2026-07-15|HappyValley"])
        self.assertNotIn("2026-08-05|Belmont", out["races"])
        # consensus keys 係 `{meeting_key}|...`，要跟埋走，唔可以留孤兒。
        self.assertEqual(sorted(out["consensus"]),
                         ["2026-07-15|HappyValley|1", "2026-08-05|Cranbourne|1"])

    def test_drops_several_and_leaves_the_rest_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = generate_static.drop_au_meetings(
                self._snapshot(tmp),
                ["2026-08-05|Belmont", "2026-08-05|Cranbourne"])
        self.assertEqual(len(out["meetings"]), 1)
        self.assertEqual(out["meetings"][0]["venue"], "HappyValley")

    def test_unknown_key_is_a_no_op_not_a_crash(self):
        # 早更／晚更都會傳「dashboard 上已經冇」嘅 key（例如上一個 run 已經剪走）。
        with tempfile.TemporaryDirectory() as tmp:
            out = generate_static.drop_au_meetings(
                self._snapshot(tmp), ["2026-01-01|Nowhere"])
        self.assertEqual(len(out["meetings"]), 3)

    def test_meta_is_rebuilt_so_the_counts_match_what_remains(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = generate_static.drop_au_meetings(
                self._snapshot(tmp), ["2026-08-05|Belmont"])
        # 剪走 Belmont 之後 AU 應該只剩 Cranbourne 一個場次。meta 冇重建嘅話
        # dashboard 個 header 會報一個唔存在嘅場次數。
        self.assertEqual(out["meta"]["regions"]["AU"]["meetings"], 1)


class GenerateStaticTests(unittest.TestCase):
    def test_generate_html_always_replaces_cached_sports_feed(self):
        fresh_feed = {
            "schema_version": 2,
            "validation_status": "valid",
            "sports": {
                "nba": {"analysis_run_id": "nba:fresh", "recommendations": []},
                "tennis": {"analysis_run_id": "tennis:fresh", "recommendations": []},
            },
        }
        data = {
            "meetings": [],
            "races": {},
            "consensus": {},
            "roi": {},
            "sports_feed": {
                "schema_version": 2,
                "sports": {"nba": {"analysis_run_id": "nba:stale"}},
            },
        }

        with patch.object(generate_static, "build_multisport_feed", return_value=fresh_feed):
            html = generate_static.generate_html(data)

        self.assertEqual(data["sports_feed"], fresh_feed)
        self.assertIn("nba:fresh", html)
        self.assertNotIn("nba:stale", html)

    def test_generate_html_uses_explicit_live_tennis_database(self):
        data = {"meetings": [], "races": {}, "consensus": {}, "roi": {}}
        tennis_db = "/srv/wongchoi/live/tennis_wc.db"
        fresh_feed = {
            "schema_version": 2,
            "validation_status": "valid",
            "sports": {},
        }

        with patch.dict("os.environ", {"WC_TENNIS_DB_PATH": tennis_db}):
            with patch.object(
                generate_static,
                "build_multisport_feed",
                return_value=fresh_feed,
            ) as build:
                generate_static.generate_html(data)

        self.assertEqual(
            build.call_args.kwargs["tennis_db_path"],
            Path(tennis_db),
        )

    def test_generate_html_uses_machine_local_tennis_database_pointer(self):
        data = {"meetings": [], "races": {}, "consensus": {}, "roi": {}}
        fresh_feed = {
            "schema_version": 2,
            "validation_status": "valid",
            "sports": {},
        }

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            tennis_db = home / "stable-runtime" / "tennis_wc.db"
            (home / ".wongchoi_tennis_db").write_text(
                f"{tennis_db}\n",
                encoding="utf-8",
            )
            with patch.dict("os.environ", {"WC_TENNIS_DB_PATH": ""}):
                with patch.object(Path, "home", return_value=home):
                    with patch.object(
                        generate_static,
                        "build_multisport_feed",
                        return_value=fresh_feed,
                    ) as build:
                        generate_static.generate_html(data)

        self.assertEqual(
            build.call_args.kwargs["tennis_db_path"],
            tennis_db,
        )

    def test_unavailable_local_tennis_cannot_erase_valid_live_feed(self):
        cached_tennis = {
            "analysis_run_id": "tennis:2026-08-13",
            "validation_status": "valid",
            "recommendations": [{"id": "tennis:kept"}],
        }
        fresh_feed = {
            "schema_version": 2,
            "validation_status": "valid",
            "sports": {
                "nba": {"analysis_run_id": "nba:2026-08-13", "validation_status": "valid"},
                "tennis": {
                    "analysis_run_id": "tennis:unavailable",
                    "validation_status": "unavailable",
                    "recommendations": [],
                },
            },
        }
        data = {
            "meetings": [], "races": {}, "consensus": {}, "roi": {},
            "sports_feed": {"schema_version": 2, "sports": {"tennis": cached_tennis}},
        }

        with patch.object(generate_static, "build_multisport_feed", return_value=fresh_feed):
            generate_static.generate_html(data)

        kept = data["sports_feed"]["sports"]["tennis"]
        self.assertEqual(kept["analysis_run_id"], "tennis:2026-08-13")
        self.assertEqual(kept["recommendations"], [{"id": "tennis:kept"}])
        self.assertIn("preserved_from_live_snapshot", kept["warnings"][0])

    def test_newer_valid_live_tennis_beats_older_local_database(self):
        cached = {
            "schema_version": 2,
            "sports": {"tennis": {
                "analysis_run_id": "tennis:2026-08-13",
                "validation_status": "valid",
                "recommendations": [{"id": "newer"}],
            }},
        }
        fresh = {
            "schema_version": 2,
            "sports": {"tennis": {
                "analysis_run_id": "tennis:2026-08-12",
                "validation_status": "valid",
                "recommendations": [{"id": "older"}],
            }},
        }

        merged = generate_static._merge_sports_feed(cached, fresh)

        self.assertEqual(
            merged["sports"]["tennis"]["analysis_run_id"],
            "tennis:2026-08-13",
        )


if __name__ == "__main__":
    unittest.main()


class SlimForTransportTests(unittest.TestCase):
    """Cloudflare Pages 硬性拒收任何超過 25 MiB 嘅單一檔案。

    2026-08-07：snapshot 32.5 MiB（九個星期六場次、75 場），deploy 連試三次都被拒，
    於是一整晚嘅分析永遠上唔到 dashboard，而第二朝嘅 run 亦救唔到 —— 佢只覆核
    「已經發佈」嘅場次。體積唔係美觀問題，係一個會靜靜咁食掉一日分析嘅上限。
    """

    def _payload(self, core, raw):
        return {"races": {"k": {"races_by_analyst": {"K": [
            {"horses": [{"core_analysis": core, "raw_text": raw}]}]}}}}

    def _horse(self, payload):
        return payload["races"]["k"]["races_by_analyst"]["K"][0]["horses"][0]

    def test_duplicate_core_analysis_is_dropped(self):
        out, dropped = generate_static._slim_for_transport(
            self._payload("🧠 核心分析\n- 好狀態", "### No.1\n🧠 核心分析\n- 好狀態\n更多"))
        self.assertEqual(dropped, 1)
        self.assertNotIn("core_analysis", self._horse(out))
        # 內容冇消失 —— 前端由 raw_text 拆返 section。
        self.assertIn("核心分析", self._horse(out)["raw_text"])

    def test_core_analysis_not_inside_raw_text_is_kept(self):
        # 逐匹重新檢查，唔係盲剷：唔係子串就一定要留返，否則就係真丟數據。
        out, dropped = generate_static._slim_for_transport(
            self._payload("獨立寫嘅分析", "### No.1\n完全唔同嘅內容"))
        self.assertEqual(dropped, 0)
        self.assertEqual(self._horse(out)["core_analysis"], "獨立寫嘅分析")

    def test_horse_without_core_analysis_is_untouched(self):
        # HKJC 場次一匹都冇 core_analysis（實測 107/107）。
        out, dropped = generate_static._slim_for_transport(
            self._payload("", "### No.1\nHKJC 格式"))
        self.assertEqual(dropped, 0)

    def test_non_snapshot_payloads_pass_through(self):
        # deploy manifest 都行同一個 writer，唔可以當佢係 snapshot。
        manifest = {"files": ["a", "b"]}
        out, dropped = generate_static._slim_for_transport(manifest)
        self.assertIs(out, manifest)
        self.assertEqual(dropped, 0)

    def test_written_snapshot_is_compact_not_pretty(self):
        # indent=2 喺呢個檔案上係 4 MiB 純空白，對住一個 25 MiB 上限。
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "snap.json"
            generate_static._write_json(out, self._payload("a", "xax"))
            body = out.read_text(encoding="utf-8")
        self.assertNotIn("\n", body)        # 冇 indent 換行
        self.assertNotIn('": ', body)       # key 同 value 之間冇空格
        self.assertIn('"races":{', body)    # 緊湊分隔符


class TrackGeometryPayloadTests(unittest.TestCase):
    """AU 賽道幾何要入 meeting payload。

    2026-09-02：`au_track_geometry.json` 96 個場地有 85 個有數，但
    `static_template.html` **零次**提及周長或直路 —— 修好咗嘅數據冇人睇到。
    由 payload 帶（唔係由報告文字 parse），舊報告先至唔使重新渲染都有。

    ⚠️ 一定要喺**讀完 cache 之後**先貼。`_collect_meeting()` 嘅結果會入 cache，
    喺嗰度貼就等於「已 cache 嘅場次永遠冇賽道資料」，而且 fingerprint 唔變
    佢哋唔會重新 parse —— 靜靜咁一個場次都冇。
    """

    def test_au_venue_gets_geometry(self):
        data = generate_static._attach_track_geometry({"venue": "Sandown", "region": "AU"})
        geometry = data.get("track_geometry")
        self.assertIsNotNone(geometry)
        self.assertEqual(geometry["circumference_m"], 2087)
        self.assertEqual(geometry["straight_m"], 491)
        self.assertEqual(geometry["direction"], "anticlockwise")

    def test_alias_venues_resolve(self):
        # 呢啲名靠引擎嗰個 alias 表對；dashboard 唔可以自己抄一份
        for venue, circumference in (("Rosehill Gardens", 2048), ("Ballarat Synthetic", 1900)):
            with self.subTest(venue=venue):
                data = generate_static._attach_track_geometry({"venue": venue, "region": "AU"})
                self.assertEqual(data["track_geometry"]["circumference_m"], circumference)

    def test_venue_without_geometry_gets_no_key(self):
        # Broome：兩個來源加人手都查唔到。唔可以貼一個空 dict 落去。
        data = generate_static._attach_track_geometry({"venue": "Broome", "region": "AU"})
        self.assertNotIn("track_geometry", data)

    def test_hk_meetings_are_untouched(self):
        data = generate_static._attach_track_geometry({"venue": "Sha Tin", "region": "HK"})
        self.assertNotIn("track_geometry", data)

    def test_cached_meetings_also_get_geometry(self):
        """貼嘅位要喺 cache 之後 —— 舊 cache entry 冇呢個 key 都要補返。"""
        cached = {"venue": "Randwick", "region": "AU", "date": "2026-08-01"}
        self.assertIn("track_geometry", generate_static._attach_track_geometry(cached))

    def test_stale_geometry_is_cleared_not_kept(self):
        stale = {"venue": "Broome", "region": "AU", "track_geometry": {"circumference_m": 9999}}
        self.assertNotIn("track_geometry", generate_static._attach_track_geometry(stale))
