# EXP-20260928-05 — HKJC 未跑泥地馬：海外賽績與血統 fallback

- **日期**：2026-09-28
- **平台**：HKJC
- **狀態**：**DATA REPAIR KEEP / MODEL UNRESOLVABLE・SHADOW ONLY**
- **假設**：未有香港 AWT 歷史時，官方 PDF 內賽前可得嘅海外 Dirt／Synthetic／
  Polytrack／Tapeta 實績，比固定中性 60 更有用；若仍無實績，嚴格 PIT 同父系 AWT
  子嗣表現可以作低信心 evidence。
- **搜索過嘅舊記錄**：2026-08-21 audit 記錄一般 sire signal leave-one-out 洩漏、
  PIT 全負；今輪不重試一般 sire ranking，只測新資料源「AWT surface-specific、嚴格
  date < target、只在本駒無 local/foreign AWT 時」並預設 shadow-only。
- **Harness**：`docs/experiments/patches/hkjc_awt_transfer_audit.py`

## 已獨立證明嘅資料 bug

現有 `parse_pdf_overseas_races()` 由 PDF 第一次見到烙號開始讀，通常撞中香港本地
往績頁；所以普通香港賽績被標 `Is_PDF_Overseas=True`，真正 Overseas Form 嘅
`Racecourse`／`Going`／Dirt／Synthetic 全部掉失。呢個係 parser correctness bug，
不依賴績效結果亦應修。

## 固定 evidence hierarchy

1. 香港同表面、相近路程 ±200m PIT performance；
2. 若香港 AWT effective_n=0：同馬海外 Dirt／Synthetic／Polytrack／Tapeta；
3. 若兩者都無：同父系其他馬匹嚴格 PIT 香港 AWT，至少報 coverage，使用 12 個中性
   pseudo-runs 強收縮；
4. 全部無資料：中性 60，唔靠主觀血統印象加分。

所有個體實績轉 field-size-normalized finish percentile，365 日半衰。海外最長回看
1095 日；結果日期必須早過 target。Sire 名係靜態 metadata，但子嗣結果只可用 target
之前；target horse 自身排除，防 double count。

## 判決

- 先報 parser 修正前後 true-overseas coverage、foreign surface coverage、pedigree coverage。
- AWT archive 少於 30 場時，任何 ranking 結果只可 `UNRESOLVABLE / SHADOW`，不可 promotion。
- foreign 實績、sire fallback 必須獨立 ablation；sire 一旦 PIT 方向非正即 REJECT。
- 呢輪只接 Facts→Logic evidence；未過 Stage-4 前不入 live 7D。

## 結果

### 資料修復

修正後 parser 只會由官方 PDF 明確 `Overseas Form／海外賽績` 段落開始，並保存
地區、馬場、方向、路程、地況、表面、名次／馬匹數、賽事類型、負磅、時間及距離。
烙號亦會正規化，例如 PDF `K0228` 可正確對應 racecard `K228`。另外修正一匹馬
未有香港往績時，formatter 會過早 return、連真正海外往績都唔輸出嘅錯誤。

Facts→Logic 而家保存：

- 所有馬匹嘅父系／母系 metadata（唔再只限初出馬）；
- 結構化真正海外逐仗資料；
- 香港同表面 PIT 表現；沙田 AWT 無本地樣本時嘅海外 Dirt／Synthetic fallback，
  但標明 `shadow_only`，未進入 7D 排名。

### Shadow audit

archive 只有 **11 場 AWT／135 runners**，低過預註冊 30 場門檻，所以總判決必須係
`UNRESOLVABLE_SHADOW`。資料覆蓋：

| Evidence | 覆蓋 |
|---|---:|
| 父系／母系 metadata | 100.00% |
| 香港 AWT 歷史 | 71.11% |
| 真正海外賽績（任何表面） | 34.81% |
| 海外 Dirt／Synthetic | 3.70% |
| 無本地 AWT、可用海外 fallback | **0.74%（1 匹）** |
| 父系 PIT AWT 子嗣 evidence | 65.19% |
| 只有父系可 fallback | 14.07% |

Pairwise AUC 只作方向診斷：香港同表面 `0.5853`（692 pairs／11 場）；海外 AWT
`0.1818`（只有 44 pairs／3 場）；父系 AWT `0.5037`（接近隨機）；hierarchy
`0.5819`，反而略低過只用香港同表面。海外同父系證據都不足以進排名，尤其父系唔會
因為「聽落適合泥地」就主觀加分。

結論：**場地性能資料鏈已補好，但 ranking formula 暫時不改**。新馬／未跑香港泥地馬
會有客觀外地 Dirt／Synthetic evidence 可供分析與日後累積；無直接賽績時保留血統
metadata，同父系實績只做強收縮 shadow，等 AWT archive ≥30 場再按同一預註冊規則重測。

## Reproduction

```bash
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 \
  docs/experiments/patches/hkjc_awt_transfer_audit.py \
  --dataset /tmp/hkjc_ranking_dataset_20260928_v2.csv \
  --output /tmp/hkjc_awt_transfer_audit_20260928.json
```
