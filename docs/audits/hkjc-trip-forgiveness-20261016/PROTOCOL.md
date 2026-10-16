# 高消耗但仍跑好：預先登記（2026-10-16）

Baseline: `3083316d55fd35d798772514248ae2723e6b469b`。HKJC engine、orchestrator、
shared scoring/harness 和上一輪 `2d7ec14c` 無 code diff；只 AU contract 有變。
重用同 session production capture，所有 325 場先核對 raw ability 與完整排名 A/A。
canonical_keys.json 是既定 sample，不依今次結果重篩。351 場排除 6 場 runner
alignment mismatch、20 場 dead speed；截至 2026-10-10（實際最後 10-07）。

## 唯一改動

只作用於 production context 可辨認的沙田普通馬（草地／泥地）；HV、初出馬、
未知場地不變。最近三段 position_window 中，消耗明文為高／極高，並有 XW
數字且最大疊數 ≥3、往績日期可解析且嚴格早於今場，才可能豁免。

兩個 fixed_rule，同一候選家族；揭示結果後不可加 arm／改閾值：

1. `winner`：該仗 finish=1。贏馬正數 margin 是勝出距離，不作輸距。
2. `close_top3`：finish=1，或 finish=2/3 且已知輸距 ≤3 馬位。

合格該段只將其消耗標籤轉為中等（原52／46→60），再按現有最近三段可用值
等權平均。其餘標籤、平均分母、F、D、權重、SIP、場內 cap、其他維度全不動。
沒有 XW／名次／日期／必要輸距，不猜。不新增跑法或疲勞推斷。

## 評估

先 A/A，並將沙田非初出 T 完全中性作部件預算（只做 power，不是候選）。
v3 fixed_rule，Gold／Good、四個既有 ranking metrics，六時間塊，賽日配對
bootstrap 2000 次 seed7，兩 arm×六 metrics Holm。排名訊號預算對照 CI 半寬。
venue、field-size 四桶、baseline首選 SP 五桶、初出馬場次、going（未知照報）。
輸出觸發匹次、受影響場次、排名變化、零變化原因及逐筆最大 raw 調整。

direct production 驗證：預先取每個 arm 首五場觸發場次，加一場 HV、一場 unknown
及一場 debut-containing（去重），所有 raw ability／排名須一致。

不 fit，故無需新 ML。現有近績維度已看名次及輸距；不能由合格馬次較高上名率
推論額外效益，必須看模型全排名的配對差。

## 洩漏及決策

不讀 2026-10-11 起 forward。只用已有往績窗口，日期必須 < target，今場賽果
只在評分後 join。archive 當時可用性尚未全面認證，仍需 FLAG；日期檢查不能
當作完整洩漏 PASS。若有統計 WIN，先處理來源認證再依合約開一次 forward；
沒有 WIN 就保留 production，不因直覺自行取消扣分。研究記錄保存到非 main 分支。

## 用戶追加（頭兩個 arm 出結果後，未檢視 neutral control 績效前）

用戶直接要求測「沙田不用消耗分」。將原先 power control `neutral_trip` 加為
第三個正式 fixed_rule：所有可辨認沙田普通馬 T=60（包括取消低消耗加分），
不轉移其20%內權。原先兩個arm不改。新增arm是用戶獨立提出，並非按結果搜索。
重新計三arm×六metrics Holm；不得沿用原先兩arm顯著性。forward仍然封存。
