# EXP-20260910-02 HKJC 多仗能力＋異常仗可靠度

- 日期：2026-09-10；平台：HKJC。
- Baseline：現行主線加 EXP-20260910-01 的零出賽正確性修正。
- 假設：最近一仗有明確醫療事故時，一次異常表現不應同時被當成 L400 絕對值、
  L400 趨勢、能量趨勢及完成時間趨勢四份獨立能力下滑證據。
- 固定消融：M＝最近 L400 改用之前各仗中位數；R＝只中性化相關負面趨勢；
  M+R＝兩者合併。三組在量結果前固定，沒有搜索門檻或逐馬特例。

## 結果

歷史 PIT 回放 193 場／19 日。只有 4 匹／4 場真正觸發評分改動，而且全部在
2026-07-12（另有 1 匹醫療事件但沒有足夠相關訊號）。固定 terminal 是最後三日；
因此 development 162 場的有效觸發數是 0，terminal 31 場只有 4。
按可改變場次計的 80% power 保守二元 MDE 是 140pp，屬不可能效應量。

| arm | Gold | Good位 | 首選勝出 | capture@5 | 前三平均模型名次 | NDCG@5 |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 14.51% | 26.42% | 26.42% | 64.08% | 4.842 | 0.5405 |
| M | 14.51% | 26.42% | 26.42% | 64.08% | 4.842 | 0.5405 |
| R | 14.51% | 26.42% | 26.42% | 64.08% | 4.842 | 0.5405 |
| M+R | 14.51% | 26.42% | 26.42% | 64.08% | 4.842 | 0.5405 |

五個 chronological development folds 全部零改變。Stage 4 機械判決是
`REJECT / leakage_audit_failed`：歷史 Logic 雖只使用目標賽前的往績欄，卻沒有
immutable prediction snapshot 證明每份衍生欄位的原始時點。即使忽略 provenance，
零 development coverage 亦不能提供 promotion 證據。

09-06／09-09 共 18 場有 immutable 賽前 snapshot，但賽果已在提出本假設前看過，
只作已知個案診斷。M+R 的 Gold、Good、首選勝出全部不變；capture@5
46.30%→48.15%，前三平均模型名次 6.000→5.889，NDCG@5 0.3697→0.3843。
方向正面但只有 7 場可受影響，80% power MDE 106pp，不能稱為表現改善。

## 財將與消融判讀

財將的 immutable 原排名第12；M→第9、R→第9、M+R→第8，顯示一次心律異常大敗
確實被多個相依段速欄重複表達。不過修正後仍未進頭四，說明問題不只在段速可靠度；
班次、長期近績、騎練及其他能力證據仍需獨立研究。

M 並非一律有利：若醫療事故仗的 L400 反而較好，強制換成歷史中位數會降分。
因此本輪不將 M、R 或 M+R 改入主線。M+R 只以 `incident_reliability` shadow 保存，
讓往後每個賽日累積真正未見賽果的 prospective 樣本；主線分數、排名、選馬及部署
閘門完全沿用原值。

## 實作保護

- 只在 `medical_flags` 明確有 `第1仗: ⚠️` 時觸發。
- 新舊資料的 L400 次序相反；以 `raw_l400` 對序列端點核對，不能確定就不改。
- M 至少要有兩個事故前 L400 值；R 只移除負面趨勢，不刪正面或穩定訊號。
- Shadow 只重算 `sectional`，其餘六個矩陣維度逐值沿用主線。
- 保存 `adjustments`、原值、新值、序列方向、能力差及 shadow rank，方便賽後審計。

## 重現

```bash
PYTHONDONTWRITEBYTECODE=1 python3 docs/audits/hkjc-season-opening-20260910/incident_reliability_ab.py --out /tmp/hkjc_incident_reliability_ab.json
python3 -m unittest discover -s .agents/skills/hkjc_racing/hkjc_wong_choi_auto/tests -p 'test_zero_start_season.py' -v
./檢查.sh --quick
./檢查.sh
```

研究決定：**NEEDS MORE TESTING／SHADOW ONLY**。未證實分析命中率改善，不准升主線。
