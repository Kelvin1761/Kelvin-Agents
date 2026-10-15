# EXP-20261015-09 — 精確途程標準、分段剖面與前瞻準備

- 日期2026-10-15，AU，基準`ca2c4bd6`；後續研究，不部署參數。
- 前置：[預登記](EXP-20261015-09-au-distance-par-protocol.md)、EXP-04/05/06/07/08。
- 假設：同馬場400m band混合不同起步點，精確途程標準可能減少長途比較偏差。
- 新公式僅將contextual standard的`track_band=track:distance//400`換成
  `track:distance`；ridge懲罰仍30，其餘context、class nuisance、歷史trackday variant、
  最近六仗／90日／途程權重／可靠度收縮、排名gain1.5完全不變。
- 舊窗已觀察、歷史source capture/publication仍FLAG，沒有新盲測／正式WIN聲稱。

## 資料與完整性

2,496場／2026-08-05至2026-10-14；首30個賽日warmup，之後41日1,493場驗證。
速度可比較411場／3,145匹次／4,774對。使用EXP-08 fresh engine inputs，
相同seed-events及form identity；每個target只用較早日期fit標準。
原A/A重播71日全通過，最大raw差`2.3447910280083306e-13`。
沒有複製完整語料，沒有新數據抓取，沒有賠率進特徵。

## 同樣本純訊號（其他leaf中性／overlay零）

| 指標 | 場內AUC | 按日2000次bootstrap95% CI |
|---|---:|---|
| 舊全程A | 0.60725 | [0.58479,0.63060] |
| 精確途程全程 | 0.61290 | [0.59120,0.63640] |
| 精確途程頭段 total−L800 | 0.54734 | [0.52786,0.56734] |
| 精確途程L800 | 0.56305 | [0.53731,0.58785] |

新全程−舊全程AUC差`+0.005656`，paired CI`[-0.002433,+0.014354]`，p=.175。
三個新phase各自對0.5的diagnostic family Holm後均p<.001，但這不是對原全程的增益。
頭段、L800沒有加入排名；三個指數不相加，沒有把部分與總和的相關性當成能量因果。

| 今仗途程 | 舊全程 | 精確全程 [CI] | 精確頭段 | 精確L800 |
|---|---:|---|---:|---:|
| ≤1200 | 0.6250 | 0.6250 [0.5970,0.6512] | 0.5997 | 0.5384 |
| 1201–1700 | 0.6260 | 0.6279 [0.5877,0.6708] | 0.5223 | 0.5913 |
| >1700 | 0.4837 | 0.5212 [0.4667,0.5787] | 0.4577 | 0.5489 |

長途點估計改善，但52場可比較樣本不足確認。其頭段／L800 CI亦跨0.5。
這不是新增長途cutoff或逆向頭段評分的理由，分層只作診斷。

## 長途資料審計

- 411個有速度證據的長途出賽觀測，匹配往績中位數5仗。
- 長途往績占聚合權重中位數80.46%，並非普遍由短途往績主導。
- 85/411個觀測完全沒有匹配長途往績；精確同程往績權重中位數為0。
- 歷史往績所在track×400m band訓練樣本中位數115場；track×精確distance只有19場。
  精確標準更貼近起步點，但樣本更稀疏，保留原ridge收縮，沒有降低懲罰來救結果。
- 不能由此斷言低樣本是所有長途失效的原因；是可重現的支持度限制。

## 排名比較：相對已部署固定A1.5（相同1,493場）

| 配置 | Gold | Good positional | Pass |
|---|---:|---:|---:|
| 已部署標準回看 | 289 | 394 | 752 |
| 精確途程標準回看 | 289 | 395 | 753 |
| 差 | 0 | +1 | +1 |

NDCG差+0.000400，CI[-0.000113,+0.001064]；Top5 pairwise AUC差−0.000177，
CI[-0.000644,+0.000234]。排序證據混合且不確定；沒有證實比現役版本更好。
在候選結果之前量原A部件移除budget/MDE，完整值在JSON；沒有改把尺。
canonical v3結果REJECT/leakage_audit_failed，原歷史source FLAG沒有被改成PASS。
**決定：NEEDS MORE TESTING；精確標準留研究，不改現役模型／dashboard。**

## 固定R1前瞻影子工具

新工具`scratch/au_speed_forward_shadow.py`：

1. `freeze`從EXP-08最後一個時間窗取R1（訓練截止2026-10-08），按日期而不是
   測試成績選；輸出不可覆寫的config，凍結權重、baseline、來源結果hash及引擎fingerprint。
2. `capture`讀新賽日前已評分Logic及當時原始不可改寫時間bundle，檢查
   freeze≤prediction≤now、source capture≤prediction、target/date/hash/version、
   bundle內無同日／未來事件，並重算核對captured baseline。
3. Logic未存可驗證jump timestamp，故同日capture拒絕；只准前一日或更早。
   缺逐駒速度者貢獻零；整個source不可用或版本／baseline漂移則拒絕。
4. 獨立輸出immutable shadow JSON，有input/config/source/record hash及兩套排序。
   不讀result/SP欄位、不覆寫Logic／推介／dashboard，**尚未自動接入每日pipeline或排程**。
5. 凍結profile的204場／2,064匹次歷史公式重播與EXP-08最後窗口R1逐匹完全一致（max差0）。
   這是程式核對，不是新前瞻結果。

最終config：artifacts的`R1-forward-v1.json`；hash
`230e3872284266fc53e28331b6241d243a64e7e2bf2a64055c26dbf0df126616`。
它鎖定完整引擎Python檔及shadow程式；早期準備用`R1-frozen-forward.json`已被此版本
取代（尚無前瞻capture），保留舊檔作準備過程記錄，不可用於正式shadow。
單一profile不繼承逐窗Gold+3/Good+5，且當中其他六維都有改權重；收益不能全歸功速度。
新精確途程候選不偷加進這個family。真正前瞻資料目前**0場**；至少30個新賽日、
1000場及200場有速度可比較賽事才開一次確認，不在收集中途調參。
上述門檻已寫入config／protocol，尚未有自動結算或開盲程序；後續需依canonical
evaluation harness配對賽果及執行此gate，不能把準備好CLI說成已開始自動收樣。

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scratch/au_speed_forward_shadow.py capture \
  --logic '<新賽日前已評分Race_X_Logic.json>' \
  --config '<artifacts>/R1-forward-v1.json' \
  --bundle '<該prediction所用的原始immutable bundle>' \
  --out '<獨立shadow目錄>/新賽日_場地_Race_X.json'
```

## 重現與保存

artifacts：`/Users/imac/.codex/visualizations/2026/10/15/01a13d68-afa0-77b3-a25d-8a74906a0796/AU-distance-par-research/`。
包括完整results、逐馬預測、long-history audit、frozen config、formula proof、logs與manifest。
資料路徑及SHA256在results.json，研究腳本不下載或修改來源。

```bash
export PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
python3 -u scratch/au_distance_par_20261015.py \
 --inputs /Users/imac/.codex/visualizations/2026/10/15/01a13d68-afa0-77b3-a25d-8a74906a0796/AU-neutral-speed-research/results.inputs.json \
 --events /Users/imac/.codex/visualizations/2026/10/15/01a13d68-afa0-77b3-a25d-8a74906a0796/AU-fulltime-implementation/seed-events.json \
 --forms /Users/imac/.codex/visualizations/2026/10/15/01a13d68-afa0-77b3-a25d-8a74906a0796/AU-fulltime-implementation/form-blocks.json \
 --out /private/tmp/au-distance-par-results.json
python3 -m unittest discover -s scratch -p 'test_au_speed_stage2.py' -v
```

候選模型未通過發布證據；只保存研究分支，不merge／release／部署。現役引擎、
trial門檻、dashboard、generated model docs及golden/data-contract基準均未改。

驗證：`./檢查.sh --quick`及完整`./檢查.sh`均通過；10個針對性測試通過，
涵蓋全中性／零overlay、來源與日期、同日拒絕、manifest變更、baseline漂移、
result/SP不入分及精確distance鍵；204場重播max差0，舊假設preview被CLI拒絕且沒有輸出。
HKJC原有data-contract stale-baseline警告保留，未在本研究改其基準。
