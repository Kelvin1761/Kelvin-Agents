# EXP-20261016-01 結果：AU `pace_perf` 診斷（1–3）同修正（4–6）

- **預先登記**：[protocol](EXP-20261016-01-au-pace-perf-protocol.md)（commit `d05a0461`，睇結果之前）
  + 修訂 1（F4 參考速度來源、F5 冇候選，睇過診斷、未量 F4 之前寫）。
- **語料**：研究 dump（`scratch/au_paceperf_dump_20261016.py`），3,288 場／32,448 匹；
  診斷用乾淨窗 2,485 場／71 日；§8 OOS 1,482 場／41 日（warmup 30 日）。
- **A/A**：新 code 還原到 F6 之前（`--variant base`）同原 baseline dump 逐匹 ability 差 **0.0**、
  feature 全同。refit 工具 verify：production 重算 vs 引擎 0.0。
- **來源 availability 仍係 FLAG**：所有正式 v3／§8 判決都係 `REJECT / leakage_audit_failed`。
  下面嘅 verdict 係 `leakage_audit_passed=True` 研究診斷，**唔係 WIN**。

## 診斷（leaf 層面場內配對 AUC，現行 leaf 0.59924）

replica：離線重算對引擎 leaf 中位差 0.008，80.4% 喺 0.5 分之內（差異嚟自引擎場均
包埋冇賽果嘅馬）。所有變體同 baseline 用同一個 replica，所以配對比較公平。

### D1 後上馬偏差 —— **假設錯，方向相反**

同一個 PF 五等份之內，後上馬嘅超額入位率**低過**前置馬：

| 跑法來源 | 後上 − 前置 | 95% CI |
|---|---:|---|
| 往績 @Settled 平均 | **−5.19pp** | [−7.38, −3.00] |
| 今仗跑法標籤 | **−6.81pp** | [−8.43, −5.17] |

即係話 PF 冇低估後上馬；同 PF 分嘅前置馬反而跑得更好。呢個同已知「前置有利」一致
（memory `au-run-style-mostly-unpredictable`），分唔開係 PF 公式定係跑法本身。
**冇修正候選**；「終點 margin 包埋 600 米前蝕嘅位」呢個理論上嘅偏差，喺結果層面睇唔到。

### D2 大敗場 —— **假設錯，大敗有資訊**

| 變體 | Δ AUC | 95% CI | Holm p |
|---|---:|---|---:|
| margin 封頂 6L | **−0.0147** | [−0.0181, −0.0114] | 0.000 |
| margin 封頂 10L | **−0.0031** | [−0.0052, −0.0011] | 0.018 |
| 中位數 | −0.0046 | [−0.0090, −0.0004] | 0.120 |
| 剔最差一場 | +0.0021 | [−0.0012, +0.0054] | 0.446 |

26.3% 往績輸 > 6L、9.0% 輸 > 10L。截短佢哋會**損失**訊號。現行平均數係啱嘅。

### D3 近仗權重 —— **邊緣，未過**

| 變體 | Δ AUC | 95% CI | Holm p |
|---|---:|---|---:|
| 最近 3 場 | −0.0067 | [−0.0130, −0.0005] | 0.120 |
| 最近 5 場 | −0.0018 | [−0.0061, +0.0027] | 0.446 |
| **衰減 0.8^k** | **+0.0055** | [+0.0015, +0.0095] | **0.050** |

衰減係唯一正面嘅變體，但 Holm 後 p = 0.050，未達 < 0.05。依登記**唔入圍**。
用戶要求先可以另開登記，用 §8 測（leaf 準咗唔等於排名會好）。

## 修正

### F4 秒／馬位隨速度變 —— 冇作用，建議唔改

`v_ref` = 16.6539 m/s（修訂 1）。隱含 s/L 只喺 0.164–0.178（q10–q90）之間。
leaf Δ AUC **+0.0002** [−0.0004, +0.0008]。複雜咗但冇分別，**唔建議上**，冇跑 §8。

### F5 飽和 —— 冇候選

揀形狀窗同乾淨窗嘅 PF 分 → 超額入位率曲線都單調上升到 90–95 分
（乾淨窗：70 分 +6.7pp、85 分 +12.2pp、95 分 +14.7pp）。「70 分以上飽和」喺現行數據
唔成立。

### F6 剷走試閘表現（用戶決定）

| Arm | 改咗乜 | fixed arm（現行權重） | refit arm |
|---|---|---|---|
| F6a | 剷 `trial_score` leaf | Gold ±0；Good −0.20pp [−0.43, 0.00] | Good **−0.61pp [−1.14, −0.07]** |
| F6b | + 停初出馬試閘時間代理 | **同 F6a 逐位一樣** | 同 F6a |
| F6c | + PF 唔計試閘行（全部） | Gold −0.14、Good −0.47pp；Top3@5 **−0.0036 [−0.0066, −0.0005]**、NDCG **−0.0035 [−0.0057, −0.0013]**、Top5 AUC **−0.0027 [−0.0050, −0.0002]** | Good −0.68pp [−1.57, +0.28] |

三個都係 `REJECT / primary_regression`（研究診斷），refit 冇救返。B0 vs A0 仍然唔過時。

- **F6b = F6a**：初出馬試閘時間代理喺乾淨窗**一次都冇觸發**（149 匹全部喺 08-05 之前）。
  佢讀 `timing_trial_600m_avg_speed`，Sportsbet 年代冇呢個欄位 —— 死路，剷唔剷都冇分別。
- **F6c 嘅代價嚟自 PF 試閘行**：少過 6 場嘅馬，試閘嘅速度環境係有用嘅，同 EXP-20261012-31
  （Gold −0.37pp）一致。三個排序指標 CI 全負。
- 結論：**試閘表現唔係冇用**。`trial_score` leaf 本身貢獻好細（每分 0.007），剷走代價細；
  PF 入面嘅試閘行貢獻真實，剷走有顯著代價。

### 附帶發現：安全欄觸發率被今日 6 場門檻吹脹

證據厚度安全欄將 `trial_score = 60` 當「冇證據」。EXP-20261015-02 之後，所有
≥ 6 場嘅馬試閘分都係 60，於是：

| 狀態 | 安全欄觸發 | 首選入位 | 首選頭馬 |
|---|---:|---:|---:|
| 現行（試閘計證據） | **17.7%** 場次 | 56.66% | 24.35% |
| F6（試閘唔計證據） | 4.5% | 56.62% | 24.71% |
| 試閘全 60 但照計證據 | 28.2% | 55.17% | 23.26% |

安全欄原本設計觸發率 6.7%。一個刻意停用嘅 leaf 唔應該被當成「缺證據」——
呢個係 §7 類正確性問題，獨立於「剷唔剷試閘」。安全欄只對調 1、2 位，唔影響 Gold／Good／Pass。

## 決定

- D1、D2、F4、F5：**唔改**，現行公式喺呢幾點冇問題。
- D3 衰減：邊緣，等用戶決定要唔要另開 §8。
- F6：**等用戶揀**（證據唔支持全剷；見上表）。研究分支嘅 production code 而家係 F6 全部，
  **未發佈**。

## 重跑

```bash
export PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
for v in base f6a f6b f6c; do
  python3 scratch/au_paceperf_dump_20261016.py --variant $v --out $S/v_$v.json
  python3 scratch/au_paceperf_refit_20261016.py --variant $v predict --data $S/v_$v.json --out $S/wf_$v.json
done
python3 scratch/au_paceperf_diag_20261016.py --data $S/v_base.json --out $S/diag.json
for v in f6a f6b f6c; do
  python3 scratch/au_paceperf_s8_20261016.py --base $S/wf_base.json --cand $S/wf_$v.json --label $v --out $S/s8_$v.json
done
```
refit procedure hash（base）`7207e406…975d`；algorithm hash（去 anchor）兩邊一致。
