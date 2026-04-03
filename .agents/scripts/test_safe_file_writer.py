#!/usr/bin/env python3
"""
Test suite for safe_file_writer.py
Run: python3 test_safe_file_writer.py
"""

import base64
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

# Resolve script path relative to this test file
SCRIPT_DIR = Path(__file__).resolve().parent
SAFE_WRITER = SCRIPT_DIR / "safe_file_writer.py"


def run_writer(target: str, content: str, mode: str = "overwrite",
               dry_run: bool = False, use_stdin: bool = False) -> dict:
    """Helper to invoke safe_file_writer.py and return parsed JSON result."""
    b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")

    cmd = [sys.executable, str(SAFE_WRITER), "--target", target, "--mode", mode]
    if dry_run:
        cmd.append("--dry-run")

    if use_stdin:
        cmd.append("--stdin")
        result = subprocess.run(cmd, input=b64, capture_output=True, text=True)
    else:
        cmd.extend(["--content", b64])
        result = subprocess.run(cmd, capture_output=True, text=True)

    try:
        return json.loads(result.stdout.strip())
    except json.JSONDecodeError:
        return {"success": False, "message": f"Non-JSON output: {result.stdout} | stderr: {result.stderr}",
                "returncode": result.returncode}


class TestSafeFileWriter(unittest.TestCase):
    """Core functionality tests."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="safe_writer_test_")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # ─── Basic Write ────────────────────────────────────────────────

    def test_01_basic_overwrite(self):
        """Basic overwrite to a new file."""
        target = os.path.join(self.tmpdir, "test.md")
        content = "# Hello World\n\nThis is a test.\n"
        result = run_writer(target, content)
        self.assertTrue(result["success"])
        self.assertEqual(Path(target).read_text(encoding="utf-8"), content)

    def test_02_overwrite_existing(self):
        """Overwrite replaces existing content."""
        target = os.path.join(self.tmpdir, "test.md")
        Path(target).write_text("old content", encoding="utf-8")
        new_content = "new content\n"
        result = run_writer(target, new_content, mode="overwrite")
        self.assertTrue(result["success"])
        self.assertEqual(Path(target).read_text(encoding="utf-8"), new_content)

    # ─── Create Mode ───────────────────────────────────────────────

    def test_03_create_new_file(self):
        """Create mode succeeds for new files."""
        target = os.path.join(self.tmpdir, "new.md")
        result = run_writer(target, "content\n", mode="create")
        self.assertTrue(result["success"])

    def test_04_create_existing_fails(self):
        """Create mode fails if file already exists."""
        target = os.path.join(self.tmpdir, "exists.md")
        Path(target).write_text("already here", encoding="utf-8")
        result = run_writer(target, "new content", mode="create")
        self.assertFalse(result["success"])
        self.assertIn("already exists", result["message"])

    # ─── Append Mode ───────────────────────────────────────────────

    def test_05_append(self):
        """Append mode adds to existing content."""
        target = os.path.join(self.tmpdir, "append.md")
        Path(target).write_text("line1\n", encoding="utf-8")
        result = run_writer(target, "line2\n", mode="append")
        self.assertTrue(result["success"])
        self.assertEqual(Path(target).read_text(encoding="utf-8"), "line1\nline2\n")

    # ─── Chinese + Emoji Content ───────────────────────────────────

    def test_06_chinese_and_emoji(self):
        """Handles Chinese characters and emojis correctly."""
        target = os.path.join(self.tmpdir, "chinese.md")
        content = textwrap.dedent("""\
            # 🏆 Top 4 位置精選

            🥇 **第一選**
            - **馬號及馬名：** 3 勁力衝刺
            - **評級與✅數量：** `A+` | ✅ 8
            - **核心理據：** 段速法醫顯示 L400 持續進步
            - **最大風險：** 首次接觸 AWT 場地

            🐴⚡ **冷門馬訊號 (Underhorse Signal)：** `觸發`
        """)
        result = run_writer(target, content)
        self.assertTrue(result["success"])
        written = Path(target).read_text(encoding="utf-8")
        self.assertIn("🏆 Top 4 位置精選", written)
        self.assertIn("勁力衝刺", written)
        self.assertIn("🐴⚡", written)

    # ─── Backticks and Special Characters ──────────────────────────

    def test_07_backticks_and_brackets(self):
        """Handles Markdown backticks, brackets, and special chars."""
        target = os.path.join(self.tmpdir, "special.md")
        content = textwrap.dedent("""\
            ```python
            def hello():
                return "world"
            ```

            > [!CAUTION]
            > **This is a warning** with `code` and [links](http://example.com)

            Price: $100 | Discount: 50%
            Path: C:\\Users\\test\\file.txt
            Backtick: ` and triple: ```
        """)
        result = run_writer(target, content)
        self.assertTrue(result["success"])
        written = Path(target).read_text(encoding="utf-8")
        self.assertIn("```python", written)
        self.assertIn('[!CAUTION]', written)
        self.assertIn("$100", written)

    # ─── Large File (Stress Test) ──────────────────────────────────

    def test_08_large_file_2000_lines(self):
        """Stress test: 2000+ lines of realistic analysis content."""
        lines = []
        for i in range(200):  # 200 horses × ~10 lines each = 2000 lines
            lines.append(f"**[{i+1}] 快馬{i+1}號** | 騎師{i} | 練馬師{i} | {50+i}磅 | 檔位{i%14+1}")
            lines.append(f"> **📌 情境標記：** `復出首仗`")
            lines.append(f"- **近六場：** `1-3-2-5-4-1`")
            lines.append(f"- **段速質量：** `✅` | 理據: L400 = 22.{i:02d}s")
            lines.append(f"- **EEM 潛力：** `✅` | 累積消耗: 無")
            lines.append(f"**⭐ 最終評級：** `A-`")
            lines.append(f"🐴⚡ **冷門馬訊號：** `{'觸發' if i % 5 == 0 else '未觸發'}`")
            lines.append("")
            lines.append("---")
            lines.append("")

        content = "\n".join(lines)
        target = os.path.join(self.tmpdir, "stress_test.md")
        result = run_writer(target, content)
        self.assertTrue(result["success"])
        self.assertGreater(result["lines"], 1500)
        written = Path(target).read_text(encoding="utf-8")
        self.assertEqual(written, content)

    # ─── Stdin Mode ────────────────────────────────────────────────

    def test_09_stdin_mode(self):
        """Reading Base64 from stdin works correctly."""
        target = os.path.join(self.tmpdir, "stdin_test.md")
        content = "# Stdin Test\n\n內容來自 stdin\n"
        result = run_writer(target, content, use_stdin=True)
        self.assertTrue(result["success"])
        self.assertEqual(Path(target).read_text(encoding="utf-8"), content)

    # ─── Dry Run Mode ──────────────────────────────────────────────

    def test_10_dry_run(self):
        """Dry run validates without writing."""
        target = os.path.join(self.tmpdir, "dryrun.md")
        result = run_writer(target, "should not be written\n", dry_run=True)
        self.assertTrue(result["success"])
        self.assertIn("Dry-run", result["message"])
        self.assertFalse(Path(target).exists())

    # ─── Auto-create Parent Directories ────────────────────────────

    def test_11_auto_create_parents(self):
        """Automatically creates parent directories."""
        target = os.path.join(self.tmpdir, "deep", "nested", "dir", "file.md")
        result = run_writer(target, "nested content\n")
        self.assertTrue(result["success"])
        self.assertTrue(Path(target).exists())

    # ─── Line Count Accuracy ───────────────────────────────────────

    def test_12_line_count(self):
        """Line count in result matches actual content."""
        target = os.path.join(self.tmpdir, "linecount.md")
        content = "line1\nline2\nline3\n"
        result = run_writer(target, content)
        self.assertTrue(result["success"])
        self.assertEqual(result["lines"], 3)

    def test_13_line_count_no_trailing_newline(self):
        """Line count handles content without trailing newline."""
        target = os.path.join(self.tmpdir, "linecount2.md")
        content = "line1\nline2\nline3"
        result = run_writer(target, content)
        self.assertTrue(result["success"])
        self.assertEqual(result["lines"], 3)


class TestSafeFileWriterErrors(unittest.TestCase):
    """Error handling tests."""

    def test_empty_content(self):
        """Empty content returns error."""
        cmd = [sys.executable, str(SAFE_WRITER), "--target", "/tmp/empty.md",
               "--mode", "overwrite", "--content", ""]
        result = subprocess.run(cmd, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)

    def test_invalid_base64(self):
        """Invalid Base64 returns decode error."""
        cmd = [sys.executable, str(SAFE_WRITER), "--target", "/tmp/invalid.md",
               "--mode", "overwrite", "--content", "NOT_VALID_BASE64!!!"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        # Should either fail with exit code 2 or produce an error JSON
        parsed = json.loads(result.stdout.strip()) if result.stdout.strip() else {"success": False}
        if result.returncode != 0:
            self.assertNotEqual(result.returncode, 0)
        else:
            self.assertFalse(parsed.get("success", True))


if __name__ == "__main__":
    unittest.main(verbosity=2)
