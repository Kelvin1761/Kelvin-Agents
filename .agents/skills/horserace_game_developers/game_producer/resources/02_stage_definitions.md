# 7 階段交付定義

## Stage 1: 需求收集
- **輸入**: 用戶口頭需求 + GAME_CONFIG.txt + 實作計劃書.txt
- **輸出**: 需求清單 (markdown)
- **評審標準**: 用戶確認需求無遺漏
- **Checkpoint**: ✅ 必須

## Stage 2: 設計
- **輸入**: 需求清單
- **輸出**: `_Game_Design_Package.md`
- **參與 Agent**: Lead Designer, Systems Designer, Content Designer
- **評審標準**: GDD 一致性 + 數值合理性 + 內容完整性
- **Checkpoint**: ✅ 必須

## Stage 3: 引擎開發
- **輸入**: _Game_Design_Package.md
- **輸出**: gameEngine.js, raceGenerator.js, GameCanvas.jsx 等
- **參與 Agent**: Game Engine Dev
- **評審標準**: 60 FPS + 物理模型正確 + Config 已同步
- **Checkpoint**: ✅ 必須

## Stage 4: UI 開發
- **輸入**: _Game_Design_Package.md + 引擎 API
- **輸出**: React 組件 (ArcadePage, BettingPanel, LiveRankingPanel 等)
- **參與 Agent**: Frontend Engineer
- **評審標準**: DFII ≥ 8 + 響應式 + Mobile-Ready + Doc 已同步
- **Checkpoint**: ✅ 必須

## Stage 5: 素材製作
- **輸入**: 設計規格
- **輸出**: 精靈圖 + 音效 + BGM
- **參與 Agent**: Pixel Artist + Sound Designer (可平行)
- **評審標準**: 風格一致 + 規格符合 (16色/50KB限制)
- **Checkpoint**: ❌ 無需 (可直接進 Stage 6)

## Stage 6: 測試
- **輸入**: 全部已完成嘅代碼 + 素材
- **輸出**: QA 報告 + Bug 清單
- **參與 Agent**: QA Tester
- **評審標準**: 輕量級 + 重量級 QA 全通過
- **Checkpoint**: ✅ 必須

## Stage 7: 發布
- **輸入**: QA 通過嘅版本
- **輸出**: 最終版本 + CHANGELOG + 文檔同步報告
- **參與 Agent**: Game Ops + (可選) Mobile Engineer
- **評審標準**: 文檔 100% 同步 + 用戶確認
- **Checkpoint**: ✅ 必須
