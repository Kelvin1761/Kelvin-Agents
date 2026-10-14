# EXP-20261013-03 — Stability 分開能力、適用性同可靠性

## 預先登記（未讀本輪候選結果）

日期：2026-10-13；平台：AU。用戶要求重審 stability 設計；現行 baseline 包含
EXP-02 已確認 decoded-form 正確性修正。A/B沿用FORM:PQ=60:40；用戶追加C配比
研究另見下節。外層係數、其他維度、overlay及評估合約固定。新候選只喺
research scorer，唔修改live engine。

### 用戶追加配比研究（候選結果揭示前登記）

用戶明確授權改60／40。增加獨立 **C — FORM:PQ 配比**，固定 FORM 份額
`0,.2,.4,.6,.8,1` 六格（包含baseline .6），唔改 stability 外層係數／其他維度。
先量每格完整 dev 同五個固定日期 folds；全部都係 research。

再做 expanding-time 選擇驗證：用之前 folds，保留 train Gold／Good 都唔低於
baseline、而且至少一個 primary 嚴格更好嘅配比；合格配比取逐維中位數，冇合格
就用baseline .6。鎖定之後測下一個 fold，唔讀下一個 fold 決定配比，唔取argmax。
同時報明改善／損害場次。日期fold1冇歷史訓練，唔入 forward 比較。

今輪配比只同baseline source／PQ測，唔追加6×A×B任意組合搜索。若A／B獨立
失敗，唔因配比後合併數字靚而救返。唔把全部dev最佳配比直接部署。

已搜尋舊實驗，讀 EXP-20260822-04、EXP-20260831-10、EXP-20260902-07/08/09、
EXP-20261013-01/02。唔重試全部移除／減半 PQ、固定久休扣分、單純加大大敗扣分。

### 問題定義

現行 stability 主要量已展示表現，並非統計上嘅「低波動」。今次分開：

1. **能力**：FORM 同完整 PQ 實際表現；保留正負訊號。
2. **適用性**：同途程／跑道接近嘅證據應如何影響今日質素估計。
3. **可靠性**：來源類型、有效場數、資料缺口及情境差異，先作描述性 metadata，
   唔將「波動大」自動變成排名扣分。

### 固定候選（只三個，唔擴展搜索）

- **A — fallback-centre**：只對 career starts>0、PQ provenance 明確為
  `consistency_fallback` 嘅馬，將 PQ fallback 減去現行 consistency 基礎分相對
  中性嘅偏離（64.6−60=4.6），保留原本前三／大敗／其他修正，clip 0–100。
  初出固定52.4保持原樣。完整／recovered PQ 不改。
  假設：缺完整 PQ 時，固定截距可能被當成已證明能力；唔係移除 PQ 全維度。
- **B — contextual-PQ**：只處理明確完整、原 source 為
  `class_adjusted_margin_field_relative` 嘅 PQ。沿用同一批最多四場 dated runs、
  同一 quality 定義及序列權重1/.8/.6/.4，乘
  `(min(歷史距離,今日距離)/max(歷史距離,今日距離))²`；已知跑道種類不同再乘 .25。
  距離／跑道未知不猜，該項兼容權重1。重新加權平均 raw quality，再用同一
  full pre-race field summary／SD 轉回60+20z。包括正負表現，唔只縮高分。
  相同情境嘅全部往績應 algebraically 不變。Recovered/fallback PQ 原樣保留。
- **A+B**：只有上述兩項合併，量相對 A 同 B 嘅邊際；兩種 provenance 不重疊，
  但 race ranking 仍可能有交互作用。唔因組合升而保留獨立失敗 component。

候選係機制假設，固定數值唔宣稱最佳；本輪唔調參，唔反覆救候選。

### 固定語料及驗證

沿用 EXP-01 eligible development：1,762 場、2026-08-05 至 09-21。用 current
runtime 全量重新建立 baseline 與來源／dated-run metadata，結果只喺評分後 join。
Same-day／future PQ run fail closed；legacy recovery 不冒認可用 fresh raw evidence。
包含完整賽前馬群做場內尺度，不能只用有賽果嘅馬重算 SD。

原 terminal 全部已曝光，**本輪完全唔開**，唔重新切一個「新 holdout」。
五個 whole-date chronological dev folds只量穩定性，唔聲稱 pristine out-of-sample。
任何 dev Gold／Good 點估計退步＝DEV_REJECT；分 field-size、來源／證據場數、
途程／跑道、及 baseline SP（如可得）描述／守衛。過 dev 都只係可供未來 shadow。

指標：canonical Gold、Good、Pass、top3_capture_at5、mean_top3_model_rank、
competitive_recall_at5、ndcg_at5、top5_pairwise_auc；配對按場 bootstrap2000／seed7。
排序指標另報 stability 中性消融預算同 paired CI 半寬，細於 MDE 唔作判決訊號。

### 不會做嘅事

唔用 Tamworth 或之前失手 oracle 權重做今日權重；唔加市場 proxy；唔改 FORM
名次／獎金公式；唔用 calendar decay 重試已失敗嘅久休折扣；唔改 live 模型、
golden、健康基準或生成模型說明。

## 執行結果

Current baseline：Gold21.5664%、Good25.6527%、Pass49.7162%。
1,762場／16,921匹；replica逐匹與engine max error<0.01。十項工具測試通過。

| 候選 | dev Gold Δ | dev Good Δ | 救失手／壞成功 | 無primary回歸folds | 判決 |
|---|---:|---:|---:|---:|---|
| A | −0.0568pp | −0.1135pp | 3／1 | 3/5 | DEV_REJECT |
| B | +0.0568pp | +0.2270pp | 17／11 | 3/5 | DEV_ONLY_NOT_VALIDATED |
| AB | −0.1135pp | +0.2270pp | 19／12 | 3/5 | DEV_REJECT |

B Gold CI[−0.5108,+0.6243]pp、Good[−0.2838,+0.7946]pp，13+馬群Gold／Good
各跌1場。B只留研究；冇證實改善，唔部署。AB相對B Gold下降，A唔因組合而保留。

### 六格配比及forward

| FORM:PQ | Gold Δ | Good Δ |
|---|---:|---:|
| 0:100 | −0.9081pp | +0.3405pp |
| 20:80 | −0.2838pp | +0.6243pp |
| 40:60 | +0.0568pp | +0.7946pp |
| 60:40 | 0 | 0 |
| 80:20 | −0.7946pp | −0.0568pp |
| 100:0 | −1.8729pp | −1.1351pp |

40:60係全dev較好，但Gold CI[−0.8513,+0.9648]pp、Good CI[−0.1717,+1.7594]pp；
第二／第三日期foldGold跌，13+Good跌1場、9–10Gold跌1場。不是可部署argmax。

按預先登記規則，前段選配比，四個後段fold依次鎖FORM.2/.4/.6/.6。
1,408個後段場次 pooled Gold −1.0653pp、CI[−1.9886,−0.2131]pp；Good
−0.2131pp、CI[−1.0653,+0.6392]pp。呢個選配比策略拒絕，唔改 live60:40。

### Source regime

完整PQ但FORM無可用名次1,726匹；formal表多為`- (-輸距L)`。頭兩個日期fold
比例26.9%／26.0%，其餘三個接近0%。FORM仍有獎金等調整，唔等於冇訊號。
全期best ratio受資料格式regime混合影響，不能當成live最佳。

### Evidence discipline

Terminal從未開，新dated PQ均嚴格早於目標日；existing reconstructed baseline
嘅mutable歷史統計PIT仍FLAG，不能promotion。所有原始候選／結果保存，不改
指標／日期切法／窗去救候選。MDE表係整個stability中性化嘅參考量級，唔係
個別子component已通過正式RANKING_WIN功效閘；本輪唔做promotion。

**決定**：KEEP RESEARCH TOOL；A／AB／forward配比策略不採用；B及40:60只作
未驗證研究。冇修改 model code，冇commit／push／deploy。

## 可重現性

Snapshot：`scratch/au_stability_redesign_20261013/snapshot.json`（135MB）。
SHA256：`3782d6f6e3cb60c2ed870f07959818c0e660d697ef0d08678e3630081a19cf37`。
Snapshot design保存engine及dev manifest hash、commit、原係數；每場source hash。
原始結果：同目錄`results.json`及`comparison_rows.json`。
[完整設計審視](../audits/au-race-weight-oracle-20261013/STABILITY_DESIGN_REVIEW.md)。

```bash
PYTHONDONTWRITEBYTECODE=1 .venv-au-ml/bin/python \
  docs/experiments/patches/au_stability_redesign.py \
  --snapshot scratch/au_stability_redesign_20261013/snapshot.json \
  --out scratch/au_stability_redesign_20261013

PYTHONDONTWRITEBYTECODE=1 .venv-au-ml/bin/python -m unittest discover \
  -s docs/experiments/patches -p test_au_stability_redesign.py -v
./檢查.sh --quick
./檢查.sh
```

建立current runtime新快照（不能覆蓋原證據）：

```bash
PYTHONDONTWRITEBYTECODE=1 .venv-au-ml/bin/python \
  docs/experiments/patches/au_stability_redesign.py --build \
  --manifest scratch/au_stability_redesign_20261013/dev_manifest.json \
  --snapshot scratch/au_stability_redesign_new/snapshot.json \
  --out scratch/au_stability_redesign_new
```

十項工具tests、quick及完整repo檢查全部通過，log留scratch。
