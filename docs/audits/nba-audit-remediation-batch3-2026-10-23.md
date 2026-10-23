# NBA 全面修正第三批：資料／模型方法／接線／報告

起點：`1fa3e4fa8afefd4dee6e9e6ff6784144d602962b`。原始審核 F01–F03 已發佈 `2a6695e9`；F04／F10／F12 已發佈 `0bffbeb6`；F05 已發佈 `1fa3e4fa`，完整 gate 736 秒通過、NBA scheduler 對齊、dashboard 部署成功。呢份係後續修正證據，唔改原始審核紀錄。

## 完整範圍對照

| Finding | 最終行為／驗證 | 第三批狀態 |
|---|---|---|
| F01 cache 身份 | runtime flags／模型／renderer／輸入 hash 綁定，唔重用另一模式舊報告 | 前批已部署；回歸照跑 |
| F02 unresolved ledger | 未定賽果唔佔 immutable settlement key | 前批已部署；回歸照跑 |
| F03 Final | 空白／Not Final／pending 狀態唔結算 | 前批已部署；回歸照跑 |
| F04 傷停／roster | 30 分鐘獨立刷新，換 roster 重抽，失敗停，復出重算 usage；未在已驗證 roster 球員禁止入組合，亦唔當傷兵提供 usage 紅利；FW-14 令其他 domain 重建 dashboard 亦唔繞過來源時效／statistics contract | 新增跨入口 regression 通過 |
| F05 真實 SGM 價 | 同 event／腿／quote hash，5 分鐘有效；真價 EV／Kelly／回報／匯出／凍結 ROI | 前批已部署；FW-13 照驗 |
| F06 資料／訓練 | v2 共用真對手特徵，PIT／source hash／Final／US 日／DNP，整日五折時間切分、train-only imputer Pipeline、嚴格 post-training backtest | CLI／真實資料實測及合成防洩漏 tests 通過 |
| F07 大勝風險 | 原本 minutes_floor 已傳到候選，原有 5% correlation 修正可生效 | source→candidate→EV integration＋固定重播通過 |
| F08 Usage／pace | confirmed absence funding，刷新清舊紅利，full-name identity，己隊 PACE，第 10 因子及 MC PTS／3PM stat-unit 換算 | marginal／joint 真實呼叫 tests＋9-arm 消融完成 |
| F09 Defender | Totals 樣本、20 total attempts floor、GP／unit／league coverage，canonical team，cache contract 2 | 官方 API smoke＋cache migration tests 通過 |
| F10 model lineage | 最新實際快照先決定，再按 C 係數身份分組；舊／未知版本唔污染 current alert；MC 版本亦寫入 ledger | 前批已部署；回歸照跑 |
| F11 文案／數值 | frozen selector policy 與描述共用；真實 strict／fallback、腿數／CoV／目標，C 最終來源／10F 診斷分開；風險及 Kelly 用同一 adjusted joint、真實 quote | policy／quote／完整報告 tests 通過 |
| F12 壞設定 | 啟用 C 時 malformed／缺檔／非法係數 fail closed；explicit disabled 明示；explicit live ML 未具資格亦唔靜靜轉另一模型 | 前批及新增 CLI tests 通過 |

Central 規則要求 cache contract 常數、runtime／serving、backtest CLI 分開 release，按依賴次序接通。以上第三批 source 未以呢份文件聲稱已部署；最終 immutable gate／merge／activation 以本批 release manifest 為準。

## 評估結果與限制

- 228 份輸入／標籤 bytes／hash 核對；80 raw game JSON 中 55 個有獨立賽前來源時間證據。50 個有價 captures，**49 場**／24 US 日期（同場兩快照按最早合法來源去重）。
- 新 v2 dataset 8,468 列，8,286 有 Final label。966 個球員數字 ESPN／NBA 交叉一致；308 DNP 獨立處理。缺 label 唔當 miss，來源／features／labels 分開。
- RF 訓練 7,344 列／44 場；固定 terminal 942 列／5 場，Brier **0.182219**；現役 C 相同列 **0.171071**。RF − C = +0.011148，按日 CI [+0.001562,+0.019958]，候選不晉升。歷史窗曾被檢視，唔當新盲測；唔拿無效 v3 0.939 AUC 比成「進步」。
- 9 個 code-only context arm × 50 captures，450 次 real renderer 全部成功。全部 8,606 個 capture×leg **p_final 無變**、組合無變（原本全部 0）。8,286 個去重 labels 全部對返 source capture，無漏配。
- full MC ΔBrier **−0.000688**，CI [−0.002223,+0.000652]，跨零。只係資料／接線正確性及冇觀察到 C regression；唔聲稱命中或盈利改善，唔將 MC 或 RF 升為 final probability。
- 官方 defender 同截點 576 位：PerGame ≥20 = 0，Totals ≥20 = 523，壓制百分點完全一致；修來源單位而唔改 floor／權重。
- 新 model weights 只留外置 `model_v2_diagnostic*`，`deployment_eligible=false`；現役 v3 artifact 及 C 係數冇覆蓋。兩次固定訓練 tree arrays 及 imputer 完全一致；僅 2.22e-16 浮點加總次序差，4 位 serving 機率完全一致，非調參。最早市場時間按 UTC epoch 排序後重建 dataset，CSV SHA 完全一致。

詳細協議、人口分佈、逐項／移除項消融、來源 hash、限制及命令：

- `docs/experiments/EXP-20261023-06-nba-verified-temporal-ml-rebuild.md`
- `docs/experiments/EXP-20261023-07-nba-context-wiring-ablation.md`
- `docs/audits/nba-remediation-wave3-evidence-20261023.json`
- `.agents/scripts/nba_ml/README.md`

最後 NBA 專項 454 項、dashboard exporter 22 項，共 476 項通過；final quick／全量 gate 會對交付嘅 immutable SHA 再跑，唔將舊 log 當新 SHA 證據。
