# EXP-20261113-43 預先登記：前置馬加分按直路長度／逐場地（walk-forward，補齊幾何之後）

> 量度之前寫（未睇任何候選賽果）。結果另寫 `EXP-20261113-43-au-front-by-straight-length-results.md`。

- **提出**：用戶 2026-11-13「好，重測」—— 用 EXP-20261113-42 補完嘅直路數據（120／133 場地，08-05 起場次覆蓋 93%），
  再試「邊啲場地應該幫前置馬加分」。
- **baseline**：`FINAL.json`（`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/au-noise-20261113/`，main `1c33b058` 評分；
  之後 AU 引擎只有 `b0ab4a7e` 純顯示改動）。判決窗 2026-08-05 起。幾何：`au_track_geometry.json` @ main `ce1bdcc1`（靜態場地資料，冇前視）。

## 已知（寫登記之前）

- EXP-20260902-01（跑法 × 直路特徵）、EXP-20261113-23 L1–L3（< 375m 人手 +1／+2）、EXP-20261113-41 W1（< 375m walk-forward β≈2.2）：全部 REJECT。
- 描述（唔做判決）：前置馬喺模型名次 × 馬群格內剩餘超額，逐場地 r(直路, 超額) = −0.61（11 個場地）；Ipswich／Townsville 正、Ascot 負。
  ⚠️ 逐場地表係睇咗先講，**唔用嚟揀場地**；以下兩個 arm 都由 walk-forward 自己揀。

## 共同設定（全部寫死）

- 前置 = 跑法標籤（`running_style_line`，賽前）含「前領」或「跟前」（同 L2／W1）。
- 只有場地有直路長度先會郁；冇幾何 → 唔加。
- `ability' = ability + β`（前置馬），β 夾喺 [−5, +10]（容許長直路扣分）。
- 每個賽日 t 只用 **t 之前** 嘅賽日 fit；頭 **20 個賽日** warmup（β = 0）。logistic 用 Newton（最多 50 次）；
  `b`（ability 斜率）≤ 0 或者唔收斂 → 當日所有 β = 0。

## 候選

- **V1 直路線性**（2 個參數）：`入前三 ~ a + b·Δability + c0·F + c1·F·z`，F = 前置且有幾何，z = (直路 − 350) ÷ 100。
  場地 v 嘅 β_v = (c0 + c1·z_v) ÷ b。即係每個場地按佢自己嘅直路長度攞唔同加分。
- **V2 逐場地收縮**：先 fit 全體 `a + b·Δability + c0·F`；再逐場地用 offset 只 fit d_v（`F` 喺場地 v 嘅額外效應，1 維 Newton），
  收縮 c_v = c0 + n_v ÷ (n_v + 200) · d_v（n_v = 該場地之前前置馬匹數；k = 200 寫死）。β_v = c_v ÷ b。
  場地未出現過 → c_v = c0。

## 判決

- 合約 v3，`mode="walk_forward_oos"`，primary Gold／Good，ranking `top3_capture_at5`／`ndcg_at5`／`top5_pairwise_auc`，賽日 bootstrap 2000。
  §8 唔適用（overlay，唔改 leaf）。
- 預先聲明分層（任何一個 CI 全負 → 唔上線）：judge 內置（馬群、地況、首選 SP、路程、首選跑法）。
- **多重比較**：同 L1／L2／L3／W1 當同一 family（6 個 arm），Holm 調整後 p < 0.05 先算 WIN。
- 冇 WIN → REJECT。

## 描述（唔做判決）

- 最後一日每個場地嘅 β_v（V1、V2），同頭三選命中數分佈（0／1／2／3 hit）。

## 唔准做嘅嘢

改 k、z 中心 350、夾範圍、warmup、前置定義；睇完結果加第三個 arm；用某段日子揀；揀場地名單。

## 已知限制

08-05 起窗已重用好多次；同一個「直路 × 前置」問題今日第三次開。Holm 6 個 arm 之後功效要求好高 —— 冇 WIN 唔代表冇效應。
