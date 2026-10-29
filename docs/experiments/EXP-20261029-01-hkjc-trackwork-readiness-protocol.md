# EXP-20261029-01 — HKJC 晨操讀法深度審查 + 重建候選（預先登記）

- **日期**：2026-10-29；平台：HKJC；baseline = main `dd824007`
- **Kelvin 要求**：晨操最初只係好基本嘅讀法，一直用到而家；審查同重建，睇吓有冇 hidden gems。
- **先讀過**：EXP-20261010-11（子訊號篩選、兩個 arm 全 REJECT）、EXP-20261018-11（§7 唔同路程唔比趨勢）、
  EXP-20261019-04（剷走晨操 leaf 零變化）、EXP-20261019-02（refit 想將晨操設 0）。
  外層權重同 leaf 已確認接近最優 → 呢次唔調權重，只問「有冇讀漏咗新資訊」同「有冇讀錯」。

## 語料

`hkjc_eval_harness.py run --dump-matrix`（真 production 計分路徑 + PIT priors，自動剔 speed_score 死日）。
晨操 JSON 只喺 2026-05-03 起有：36 個賽日、369 場（Forward tracker `trackwork_rescreen` 要 60 個賽日）。
**功效有限，預先承認**：EXP-20261010-11 用 30 個賽日冇一個子訊號過 CI。

## A. §7 正確性修正候選（`fixed_rule`）

審查時見到（數字見 results）：

1. **晨操表入面有「出賽」行**（`type_raw == 出賽`，連名次 `(5/12)`），抽取層冇剔走：
   - `race_jockey_involved`（「賽日騎師有參與操練」）會因為騎師喺**比賽**策騎過而觸發，唔係晨操；
   - `active_days` 將比賽日當操練日。
2. **賽後先抽嘅檔案包含今仗本身**（`date == racedate` 嘅出賽行同當朝踱步），即係回放同 live 睇到唔同嘢；
   今仗出賽行仲會令「賽日騎師有參與操練」100% 觸發 → 備戰分 +15、復刻分 +12。
   備戰分會經 `_prep_score` 入初出馬穩定性分。
3. **跑步機誤分類**：`type_raw == 馬匹跑步機` 但 details 有「快操／踱步」字眼嘅，被當咗快操／踱步。

修正規則（冇 fit）：晨操記錄只用 `date < 賽日` 而且唔係「出賽」行；`馬匹跑步機` 一律當 treadmill；
`hydrate_trackwork_jockey_involvement` 同樣唔睇出賽行。之後由清理咗嘅記錄重算 digest／summary／三行文字。

- Arm：`docs/experiments/patches/hkjc_arm_trackwork_pit_clean.py`
- 判決：Stage 4 v3 `fixed_rule`，全紀錄。§7：正確性修正唔要求改善，但 primary 點估計負就要報、唔可以講改善。

## B. 新訊號篩選（全部由清理後記錄計，point-in-time）

每個都只用賽日之前嘅晨操行。六個候選一個家族，**Holm 調整**：

| key | 定義 | 點解可能有料 |
|---|---|---|
| `trial_any` | 近 21 日有試閘 | EXP-11 最接近（+0.0035 [−0.0003, +0.0080]），重測 |
| `days_since_work` | 距最後一課快操／試閘日數（冇 = 22） | 「休息咗幾耐先出」= 最後衝刺時間 |
| `post_race_load` | 上仗之後（窗口內冇上仗就成個窗口）快操 + 2×試閘，按日數正規化到每 7 日 | 舊計數將上仗之前嘅備戰都計埋 |
| `work_speed_z` | 最近一課快操嘅最後一段（20–30 秒），同日同場地（地點字串）所有快操入面嘅 z 分，負號（快 = 正） | 舊「最快末段」冇按場地／日子調；從化、全天候、草地快慢差好遠 |
| `habit_dev` | 今窗快操 + 試閘課數 − 呢匹馬之前所有晨操窗口嘅平均（只用今日之前嘅賽日檔），冇前窗 = 0 | Kelvin 提嘅「同平時習慣比」 |
| `jockey_work` | 今仗騎師喺晨操／試閘真係策騎過（剔走出賽行） | 舊旗標有一部分係假嘅 |

方法同 EXP-20261010-11：baseline 綜合分（`raw`/τ=3）做 offset 嘅 conditional logit，前 60% 日期 fit、後 40% 測，
OOS ΔLL 用場次 bootstrap 95% CI；另報 cohort 超額同場內 AUC。剔初出馬（佢哋冇綜合分可比）。

**晉級規則（預先定）**：只有 Holm 調整後仍然顯著（OOS ΔLL CI 下界 > 0）嘅訊號先寫 arm 入 harness 跑 Stage 4 v3。
冇一個過 → 判 `UNRESOLVABLE（功效不足）`，唔寫 arm，唔改模型；過唔到但點估計正嘅加入 `FORWARD_TESTS`。
唔會因為結果再加特徵、換窗口或者換門檻。

## Leakage

所有 B 特徵只用 `date < 賽日` 嘅行、剔出賽行；`habit_dev` 只讀日期早過今日嘅賽日檔；`work_speed_z` 嘅
參照群體係同一日同一場地嘅操練（全部喺賽前發生）。冇用賠率、冇用賽果。
