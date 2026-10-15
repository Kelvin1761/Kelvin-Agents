# EXP-20261016-11 預先登記：pg33_N6 forward shadow

> 凍結之前寫。凍結檔（`EXP-20261016-11-forward/freeze.json`）同評估結果檔一經寫入就唔准改。

- **日期**：2026-10-16；**平台**：AU
- **候選**：pg33_N6（EXP-20261016-10）：近績質素分每場 = (z名次 + G) / 2，
  G = z獎金（該場名次喺前三分一，p = (名次−1)/(出賽數−1) ≤ 1/3），否則 min(0, z獎金)。
  即係高班加分只俾跑得入前列嘅往績；低班照扣。其餘（最近 6 場、權重、最少 2 場、場內 z、fallback）同 eq2_N6 一樣。
- **baseline**：已上線 eq2_N6（`c242b6c1`）。
- **點解要 forward**：EXP-10 係同一個 41 日窗嘅第三個 family（EXP-06／09／10），結果只算研究證據。
- **用戶指示**：2026-10-16「將 pg33_N6 加入 forward shadow，同 S2 一樣凍結、新賽日、評一次」。

## 凍結

| 項 | 值 |
|---|---|
| forward 窗 | 2026-10-17 起 |
| 評估時機 | 有快照兼有賽果嘅賽日 ≥ **41**，之後**一次** |
| A0 | 現行引擎（eq2_N6 近績質素分）+ live `MATRIX_WEIGHTS` |
| A1 | 同一份重播，只將 `form_quality_score` 換做 pg33 leaf，**同一套** live 權重（冇 refit） |
| code | 引擎目錄全部 `.py` + 5 個工具檔逐個 sha256 寫入凍結檔；評估時任何一個唔夾就拒絕 |

點解冇 refit arm：pg33 只係改一個 leaf 嘅內部寫法，同一個係數；EXP-10 嘅 §8 refit arm 已經喺研究窗跑過。
forward 嘅問題係「同一套權重下，換咗 leaf 有冇更好」。

## 輸入：只用賽前不可改快照

- 同 EXP-20261016-03：`pick_snapshot` 嘅 `pre_cutoff`（悉尼 11:00 前最後一個），簽名同逐檔 sha256 要夾，唔夾就跳過並記數。
- **重播要喺以場次命名嘅目錄做**：引擎由 Facts 檔 parent 目錄名攞賽日（`engine_core.refresh_form_quality`）。
  快照目錄名（`20261014T004339…`）冇日期 → 賽日變空 → 全部往績被篩走 → 近績質素分**全部靜靜跌落 fallback**
  （10-14 五個場次實測：原地重播 0 匹有值，抄去 `<場次名>/` 之後 310/376，同 live 資料夾一樣）。
  所以工具將已驗證嘅快照抄去臨時 `<場次名>/` 先評分。
- pg33 用引擎自己嘅 `form_quality_runs`（同 eq2 一樣嘅往績揀選），場內 z 用全場報名馬（同 `_build_field_summary`）。

### 重播核對（`replay-check --date 2026-10-14`，窗外，唔計指標）

- 用 G = z獎金（即 eq2）重算 leaf，同引擎 `form_quality_score` 逐匹最大差 1e-6（288 匹）。
- `exact_score` 重算 ability 同引擎差 0。
- pg33 ability 同 EXP-10 研究 replica 喺 base 一致嘅 247 匹逐匹差 **0**；
  其餘 41 匹 base 唔同係因為研究 dump 用之後嘅 live 資料夾、呢度用賽前快照。

## 判決（預先登記，唯一一次）

1. A1 vs A0，`evaluate_full_record(mode="fixed_rule")`，primary Gold／Good，ranking `top3_capture_at5`、
   `ndcg_at5`、`top5_pairwise_auc`，`leakage_audit_passed=True`（輸入係快照證實嘅賽前資料）。
2. 跑包尾（只作評估，SP 唔入特徵）：頭兩名 SP $15+ 而跑尾三分一嘅場數，A1 − A0，按賽日 bootstrap 2000、seed 7。
3. `ship_eligible` = v3 `PRIMARY_WIN`／`RANKING_WIN`，**或** Gold、Good 點估計都 ≥ 0 **而且** 跑包尾差 95% CI 上界 < 0
   （同 EXP-09／10 嘅上線規則 B 一樣，但係喺未睇過嘅新賽日）。
4. 合資格 → 準備上線改動（照 `./保存.sh` 流程）；唔合資格 → pg33 結案，**唔准**開第二個 forward family 救佢。

## 唔准做

- 中途睇指標：`status` 只數賽日，`evaluate --dry-run-counts` 只數可重播場次。
- 改 code、門檻（1/3）、評估時機或者指標。
- 因為 forward 結果再調然後重開。

## 指令

```bash
python3 scratch/au_pg33_forward_shadow_20261016.py replay-check --date 2026-10-14
python3 scratch/au_pg33_forward_shadow_20261016.py freeze
python3 scratch/au_pg33_forward_shadow_20261016.py status
python3 scratch/au_pg33_forward_shadow_20261016.py evaluate      # 夠 41 日先跑，一次
```

## 附帶發現（未修）

`engine_core` 有四處由 `facts_path.parent.name` 攞賽日或場地（約 L1842、L5591、L6841、L7135；L7686 攞場地）。
live 同 dump 都喺場次資料夾行所以冇事；`au_window_review` 只讀快照入面記低嘅預測，冇重新評分，亦冇事。
受影響嘅只有「原地重播快照」嘅工具。S2 嗰個（EXP-03）凍結喺近績質素分之前，而且重播核對同 dump 差 0。
