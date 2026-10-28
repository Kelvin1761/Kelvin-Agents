# EXP-20261029-02：Tennis kernel數學核對及win-a-set API修正

- 日期／平台：2026-10-29 Sydney，Tennis F02工程正確性。
- 假設：相同固定假設下，獨立DP應與現有MC一致；逐分1-2-2及7/10分TB應符合規則及對稱性。
- 搜尋：EXP-20261026-05跨盤首發已修；現有match_simulator、set_distribution、P02/P04/P07已知限制。沒有重跑舊weight／dispersion候選。
- Baseline：`1f46514bf9f7ab3386e9054363da93baf9ad3d83`；production參數及dispersion預設不變。
- 方法：`research/tennis_unified/protocol_f02.json`在MC之前lock，case list不按結果改動；原結果及API修正後結果分開保存。

## 結果

22 cases × 100,000 simulations，seed20260826，family-wise α=.01、exact Clopper–Pearson＋Bonferroni simultaneous intervals，**22/22通過**。

10個game-level BO3/BO5 cases用**同一個既有hold-ratio TB近似**作MC/DP比較。12個逐分TB cases另外驗7/10分、兩個先發方向及三組point probabilities。Deuce closed-form、1-2-2、A/B互換、比分terminal及mass conservation有獨立單元測試。唔將兩種假設混為真實賽果準確度。

額外發現API bug：`player_wins_a_set('b')`原用`sets_a<=1`，A贏2-1時回0，但B已贏一盤應回1。修正按`sets_b>=1`；A方同樣按自己贏盤數，新增9個BO3/BO5確定比分測試。

修正前／後相同22個case，DP、MC概率、interval及pass值**逐個完全相同**；只係判斷API修正，沒有改模擬比分／seed／分佈／權重。現役daily win-a-set用`set_joint`而無此helper靜態caller，不聲稱呢個修正已提升live card準確度。

## 限制及判決

**工程correctness通過；不作model promotion。** Helper修正在研究分支保存，未部署。歷史tournament/year TB mapping、iid假設是否適合真實球員、real-data配對Brier/LL、props market/settlement完整資格仍未完成。

18個基礎研究測試（後連book inventory共20個）、147個相關Tennis／研究測試、完整16組repo gate通過（Tennis875）。沒有新model fit、下注、收益或ruler更改。Leakage：synthetic規則測試不讀歷史outcome，不構成PIT證據。

規則：[ITF 2026，5(b)/6/7/14](https://www.itftennis.com/media/7221/2026-rules-of-tennis-english.pdf)、[AO官方說明](https://ausopen.com/articles/news/guide-scoring-tennis)。

## 重現及保存

```bash
P=/Users/imac/Antigravity-repo/tennis-wong-choi/.venv/bin/python
R='/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028'
PYTHONDONTWRITEBYTECODE=1 "$P" -m research.tennis_unified.kernel_audit --protocol research/tennis_unified/protocol_f02.json --output "$R/kernel-new-replay"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tennis-wong-choi/src "$P" -m pytest tennis-wong-choi/tests/test_simulator_service_order.py research/tennis_unified -q
```

原始：`$R/kernel-f02/`；修正後：`$R/kernel-f02-correctness-v2/`，含protocol/source hashes及全部case。原runtime源碼在`$R/runtime/source/`，新source在研究分支；不覆寫舊結果。
