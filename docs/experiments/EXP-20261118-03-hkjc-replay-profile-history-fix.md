# EXP-20261118-03 — 轉場組件 live 對唔返測試：回放冇往績（已修）＋ live 馬匹頁只得近季（已修）

- 日期：2026-11-18｜類別：**回放 harness 正確性修正 ＋ live 數據正確性修正**（令 live = K2／D1 測試時嘅定義）
- 起因：EXP-20261118-02 發現現行 main 嘅回放對唔返 K2 測試 dump，仲差過 D1。

## 原因 1（主因）：回放入面 D1、K2 兩個組件完全冇郁
- live 嘅 `_enrich_profile_history` 用排位表 trackwork 嘅 horseid 抓 HKJC 馬匹頁，砌 `_data.hk_history`（轉場 K2）同
  `_data.prev_distance`（大幅增程 D1）。回放語料 Logic 冇 horseid，harness 又設咗 `WC_DISABLE_HKJC_PROFILE_ENRICH=1`。
- 實測（2023-01-01–02-15，1,676 匹）：**有往績 0／1,676**，轉場旗 0，prev_distance 0。
- 即係 2026-11-17 起任何「經引擎重跑」嘅回放（`hkjc_history_replay_prun.py`）都等於冇 D1／K2。
  受影響：今日 EXP-20261118-02 嘅 `base_main`／M1（已用修正版重做）。J1／J2、R1、K5 係由 dist_D1／k7_K2 離線砌，**唔受影響**。
- 修正：`hkjc_reflector/scripts/hkjc_history_replay_profile.py`（`hkjc_history_replay_eval.py` 自動 install）——
  用同日同馬名喺賽果搵馬匹編號，暫時塞入 horseid，行**原版** enrich（as-of、新→舊、40 場上限全部一樣），
  抓頁換成讀存檔 `parsed/horses.jsonl.gz`（同一個 HKJC 馬匹頁來源），永遠唔上網；事後還原 trackwork。
  測試：`hkjc_reflector/tests/test_history_replay_profile.py`。
- 驗證：同一段 1,676 匹 → 有往績 1,608（其餘係初出）；轉場旗同 K2 測試特徵逐匹對：6,700 個旗得 2 個唔同。
  全 6,047 場重跑（`v4/cons/base_fixed.jsonl`）：

| 比較 | dev Δlog-loss | holdout Δlog-loss |
|---|---|---|
| 修正後 live 對 K2 測試 dump | +0.00013 [−0.00008,+0.00034]（打和） | −0.00007 [−0.00015,−0.00000] |
| 修正後 live 對 D1 | −0.00059 [−0.00111,+0.00001] | **−0.00103 [−0.00157,−0.00046]**（PASS） |
| （修正前 live 對 D1） | +0.00030（差） | +0.00013（差） |

→ **live 冇問題**，係回放壞咗。K2 dump 用逐季 walk-forward β、live 用 2026/27 β，所以 picks 唔會完全一樣（3,614／6,047 場一樣）。

## 原因 2（live 細 bug）：馬匹頁預設只顯示近幾季
- 11-18 跑馬地 100 匹有往績：98 匹同存檔一致；2 匹 live 往績被截（例如 HK_2022_H208：26 對 42 場），
  「見過邊啲場地」唔齊 → 長年資馬會被錯判「初次田草／初次泥地」（K2 測試用完整往績）。
- 修正：`scrape_hkjc_horse_profile.py` URL 加 `&Option=1`（全部往績；H208 實測 42 場齊），舊 cache 冇 `full_record` 就重抓一次。
- 影響：只會改 `first_st`／`first_awt` 旗（長年資馬），令 live 同已驗證嘅 K2 定義一致；其他用馬匹頁嘅顯示（班次表現、季初評分、換騎紀錄）
  本身已按季數／日期過濾，冇變或者更完整。

## 之後
- `v4/cons/base_fixed.jsonl` 係而家正確嘅「現行 live」回放 base；之後經引擎重跑嘅 arm 一律用修正版 harness。
