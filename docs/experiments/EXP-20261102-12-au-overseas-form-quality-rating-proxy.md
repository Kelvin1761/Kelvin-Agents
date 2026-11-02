# EXP-20261102-12 英愛法往績為主嘅馬：近績質素分改由官方讓磅分推算（USER-ACCEPTED EXPERIMENTAL LIVE）

- **日期**：2026-11-02（Melbourne Cup 前一晚）；**平台**：AU。
- **用戶**：「go ahead and fix, yes i want to add 官方讓磅分。do our best to reflect the score as accurate as possible」。
- **類型**：用戶接受嘅實驗性上線 —— **唔係已證實改善**（樣本太細，判唔到）。即時回退：`WC_AU_OVERSEAS_RATING_PROXY=0`。

## 問題

近績質素分 = 名次（場內百分位）同賽事獎金級別各半。英愛法同級賽獎金結構上細過澳洲（Enfjaar Goodwood Group 3 $202,315 → 獎金 z 2.03；
Kingswood Caulfield Stakes $1,000,000 → z 3.99），而 Sportsbet `CL1` 分唔出 Group 1 定 Listed（EXP-11 已將佢當 Listed），
所以英愛法馬嘅近績質素分冇得同澳洲馬比。2026 Caulfield Cup：Enfjaar 43.6（全場第 14），跑第 3。

## 做法

最近 6 場正式往績有一半或以上喺英愛法（`overseas.mostly_europe`；香港獎金高，唔包）、本駒有官方讓磅分、場內 ≥3 匹有評分兼 SD ≥ 0.5：

    近績質素 z = 0.43 × 場內評分 z；近績質素分 = clip(60 + 20 × z)

0.43 = 08-05 起 2,389 場、場內 corr(近績質素分, 評分分) 平均 —— 即係「只知道評分，近績質素分最好嘅線性估計」，冇用賽果擬合。
用迴歸收縮而唔係照搬評分 z，係因為評分本身單獨 AUC（0.58）弱過近績質素分（0.65），而且評分已經喺官方評分對位維度入面。

## 量到嘅（全部太細，唔係判決）

- 全語料 75 場／91 匹郁；08-05 起 29 場／35 匹。v3 fixed_rule：Gold −0.03pp、Good −0.03pp（各 1 場，CI 掂 0）、排序指標 −0.01；冇分層 CI 全負。
- 受影響馬「模型名次 − 實際名次」平均絕對差 3.60 → 3.37；11 匹近咗、9 匹遠咗。
- Caulfield Cup：Enfjaar 10 → 7（跑第 3）、Wine Dark Sea 11 → 8（跑第 11）、Starford 16 → 12（跑第 13）。
- 舊 Racenet 年代語料（08-05 前）方向相反：嗰陣好多外地馬近績質素分本身偏高，proxy 將佢哋拉低。

## 冇做

- 海外段速（中性 60）、外地騎師（中性 60 ≈ 大賽中位）：冇資料源，維持。
- 冇登記 forward 測試：英愛法往績馬一年得幾十匹，「夠 N 場先判」要等一年以上；改為每個春季嘉年華後人手覆盤。
