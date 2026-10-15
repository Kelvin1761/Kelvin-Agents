# EXP-20261015-10 — 上一仗速度剖面預測下一次出賽

- 日期2026-10-15，AU，基準origin/main `81597057`。
- 搜尋過EXP-04/05/06/08/09及實驗索引；沿用其資料與評估工具，沒有原樣重試同仗能量修正。
- [預登記](EXP-20261015-10-au-next-start-speed-protocol.md)在本輪特徵／結果計算之前寫入。
- 模型／dashboard／試閘門檻／已凍結R1前瞻方案均未改；研究候選不部署。

## 問題與固定方法

X只用目標賽之前**最近一場正式賽**，y是目標賽上名與落第馬的場內配對。
這是跨次出賽預測，不是用同一仗頭段去回歸它自己的全程時間。
最新正式賽缺逐駒時間就缺值，不跳到更舊的一仗；同日／未來往績不准進X。

T是前仗全程相對標準；P是前仗field early相對class-aware標準；Q是個體early
相對該場median。完整profile=[T,P,Q,P²,Q²,PQ]，不另塞late time重複計。
標準沿用現役原版（不是EXP-09新精確途程候選），只用prediction日前source事件fit。
按今仗field z/clip，再乘原recency/distance/going單仗可靠度w/(w+3)。
pairwise logistic ridge固定10，沒有lambda/gain/時窗／子集搜索；零初始化、Newton。
N兩臂其他項目全中性；D兩臂保留deployed score/10作offset，只學額外修正。
所有24次fit均收斂，沒有刪失敗窗或重選最好beta。

## 資料與可重現性

fresh dump SHA256 `f32292b2a4e156400ac135c0764425b5dffc6dc5107547776f39900656680f9f`，
與EXP-08 dump逐位相同（本次main新增HKJC修正與AU測試，AU引擎未變）。
嚴格配對2,496場；71個賽日，首30日warmup，其後六窗41日／1,493場／14,487匹次。
訓練pair數依次2220/2625/3108/3525/3876/4254；每窗只收之前日期的目標賽labels。
原A/A最大差2.3447910280083306e−13；樣本、日期切法、canonical metrics沒有改。
完整輸入hash、24組beta、train-through、各筆previous日期及缺值原因在artifacts。

## 資料覆蓋

| 狀態 | 驗證匹次 |
|---|---:|
| 最近正式賽有完整逐駒時間 | 1,816（12.54%） |
| 最近正式賽未覆蓋 | 11,883 |
| form沒有更早正式賽紀錄 | 788 |

「沒有紀錄」不等於已證實初出馬。嚴格最近一仗口徑比EXP-08任一近期六仗匹配的
3,145匹次少，不能把兩個不同覆蓋率AUC直接當進步。最近往績至target gap中位19日，
四分位14/29日，range2–556日；久休沿固定recency收縮，沒有事後加cutoff。
本輪有297場可比較、2,193對，以下純訊號全部用這同一批馬／同一批pairs。

## 純速度訊號（其餘neutral，overlay0）

| 配置 | 場內AUC | 按日bootstrap95% CI |
|---|---:|---|
| N_total：上一仗全程 | 0.60762 | [0.57382,0.64268] |
| N_profile：上一仗完整剖面 | 0.62061 | [0.59021,0.65164] |
| 現行模型（同observed cohort） | 0.68719 | [0.65927,0.71663] |

N_profile−N_total +0.012996，paired CI[-0.003216,+0.029269]，p=.125；六時間塊4正2負。
剖面有自身訊號，但額外訊號尚未確認，亦未超過現行綜合模型。
這不是「62%推介命中率」，而是同場上名／落第pair的先後辨識率。

## 現行模型以外的增益（相同1,493場，場數）

| 配置 | Gold | Good positional | Pass | 相對現行 |
|---|---:|---:|---:|---|
| 現行固定A1.5回看 | 289 | 394 | 752 | — |
| D_total：加上一仗全程修正 | 291 | 396 | 756 | +2/+2/+4 |
| D_profile：加完整剖面修正 | 291 | 391 | 752 | +2/−3/0 |

D_profile−D_total：Gold0／Good−5／Pass−4。不能因獨立AUC點估計較高便把profile加進模型。
訓練殘差模型會處理與現行模型的重疊，但仍沒有帶來可靠headline改善。

D_total對現行：

- Gold +0.134pp，CI[-0.194,+0.504]pp；Good +0.134pp，CI[-0.224,+0.505]pp。
- NDCG +0.000866，CI[-0.001172,+0.003050]。
- Top5 pairwise AUC +0.000649，CI[-0.000920,+0.002176]。
- Gold六塊4/6不下降、Good5/6不下降，但區間仍跨零，不能稱已證實改善。

D_profile對現行：Good點估計下降，本身已不符primary無回歸要求；NDCG、pairwise
點估計雖較正，不能拿排序指標掩蓋Good損失。兩臂×七metric的Holm調整最小p=1。
pairwise logistic目標與Gold/Good並不完全相同，這個結果不構成事後改KPI或換loss的授權。

### 預先登記的距離分層（對現行，Gold／Good／Pass場數差）

| 今仗距離 | 全部場數 | D_total | D_profile |
|---|---:|---|---|
| ≤1200 | 650 | 0/+3/+1 | −1/+1/−2 |
| 1201–1700 | 668 | +2/−2/+3 | +3/−4/+1 |
| >1700 | 175 | 0/+1/0 | 0/0/+1 |

最新全程修正亦不是所有cohort都正：中距離Good−2。長途有速度可比較僅37場，
純profile AUC0.557 [0.466,0.638]，未證實有效；不據此換長途cutoff。
field-size、venue、going及首選result-SP完整表在results.json；SP只作評估，不進fit。

## 判決與限制

**D_total：NEEDS MORE TESTING，研究候選保留；D_profile：不採用。**
兩臂正式v3判決均REJECT/leakage_audit_failed：原歷史source publication/capture
未完整認證，不能把source FLAG改成PASS。舊窗已看過，不是新的forward holdout。
在fit前記錄原A部件budget/MDE只作背景，不代替新profile完整§6功效預算；
沒有宣稱PRIMARY_WIN或RANKING_WIN，不部署／改dashboard。

下一步較值得驗證的是「最近正式賽全程」的額外資訊及可靠來源覆蓋。
完整剖面單獨有研究訊號，但其與既有模型的重疊／噪音仍未解決；不能把模型係數
解讀成能量消耗因果或真實能力百分比。新的forward R1 family沒有被此輪替換或擴張。

## 測試與重跑

11個針對性測試：missing-latest不能跳舊、future／target往績排除、同日run ambiguity、
可靠度、logistic方向、offset降低已解釋訊號、全零及不足pair中性、future append不改
過去fit／feature、result/SP不進X。完整資料亦驗證1,816筆previous<target、
12,671筆缺值D保持原分、N=60，以及24次train-through<test日期。

artifacts：`/Users/imac/.codex/visualizations/2026/10/15/01a13d68-afa0-77b3-a25d-8a74906a0796/AU-next-start-speed-research/`。
來源seed/form/reference沿用前輪持久artifact，不複製整份原始語料；fresh dump及結果保留。

```bash
export PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_dump_engine_leaves.py --out /private/tmp/au-next-start-current-leaves.json
python3 -u scratch/au_next_start_speed_20261015.py \
 --fresh /private/tmp/au-next-start-current-leaves.json \
 --reference /Users/imac/.codex/visualizations/2026/10/15/01a13d68-afa0-77b3-a25d-8a74906a0796/AU-neutral-speed-research/results.inputs.json \
 --events /Users/imac/.codex/visualizations/2026/10/15/01a13d68-afa0-77b3-a25d-8a74906a0796/AU-fulltime-implementation/seed-events.json \
 --forms /Users/imac/.codex/visualizations/2026/10/15/01a13d68-afa0-77b3-a25d-8a74906a0796/AU-fulltime-implementation/form-blocks.json \
 --out /private/tmp/au-next-start-results.json
python3 -m unittest discover -s scratch -p 'test_au_next_start_speed.py' -v
```

今輪是未通過發布證據的研究，按repo收工規則只保存研究分支，不merge／release／部署。

驗證：`./檢查.sh --quick`及完整`./檢查.sh`全部通過；11個針對性測試亦通過。
AU/HKJC golden與模型說明檢查均通過，沒有重錄／重校準其他平台資源。
