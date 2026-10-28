# C層與市場定價的結構診斷

C用市場價作預測特徵，再用市場價計EV，本身不是邏輯矛盾。問題在於是否有經獨立驗證的增量訊號。EXP-20261022-03證明C比舊live-like引擎校準好，**沒有證明贏市場**；其原記錄亦預先指出會令多數舊穩膽變負EV。

現有公式 `logit(p)=a_stat+.755logit(1/odds)+.140logit(h)`，h最大.95。係數不是75.5%／14%的線性權重。在market clipping沒啟動的區域，p>1/odds等價：

`a_stat+.140logit(h)>.245logit(1/odds)`。

因此偏低價的腿較難通過。即使L10十場全中，價1.30：

| stat | C | 打和概率 |
|---|---:|---:|
| PTS | 73.6% | 76.923% |
| AST | 73.1% | 76.923% |
| REB | 76.2% | 76.923% |
| 3PM | 73.8% | 76.923% |

未四捨五入的最大L10零edge價約PTS1.620／AST1.686／REB1.357／3PM1.600。程式有0.1pp rounding，edge>=0可容許邊界小差。這些是純公式推導，不是績效結果或全市場價值判決。banker_pool要求每腿edge>=0，故低價腿可在組合前被系統性排走。C較高價仍可報正EV，不是永遠沒有bets。

`1/odds`是含margin的原始隱含概率，C截距不等於逐腿唯一去水。現役C只有價／L10／stat直接輸入，上游情境／ML概率會被覆蓋；不能將上述公式當成已包含全部usage、防守、分鐘的獨立模型。

建議比較市場baseline、C、無價格的逐stat模型及將來經獨立證據支持的hybrid；不能單純關C恢復舊過度自信機率。新獨立模型結果見EXP-20261025-04：目前未能證明勝市場，沒有替換C。SGM聯合EV仍需聯合概率及原生組合價，逐腿正EV是現有保守policy，並非所有正EV組合的數學必要條件；若要評估該policy應另立shadow實驗。

可重現代數、model ID及config hash：`/Users/imac/WongChoiData/NBA_Research/2026-10-25-selection-flow-and-daily-multi/C_Market_Anchor_Diagnostic.json`，不使用賽果、不fit、不改C或EV閘。
