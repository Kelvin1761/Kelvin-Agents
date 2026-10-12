# AU Wong Choi 全模型審計 —— 最終報告（2026-10-12）

- **base**：origin/main `1dc706a1`
- **worktree／branch**：`claude-au-trial-leak-20261012`（scratchpad `au-pc`）
- **組成**：Codex 審計未 commit 改動（EXP-20261011-01 → 20261012-30）+ Claude 第一輪修正（EXP-20261010-01）+ 今日修正（EXP-20261012-31／32）
- **判決尺**：Stage 4 v3（main `5ffdf9aa`）
- **前一份報告**：`AU_FULL_MODEL_AUDIT_2026-10.md`（第一輪，v2 判決）

## 一句總結

**排名嘅主幹冇問題，問題喺輸入。** 今日搵到嘅都係「數據入錯模型」，唔係權重錯：

- 2,188 場正式短途賽被當試閘。
- 14.3% 嘅 PF 往績行嚟自試閘（量過之後證實**係有用嘅**，唔改）。
- 單場第 10 被解成「1 場頭馬 ＋ 1 場第 10」。
- 往績行缺失嘅馬 form 被當中性。

修完 form 同 consistency 兩個 bug 之後，Platinum Card 由 64.85 跌到 62.2：首選 Halcyon Belle 退出之後，佢由「實際首選」變成排喺 Boa Vista（實際跑第 2）之後。pace_figure 用咗試閘數據原來有道理（見 §1）。

**馬齡 × 性別**喺診斷入面過到多重比較，但經正式 artifact 路徑之後判 REJECT：佢喺細場（4–8 匹）令 Gold 顯著跌。按馬匹數縮放嘅版本已登記做前瞻假設。

---

## 1. Tamworth R4 Platinum Card —— 根因同修正

| 項目 | 修正前 | 根因 | 修正後 |
|---|---:|---|---:|
| pace_figure | 84.1 | 唯一一場 PF 係 2025-11-04 **試閘** | 84.1（照留：試閘 PF 平均有預測力，F2 REJECT） |
| performance_quality | 69.8 | consistency 解 `10` 做 [1, 10] → 虛構頭馬 +7 | 61.9 |
| form | 60 | Sportsbet 往績頁冇嗰場正式賽 → 當冇證據 | 53.3（用官方 Last 10：第 10） |
| 綜合分／名次 | 64.85／第 2（Halcyon Belle 退出後＝**首選**） | | **62.2**／第 3（退出後排 Boa Vista 之後，唔再係首選） |

### 四個修正（全部 §7 正確性修正）

| # | 修正 | 規模（08-05 起） | 檔案 |
|---|---|---|---|
| F1 | 試閘判斷信 Sportsbet 明確標記，唔再用「600–950m = 試閘」 | 2,188 場正式賽被錯標（1,363 個馬匹段落） | `.agents/scripts/inject_fact_anchors.py` |
| F2 | ~~pace_figure 唔計試閘~~ **撤回** | 14.3% PF 行；745 匹全靠試閘 | 兩個版本 Gold −0.37／−0.29pp：試閘 PF 有用 |
| F3 | 已解碼近績 `10` = 一場第 10 | 131 匹 | `scoring.parse_recent_finishes` |
| F4 | 往績行缺失時用官方 Last 10 計 form | 待量 | `engine_core._form_score` |

**v3 fixed_rule 判決**（2,436 場重建語料，EXP-20261012-31）：

| 組合 | Gold | Good | 判決 |
|---|---:|---:|---|
| F1+F2+F3+F4 | −0.45 | −0.16 | REJECT —— F2 拉低（邊際 −0.37） |
| **F1+F3+F4（最終）** | **−0.08 [−0.31,+0.13]** | **+0.04** | 冇顯著退步 → **§7 上，唔係已證實改善** |

即係話：Platinum Card 個 pace_figure 84.1 其實唔係 bug —— 試閘嘅速度環境平均有預測力。真 bug 係 form 同
consistency 嗰兩個（佢被當咗冇證據，同埋多咗一場虛構頭馬）。

## 2. 今日（10-12）頭 2 揀全部唔入位嘅 7 場

| 場次 | 頭 2 揀（名次） | 主要原因 |
|---|---|---|
| Tamworth R4 | Halcyon Belle（**退出**）、Platinum Card（第 7） | ① 首選 12:08 之後退出，冇 refresh；② Platinum Card 嘅四個 bug |
| Bairnsdale R3 | Ostrom（8）、Tyrant Rex（10） | 高 PQ／pf，正常波動 |
| Bairnsdale R5 | Precambrian（7）、Just Dance（4） | 正常波動；頭兩名分差 0.7 |
| Bairnsdale R6 | Astari（4）、Just Remember It（5） | 跑第 4、5，差少少 |
| Bairnsdale R8 | Rich King（4）、Prevention（6） | 正常波動 |
| Tamworth R6 | Comongin（4）、Gold Lover（8） | pf 100 嘅首選跑第 4 |
| Tamworth R8 | Jagerschnitzel（4）、Maximum Ride（11） | 正常波動 |

**語料層面嘅答案**（唔係淨睇一日）：

- **pace_figure 冇壞**：≤30 −13.4pp … ≥90 +11.9pp，單調。
- **單場樣本收縮 walk-forward REJECT**：揀到嘅 k 只有 0.5，Good −0.08pp。
- **真正可修嘅只有兩樣**：
  - Platinum Card 嘅四個 bug（§1）。
  - 遲退出冇 refresh：加咗 14:00、16:00 兩個 launchd 模板，**要你人手裝**，見 §6。

## 3. Phase R／C／F —— 重新砌檔位、步速形勢、馬場、pace_figure（EXP-20261012-32）

walk-forward（每個賽日只用之前嘅賽日），殘差 = 入位 − 模型名次 × 馬匹數嘅歷史入位率，分層收縮，形勢類按馬匹數縮放。

| 家族 | v3（診斷） | Gold | Good | Holm |
|---|---|---:|---:|---|
| R3 pace_figure 收縮 | REJECT | +0.00 | −0.08 | — |
| R1 檔位 | REJECT | +0.04 | −0.12 | — |
| R2 步速形勢 | REJECT | −0.12 | −0.16 | — |
| 檔位 × 跑法 | REJECT | +0.08 | −0.04 | — |
| C 馬場 × 跑法 | RANKING_WIN | +0.12 | +0.21 | p 0.05，**唔顯著** |
| H6 馬齡 × 性別 | 診斷 RANKING_WIN → **正式路徑 REJECT（細場 Gold −0.98 [−1.91,−0.13]）** | +0.04 | +0.65 | Holm 0.195 |

**答你兩條問題：**

- **「HKJC race_shape 27%、AU 零，好怪」**：量咗，AU 檔位同步速形勢喺模型之外冇剩餘訊號。
  - 已經用咗 point-in-time 效應表、馬匹數縮放、按馬場分層，結果都一樣。
  - 原因係 AU 有 129 個馬場（≥40 場嘅只有 19 個），馬匹數又由 4 到 18 匹，收縮之後大部分 cell 都返去全國平均。
  - 而全國平均嘅檔位效應，form 同 rating 已經吸收咗。
- **「要唔要逐個馬場微調」**：做唔到，樣本唔夠。
  - 只有「馬場 × 跑法」有少少跡象，但 Holm 調整後唔顯著，所以唔上線。
- **馬匹數（4–18 匹）**：已經內置喺所有形勢類候選。
  - 細場縮向零，大場先用全幅。
  - Codex EXP-13 逐 leaf 按馬匹數分層嘅結果冇發現 leaf 失效或者調轉。

## 4. 新訊號：馬齡 × 性別（SHADOW）

- **殘差**（控制模型名次之後）：
  - 3 歲 +3.2pp，CI [+2.1, +4.4]
  - 7 歲以上 −3.3pp，CI [−4.6, −2.1]
  - 雌馬 −1.7pp
  - 雄馬 +6.7pp
- **點解之前冇用**：Racecard 有 `Age: 5yoM`，但模型由來冇用。
- **已接好**：Racecard → Logic `age_sex` → `age_sex_shadow_delta`。
- **預設唔入排名**：`WC_AU_AGE_SEX_LIVE=1` 先生效。
- **forward holdout**：2026-10-13 起，已登記喺 `au_retest_watch.PENDING_REGISTRATIONS`（review_after 2026-12-01）。

## 5. 已修（worktree 合計）

| 來源 | 內容 |
|---|---|
| **今日（Claude）** | |
| | F1–F4 試閘／Last 10 |
| | 馬齡性別 shadow |
| | 14:00／16:00 refresh 模板 |
| **Claude 第一輪補返** | |
| | going 被 Facts 蓋返 |
| | 對手索引 54→7.5 秒（輸出逐 byte 一樣） |
| | 健康閘語料路徑錯 |
| | 騎練人名被清空 |
| | refit 切分偷睇 terminal |
| | 乾地假報 wet overlay 消失 |
| | parser 參考維度標題 |
| | consistency −4 錯標籤 |
| **Codex（EXP-20261011-01 → 20261012-30）** | |
| | 維度登記表接入報告同 dashboard，加 plug-in test（Phase A） |
| | 賽果 CSV 補欄同身份修復 |
| | 重測語義 |
| | shadow 狀態 |
| | refresh 原抽檔位比較同 going 傳遞 |
| | 班次標題同 cache |
| | 靜靜失敗依賴 |
| | 檔位基準拒寫 |
| | PF 有限值守衛 |
| | 效能（人庫單次 parse、fingerprint 重用） |
| | 輸出層描述 |

## 6. 要你決定／做

1. **送審**：按「地基分開送審」嘅決定，建議分四個 release，經 `./保存.sh --path …`：
   - A：Codex 嘅登記表同正確性修正
   - B：第一輪補返嗰批修正
   - C：F1–F4
   - D：馬齡性別 shadow（預設關）
2. **裝下晝 refresh**：
   ```bash
   sed -e "s#__SCRIPT_DIR__#…/au_daily_auto#g" -e "s#__PROJECT_ROOT__#…#g" com.antigravity.au-wong-choi.afternoon.plist.template > ~/Library/LaunchAgents/com.antigravity.au-wong-choi.afternoon.plist
   ```
   16:00 嗰個（`late`）一樣做法。
3. **見習減磅**：頁面有 `(a-2)`，但 `parse_overview` 剷咗。未接駁，屬下一步抽取層工作。

## 7. 九條問題 × 組件（最終判決表）

**九條問題：**
- Q1 中性化／權重
- Q2 噪音
- Q3 bug
- Q4 唔合理
- Q5 改善
- Q6 新特徵
- Q7 重建
- Q8 數據
- Q9 關係／overlay

**判決詞：**
- **KEEP**：量過，現狀已經係最好。
- **FIXED**：§7 已發佈。
- **REJECT**：試過唔得。
- **SHADOW**：已實作，未入排名。
- **UNRESOLVABLE**：而家判唔到。
- **NO-ISSUE**：查過冇問題。

| 組件 | Q1 | Q2 | Q3 | Q4 | Q5 | Q6 | Q7 | Q8 | Q9 |
|---|---|---|---|---|---|---|---|---|---|
| **全模型** | KEEP（dev-only 共識 refit REJECT） | KEEP（11 組件冇一個可剷） | FIXED（第一輪 15＋今日 3＋Codex 30） | NO-ISSUE | REJECT（R1、R2、R3 全唔過） | SHADOW（馬齡 × 性別） | KEEP（GBM 天花板；只重建輸入） | FIXED（語料 CSV 補欄、身份修復） | REJECT（維度交互兩對） |
| stability | KEEP | KEEP（剷走 Good −4.72pp，CI 全負） | NO-ISSUE | KEEP（form −4 方向對） | NO-ISSUE | NO-ISSUE | KEEP | NO-ISSUE | REJECT（stability × pace_perf） |
| └ form | KEEP | KEEP | FIXED（F4 往績行缺失） | FIXED（F1 900m 當試閘） | NO-ISSUE | NO-ISSUE | KEEP | FIXED | NO-ISSUE |
| └ performance_quality | KEEP | KEEP | FIXED（F3 `10`→虛構頭馬經 fallback） | NO-ISSUE | NO-ISSUE | NO-ISSUE | KEEP | NO-ISSUE | NO-ISSUE |
| pace_perf | KEEP | KEEP | NO-ISSUE | NO-ISSUE | REJECT（單場收縮 R3） | UNRESOLVABLE（速度盲測未夠 2,000 場） | KEEP | NO-ISSUE | NO-ISSUE |
| └ pace_figure | KEEP | KEEP | NO-ISSUE（試閘 PF 有用：全靠試閘 681 匹 ≥70 +10.5pp／<50 −12.3pp；F2 REJECT） | NO-ISSUE | REJECT | NO-ISSUE | KEEP（全距單調） | FIXED（Codex PF 有限值守衛） | NO-ISSUE |
| └ trial | KEEP | KEEP（剷走 dev −0.08） | NO-ISSUE | NO-ISSUE（冇試閘預設 56，B7 REJECT） | NO-ISSUE | NO-ISSUE | KEEP | NO-ISSUE | NO-ISSUE |
| jockey_trainer | KEEP（內權重三個配置 REJECT） | KEEP | FIXED（人名清空） | NO-ISSUE | NO-ISSUE | REJECT（換騎分類：−0.86pp，細過 MDE） | KEEP | UNRESOLVABLE（as-of 要等 12-01） | NO-ISSUE |
| └ jockey | KEEP | KEEP | NO-ISSUE | NO-ISSUE | REJECT（冇記錄預設值，正式 walk-forward 全指標 Δ 0，EXP-34） | NO-ISSUE | NO-ISSUE | NO-ISSUE | NO-ISSUE |
| └ trainer | KEEP | KEEP | NO-ISSUE | NO-ISSUE | REJECT（冇記錄預設 B7 dev 唔過） | NO-ISSUE | NO-ISSUE | NO-ISSUE | NO-ISSUE |
| └ jockey_horse_fit | KEEP | KEEP | NO-ISSUE | REJECT（jhf −3 死 code，剷走零差異） | NO-ISSUE | NO-ISSUE | KEEP | NO-ISSUE | NO-ISSUE |
| class_weight | KEEP | KEEP | NO-ISSUE | NO-ISSUE | UNRESOLVABLE（class_score 11-09 前瞻閘） | UNRESOLVABLE（班次標籤 11-15） | KEEP | FIXED（Codex 班次標題 cache） | REJECT（stability × class） |
| └ rating | KEEP | KEEP | NO-ISSUE | NO-ISSUE | NO-ISSUE | NO-ISSUE | KEEP | NO-ISSUE | NO-ISSUE |
| └ class_score | UNRESOLVABLE | KEEP（中性化近零） | NO-ISSUE | NO-ISSUE | UNRESOLVABLE | NO-ISSUE | NO-ISSUE | NO-ISSUE | NO-ISSUE |
| preparation | KEEP | KEEP | FIXED（逐維一覽漏顯示，登記表） | NO-ISSUE | NO-ISSUE | NO-ISSUE | KEEP | NO-ISSUE | NO-ISSUE |
| track | KEEP | KEEP（auc5 一致負，保留） | NO-ISSUE | NO-ISSUE（冇證據 62.9；安全欄只影響 #1／#2） | REJECT（R1 檔位） | REJECT（馬場 × 跑法，Holm 後唔顯著） | KEEP | NO-ISSUE | REJECT（wet × track 已試） |
| wet overlay | KEEP | KEEP | FIXED（合約假警報） | NO-ISSUE | NO-ISSUE | NO-ISSUE | NO-ISSUE | NO-ISSUE | NO-ISSUE |
| proven_class overlay | KEEP | KEEP | NO-ISSUE | NO-ISSUE | NO-ISSUE | NO-ISSUE | NO-ISSUE | NO-ISSUE | NO-ISSUE |
| 情境扣分（form −4／consistency −4／jhf −3） | KEEP／REJECT／REJECT | REJECT（後兩個死 code，剷走零差異） | FIXED（錯標籤） | NO-ISSUE | NO-ISSUE | NO-ISSUE | NO-ISSUE | NO-ISSUE | NO-ISSUE |
| race_shape（退役） | REJECT（加返 dev 唔過） | NO-ISSUE | FIXED（parser 錯配） | NO-ISSUE | REJECT（R2 步速形勢） | REJECT（檔位 × 跑法） | REJECT（重新砌都唔過） | UNRESOLVABLE（11-22 重驗） | REJECT |
| form_line（退役） | REJECT | NO-ISSUE | NO-ISSUE | NO-ISSUE | REJECT | NO-ISSUE | NO-ISSUE | NO-ISSUE | NO-ISSUE |
| sectional（零權重） | REJECT | NO-ISSUE | NO-ISSUE | NO-ISSUE | REJECT（新維度） | NO-ISSUE | REJECT（缺失指示重建，正式路徑 EXP-33） | NO-ISSUE（48.8% 冇 PI 係來源限制） | NO-ISSUE |
| distance（零權重） | REJECT | NO-ISSUE | NO-ISSUE | NO-ISSUE | REJECT（新維度 dev 唔過） | NO-ISSUE | REJECT（重建 + leakage PASS，正式路徑 Holm 後唔顯著） | NO-ISSUE | NO-ISSUE |
| 輸出層（信心級別、評級、安全欄） | NO-ISSUE | NO-ISSUE | FIXED（Codex 描述層） | UNRESOLVABLE（信心級別 Gold 分唔開；要預先登記先改） | NO-ISSUE | NO-ISSUE | NO-ISSUE | NO-ISSUE | NO-ISSUE |
| 排程／管線 | NO-ISSUE | NO-ISSUE | FIXED（refresh 檔位假陽性、going、健康閘） | FIXED（下晝冇 refresh：模板已加，要人手裝） | FIXED（對手索引 7×快） | NO-ISSUE | NO-ISSUE | FIXED | NO-ISSUE |
| 馬齡 × 性別（新） | — | — | — | — | REJECT（正式路徑：細場傷害） | REJECT；按馬匹數縮放版本做前瞻假設（2026-10-13 起） | — | — | — |
| 見習減磅（新） | — | — | — | NO-ISSUE（殘差真：a2 −3.2pp） | UNRESOLVABLE §6（正式路徑：預算 < MDE，primary 近零，EXP-34） | 唔接駁（冇可量度收益） | — | — | — |

**表入面「—」嘅意思**：新特徵未入模型，問題唔適用。

**發佈記錄**（2026-10-12，全部自動 merge 同 activate）：

| Release | commit | 內容 |
|---|---|---|
| A1 | `c7096055` | 評估尺：預測 artifact 路徑、數據合約指紋 |
| A2 | `e348a74e` | Codex 審計基建 |
| B1 | `9b0c5f14` | 數據合約乾地假警報 |
| B2 | `c28db618` | F1／F3／F4、第一輪修正、下晝 refresh 模板 |

**馬齡 × 性別** 正式路徑 REJECT，shadow code 留喺 worktree `claude-au-trial-leak-20261012`，唔發佈。

## 8. 正式 artifact 路徑判決（EXP-20261012-33）

| arm | 判決 | 重點 |
|---|---|---|
| 馬齡 × 性別 | REJECT cohort_regression | 細場 Gold −0.98pp [−1.91,−0.13] |
| distance 重建（缺失指示、leakage PASS） | REJECT ranking_evidence_too_weak | top3_capture p 0.042，Holm 0.546 |
| sectional 重建（冇 PI 自成一組） | REJECT primary_regression | 全部近零 |

**Platinum Card 個 pace_figure（試閘）**：「全靠試閘」681 匹，≥70 分 +10.5pp、<50 分 −12.3pp，單調而且有預測力。
即係保留試閘 PF 係實證決定。真正嘅 bug（form 當冇證據、`10` 變虛構頭馬、900m 當試閘）已經喺 `c28db618` 修好。

**仲要等時間先判得到嘅**（全部已登記，數據喺未來先存在）：
- 速度盲測：要 2,000 場。
- class_score 前瞻：11-09。
- 班次標籤：11-15。
- race_shape 重驗：11-22。
- 騎練 as-of：12-01。
- 馬齡性別（按馬匹數縮放）：2026-10-13 起，≥600 場。

## 9. 補充（EXP-20261012-34）

- **jockey 冇記錄預設值**：正式 walk-forward 判 REJECT，所有指標 Δ 0；v2 嗰次邊緣過閘係噪音。
- **見習減磅**：殘差真（a2 −3.22pp [−5.06, −1.44]），但正式路徑判 UNRESOLVABLE（§6 預算細過 MDE）。唔接駁。
- **Platinum Card production 核實**：
  - 用 `wongchoi-scheduler` @ `16c028ab` 嘅 code 重跑 10-12 Tamworth：**62.2、第 3**，form 53.3、PQ 61.9。
  - Smashit 嗰場 Scone 900m 正確標做「正式」。
