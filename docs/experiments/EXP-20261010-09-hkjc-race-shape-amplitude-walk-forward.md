# EXP-20261010-09 — race_shape 幅度 walk-forward（處理押注內檔）

- **日期**：2026-10-10；平台：HKJC；**Stage 4 v3 `walk_forward_oos`**
- **動機**：模型頭三平均檔位百分位 0.30 vs 實際上名馬 0.43；每日 Good 對內檔偏差 r −0.616（EXP-20261010-02）
- **工具**：`hkjc_weight_study.py --arm wf_shape_k`；9D dump（main `13999e13`）
- **定義**：race_shape′ = 場內中位數 + k ×（race_shape − 場內中位數），只改非初出馬；每個賽日只用之前賽日
  fit k ∈ [0, 1.5]（場內 softmax、τ=3），首 10 個賽日 k = 1

## 結果

- **每次 fit 都要大幅縮細 race_shape**：k 由 0.44 慢慢跌到 0.31，25 次 refit 好穩定。即係以機率
  （likelihood）計，race_shape 嘅分差應該只有而家三分之一左右。
- **但排名冇改善**（286 場，244 場變）：Gold −1.40pp [−4.5, +1.4]、Good −1.05pp [−3.7, +1.5]、
  recall@5 +0.008 [−0.004, +0.021]，全部跨零 → **REJECT（primary_regression）**。賽日 Good SD 0.153 → 0.147。

## 解讀

「機率校準」同「頭幾選準唔準」係兩件事：縮細 race_shape 令全場機率更貼實際，但頭兩三選反而
冇好處 —— 同 [[hkjc-ranking-gains-cost-good]]、EXP-0928-08 一樣嘅形狀。所以押注內檔問題用
「縮細檔位幅度」解決唔到排名；如果日後要用模型機率做落注金額，k ≈ 0.35 嘅校準就有用。

**維持現狀。** 下一步唔係再縮檔位，而係搵 race_shape 以外能夠喺外檔有利日捉到馬嘅資訊
（例如早段位置／步速，EXP-20261010-02 篩選有獨立訊號）。
