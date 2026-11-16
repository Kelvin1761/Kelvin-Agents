# AU Betfair 自動落注：設定指南（2026-11-16）

> ⚠️ **而家冇任何策略證實賺錢。** AU 位注紙上策略（`au_betting`）實測 ROI 係負；另一個研究跑緊。
> 呢套嘢只係「準備好」，**開關要一直閂住**，直至有一個策略過咗 `model-regression-gate`（holdout + forward）先好開。

Module：`.agents/skills/au_racing/au_betfair/betfair_betting.py`（CLI）
設定：`.agents/skills/au_racing/au_betfair/betting_config.json`
策略插頭：`.agents/skills/au_racing/au_betfair/betting_strategies.py`
落注 client：`.agents/skills/au_racing/au_betfair/betfair_trading.py`（記錄器用嘅 `betfair_client.py` 仍然只讀）
測試：`.agents/skills/au_racing/tests/test_au_betfair_betting.py`

## 佢做乜

- 只落 **BACK**、只用 **BSP**：`LIMIT_ON_CLOSE`（有最低可接受 BSP）；`MARKET_ON_CLOSE` 預設唔准（冇價保護）。
- 只限 **AU 純種馬** WIN／PLACE 市場、未開跑（至少 2 分鐘前）、唔係走地、係 BSP 市場；harness 剔走。
- 冇取消／改單功能（冇 `cancelOrders` 等）—— 要取消就上 Betfair 網站手動做。
- 每注有固定 `customerOrderRef`（日期＋策略＋市場＋馬），重跑唔會落多次；送之前會查帳本同 `listCurrentOrders`。
  如果送咗之後網絡斷咗（唔知有冇落到），嗰注會鎖住唔再送，Telegram 叫你上 Betfair 確認。
- 帳本：`~/WongChoiData/WongChoiControl/betfair-betting/ledger.jsonl`（append-only，repo 外）。
- Telegram 只發 Kelvin（`primary`）：每次真落注摘要、每個錯誤／被拒、觸發限額、每日結算。dry-run 最多每日一條摘要（要加 `--notify`）。
- 冇裝任何排程。要自動跑，係你決定之後先另外加。

## 四重開關（全部開先會落真注）

| # | 開關 | 預設 | 點開 |
|---|---|---|---|
| 1 | `betting_config.json` 嘅 `"enabled": true` **同** `"mode": "live"` | 閂 | 改檔，經 `./保存.sh` 發佈 |
| 2 | 環境變數 `WC_BETFAIR_BETTING=live` | 閂 | 加入 `~/.wongchoi_betfair.env` |
| 3 | 環境變數 `BETFAIR_LIVE_APP_KEY`（live key） | 冇 | 加入 `~/.wongchoi_betfair.env`；**唔會**用 delayed key 頂替 |
| 4 | 停止檔 `~/WongChoiData/WongChoiControl/betfair-betting.STOP` **唔存在** | 唔存在 | — |

另外仲有第五道閘：注單嘅策略名一定要喺 `allowed_strategies`（預設空），同埋設定入面每個限額都要齊、合理，唔齊就當閂。
`place` 喺最頂查一次、每注送出前再查一次；落注 client 自己 call `placeOrders` 前亦會再查一次。

**即刻停**：

```bash
touch ~/WongChoiData/WongChoiControl/betfair-betting.STOP
```

下一注就唔會再送（跑緊嗰輪都會即刻停）。刪咗個檔先會恢復。

## 限額（`betting_config.json` → `limits`）

| 設定 | 預設 | 意思 |
|---|---|---|
| `min_stake` | 5 | 每注最少（Betfair BSP 最低注碼請自己喺網站確認） |
| `max_stake_per_bet` | 5 | 每注最多 |
| `max_total_stake_per_day` | 50 | 每日（悉尼日）總注碼 |
| `max_bets_per_day` | 10 | 每日注數 |
| `daily_stop_loss` | 30 | 今日已結算淨蝕到呢個數就停（Betfair `listClearedOrders` 同帳本取差嗰個） |
| `max_exposure_per_race` | 10 | 同一場（WIN＋PLACE 一齊計）最多 |
| `min_bsp`／`max_bsp` | 1.5／30 | 最低可接受 BSP 一定要喺呢個範圍；預計 BSP（near price）出界都唔落 |
| `min_minutes_before_start` | 2 | 開跑前幾多分鐘之後唔再落 |
| `max_minutes_before_start` | 720 | 太早唔落 |
| `min_available_funds` | 100 | 帳戶可用餘額低過呢個就唔落 |
| `allow_market_on_close` | false | 准唔准 MOC（冇價保護） |
| `default_commission_pct` | 10 | dry-run 估算用（真實佣金跟市場 `marketBaseRate`：VIC 8%、NSW 10% 等，唔係 5%） |

## 開通步驟（全部由 Kelvin 自己做）

1. **帳戶**：Betfair AU 帳戶要完成身份驗證（KYC）同入咗錢。
2. **申請 live app key**：
   - 喺 Betfair Developer Program 申請 live（即時）application key。一次性收費 **£299**（扣你帳戶）。
   - 申請時講明係 **個人投注用途**（personal betting use），唔係商業／第三方軟件。
   - 批咗之後，live key 同而家記錄器用緊嘅 delayed key 係兩條唔同嘅 key。
   - 註：Betfair 文件對 delayed key 可唔可以落注講法前後唔一致；呢個 module 一律只用 live key。
3. **證書登入（建議）**：跟 Betfair「Non-Interactive (bot) login」整一對自簽證書，上載 `.crt` 去 Betfair 帳戶，
   本機放 `~/.betfair/client-2048.crt`、`~/.betfair/client-2048.key`（`chmod 600`）。
4. **環境變數**：只放喺 `~/.wongchoi_betfair.env`（repo 外，`chmod 600`），**唔好**放入 repo、唔好貼入對話：
   ```
   BETFAIR_LIVE_APP_KEY=...
   BETFAIR_CERT_FILE=~/.betfair/client-2048.crt
   BETFAIR_KEY_FILE=~/.betfair/client-2048.key
   # WC_BETFAIR_BETTING=live      ← 決定開先加
   ```
   `BETFAIR_USERNAME`／`BETFAIR_PASSWORD` 已經有（記錄器用緊）。落注 client 用自己嘅 session 檔
   `~/.wongchoi_betfair_trading_session.json`。
5. **檢查**：
   ```bash
   set -a; . ~/.wongchoi_betfair.env; set +a
   python3 .agents/skills/au_racing/au_betfair/betfair_betting.py status   # 睇四重開關
   python3 .agents/skills/au_racing/au_betfair/betfair_betting.py funds    # 試 live key 讀餘額
   ```

## 先 dry-run 最少一個星期

```bash
B=.agents/skills/au_racing/au_betfair/betfair_betting.py
python3 $B plan --strategy <策略> --date 2026-11-21 --out /tmp/bets.json   # 產生候選注
python3 $B dry-run --bets /tmp/bets.json --notify                          # 全部檢查照做，只記低「會送乜」
python3 $B settle --date 2026-11-21 --dry-run                              # 賽後用真實 BSP 估盈虧（扣佣）
```

- 策略：`none`（預設，一注都冇）、`json`（`--bets-in` 你自己寫嘅 JSON）、`au_betting_place`（現有紙上位注規則，**ROI 負，只係示範接駁**）。
- dry-run 永遠唔會 call `placeOrders`。逐日對 Telegram 摘要同帳本，確認注單、限額、重覆檢查同你預期一樣。

## 正式開（只喺有策略過咗 gate 之後）

1. `betting_config.json`：`"enabled": true`、`"mode": "live"`、`"allowed_strategies": ["<策略名>"]`，按你承受得起調細限額，經 `./保存.sh` 發佈。
2. `~/.wongchoi_betfair.env` 加 `WC_BETFAIR_BETTING=live`。
3. `status` 確認四個都係 ✅。
4. `python3 $B place --bets /tmp/bets.json`。
5. 每晚：`python3 $B settle --date <日期>`（Telegram 發結算）。

閂返：`touch` 停止檔（即時）→ 再將 env 刪走／config 改返 `false`。

## 仲未確認嘅嘢

- BSP back 注最低注碼（AUD）—— `min_stake` 設咗 5，開之前喺 Betfair 網站確認。
- `getAccountFunds` 用 global endpoint（`api.betfair.com/exchange/account`）；AU 帳戶 2016 年起已經單一錢包，應該冇問題，`funds` 會驗證到。
- 每日結算訊息未接入統一 ROI 板（`wongchoi_roi.py`）；有策略上線先接，並跟 AGENTS.md 嘅 ROI 口徑。
