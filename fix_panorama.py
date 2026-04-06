import re

def fix_file(filepath, new_panorama):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    
    # regex to find the 第一部分 block until the 第二部分
    new_content = re.sub(
        r"## \[第一部分\] 戰場全景 \(Battlefield Panorama\).*?(?=## \[第二部分\] 馬匹深度剖析 \(Horse-by-Horse Forensic\))",
        new_panorama,
        content,
        flags=re.DOTALL
    )
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content)

# Race 2 Fix
race2_panorama = """## [第一部分] 🗺️ 戰場全景

| 項目 | 內容 |
|:---|:---|
| 賽事格局 | 第四班 / 1650米 / 快活谷 |
| **賽事類型** | **`[草地]`** |
| 跑道偏差 | C+3賽道利前置及內欄 (Inner-track bias)。這類型場地特別不利於排在外檔(10-12檔)且缺乏前速的賽駒，如果被迫全程三疊轉彎將提早宣佈出局。 |
| 步速預測 | 慢至中等 (Slow-to-Normal) |
| 戰術節點 | 本場缺乏極端快馬。預期賽事步速偏慢，這將極大程度保護前置馬的體力，而削弱後上馬的追趕空間。 |

**📍 Speed Map (速度地圖):**
- 領放群: #6(1), #12(2)
- 前中段: #5(9), #8(8) 
- 中後段: #1(5), #2(4), #3(6), #9(12), #11(11)
- 後上群: #4(7), #7(10), #10(3)

**🏃 步速瀑布推演 (Step 0 結論):**
- 領放馬: 6 佳福駒, 12 隨緣得勝 | 搶位數量: 2
- 預計步速: 慢至中等 (Slow-to-Normal) | 崩潰點: 唔會崩潰
- 偏差方向: C+3 慢步速極度有利內檔前置馬，後上馬極難反先。
- 受惠: 6 佳福駒 | 受損: 10 耀昌勝世

---

"""

fix_file("/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/2026-04-08_HappyValley (Kelvin)/04-08 Race 2_Analysis.md", race2_panorama)
print("Race 2 fixed")
