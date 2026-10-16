# 高消耗但仍跑好：扣分豁免測試

baseline `3083316d55fd35d798772514248ae2723e6b469b`；325場／33個賽日，2026-04-19 至 2026-10-07。
同 session capture 的 HKJC production code 與目前完全相同，A/A 全部 raw ability 及排名一致；沒有重複抽取、改寫 archive 或開 forward。

## 測咗乜

只改沙田普通馬近三段往績：日期必須早於今場、有 XW≥3 明確外疊、標籤為高／極高消耗，才按下列條件將該段 52／46 還原 60。沒有額外 bonus。
A：仍勝出；B：仍勝出，或第二／第三且輸距≤3。贏馬 margin 是勝出距離，完全不當作輸距。分數仍按原有最近三段可用值平均。
C：用戶追加要求，沙田普通馬 T 一律60，連低消耗加分亦取消；不重分配內權。追加發生於A/B初步結果後、檢視C績效前，詳見PROTOCOL追加段。三arm重新做Holm。
沙田 R=0.55D+0.25F+0.20T，外權0.2737；SIP及場內限幅照原路跑。HV普通馬V3本來就不使用T，沒有硬加新分。

## 配對結果

| 方案 | 觸發匹次 | 往績引用 | Gold場數差 | Good場數差 | 完整排名改變場數 | v3統計篩查 |
|---|---:|---:|---:|---:|---:|---|
| 外疊仍勝出 | 103 | 109 | +0 | +0 | 13 | REJECT / ranking_evidence_too_weak |
| 外疊仍勝出／前三且輸≤3馬位 | 310 | 364 | +0 | +3 | 34 | REJECT / holm_not_supported |
| 沙田消耗分一律60 | 1853 | 不適用 | +4 | -2 | 129 | REJECT / primary_regression |

基準 Gold 44/325、Good 81/325。Gold＝實際前三全在模型頭四；Good＝模型首兩選都上名。

## 信賴區間及幅度

| 方案／指標 | 差（pp） | 95%賽日配對CI（pp） | Holm p |
|---|---:|---:|---:|
| 外疊仍勝出／gold | +0.000 | [+0.000, +0.000] | 1.0000 |
| 外疊仍勝出／good_positional | +0.000 | [+0.000, +0.000] | 1.0000 |
| 外疊仍勝出／前三且輸≤3馬位／gold | +0.000 | [+0.000, +0.000] | 1.0000 |
| 外疊仍勝出／前三且輸≤3馬位／good_positional | +0.923 | [+0.000, +2.090] | 1.0000 |
| 沙田消耗分一律60／gold | +1.231 | [+0.000, +2.744] | 1.0000 |
| 沙田消耗分一律60／good_positional | -0.615 | [-1.524, +0.000] | 1.0000 |

## 點解唔可以直接話「取消扣分更合理，所以應該上線」

- 現有近績維度已計名次及輸距；要量額外排名貢獻，不能只看外疊仍勝出馬本身上名率。
- 這次只取消消耗扣分；幅度會被20%內權、27.37%外權、最近三仗平均及場內cap進一步縮細。觸發不等於有排名變化。
- 既有SIP亦有raw總分門檻，細幅T變化可能觸發／取消原有bonus；報告最大raw差包括這個下游效果，沒有額外改SIP。
- 沒有用 ML 重fit：兩條固定規則已直接測到提議，沒有理由為小改動追加調權重搜索。
- 部件預算及各 ranking metric CI 半寬見 results.json。功效不足只代表判唔清細效益，不會被包裝成改善或改閾值再試。

## 資料與驗證

- 9 項 parser／日期安全檢查；24 組 direct production raw ability／完整排名完全一致。
- 當場賽果、SP不進候選條件；SP只在分層評估使用。缺資料一律不猜。
- 歷史文字窗口的確切賽前可用時間尚未全面認證：leakage仍為FLAG。嚴格日期不是完整PASS，不能據此直接promote。
- 缺場地的舊場次保持baseline；venue、field四桶、SP五桶、初出馬場次及going（未知照列）的primary CI見 results.json。
- 2000次bootstrap按賽日、seed7、六個時間塊；三候選×六metrics Holm。v3原始RANKING_WIN仍須經Holm，表內採家族修正後判斷。2026-10-11起forward未開。
- Production code、權重、golden、data-contract baseline沒有改動。

## 結論

- 外疊仍勝出：REJECT / ranking_evidence_too_weak（原始v3：REJECT／ranking_evidence_too_weak）。最大raw能力變化 0.4400；頭兩選成員變動0場，頭四選成員變動1場。
- 外疊仍勝出／前三且輸≤3馬位：REJECT / holm_not_supported（原始v3：RANKING_WIN／primary_neutral_ranking_supported_gain）。最大raw能力變化 0.6662；頭兩選成員變動3場，頭四選成員變動5場。
- 沙田消耗分一律60：REJECT / primary_regression（原始v3：REJECT／primary_regression）。最大raw能力變化 1.7600；頭兩選成員變動15場，頭四選成員變動22場。
不因邏輯直覺更改現役模型；本次只保存研究方法與證據。

## 重跑

```bash
export PYTHONDONTWRITEBYTECODE=1
# 如需重新產生同一界線的baseline/evidence（已有同session快照可省）
python3 docs/audits/hkjc-trip-forgiveness-20261016/capture.py /private/tmp/hkjc-draw-20261016-evidence.jsonl /private/tmp/hkjc-draw-20261016-baseline.jsonl
python3 docs/audits/hkjc-trip-forgiveness-20261016/study.py
python3 docs/audits/hkjc-trip-forgiveness-20261016/validate.py
python3 docs/audits/hkjc-trip-forgiveness-20261016/report.py
```
baseline/evidence的路徑與SHA256見results.json。原始dump留在/private/tmp；canonical keys保存在本目錄。capture.py配合hkjc_eval_harness，保持截至2026-10-10的界線；重跑前應將現有snapshot另存，避免覆蓋已量過baseline。
