"""evidence_integrity：原位／offload／冇咗、sha 抽查、新 missing = bad、已知 = warn。"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import evidence_integrity as ei  # noqa: E402


class EvidenceIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.rec = t / "records"
        self.rec.mkdir()
        good = t / "a.txt"
        good.write_text("hello")
        moved = t / "moved.txt"
        moved.write_text("bytes")
        self.moved = moved
        arts = [{"path": str(good), "sha256": hashlib.sha256(b"hello").hexdigest()},
                {"path": str(t / "orig.txt"), "sha256": hashlib.sha256(b"bytes").hexdigest()},
                {"path": str(t / "gone.txt"), "sha256": "0" * 64}]
        (self.rec / "wc%3Anba%3Aprediction%3Ax.json").write_text(json.dumps({"domain": "nba", "artifacts": arts}))
        self.resolve = lambda p: moved if p.name == "orig.txt" else None

    def tearDown(self):
        self.tmp.cleanup()

    def test_scan_and_compare(self):
        r = ei.scan(self.rec, sample=5, seed=0, offloaded=self.resolve)
        self.assertEqual(r["domains"]["nba"], {"records": 1, "refs": 3, "direct": 1, "relocated": 1, "missing": 1})
        self.assertEqual(r["sha_mismatch"], [])
        self.assertEqual(ei.compare(r, None)["level"], "bad")                 # 第一次見 = 新
        self.assertEqual(ei.compare(r, r)["level"], "warn")                   # 已知 = 只報數

    def test_sha_mismatch_is_bad(self):
        self.moved.write_text("tampered")
        r = ei.scan(self.rec, sample=5, seed=0, offloaded=self.resolve)
        self.assertEqual(len(r["sha_mismatch"]), 1)
        self.assertEqual(ei.compare(r, r)["level"], "bad")


if __name__ == "__main__":
    unittest.main()
