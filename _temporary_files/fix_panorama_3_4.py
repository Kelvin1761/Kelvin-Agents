import re

def fix_file(filepath, new_panorama):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    
    new_content = re.sub(
        r"## \[第一部分\] 戰場全景 \(Battlefield Panorama\).*?(?=## \[第二部分\] 馬匹深度剖析 \(Horse-by-Horse Forensic\))",
        new_panorama,
        content,
        flags=re.DOTALL
    )
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content)

# Race 3
race3_panorama = """## [第一部分] 🗺️ 戰場全景

| 項目 | 內容 |
|:---|:---|
| 賽事格局 | 第四班 / 1000米 / 快活谷 |
| **賽事類型** | **`[草地]`** |
| 跑道偏差 | C+3 賽道 1000 米極端依賴前速及內欄。起步後直路極短即入彎，排外檔馬匹若未能及早切入，極易被頂出三四疊，等同提早出局。 |
| 步速預測 | 快 (Genuine-to-Fast) |
| 戰術節點 | 此程排檔影響極深，特別留意內檔起步的前速馬。外檔馬必須擁有極強爆發力或特佳際遇方能克服偏差。 |

**📍 Speed Map (速度地圖):**
- 領放群: #3(8), #8(9), #10(2), #11(5)
- 前中段: #4(7), #7(3) 
- 中後段: #1(6), #12(4)
- 後上群: #2(11), #5(1), #6(10), #9(12)

**🏃 步速瀑布推演 (Step 0 結論):**
- 領放馬: 10 佳佳友, 8 風采人生, 11 友得盈 | 搶位數量: 3+
- 預計步速: 快 (Genuine-to-Fast) | 崩潰點: 600m
- 偏差方向: 快步速兼排檔極端化，內檔後追馬可受惠，外檔前置馬爭位必大消耗。
- 受惠: 10 佳佳友, 12 萬眾開心 | 受損: 9 怪獸波士, 2 凝聚美麗

---

"""

# Race 4
race4_panorama = """## [第一部分] 🗺️ 戰場全景

| 項目 | 內容 |
|:---|:---|
| 賽事格局 | 第四班 / 1650米 / 快活谷 |
| **賽事類型** | **`[草地]`** |
| 跑道偏差 | C+3 賽道存在明顯的內欄及前置優勢 (Inner-track bias)。外檔馬匹若未能及早切入，全程走三疊的體力消耗極為致命。 |
| 步速預測 | 中等至快 (Normal-to-Fast) |
| 戰術節點 | 外檔爭奪激烈，排外檔的前領馬被迫大步搶前以求切入，可能扯快步速，將為排好位或部分後列馬提供追趕空間。 |

**📍 Speed Map (速度地圖):**
- 領放群: #4(11), #7(7), #8(3)
- 前中段: #1(5)
- 中後段: #2(8), #5(9), #6(6)
- 後上群: #3(2), #9(10), #10(12), #11(4), #12(1)

**🏃 步速瀑布推演 (Step 0 結論):**
- 領放馬: 8 頌星, 4 新力飆, 7 喜馬 | 搶位數量: 3
- 預計步速: 中等至快 (Normal-to-Fast) | 崩潰點: 400m
- 偏差方向: 外側馬強行切入將致前段步速消耗，有利留前的內檔馬及中置馬。
- 受惠: 8 頌星, 2 勁進駒 | 受損: 4 新力飆, 10 大數據

---

"""

fix_file("/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/2026-04-08_HappyValley (Kelvin)/04-08 Race 3_Analysis.md", race3_panorama)
fix_file("/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/2026-04-08_HappyValley (Kelvin)/04-08 Race 4_Analysis.md", race4_panorama)

print("Race 3 and 4 fixed")
