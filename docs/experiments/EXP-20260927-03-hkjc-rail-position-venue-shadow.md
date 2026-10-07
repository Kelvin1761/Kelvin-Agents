# EXP-20260927-03 HKJC rail／走位／場地公式 shadow audit

- **日期**：2026-09-27
- **平台**：HKJC
- **模式**：資料正確性修復＋shadow-only 診斷；production 7D 分數／排名零改動
- **問題**：跑馬地 A／B／C／C+3 是否需要 rail-aware 走位模型？沙田與跑馬地是否應拆成兩套完整公式？

## 實作前發現

1. `rail` 已由 Racecard 注入 `race_analysis`，但 `_rail_label()` 明文只供顯示，唔入分。
2. 普通轉彎賽用同一檔位先驗：1–4檔 75、5–8檔 65、9+檔約50。
3. 現行 race-shape **已經按場地分兩種內部組合**：沙田係檔位55%＋走位匹配25%＋近仗消耗20%；跑馬地係檔位分＋有上限情境 delta。外層 7D 權重共用。
4. 舊 `rail_draw_results.csv` 建構器冇掃現役 `HK_RACING/YYYY-MM-DD_*` meeting folder；舊結果缺 metadata 時亦冇用 Logic／Racecard 補回，令 rail dataset 大量空欄。

## 今次修正

- `build_rail_draw_dataset.py`
  - 掃季度 results DB、現役 meeting folder、legacy archive；
  - 結果 header 缺資料時，以同場 pre-race Logic，再以 Racecard 補 Date／Venue／Track／Going／Distance／Rail；
  - 加 HorseNo、FieldSize、FirstCall、EarlyGroup；
  - 寫檔前預設要求 metadata coverage ≥95%，避免低質 dataset 覆蓋已知版本。
- `hkjc_rail_position_shadow.py`
  - 只輸出研究統計，明文 `live_score_changed=false`；
  - 分 venue／rail／distance／draw／going／field-size；
  - actual first-call 只可作 post-race diagnostic target，唔可當賽前特徵；
  - cell 用場內 `3 / field_size` 作 expected place rate，並以60匹 runner 收縮 excess。

## 語料

- 本機結果：**21,760 runners**（日期正規化後合併101條 slash-date 重複行）
- 完整 metadata：**21,621（99.4%）**
- **1,755 races／181 meetings**
- 缺失：139 runners；全部保留作 coverage 報告，但不進完整 cohort
- Odds／市場資料：**冇使用**

## 結果

### 場地總體檔位

| Venue | Draw | Place | Expected | Shrunk excess |
|---|---|---:|---:|---:|
| 沙田 | 1–4 | 27.9% | 24.1% | +3.8pp |
| 沙田 | 5–8 | 24.4% | 24.0% | +0.5pp |
| 沙田 | 9+ | 19.2% | 22.7% | −3.5pp |
| 跑馬地 | 1–4 | 31.5% | 26.0% | +5.4pp |
| 跑馬地 | 5–8 | 26.2% | 26.0% | +0.2pp |
| 跑馬地 | 9+ | 19.5% | 25.4% | −5.8pp |

跑馬地整體唔支持「外檔一般有利」；但 rail × distance 顯示現行單一外檔 penalty 太粗。

### 跑馬地 1400–1650m：外檔 9+

| Rail | Runners / races | Place | Expected | Shrunk excess |
|---|---:|---:|---:|---:|
| A | 251 / 67 | 16.3% | 25.5% | −7.4pp |
| B | 190 / 51 | 18.4% | 25.6% | −5.4pp |
| C | 167 / 44 | 24.6% | 25.2% | **−0.5pp** |
| C+3 | 147 / 40 | 21.8% | 25.6% | −2.7pp |

用 actual first-call 做診斷亦係同方向：C欄1400–1650m後置9+只係 −0.9pp；A −7.3pp、B −5.8pp、C+3 −7.2pp。呢個支持用戶觀察嘅核心：**C欄中距離外檔／後置劣勢明顯較細**。但 C欄1000–1200m外檔仍 −6.4pp、後置 −11.8pp，所以絕對唔可以寫成「C欄一律利外檔後追」。

Going 再拆後，C欄中距離單格未同時達到100 runners／20 races stability gate；暫時只保存 shadow，不作規則。

## 沙田與跑馬地要唔要兩套完整公式？

**決定：暫時唔拆外層 7D；保留共用 7D＋場地專屬 component。**

原因：

1. 現行 race-shape 內部本身已分沙田／跑馬地，真正缺口係跑馬地內再分 rail × distance，而唔係整套模型完全冇場地概念。
2. [`EXP-20260905-03`](EXP-20260905-03-hkjc-trainer-signal-venue-split.md) 已做真引擎 PIT A/B：12個場地排名 arm 全部不過閘；部分 venue signal 準但幅度只佔場內分數 SD 約1%，放大後反而顯著傷害 Gold。
3. outcome-only rail dataset 可以量 position component，唔足以判定 sectional／class／health／form-line 等其餘六維都需要獨立權重。
4. 拆兩套完整公式會令每邊有效回放樣本再減半；目前正式引擎 PIT 語料本身只有約193場，功效不足。

下一個可證伪候選只應係 **HV rail × distance position-conversion overlay**，並保持 shadow；不得把沙田／跑馬地兩套7D權重一次過重 fit。

## Reflector／資料正確性同步修正

- incident excerpt 改為逐馬 `placing + horse_no` 分段；找不到自己段落回空字串，唔再借第一匹馬事故。
- improvement theme 改為按最低分 leaf，而唔係最高分 leaf。
- Logic 馬名帶「(退出)」會報 `WITHDRAWN_RUNNER_PRESENT`，要求套用退出名單後重新排名；唔再用含糊 name mismatch 表達。
- 中文「第三班／第四班…」會正規化至 C3／C4 再查標準時間，避免靜靜跌落 C4 fallback。呢項係語義正確性修正，未聲稱命中率改善。

## 驗證

- 新增／相關 targeted tests：**39 passed**
- 2026-09-16、2026-09-23 跑馬地 reflector meeting replay：成功
- 2026-09-23 full archive candidate review：成功
- Rail dataset rebuild：成功，metadata coverage 99.4%；日期全部正規化為 `YYYY-MM-DD`

## 重現

```bash
export PYTHONDONTWRITEBYTECODE=1
python3 .agents/scripts/build_rail_draw_dataset.py
python3 .agents/scripts/hkjc_rail_position_shadow.py
python3 -m pytest -q \
  .agents/scripts/tests/test_build_rail_draw_dataset.py \
  .agents/scripts/tests/test_hkjc_rail_position_shadow.py \
  .agents/scripts/tests/test_hkjc_standard_time_class_normalization.py \
  .agents/skills/shared_racing/tests/test_reflector_incident_attribution.py
```
