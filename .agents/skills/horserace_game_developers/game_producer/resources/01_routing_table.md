# 遊戲監製路由表

## 路由決策樹

```
用戶需求
├── 涉及遊戲規則/機制/流程？ → @Lead Designer
├── 涉及數值/賠率/經濟/平衡？ → @Systems Designer
├── 涉及馬匹資料/情報/內容？ → @Content Designer
├── 涉及 UI/React/頁面/組件？ → @Frontend Engineer
├── 涉及 Canvas/物理/引擎/比賽模擬？ → @Game Engine Dev
├── 涉及像素美術/精靈圖/素材？ → @Pixel Artist
├── 涉及音效/BGM/音樂？ → @Sound Designer
├── 涉及測試/QA/品質？ → @QA Tester
├── 涉及 Bug修復/維護/文檔同步？ → @Game Ops
├── 涉及 iOS/Android/手機？ → @Mobile Engineer
└── 唔確定？ → 問用戶澄清
```

## 路由附帶資訊

每次路由畀下游 Agent 時，必須附帶：
1. **任務描述**：明確嘅工作範圍
2. **輸入文件**：需要讀取嘅文件列表
3. **完成標準 (DoD)**：點先算完成
4. **Design-Code Sync 提醒**：工程師 Agent 必須同步文檔
5. **預計回報時間**：畀用戶預期管理

## 跨 Agent 任務處理

當需求涉及多個 Agent 時，按以下優先順序路由：
1. 規則/數值定義（Designer 類）→ 先做
2. 內容/素材準備 → 次做
3. 工程實作 → 最後做
4. QA 測試 → 工程完成後

## 衝突處理
- 兩個 Agent 職責重疊 → 查閱跨系統分工表
- 下游 Agent 回報失敗 → 最多重試 3 次，然後暫停問用戶
