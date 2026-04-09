import base64
import subprocess
import sys

content = """
---

## [第四部分] 💰 戰術與投注策略

**Top 2 入三甲信心度:**
- 8. Good Harmony: `[HIGH]` — 長直路極合其展步發揮，Third-up 狀態大勇。
- 3. Corviglia: `[MEDIUM]` — 增程變數大，若發揮入位後出有機會。

**步速逆轉保險:**
- 若發生極慢步速 (Crawl)，後追馬如 Good Harmony 可能受困，領放的 War No More 注意有機偷襲一席位置。
"""

b64 = base64.b64encode(content.encode('utf-8')).decode('utf-8')
cmd = [sys.executable, ".agents/scripts/safe_file_writer.py", "--target", "2026-04-08 Sale Race 1-8/04-08 Race 1 Analysis.md", "--mode", "append", "--content", b64]
subprocess.run(cmd, check=True)
