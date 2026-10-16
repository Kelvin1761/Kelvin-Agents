# EXP-20261016-18 結果：AU 官方評分對位六項審計

- **預先登記**：[protocol](EXP-20261016-18-au-class-weight-audit-protocol.md)（`39fd8db4`，量度之前）。
- **語料**：`scratch/au_class_audit_dump_20261016.py` @ `05dd1b20`，乾淨窗 2,485 場／23,949 匹。
  離線 replica：class_score、rating_score 同引擎差 0，ability 差 1e-4（已知 proven_class 捨入）。證據：`EXP-20261016-18-evidence/`。
- **上線**：R1x、R2x、R4x、R5a、R5b、R6x。R3x 冇測（條件唔成立）。

## 描述

| 項 | 量到 |
|---|---|
| R1 同場兩把尺 | 145 場混合場次。同一 rating_score 區間，代理馬跑輸評分馬：64+ 區 +3.3pp vs **+16.6pp**；60–64 區 −0.6pp vs +2.6pp —— 代理分高估 |
| R2 級數分計兩次 | 代理馬 8,705 匹（36%），維度入面級數佔 0.50（評分馬只 0.15） |
| R3 降班 +2.1 | 今場獎金覆蓋：08、09 月 0%，10-02 起 38.4%；觸發率 08–09 月 0%、10-02 起 5.2%。觸發馬超額 **+10.6pp**（n 246）vs −0.1pp —— 方向啱。live 觸發率**高過**以前，唔係「live／回測唔一致」→ 依登記只報告 |
| R4 絕對名次 | 1,755 匹嘅上名／冇表現旗改變 |
| R5 人手係數 | 有評分馬：BM58 2,055、處女 611、BM72 41；其他 12,489 |
| R6 場地分級 | Belmont（564 次）、Morphettville（299 次）被當省賽；「省賽轉都會」條件 1,088 → 1,469 |

## 候選（v3 fixed_rule 全紀錄，2,485 場，對 baseline）

| 候選 | 判決器 | Gold | Good | 規則 → 決定 |
|---|---|---|---|---|
| R1x 混合場代理只用負磅尺 | **RANKING_WIN** | +0.04 [0.00, +0.13] | 0.00 | 簡化／修正 → 採用 |
| R2x 代理馬級數只計一次 | REJECT（too weak） | +0.12 [−0.08, +0.37] | 0.00 | Gold、Good ≥ 0 → 採用 |
| R4x 名次場內百分位 | REJECT（too weak） | +0.04 [−0.08, +0.19] | +0.12 [0.00, +0.28] | §7 → 採用 |
| R5a 剷 BM／處女乘數 | **RANKING_WIN** | 0.00 | 0.00 | 簡化 → 剷走 |
| R5b 剷前三門檻 | **PRIMARY_WIN** | **+0.40 [+0.08, +0.73]** | 0.00 | 簡化 → 剷走 |
| R6x 補阿德萊德／珀斯都會 | REJECT（too weak） | 0.00 | 0.00 | §7 → 採用 |

冇候選有 primary 或分層 CI 全負。各自最細 p：R5a NDCG 0.004、R5b Gold 0.015、R1x NDCG 0.035；Holm 跨 6 個候選只有 R5a 嘅 NDCG 過（0.024）。

## 合併版（上線嘅引擎，用真引擎前後 dump 量）

- 離線 replica 合併版同真引擎有 81 匹（0.3%）差最多 0.89 分：class_score 喺引擎入面仲會餵 stability 嘅 −4 同配搭分嘅 −3，replica 冇傳導。**以真引擎為準。**
- v3 fixed_rule：**PRIMARY_WIN**；Gold **+0.60pp [+0.19, +1.04]**（p 0.003）、Good +0.04pp [−0.28, +0.37]；
  NDCG@5 +0.0016 [+0.0002, +0.0031]；冇分層 CI 全負。Gold 21.17% → 21.77%，首選贏率 23.42% → 23.66%。
- 頭兩名 $15+ 跑尾三分一：163 → 160 [−9, +3]。
- §8 四 arm（參考，ruler 分支模組；OOS 1,482 場／41 日）：研究判決 **PRIMARY_WIN / fixed_arm_win（用現行權重上線）**；
  fixed arm Gold **+0.81pp [+0.32, +1.30]**（六個 block 全正，Holm p 0.002），Good +0.07pp；refit arm 打和；`baseline_weights_stale = False`。

## 警告

- 同一 41 日 OOS 窗已經用過多次（EXP-06／09／10／12／17）。合併版 p 0.003 用 Holm 跨 7 個檢定仍然 < 0.05，
  但係「重用窗口」嘅證據；要靠之後新賽日確認。
- R2x 嘅實施：rating 代理減 (0.15／0.70) × (class_score − 60)，令維度入面級數總份額 = 0.35，同評估嘅「維度內級數當 60」數學等價
  （clip 邊界除外）。報告入面代理 Rating 分會細過以前。
- `class_score_live_delta`（EXP-20261009-04 回退影子）冇跟 R2x 調整，代理馬嘅影子值會差少少；純顯示／回退用。

## 留低

- R3：降班觸發馬超額 +10.6pp，而家只加 +2.1。10-02 先開始有今場獎金，乾淨數據得兩星期，**另開登記**等夠樣本先測幅度。

## 重跑

```bash
export PYTHONDONTWRITEBYTECODE=1
python3 scratch/au_class_audit_dump_20261016.py --variant f6a --out $S/cls.json            # 改動前 @05dd1b20
python3 scratch/au_class_audit_eval_20261016.py --dump $S/cls.json --outdir $S/arms
python3 scratch/au_tier_fix_eval_20261016.py $S/arms/base.json $S/arms/<arm>.json $S/arms/v3_<arm>.json
python3 scratch/au_class_audit_dump_20261016.py --variant f6a --out $S/cls_new.json        # 改動後
python3 scratch/au_tier_fix_eval_20261016.py $S/cls.json $S/cls_new.json $S/v3_engine.json
```
