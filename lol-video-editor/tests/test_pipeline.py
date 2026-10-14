import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request

from lol_editor.analysis import analyze
from lol_editor.common import identity, load, lock, probe, save, validate_selection
from lol_editor.render import render, subtitles
from lol_editor.selection import score_rows, select
from lol_editor.captions import hk, validate as validate_captions
from lol_editor.conversation import select_conversation, budget
from lol_editor.framing import client_rectangle, prefix, split, safe_edges


class SelectionTests(unittest.TestCase):
    def test_conversation_keeps_pregame_and_comedy_without_time_budget(self):
        rows=[dict(start=0,end=5,active=False,score=0,effects_norm=0,motion_norm=0)]
        voices=[dict(start=10,end=13),dict(start=20,end=23)]
        result=select_conversation(dict(rows=rows),voices,100,
                                   [dict(start=12,end=16,text="芝心批",funny=True)])
        self.assertEqual(result['mode'],'conversation')
        self.assertIsNone(result['target_seconds'])
        self.assertEqual(len(result['highlights']),2)
        self.assertEqual(len(result['shorts']),1)
        self.assertEqual(result['shorts'][0]['reasons'],['reviewer marked funny'])

    def test_conversation_budget_preserves_user_joke(self):
        rows=[dict(start=t,end=t+5,audio_rms_norm=.7,audio_peak_norm=.6,score=.5) for t in range(0,1200,5)]
        clips=[dict(start=t,end=t+25,score=0,reasons=['voice']) for t in range(0,1200,40)]
        pinned=dict(start=510,end=580,score=1,reasons=['user joke'])
        result=budget(dict(highlights=clips,notes=[]),dict(rows=rows),500,[pinned])
        self.assertLessEqual(result['selected_seconds'],500)
        self.assertTrue(any(c['start']<=510 and c['end']>=580 for c in result['highlights']))

    def test_invalid_shorts_jump_cut_bounds(self):
        with self.assertRaises(ValueError):
            validate_selection(dict(highlights=[],shorts=[dict(start=10,end=30,clips=[dict(start=5,end=20)])]),100)

    def test_caption_validation_and_hong_kong_conversion(self):
        self.assertEqual(hk('游戏里说话'),'遊戲裏説話')
        good=dict(segments=[dict(id='a',start=1,end=2,text='芝心批')])
        validate_captions(good,10)
        with self.assertRaises(ValueError):
            validate_captions(dict(segments=[dict(id='a',start=0,end=float('nan'),text='字')]),10)

    def test_client_crop_and_phase_splits(self):
        import cv2
        import numpy as np
        image=np.full((360,640,3),190,dtype=np.uint8)
        cv2.rectangle(image,(136,68),(504,276),(20,20,20),-1)
        rect=client_rectangle(image)
        self.assertIsNotNone(rect)
        self.assertGreater(rect[0],136)
        self.assertLess(rect[0]+rect[2],505)
        clips=split([dict(start=2,end=8)],dict(regions=[dict(start=0,end=5,mode='client',crop=[20,20,100,60]),
                                                    dict(start=5,end=10,mode='game',crop=None)]))
        self.assertEqual([(c['start'],c['end']) for c in clips],[(2,5),(5,8)])
        self.assertEqual(prefix(clips[0]),'crop=100:60:20:20,')
        self.assertEqual(prefix(clips[1]),'')
        self.assertIsNone(safe_edges([136,68,368,208],np.full((360,640),180,dtype=np.uint8)))

    def test_short_context_stays_inside_gameplay(self):
        rows = [dict(start=t, end=t + 5, score=.9 if t == 115 else .1,
                     reasons=["action"], gameplay_present=t < 120) for t in range(0, 200, 5)]
        result = select(rows, 200)
        self.assertEqual(result["shorts"][0]["end"], 120)
        self.assertEqual(result["shorts"][0]["start"], 90)
        self.assertEqual(result["highlights"][0]["end"], 120)

    def test_distinct_shorts_budget_and_chronology(self):
        rows = [dict(start=t, end=t + 5, score=.9, reasons=[], active=True) for t in range(0, 1000, 5)]
        result = select(rows, 1000, target=185)
        self.assertEqual(len(result["shorts"]), 5)
        self.assertLessEqual(result["selected_seconds"], 185)
        validate_selection(result, 1000)
        for a, b in zip(sorted(result["shorts"], key=lambda c: c["start"]),
                        sorted(result["shorts"], key=lambda c: c["start"])[1:]):
            self.assertGreaterEqual(b["start"] - a["end"], 10)
        self.assertEqual(result["highlights"], sorted(result["highlights"], key=lambda c: c["start"]))

    def test_quiet_static_recording_is_not_padded(self):
        rows = [dict(start=t, end=t + 5, motion=0, effects=0, feed_change=0,
                     audio_rms=0, audio_peak=0, gameplay=0, hud=0) for t in range(0, 100, 5)]
        scored = score_rows(rows, [])
        self.assertEqual(select(scored, 100)["highlights"], [])
        self.assertEqual(select(scored, 100)["shorts"], [])

    def test_cantonese_reaction_and_menu_suppression(self):
        rows = [dict(start=t, end=t+5, motion=.1, effects=.1, feed_change=.1,
                     audio_rms=.1, audio_peak=.1, gameplay=.5, hud=1 if t == 0 else 0)
                for t in [0, 5]]
        scored = score_rows(rows, [dict(start=0, end=3, text="嘩！五殺！笑死")])
        self.assertIn("reaction phrase", scored[0]["reasons"])
        self.assertIn("spoken gameplay event", scored[0]["reasons"])
        self.assertFalse(scored[1]["active"])

    def test_invalid_and_duplicate_intervals(self):
        for bad in [float("nan"), float("inf"), -1, 101]:
            with self.assertRaises(ValueError):
                validate_selection(dict(highlights=[dict(start=bad, end=100)], shorts=[]), 100)
        with self.assertRaises(ValueError):
            validate_selection(dict(highlights=[], shorts=[dict(start=0, end=30), dict(start=20, end=50)]), 100)

    def test_subtitle_remapping_across_cuts(self):
        result = subtitles([dict(start=8, end=12, text="嘩"), dict(start=31, end=33, text="哈哈")],
                           [dict(start=10, end=20), dict(start=30, end=40)])
        self.assertIn("00:00:00,000 --> 00:00:02,000", result)
        self.assertIn("00:00:11,000 --> 00:00:13,000", result)

    def test_exclusive_project_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            with lock(folder):
                with self.assertRaises(RuntimeError):
                    with lock(folder):
                        pass
            self.assertFalse((Path(folder) / ".writer.lock").exists())


class EndToEndTests(unittest.TestCase):
    def test_real_ffmpeg_analysis_render_and_review(self):
        with tempfile.TemporaryDirectory(prefix="lol-test-") as tmp:
            root = Path(tmp)
            source = root / "game ' 測試.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-f", "lavfi", "-i",
                            "testsrc2=size=320x180:rate=30:duration=18", "-f", "lavfi", "-i",
                            "sine=frequency=440:duration=18", "-f", "lavfi", "-i",
                            "sine=frequency=880:duration=18", "-map", "0:v", "-map", "1:a", "-map", "2:a",
                            "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", source], check=True)
            before = hashlib.sha256(source.read_bytes()).hexdigest()
            project = analyze(source, root / "exports")
            manifest = load(project / "project.json")
            original_analysis = (project / manifest["analysis_file"]).read_bytes()
            self.assertEqual(analyze(source, root / "exports"), project)
            self.assertEqual((project / manifest["analysis_file"]).read_bytes(), original_analysis)
            selection = dict(revision=1, highlights=[dict(start=1, end=6), dict(start=8, end=14)],
                             shorts=[dict(start=i * 3, end=i * 3 + 2) for i in range(5)], target_seconds=11)
            save(project / "selection.json", selection)
            analysis = load(project / manifest["analysis_file"])
            analysis["transcript"] = [dict(start=2, end=4, text="嘩！")]
            save(project / manifest["analysis_file"], analysis)
            export = render(project, subtitles_mode="srt", height=360, preset="ultrafast")
            report = load(export / "render.json")
            self.assertEqual(report["status"], "complete")
            self.assertEqual(len(report["outputs"]), 6)
            self.assertEqual((probe(export / "youtube.mp4")["width"], probe(export / "youtube.mp4")["height"]), (640, 360))
            short = probe(export / "short_01.mp4")
            self.assertEqual((short["width"], short["height"]), (360, 640))
            self.assertEqual(len(short["audio"]), 2)
            self.assertLess(abs(short["duration"] - 2), .25)
            self.assertTrue((export / "youtube.srt").exists())
            rerender = render(project, subtitles_mode="burn", height=360, preset="ultrafast")
            self.assertNotEqual(export, rerender)
            self.assertTrue((export / "youtube.mp4").exists())
            self.assertTrue((rerender / "short_05.mp4").exists())  # No transcript here; skip empty soft subtitles.
            self.assertEqual(before, hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertEqual(manifest["source"], identity(source))
            self.check_review(project)
            # A corrupt recording must not prevent a later valid file from being processed.
            (root / "bad.mp4").write_text("not a video")
            env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
            batch = subprocess.run([sys.executable, "-m", "lol_editor.cli", "batch", str(root),
                                    "--output", str(root / "exports"), "--analyze-only"], env=env,
                                   capture_output=True, text=True)
            self.assertEqual(batch.returncode, 1)
            report = load(root / "exports" / "batch-report.json")
            self.assertEqual(report["recordings"], 2)
            self.assertEqual(len(report["failures"]), 1)
            self.assertEqual(load(project / "selection.json")["revision"], 2)  # Preserve review.
            source.touch()
            with self.assertRaisesRegex(ValueError, "Source changed"):
                render(project, height=360, preset="ultrafast")

    def check_review(self, project):
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
        server = subprocess.Popen([sys.executable, "-m", "lol_editor.cli", "review", str(project), "--port", "0"],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        try:
            url = server.stdout.readline().strip().removeprefix("Review: ")
            base, query = url.split("?", 1)
            req = urllib.request.Request(base + "video?" + query, headers={"Range": "bytes=0-99"})
            with urllib.request.urlopen(req, timeout=5) as response:
                self.assertEqual(response.status, 206)
                self.assertEqual(len(response.read()), 100)
            with self.assertRaises(urllib.error.HTTPError) as denied:
                urllib.request.urlopen(base + "api", timeout=5)
            self.assertEqual(denied.exception.code, 403)
            data = load(project / "selection.json")
            req = urllib.request.Request(base + "selection?" + query, data=json.dumps(data).encode(),
                                         headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=5) as response:
                edited = json.load(response)
                self.assertEqual(edited["revision"], 2)
                self.assertTrue(edited["reviewed"])
            with self.assertRaises(urllib.error.HTTPError) as conflict:
                urllib.request.urlopen(req, timeout=5)
            self.assertEqual(conflict.exception.code, 409)
            with urllib.request.urlopen(base+'api?'+query,timeout=5) as response:
                captions=json.load(response)['captions']
            analysis=load(project/'project.json')['analysis_file']
            before=(project/analysis).read_bytes()
            captions['segments'][0].update(text='芝心批',reviewed=True,funny=True)
            caption_request=urllib.request.Request(base+'captions?'+query,data=json.dumps(captions).encode(),
                                                  headers={'Content-Type':'application/json'},method='POST')
            with urllib.request.urlopen(caption_request,timeout=5) as response:
                saved=json.load(response)
            self.assertEqual(saved['revision'],1)
            self.assertEqual(load(project/'captions.json')['segments'][0]['text'],'芝心批')
            self.assertEqual((project/analysis).read_bytes(),before)
        finally:
            server.terminate()
            server.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
