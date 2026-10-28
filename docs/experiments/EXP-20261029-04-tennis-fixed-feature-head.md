# EXP-20261029-04：相同賽前特徵嘅非線性head

2026-10-29 Sydney；Tennis勝負／F09 C11。**於head候選結果前登記**。

假設：固定同一七欄賽前feature matrix，histogram gradient boosting可提供無截距logistic以外嘅準確度增量。搜索EXP-20261027-07／08／09及EXP-20261029-03；本次不重試已拒絕特徵，亦不選用EXP03點估計最好嘅R。只用事前定義嘅原B_simple七欄。

資料／五段時間fold／21日隔離／缺值／A-B方向沿用EXP03同一lock；13,274個dev targets不變。Logistic重新fit須逐場同保存simple控制誤差≤1e−12。Scaler只fit train、除尺度不扣均值；同一matrix用於兩head。HGB參數沿用總協議：learning_rate=.05、max_iter200、leaves7、min_leaf30、L2=1、early_stopping=False、seed20260826、sklearn1.6.1；其餘明示值見[head source](../../research/tennis_unified/head.py)。沒有grid search。

訓練用+x/−x及y/1−y鏡像、各權重.5；原match總權重1。推論`(f(x)+1−f(−x))/2`，再共同clip[.02,.98]。Swap誤差≤1e−10。只讀自己產生及hash記錄嘅模型artifact，唔載入外部pickle。

比較係原38比較／76檢定family預留嘅`hgb_vs_logistic`；不新開alpha family。輸出另存`head-development/`，重新合併bootstrap／Holm但保留EXP03原結果，逐個已拒絕特徵不因head結果改判。五fold LL／Brier均不退步、pooled正且多重比較支持先ADVANCE_DEV_ONLY；其他同原協議。未驗historical publication clocks，leakage仍FLAG；無同群體完整B_live／市場，不能promotion或聲稱可執行ROI。

事前設定如上；已完成結果見下方。證據根目錄同EXP03；方法／runtime／data／測試log先記入`head-lock.json`。

```bash
P=/Users/imac/Antigravity-repo/tennis-wong-choi/.venv/bin/python
RUN='/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028/f03-f09'
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 "$P" -m research.tennis_unified.head run --lock "$RUN/head-lock.json" --prior-results "$RUN/development" --output "$RUN/head-development"
```

## 結果及判決

44項研究先決測試及quick gate通過。Head lock於`2026-10-28T21:41:47.249685Z`寫入，SHA256 `7e41a7d0c4c564d43c71efd662b2ea152b7cd06dcfeca57680fc7a42e518d37f`。重新fit嘅logistic同EXP03保存simple控制**逐場完全相同**（最大誤差0），排除refit／群體改變造成差異。

| 同13,274場 | Logistic | HGB |
|---|---:|---:|
| Log loss | .62016007 | .62116061 |
| Brier | .21605694 | .21637029 |
| 命中率（輔助） | 64.8862% | 65.1273% |

gain定義control−candidate：LL −.00100054，95% CI[−.00212415,+.00010758]；Brier −.00031335，CI[−.00076225,+.00012486]。兩項都只1／5段不退步，Holm p均1。命中率升約.24pp，但概率準確度及時間穩定性更差，不能改用命中率救候選。

逐fold LL gains依次−.00209589／−.00089753／−.00169238／−.00061201／+.00041636；Brier −.00061690／−.00031981／−.00056347／−.00017281／+.00013813。全部分層及校準另保存在`head-development/summary.json`，五個自己產生嘅模型檔各有hash。

**決定：REJECT_DEV C11本次非線性head。不掃樹深／葉數／特徵救結果，不開新確認或forward。** 更新後76檢定family及原結果分別保存，不覆寫EXP03。最終完整16組gate通過。獨立head replay先核對五個本機產生model hashes及全部預定參數，再逐場推論：最大概率誤差0，loss誤差7.22e−16，PASS；source/report保存在`head-independent-replay*`。`report-export/head-development/`另有exact round-trip Parquet及完整CSV／JSON交付。正式模型及registry沒有由本研究更改。
