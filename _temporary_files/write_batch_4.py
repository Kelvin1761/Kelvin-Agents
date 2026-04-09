import base64
import subprocess
import sys

content = """
## [第三部分] 🏆 全場最終決策

**Speed Map 回顧:** MODERATE | 領放群: 2. War No More | 受牽制: N/A

**Top 4 位置精選**

🥇 **第一選**
- **馬號及馬名:** 8 Good Harmony
- **評級與✅數量:** `[S-]` | ✅ 7
- **核心理據:** 上仗於 1600m 展現全場最佳衝刺力，今戰轉排 3 檔形勢大逆轉，加上 Third-up 勇銳狀態，增程極合發揮。
- **最大風險:** 若早段步速太慢，或有於內欄受困風險。

🥈 **第二選**
- **馬號及馬名:** 3 Corviglia
- **評級與✅數量:** `[A-]` | ✅ 6
- **核心理據:** 3歲質新馬，剛戰 1400m 旨在熱身並未盡全力，今仗大幅增程切合其 Super Seth 血統，有大幅進步空間。
- **最大風險:** 經驗尚淺，8 檔起步容易造成走位失誤疊外走。

🥉 **第三選**
- **馬號及馬名:** 9 Sonic Belle
- **評級與✅數量:** `[B+]` | ✅ 3
- **核心理據:** 名牌大馬房刻意大幅增程兼換強配，內檔 2 檔形勢極佳，若能把握慳位優勢有力爆冷。
- **最大風險:** 長力從未受考驗，若再次無遮擋或會重蹈覆轍。

🏅 **第四選**
- **馬號及馬名:** 1 Duke Of Clarence
- **評級與✅數量:** `[B+]` | ✅ 2
- **核心理據:** 剛戰克服極劣走位上名，顯示出韌力及狀態正處於上升軌，1732m 適中。
- **最大風險:** 經常出閘緩慢，若今仗步速太慢會導致後追不及。

---

## [第五部分] 📊 數據庫匯出 (CSV)

```csv
1, Maiden, 1732m, Lachlan Neindorf, Peter Gelagotis, 8, Good Harmony, S-
1, Maiden, 1732m, Jake Noonan, Alex Rae, 3, Corviglia, A-
1, Maiden, 1732m, Daniel Stackhouse, Ben Will & Jd Hayes, 9, Sonic Belle, B+
1, Maiden, 1732m, Jason Maskiell, Kim & Gayle Mayberry, 1, Duke Of Clarence, B+
```

✅ 批次完成: 全場 9 匹馬完滿結束 | Top 4 及 CSV 已生成 ✔️
"""

b64 = base64.b64encode(content.encode('utf-8')).decode('utf-8')
cmd = [sys.executable, ".agents/scripts/safe_file_writer.py", "--target", "2026-04-08 Sale Race 1-8/04-08 Race 1 Analysis.md", "--mode", "append", "--content", b64]
subprocess.run(cmd, check=True)
