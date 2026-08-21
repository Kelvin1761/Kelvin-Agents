# AU Wong Choi — 2026-07-25 三地模型深度覆盤與校準

範圍：Randwick 10 場、Caulfield 9 場、Eagle Farm 9 場。賽果以已保存嘅
Racenet 單次頁面快照為準；賽前排名以原 `Meeting_Auto_Scoring.csv` 為準，
冇用賽果重建或改寫分數。

## 結論先行

今次唔支持改 7D 權重。模型嘅主要問題唔係「將某個已有強訊號計得太少」，
而係部分實際冠軍喺現有數據上真係顯得較弱。硬調權重會用 28 場結果追答案，
而 repo 既有 708–710 場 walk-forward 已證明同類調權普遍 out-of-sample
倒退。

今次實裝三項零排名風險改善：

1. 頭一、頭二相差少於 0.5 分時標示「實質並列」，唔製造虛假精確感。
2. 顯示逐場 PF 覆蓋率；有 provenance 而低過 90% 即警報。
3. 保存 clean-7D 排名前／後 decision trace，明確證明有冇後置 rerank。

## 三地表現

| Meeting | Gold | Good | Pass | 1 Hit | Miss | 官方 shortlist ≥2匹入實際前三 | 冠軍在純分 Top 5 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Randwick | 1 | 0 | 1 | 4 | 4 | 5/10 | 6/10 |
| Caulfield | 0 | 4 | 2 | 3 | 0 | 7/9 | 7/9 |
| Eagle Farm | 0 | 0 | 1 | 7 | 1 | 6/9 | 4/9 |
| 合計 | 1 | 4 | 4 | 14 | 5 | 18/28 | 17/28 |

純 ability 排名另有以下讀法：

- 頭揀贏 8/28（28.6%），高過 708 場 stored-score 基準約 23.7%。
- 頭揀入三甲 18/28（64.3%）；其中 Caulfield R2 頭揀賽後顯示非正常完成，
  反映 late-scratch／runner-status refresh 係流程風險，唔應當普通模型輸。
- 純分冠軍排名：#1 8 場、#2 4 場、#3 1 場、#4–5 4 場、#7 或以後 11 場。

## 模型做得好嘅地方

### 1. Caulfield 係強 negative control

Caulfield 同 Randwick 同為 Soft 6，Caulfield 仲有全程移欄 10m，但模型：

- 9 場零 Miss；
- 7/9 冠軍在 Top 5；
- 純分頭揀贏 5/9。

所以今次冇證據支持全域「Soft 地降權」、「濕地提高 track_score」或者
「大移欄一律加闊 shortlist」。任何 Randwick 修正都必須保住 Caulfield。

### 2. 頭揀整體仍有實用辨識力

雖然官方 Gold/Good 指標唔高，純分頭揀仍贏 28.6%、入三甲 64.3%。即係
模型最前端並非失效；主要落差係部分 meeting 嘅冠軍排序同 shortlist 尾段。

### 3. 場內位置馬 recall 好過冠軍 ordering

Eagle Farm 官方 shortlist 6/9 場至少包兩匹實際前三，但冠軍入純分 Top 5
只有 4/9。呢個組合顯示 7D 能識別「有條件跑近」嘅馬，卻未必有足夠新資訊
將當日最有爆發力嗰匹推到最前。

## 模型做得唔好嘅地方

### 1. 短途 winner ordering

1000–1199m 共 8 場：

- 頭揀零勝；
- 冠軍只得 3/8 在 Top 5；
- 但 8/8 場純分 Top 5 仍至少包兩匹實際前三。

即係短途問題主要係「冠軍排序」而唔係成個 shortlist 完全失明。Randwick
1100–1300m 配大幅移欄係最明顯 cohort，但 Caulfield 表現證明 venue 條件
不可省略。

### 2. Eagle Farm 有明顯市場可見、模型不可見嘅冠軍

Eagle Farm R3、R4、R8、R9 冠軍 SP 分別約 3.8、3.9、2.6、2.6，但模型
排第 7–9。呢啲唔係全部冷門運氣；市場對當日狀態／部署掌握到一啲現有
odds-blind 資料層未捕捉嘅訊息。

三地 11 匹跌出 Top 5 嘅冠軍之中，8 匹 SP ≤ 8。另有 17、21、31 倍三匹
較合理視為高變異／爆冷。

### 3. 一匹頭揀非正常完成係 process miss

Caulfield R2 頭揀喺結果資料為非正常完成狀態。模型輸出如未在開跑前重抓
runner status，就會保留一匹已退出／未正常參賽嘅高分馬。呢類錯誤唔應用
權重補救；正解係 race-time scratch refresh gate。

## 點解唔改權重

喺 20 場頭揀未贏嘅賽事，實際冠軍相對模型 #1 嘅平均 feature 差：

| Feature | 冠軍 − 模型 #1 |
|---|---:|
| pace_figure_score | −15.90 |
| consistency_score | −12.55 |
| form_score | −8.90 |
| sectional_score | −5.12 |
| track_score | −4.46 |
| distance_score | +1.05 |
| trainer_score | +0.38 |
| health_score | +0.16 |
| trial_score | +0.05 |

失手冠軍喺模型最強、歷史最穩嘅訊號上反而更差。只有路程、練馬、健康、試閘
有輕微正差，而且方向及 meeting 穩定性不足。將呢啲微差放大會雙重計數，
亦會破壞 Caulfield negative control。

呢個結果同既有 archive 結論一致：現有數據上，大量 missed winners
「睇落真係較差」。改善需要新資訊或更好嘅 live freshness，而唔係再調同一組
數字。

## 今次實裝嘅改善

### A. Top1≈Top2 校準

Stored pre-race score 可比對樣本 708 場：

- gap < 0.5：154 場，#1 勝 17.5%，#2 勝 15.6%；
- 全體：#1 勝 23.7%。

即係唔應將 #2 自動換上去，而係應承認兩匹實質並列。用現行 engine 重算後，
tie cell 優勢收窄，但 #1 仍冇足夠分野支持「單膽式」表達。

7 月 25 日會觸發 6 場：Randwick R1/R4、Caulfield R3/R5/R6、
Eagle Farm R9。

### B. PF coverage live gate

PF 係有數據時分隔力最高嘅 feature，而近期 live coverage 約 95%。新輸出會：

- provenance 足夠時顯示 `covered/known`；
- 低過 90% 顯示警報；
- 舊檔冇 provenance 時顯示「未能量度」，唔會誤報。

### C. Decision trace

每場 verdict 保存：

- `pre_rank_order`
- `post_rank_order`
- `changed`
- `reason`

現行 scoring contract 係 clean static 7D，所以正常情況必須
`changed=false`。如果將來有人加入 reranker，前後次序同原因會即時可審計。

## 驗證

- AU unit/regression：43 tests 全過。
- 7 月 25 日 replay：28/28 場排名完全不變。
- Decision trace：28/28 `changed=false`。
- Top1≈Top2：6/28 場正確觸發。
- 未實裝任何 wet、venue、rail、sprint 或 Eagle Farm 權重修正。

## 下一輪優先次序

1. race-time scratch refresh gate：屬資料新鮮度修復，優先過調權。
2. odds／market rank 保持獨立第二欄：用作 consensus、blind-spot 警報，
   唔合併入 7D score。
3. Randwick × rail-out × sprint 只做 shadow cohort；等多個 meeting
   有同條件樣本先判斷，並以 Caulfield Soft 6 作固定 negative control。
4. Eagle Farm winner-upside 只接受新資訊（gear change、stewards excuse、
   更即時 trial／market context）；唔再用既有 feature 重排。
