# EXP-20261009-04 — 七月外層權重上線（user-accepted）＋ race_shape 前瞻 arms

- 日期：2026-10-09；平台：HKJC
- 狀態：**USER-ACCEPTED LIVE／未通過 Stage-4 閘**＋前瞻觀察
- 上游：EXP-20261009-03（同一個候選，Stage-4 判 REJECT: good_positional）

## 決定

Kelvin 2026-10-09 睇咗 EXP-20261009-03 嘅結果（Gold／capture@5／平均排名方向啱、dev Good
−1.09pp ≈ 3 場、全部 CI 跨零），明確接受呢個 trade-off，要求上線並繼續向「減 race_shape」
方向搵最好嘅值。**呢個冇通過表現閘，唔係一個已證實嘅改善。** 先例：EXP-20261007-01。

Live `MATRIX_WEIGHTS`：sectional 0.1285、trainer_signal 0.2469、stability 0.1090、
**race_shape 0.2417**、class_advantage 0.1534、horse_health 0.0404、form_line 0.0801。
（A/B 測嘅係 0.2416，總和 0.9999；largest-remainder 取整令總和＝1，差 0.0001。）
Contract：`HKJC_7D_CONTRACT_2026_10_09_PURE_7D_CORE_BALANCE_RESTORED_...`。初出馬權重不變。

## 點解唔喺舊語料搵「最好」嘅值

333 場上 Good 一場 = 0.36pp，terminal 已經為 0.2416 開咗一次。再喺同一批場次揀最好嘅值
＝用 holdout 調參。四次獨立 fit（0.17–0.24）已經係「搵最好」嘅工作；佢哋同意方向，
冇一個證明到幅度。所以搵最好嘅值改喺**新場次**做。

## 前瞻 arms（任何前瞻場次之前登記，絕對值，唔准之後改）

| Arm | race_shape | 用途 |
|---|---:|---|
| `weight_rollback_0809` | 0.2737 | 舊 live，回退對照 |
| `weight_refit_t02` | 0.2537 | 既有（EXP-20260928-10） |
| live | 0.2417 | 正式排名 |
| `race_shape_w200` | 0.2000 | 候選（其餘按比例） |
| `race_shape_w170` | 0.1700 | 候選（其餘按比例） |

- 每個 arm 120 場 active 先判；Stage-4 v2 配對 bootstrap；永不自動 promote。
- **回退規則**：`weight_rollback_0809` ≥120 場時，如果舊值淨多贏 ≥2 場 Gold 或 Good，
  而另一項唔輸，monitor 會出 `recommend_rollback`（唔會自動執行）。
- 揀 w200／w170 嘅規則：只用 10-09 之後嘅前瞻場次；兩個都要過 Stage-4 v2 對 live；
  兩個都過就揀**較細嘅改動**（w200）。

## 賽日穩定性（Kelvin：有啲日 45%+ Good，有啲日 0%）

332 場／35 個賽日（舊 live 權重）：

- 賽日之間 Good 嘅波動**大過運氣**：賽日 SD 0.169 vs 純運氣 0.135（p=0.015），範圍 0%–57%。
  capture@5 就冇（0.091 vs 0.089，p=0.41）。
- race_shape 當日實際有幾準（場內 AUC，0.42–0.76）同當日表現相關：Good r=+0.47，capture r=+0.63。
  （部分係機械性：race_shape 本身入排名。）
- race_shape 準確度嘅波動有 16.4% 屬於「賽日」層面（運氣只解釋 10.1%，p=0.005）→ 真係有「日」效應。
- 完全剷走 race_shape：Good 22.2%→13.7%、賽日 SD 降到 0.108，但零 Good 日由 5 個變 8 個 —
  佢係 Good 嘅主要來源，唔可以剷。
- 0.2416：賽日 SD 0.169→0.163，最差五日 capture 47.4%→49.4%，最好五日 Good 53.2%→51.0%。
  方向啱但幅度細；真正嘅穩定性要靠「按條件調整」。

### 條件感知要先補數據

- Logic 嘅 going **全部空白**；rail／course 332 場入面 228 場空白。排位表每場都有
  `賽道: C+3 賽道`，可以補返。going 只喺賽果（比賽時嘅地況），要先處理洩漏問題先用得。
- 細格提示（唔可以當結論）：沙田 A 欄 race_shape AUC 0.502（30 場），B 欄 0.679（17 場）。
- 下一步：補 rail 入語料 → 預先登記「按 venue × rail × 路程，只用之前賽日估計 race_shape
  可靠度，收縮後調整權重」→ walk-forward 判。之前已 REJECT 嘅「同日賽果追 bias」
  （EXP-20260928-04）唔重做。

## 驗證

- HKJC auto tests 150 passed；`./檢查.sh` 全綠；golden 重新記錄（120/120 匹非初出馬分數變）。
- 初出馬：145 匹入面 133 匹完全不變；11 匹喺 engine 拒絕嘅場（baseline 冇重新計，假差異）；
  1 匹 raw −0.0007 —— distance-record adjustment 讀 `MATRIX_WEIGHTS["class_advantage"]`，
  初出馬路徑都會讀到。幅度可忽略，但同 `hkjc-debut-weights-are-a-second-ruler` 同類，記低。
- 數據合約重新 calibrate（150 場／1,898 匹，引擎指紋 c4d66a6cbcd4）。
- 三份寫住舊權重嘅文件已更新：`01_scoring_contract.md`、`04_walk_forward_calibration.md`、
  `hkjc-competitiveness-optimisation.md`。
