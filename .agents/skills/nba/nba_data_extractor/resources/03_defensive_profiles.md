# 防守大閘分類標準與知名球員清單 (Defensive Profiles)

本文件定義三大防守類型嘅分類標準，以及目前聯盟中嘅知名防守大閘。Extractor 使用此清單進行 Step 3 防守大閘掃描。

---

## 分類標準

### Type 1: 外線鎖死型 (Perimeter Lockdown) — PG/SG 防守者
**特徵**：
- 入選過 All-Defensive Team 或以頂級單防後衛聞名
- 擅長壓制對方主控/得分後衛嘅持球進攻
- 影響範圍：直接降低對位後衛嘅得分 + 助攻

**影響對象**：對位 PG/SG

**知名球員** (需每季更新)：
- Jrue Holiday
- Alex Caruso
- Derrick White
- Marcus Smart
- Davion Mitchell
- Herb Jones (可守 1-3)
- Amen Thompson
- Dyson Daniels
- Cason Wallace

### Type 2: 側翼封鎖型 (Wing Stopper) — SF/Wing 防守者
**特徵**：
- 擁有頂級臂展與橫移速度
- 具備 1 守到 4 嘅「無限換防 (Switch-All)」能力
- 影響範圍：壓制對位側翼嘅得分效率

**影響對象**：對位 SF/PF，有時延伸到 SG

**知名球員** (需每季更新)：
- OG Anunoby
- Mikal Bridges
- Herbert Jones
- Andrew Wiggins
- Dillon Brooks
- Dorian Finney-Smith
- Kawhi Leonard (健康時)
- Jimmy Butler
- Aaron Gordon
- Tari Eason

### Type 3: 禁區守護者 (Rim Protector) — C/PF 防守者
**特徵**：
- 場均阻攻 (BLK) ≥ 1.5 或對手籃下命中率極低
- 護框威脅大幅壓制所有依賴切入得分嘅球員（**不僅限大個子，包括切入型後衛/側翼**）
- 影響範圍：降低全隊禁區內得分效率

**影響對象**：所有依賴切入得分嘅球員（跨位置）

**知名球員** (需每季更新)：
- Rudy Gobert
- Anthony Davis
- Victor Wembanyama
- Jaren Jackson Jr.
- Evan Mobley
- Brook Lopez
- Myles Turner
- Chet Holmgren
- Walker Kessler
- Kel'el Ware

---

## 複合防守陣式

### 鐵桶陣 (Lockdown Formation)
當一支球隊**同時擁有**外線鎖死型/側翼封鎖型 + 禁區守護者上場時：
- 標記為 🔒🔒 **鐵桶陣**
- 全隊得分 Over 盤口需全面警戒
- 切入型球員受壓最嚴重

### 禁區真空 (Rim Vacuum)
當一支球隊嘅**主力禁區守護者缺陣**時：
- 標記為 🎯 **禁區真空**
- 切入型球員得分預期大增
- 籃板盤口可能受影響

---

## 掃描輸出格式

```
🛡️ 防守大閘狀態 ([Team Name])

外線鎖死型 (Perimeter):
  - [球員名] — [Active/Out/GTD] | 防守評級: [All-Defensive 1st/2nd / Elite] | 來源: [X]

側翼封鎖型 (Wing):
  - [球員名] — [Active/Out/GTD] | 換防範圍: [1-3 / 1-4] | 來源: [X]

禁區守護者 (Rim):
  - [球員名] — [Active/Out/GTD] | BLK: [X.X] | 防守覆蓋: [Drop/Switch/Hybrid] | 來源: [X]

球隊防守效率: 第 [X]/30 (DRTG: [XXX.X]) | 來源: [X]

⚠️ 特殊標記: [🔒🔒 鐵桶陣 / 🎯 禁區真空 / 無]
```

---

## 重要提醒
- 此清單為**參考基準**，非窮舉。Extractor 搜索時若發現名單外嘅頂級防守者，亦應納入。
- 防守者名單需隨賽季更新。交易後球員嘅球隊歸屬以最新搜尋結果為準。
- 防守者是否出賽嘅狀態 (Active/Out) 必須透過當日傷病報告即時確認，不可使用舊數據。
