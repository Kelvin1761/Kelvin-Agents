# EXP-20261016-30 結果：「人馬配搭分 ≥ 72 而 class_score < 58 → −3」

- **預先登記**：[protocol](EXP-20261016-30-au-fit-weak-class-minus3-protocol.md)（`8ac16e5d`，量度之前）。
- **語料**：`scratch/au_jt_audit_dump_20261016.py` 喺 `05dd1b20` 重跑，用 `k2` 特徵做 production baseline；
  乾淨窗 2,485 場／23,949 匹；配搭分重算同 ability 重算都同引擎一致（差 < 1e-3）。

## 結論：規則係死 code，依登記只報告、唔改

| 量 | 數 |
|---|---:|
| 配搭分（搬走試閘前）≥ 72 | **3** 匹（最高 72.45） |
| class_score < 58 | 2,688 匹 |
| 兩樣同時成立（觸發） | **0** 匹 |

觸發 0 < 登記門檻 200，DiD 同 ablation 冇得做（冇觸發馬，剷走同保留逐匹一樣）。

## 點解死咗

規則 2026-05-16（`f3ee8e9b`）加入時，人馬配搭分嘅加分項大得多（例如試閘 +4、現役騎師次數上限 6）。之後：
2026-07-11 ML 歸零／縮細多項（`FIT_MICRO_WEIGHTS`）、2026-09-01 剷走騎師連續性三項、EXP-20261016-12 剷走「沿用上仗騎師」。
而家所有加分項加埋最多約 74，要同時中晒先過 72，所以實際上冇馬到達門檻。

## 決定

- **唔改**（登記規則：觸發 < 200 → 只報告）。
- 呢條同 2026-07-11「有講冇分」死支一樣，係將來清理候選：剷走對乾淨窗逐匹零影響，但要另外以「清死 code」名義做，
  並用 golden／live dump 證明逐位元不變；唔可以喺呢個實驗入面順手剷。

## 重跑

```bash
export PYTHONDONTWRITEBYTECODE=1
python3 scratch/au_jt_audit_dump_20261016.py --variant f6a --out $S/jt.json
python3 scratch/au_fit_minus3_eval_20261016.py --dump $S/jt.json --outdir $S/arms   # 觸發 0 時 describe 會 KeyError（冇 weak|hi 格）
```
